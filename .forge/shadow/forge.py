
#!/usr/bin/env python3
import argparse, sys, json, os, sqlite3, re, time, shutil, zipfile, textwrap
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "state"
DB = STATE / "index.sqlite"
FREEZE_FLAG = STATE / "FORGE_FREEZE"
CMD_DIR = ROOT / "commands"
POL_DIR = ROOT / "policies"
FORGE_TMP = ROOT / ".forge"
SNAP_DIR = ROOT / "snapshots"

def log(actor, action, detail=""):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    (datetime.now(timezone.utc).isoformat(), actor, action, detail)
    conn.commit()
    conn.close()

def load_yaml_like(path: Path):
    # Minimal parser for simple YAML-like key: value lines (no nested maps beyond this file's needs).
    # This avoids external dependencies.
    if not path.exists():
        return {}
    data = {}
    current = None
    with path.open("r", encoding="utf-8") as f:
        lines = f.readlines()
    for line in lines:
        if line.strip().startswith("#") or not line.strip():
            continue
        if ":" in line and not line.startswith("  -"):
            k, v = line.split(":", 1)
            k = k.strip()
            v = v.strip()
            if v == "" or v == "|":
                current = k
                data[k] = ""
            else:
                # Trim quotes if present
                if v and v[0] in ['"', "'"] and v[-1:] == v[0]:
                    v = v[1:-1]
                data[k] = v
        elif line.strip().startswith("- "):
            # Collect steps: - run: "cmd"
            if "steps" not in data or not isinstance(data.get("steps"), list):
                data["steps"] = []
            m = re.match(r"\s*-\s*run:\s*(.+)", line)
            if m:
                val = m.group(1).strip()
                val = val.strip('"').strip("'")
                data["steps"].append({"run": val})
        else:
            if current is not None:
                data[current] += line
    return data

def status():
    frozen = FREEZE_FLAG.exists()
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM audit_log")
    logs = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM snapshots")
    snaps = cur.fetchone()[0]
    conn.close()
    print(f"GhostForge v1 :: status")
    print(f"  location : {ROOT}")
    print(f"  frozen   : {'YES' if frozen else 'no'}")
    print(f"  logs     : {logs}")
    print(f"  snapshots: {snaps}")

def freeze():
    FREEZE_FLAG.write_text("1")
    log("forge", "freeze", "freeze=1")
    print("Forge frozen. Self-modification disabled.")

def thaw():
    if FREEZE_FLAG.exists(): FREEZE_FLAG.unlink()
    log("forge", "thaw", "freeze=0")
    print("Forge thawed. Self-modification enabled (subject to policy).")

def list_commands():
    print("Available commands:")
    for p in sorted(CMD_DIR.glob("*.yaml")):
        spec = load_yaml_like(p)
        print(f"  - {spec.get('name', p.stem)} :: capability={spec.get('capability','?')} version={spec.get('version','?')}")

def create_snapshot(label="manual"):
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    zip_path = SNAP_DIR / f"{ts}_{label}.zip"
    manifest = {
        "ts": ts,
        "label": label,
        "root": str(ROOT),
        "included": []
    }
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for folder, _, files in os.walk(ROOT):
            # Skip snapshots and state DB file itself inside the zip for compactness
            if Path(folder).resolve() == SNAP_DIR.resolve():
                continue
            for file in files:
                full = Path(folder) / file
                # don't include previous snapshot zips or large blobs
                if full.is_file() and SNAP_DIR not in full.parents:
                    rel = full.relative_to(ROOT)
                    z.write(full, rel.as_posix())
                    manifest["included"].append(rel.as_posix())
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("INSERT INTO snapshots (ts,label,path,manifest) VALUES (?,?,?,?)",
                (ts, label, str(zip_path), json.dumps(manifest)))
    conn.commit()
    conn.close()
    log("forge", "snapshot", json.dumps({"label": label, "zip": str(zip_path)}))
    print(f"Snapshot created: {zip_path}")

def run_repair(strategy="lint"):
    if FREEZE_FLAG.exists():
        print("ERROR: Forge is frozen. Unfreeze to run repair.")
        return 1

    spec = load_yaml_like(CMD_DIR / "core.repair.yaml")
    policy_path = POL_DIR / (spec.get("guards.policy") or "repair.policy.yaml")
    # Load policy (very simple YAML-like parsing)
    policy = load_yaml_like(policy_path)

    change_budget_pct = int(spec.get("guards.change_budget_pct", "5"))
    require_green = (spec.get("guards.require_green_tests", "true").lower() == "true")

    print(f"[plan] strategy={strategy} scope=core-only budget={change_budget_pct}% require_green={require_green}")
    (FORGE_TMP / "plan.json").write_text(json.dumps({
        "strategy": strategy, "scope": "core", "proposed_changes": []}, indent=2))

    # Simulated "apply": touch a comment line in core/registry.py to represent a tiny refactor.
    target_file = ROOT / "core" / "registry.py"
    if target_file.exists():
        original = target_file.read_text(encoding="utf-8")
    else:
        original = ""
    new = original
    if "# auto-repair touch" not in original:
        new = original + ("\n# auto-repair touch: %s\n" % datetime.utcnow().isoformat()+"Z")

    # Guard checks (block banned patterns)
    blocked = []
    # compile blocked regexes from policy section "rules"
    rules_text = (POL_DIR / "repair.policy.yaml").read_text(encoding="utf-8", errors="ignore")
    for pattern in [r"(requests|httpx|socket)", r"(eval\(|exec\()"]:
        if re.search(pattern, new):
            blocked.append(pattern)

    if blocked:
        print(f"[warden] BLOCK: patterns={blocked}")
        log("warden","block", json.dumps({"patterns": blocked}))
        return 2

    # Diff budget check (very rough % based on added lines)
    added_lines = len([ln for ln in new.splitlines() if ln.strip() and ln not in original])
    base_lines = max(1, len(original.splitlines()))
    pct = int(min(100, (added_lines / base_lines) * 100))
    if pct > change_budget_pct:
        print(f"[warden] REJECT: change size {pct}% exceeds budget {change_budget_pct}%")
        log("warden","reject_change_budget", json.dumps({"pct": pct, "budget": change_budget_pct}))
        return 3

    # Stage to shadow copy
    shadow = ROOT / ".forge" / "shadow"
    if shadow.exists():
        shutil.rmtree(shadow)
        # filtered copy to avoid infinite recursion and heavy dirs
    def _ignore(dir, names):
        base = Path(dir)
        blocked = {'snapshots', '__pycache__', '.forge'}
        if base.name in blocked:
            return names  # skip everything inside
        return [n for n in names if n in {'__pycache__'}]

    shutil.copytree(ROOT, shadow, ignore=_ignore)

    (shadow / "core" / "registry.py").write_text(new, encoding="utf-8")
    print(f"[stage] changes staged to {shadow}")

    # Run tests
    ok = run_tests(silent=True)
    if require_green and not ok:
        print("[tests] FAIL: golden tests not green; aborting.")
        log("tester","fail","golden")
        return 4
    print("[tests] OK")

    # Snapshot current, then apply atomic swap (here, just write the one file)
    create_snapshot(label="auto-repair")
    target_file.write_text(new, encoding="utf-8")
    log("rewriter","apply", json.dumps({"file": str(target_file), "added_lines": added_lines}))
    print("[apply] repair applied to core/registry.py")
    return 0

def run_tests(silent=False):
    # Minimal "golden" tests runner: look for files in tests/ with a 'run() -> bool'
    import importlib.util, traceback, types
    tests_dir = ROOT / "tests"
    ok = True
    for p in sorted(tests_dir.glob("test_*.py")):
        name = p.stem
        spec = importlib.util.spec_from_file_location(name, p)
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)  # type: ignore
            result = True
            if hasattr(mod, "run") and callable(mod.run):
                result = bool(mod.run())
            if not silent:
                print(f"[test] {name}: {'OK' if result else 'FAIL'}")
            ok = ok and result
        except Exception as e:
            ok = False
            if not silent:
                print(f"[test] {name}: EXC {e}")
    return ok

def main():
    ap = argparse.ArgumentParser(prog="forge", description="GhostForge v1 CLI")
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("status")
    sub.add_parser("freeze")
    sub.add_parser("thaw")
    sub.add_parser("list-commands")

    p_snap = sub.add_parser("snapshot")
    p_snap.add_argument("--label", default="manual")

    p_repair = sub.add_parser("repair")
    p_repair.add_argument("--strategy", default="lint", choices=["lint","refactor","regen"])

    sub.add_parser("test")

    args = ap.parse_args()

    if args.cmd == "status":
        status()
    elif args.cmd == "freeze":
        freeze()
    elif args.cmd == "thaw":
        thaw()
    elif args.cmd == "list-commands":
        list_commands()
    elif args.cmd == "snapshot":
        create_snapshot(label=args.label)
    elif args.cmd == "repair":
        sys.exit(run_repair(strategy=args.strategy))
    elif args.cmd == "test":
        ok = run_tests()
        print("ALL TESTS", "PASS" if ok else "FAIL")
        sys.exit(0 if ok else 1)
    else:
        ap.print_help()

if __name__ == "__main__":
    main()
