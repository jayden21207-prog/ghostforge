#!/usr/bin/env python3
# GhostForge v1.2 — clean rebuild
# Single-file CLI kernel with safe self-repair, snapshots, and agent scaffolding.

import argparse
import json
import os
import re
import shutil
import sqlite3
import sys
import zipfile
from datetime import datetime, timezone
from importlib import util as importlib_util
from pathlib import Path

# --------------------------- Paths & constants ---------------------------

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "state"
DB = STATE / "index.sqlite"
FREEZE_FLAG = STATE / "FORGE_FREEZE"
CMD_DIR = ROOT / "commands"
POL_DIR = ROOT / "policies"
FORGE_TMP = ROOT / ".forge"
SNAP_DIR = ROOT / "snapshots"
TESTS_DIR = ROOT / "tests"
AGENTS_DIR = ROOT / "agents"

# --------------------------- Bootstrap state -----------------------------

def ensure_state():
    """Ensure required folders and SQLite tables exist."""
    (STATE / "blobs").mkdir(parents=True, exist_ok=True)
    CMD_DIR.mkdir(exist_ok=True)
    POL_DIR.mkdir(exist_ok=True)
    FORGE_TMP.mkdir(exist_ok=True)
    SNAP_DIR.mkdir(exist_ok=True)
    TESTS_DIR.mkdir(exist_ok=True)
    AGENTS_DIR.mkdir(exist_ok=True)

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        actor TEXT NOT NULL,
        action TEXT NOT NULL,
        detail TEXT
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        label TEXT NOT NULL,
        path TEXT NOT NULL,
        manifest TEXT NOT NULL
    )""")
    conn.commit()
    conn.close()

# --------------------------- Utilities -----------------------------------

def log(actor: str, action: str, detail: str = ""):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO audit_log (ts, actor, action, detail) VALUES (?,?,?,?)",
        (datetime.now(timezone.utc).isoformat(), actor, action, detail),
    )
    conn.commit()
    conn.close()

def _strip_quotes(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and ((s[0] == s[-1] == '"') or (s[0] == s[-1] == "'")):
        return s[1:-1]
    return s

def load_yaml_like(path: Path) -> dict:
    """
    Minimal, forgiving YAML-ish parser:
    - Supports 'key: value' (flat)
    - Supports 'guards.change_budget_pct: 5' style dotted keys
    - Supports 'steps:' then '- run: "..."' entries
    - Ignores comments and blank lines
    """
    data: dict = {}
    if not path.exists():
        return data

    lines = path.read_text(encoding="utf-8").splitlines()
    for raw in lines:
        line = raw.rstrip("\n")
        s = line.strip()

        if not s or s.startswith("#"):
            continue

        # List item for steps
        m_run = re.match(r"^-+\s*run\s*:\s*(.+)$", s)
        if m_run:
            if "steps" not in data or not isinstance(data.get("steps"), list):
                data["steps"] = []
            data["steps"].append({"run": _strip_quotes(m_run.group(1))})
            continue

        # key: value pairs
        m_kv = re.match(r"^([A-Za-z0-9_.-]+)\s*:\s*(.*)$", s)
        if m_kv:
            k, v = m_kv.group(1), m_kv.group(2)
            v = _strip_quotes(v)
            if k == "steps" and (v == "" or v == "[]"):
                data["steps"] = []
            else:
                data[k] = v if v != "" else None
            continue

    return data

# --------------------------- Core commands -------------------------------

def status():
    frozen = FREEZE_FLAG.exists()
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM audit_log")
    logs = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM snapshots")
    snaps = cur.fetchone()[0]
    conn.close()
    print("GhostForge v1.2 :: status")
    print(f"  location : {ROOT}")
    print(f"  frozen   : {'YES' if frozen else 'no'}")
    print(f"  logs     : {logs}")
    print(f"  snapshots: {snaps}")

def freeze():
    FREEZE_FLAG.write_text("1", encoding="utf-8")
    log("forge", "freeze", "freeze=1")
    print("Forge frozen. Self-modification disabled.")

def thaw():
    if FREEZE_FLAG.exists():
        FREEZE_FLAG.unlink()
    log("forge", "thaw", "freeze=0")
    print("Forge thawed. Self-modification enabled (subject to policy).")

def list_commands():
    print("Available commands:")
    for p in sorted(CMD_DIR.glob("*.yaml")):
        spec = load_yaml_like(p)
        name = spec.get("name", p.stem)
        cap = spec.get("capability", "?")
        ver = spec.get("version", "?")
        print(f"  - {name} :: capability={cap} version={ver}")

def create_snapshot(label: str = "manual"):
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    zip_path = SNAP_DIR / f"{ts}_{label}.zip"
    zip_path.parent.mkdir(parents=True, exist_ok=True)

    manifest = {
        "ts": ts,
        "label": label,
        "root": str(ROOT),
        "included": [],
    }
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for folder, _, files in os.walk(ROOT):
            fpath = Path(folder)
            # Skip snapshot dir and tmp forge area
            if fpath.resolve() in {SNAP_DIR.resolve(), FORGE_TMP.resolve()}:
                continue
            for file in files:
                full = fpath / file
                # Exclude compiled caches
                if "__pycache__" in full.parts:
                    continue
                # Include everything else (including DB/state) for a full capture
                rel = full.relative_to(ROOT)
                z.write(full, rel.as_posix())
                manifest["included"].append(rel.as_posix())

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO snapshots (ts,label,path,manifest) VALUES (?,?,?,?)",
        (ts, label, str(zip_path), json.dumps(manifest)),
    )
    conn.commit()
    conn.close()
    log("forge", "snapshot", json.dumps({"label": label, "zip": str(zip_path)}))
    print(f"Snapshot created: {zip_path}")

def _load_repair_policy_patterns() -> list:
    """Very simple policy loader: collect 'pattern:' entries from repair.policy.yaml."""
    pol = POL_DIR / "repair.policy.yaml"
    pats = []
    if pol.exists():
        for line in pol.read_text(encoding="utf-8").splitlines():
            m = re.search(r"pattern\s*:\s*(.+)$", line.strip())
            if m:
                pats.append(_strip_quotes(m.group(1)))
    # Always add hard safety rails
    pats.extend([r"(eval\()", r"(exec\()", r"\b(requests|httpx|socket)\b"])
    return pats

def _boolish(v, default=True):
    if isinstance(v, bool):
        return v
    if v is None:
        return default
    s = str(v).strip().lower()
    return s in {"1", "true", "yes", "y", "on"}

def run_tests(silent: bool = False) -> bool:
    ok = True
    for p in sorted(TESTS_DIR.glob("test_*.py")):
        name = p.stem
        try:
            spec = importlib_util.spec_from_file_location(name, p)
            mod = importlib_util.module_from_spec(spec)  # type: ignore
            assert spec is not None and spec.loader is not None
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

def run_repair(strategy: str = "lint") -> int:
    if FREEZE_FLAG.exists():
        print("ERROR: Forge is frozen. Unfreeze to run repair.")
        return 1

    # Load spec & guards
    spec = load_yaml_like(CMD_DIR / "core.repair.yaml")
    change_budget_pct = int(spec.get("guards.change_budget_pct", 5))
    require_green = _boolish(spec.get("guards.require_green_tests", True))
    policy_file = spec.get("guards.policy", "repair.policy.yaml")

    print(f"[plan] strategy={strategy} scope=core-only budget={change_budget_pct}% require_green={require_green}")

    # Ensure tmp dirs exist & write plan
    FORGE_TMP.mkdir(parents=True, exist_ok=True)
    (FORGE_TMP / "plan.json").write_text(
        json.dumps({"strategy": strategy, "scope": "core", "proposed_changes": []}, indent=2),
        encoding="utf-8",
    )

    target_file = ROOT / "core" / "registry.py"
    original = target_file.read_text(encoding="utf-8") if target_file.exists() else ""
    if "# auto-repair touch" in original:
        new = original  # already touched; tiny change to keep under budget
    else:
        new = original + f"\n# auto-repair touch: {datetime.now(timezone.utc).isoformat()}\n"

    # Policy checks
    blocked_patterns = _load_repair_policy_patterns()
    valid_pats = []
    for pat in blocked_patterns:
        try:
            re.compile(pat)
            valid_pats.append(pat)
        except re.error:
            print(f"[warden] WARN: skipping invalid regex from policy: {pat!r}")

    hits = [pat for pat in valid_pats if re.search(pat, new)]

    if hits:
        print(f"[warden] BLOCK: patterns={hits}")
        log("warden", "block", json.dumps({"patterns": hits}))
        return 2

    # Diff budget (rough %)
    added_lines = [ln for ln in new.splitlines() if ln.strip() and ln not in original]
    base_lines = max(1, len(original.splitlines()))
    pct = int(min(100, (len(added_lines) / base_lines) * 100))

    # Escalation gate (policy-driven)
    pol = load_yaml_like(POL_DIR / "repair.policy.yaml")
    req_path = (pol.get("escalation.require") or "human-ack.txt")
    triggers_raw = pol.get("escalation.trigger_strategies") or ""
    triggers = [t.strip() for t in triggers_raw.split(",") if t.strip()]
    max_no_ack = int(pol.get("escalation.max_budget_pct_without_ack", change_budget_pct))

    need_ack = (strategy in triggers) or (pct > max_no_ack)
    if need_ack:
        ack_file = ROOT / req_path
        if not ack_file.exists():
            print(f"[warden] ESCALATION REQUIRED: create {ack_file.name} to proceed "
                      f"(triggered by strategy={strategy} or change size {pct}% > {max_no_ack}%).")
            log("warden", "escalation_required",
            json.dumps({"strategy": strategy, "pct": pct, "max_no_ack": max_no_ack, "require": req_path}))
        return 5

    # If no escalation needed but still over hard budget, reject
    if pct > change_budget_pct and not need_ack:
        print(f"[warden] REJECT: change size {pct}% exceeds budget {change_budget_pct}%")
        log("warden", "reject_change_budget", json.dumps({"pct": pct, "budget": change_budget_pct}))
        return 3


    # Stage to shadow safely (avoid recursion)
    shadow = FORGE_TMP / "shadow"
    if shadow.exists():
        shutil.rmtree(shadow)

    def _ignore(dirpath, names):
        base = Path(dirpath).name
        blocked_dirs = {SNAP_DIR.name, "__pycache__", FORGE_TMP.name}
        if base in blocked_dirs:
            return names  # ignore everything inside
        # also ignore pycache entries on any level
        return [n for n in names if n == "__pycache__"]

    shutil.copytree(ROOT, shadow, ignore=_ignore)
    (shadow / "core" / "registry.py").write_text(new, encoding="utf-8")
    print(f"[stage] changes staged to {shadow}")

    # Tests
    ok = run_tests(silent=True)
    if require_green and not ok:
        print("[tests] FAIL: golden tests not green; aborting.")
        log("tester", "fail", "golden")
        return 4
    print("[tests] OK")

    # Snapshot current state, then apply
    create_snapshot(label="auto-repair")
    target_file.write_text(new, encoding="utf-8")
    log("rewriter", "apply", json.dumps({"file": str(target_file), "added_lines": len(added_lines)}))
    print("[apply] repair applied to core/registry.py")
    return 0

# --------------------------- Agent scaffolding ---------------------------

AGENT_README = "# {name} ({kind} agent)\n\nGenerated by GhostForge. Offline by default.\n"
AGENT_MANIFEST = (
    "name: {name}\n"
    "kind: {kind}\n"
    'version: "0.1.0"\n'
    "capabilities:\n"
    "  - plan\n"
    "  - run\n"
    "defaults:\n"
    "  prompt_style: concise\n"
)

AGENT_CODE = r'''from pathlib import Path
import json, sys

class Agent:
    def __init__(self, name="{name}", kind="{kind}"):
        self.name = name
        self.kind = kind

    def plan(self, goal: str):
        base = [
            "[" + self.kind + "] analyze goal: " + goal,
            "collect local data (stub; offline)",
            "generate structured summary",
        ]
        if self.kind == "game":
            base.insert(1, "enumerate mechanics, loops, and difficulty curve")
        elif self.kind == "tv":
            base.insert(1, "enumerate characters, arcs, episodes, motifs")
        return base

    def run(self, goal: str):
        steps = self.plan(goal)
        return {{
            "agent": self.name,
            "kind": self.kind,
            "goal": goal,
            "steps": steps,
            "result": "[demo] " + self.kind + " agent processed goal"
        }}

if __name__ == "__main__":
    goal = " ".join(sys.argv[1:]) or "demo goal"
    print(json.dumps(Agent().run(goal), indent=2))
'''


TEST_CODE = """def run():
    import pathlib, subprocess, sys, json
    root = pathlib.Path(__file__).resolve().parents[1]
    agent = root / "agents" / "{name}" / "agent.py"
    if not agent.exists():
        return False
    out = subprocess.check_output([sys.executable, str(agent), "smoke test"]).decode("utf-8", "ignore")
    return '"result"' in out and '"steps"' in out
"""

def scaffold_agent(name: str, kind: str = "generic") -> str:
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    agent_dir = AGENTS_DIR / name
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "README.md").write_text(AGENT_README.format(name=name, kind=kind), encoding="utf-8")
    (agent_dir / "manifest.yaml").write_text(AGENT_MANIFEST.format(name=name, kind=kind), encoding="utf-8")
    (agent_dir / "agent.py").write_text(AGENT_CODE.format(name=name, kind=kind), encoding="utf-8")
    # per-agent golden test
    TESTS_DIR.mkdir(parents=True, exist_ok=True)
    (TESTS_DIR / f"test_agent_{name.lower()}.py").write_text(TEST_CODE.format(name=name), encoding="utf-8")
    return str(agent_dir)

def interpret_and_create(prompt: str) -> dict:
    """Very small prompt -> (name, kind) interpreter (offline)."""
    pl = prompt.lower()
    if any(k in pl for k in ["game", "player", "enemy", "boss", "roguelike"]):
        kind = "game"
    elif any(k in pl for k in ["tv", "show", "episode", "series", "film"]):
        kind = "tv"
    elif any(k in pl for k in ["music", "song", "band"]):
        kind = "music"
    else:
        kind = "generic"

    tokens = re.findall(r"[A-Za-z0-9]+", prompt.title())
    name = (tokens[0] if tokens else "Agent")[:20]

    path = scaffold_agent(name, kind)
    info = {"name": name, "kind": kind, "path": path, "prompt": prompt}
    (STATE / f"{name.lower()}_meta.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    return info

# --------------------------- CLI ----------------------------------------

def main():
    ensure_state()

    ap = argparse.ArgumentParser(prog="forge", description="GhostForge v1.2 CLI")
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("status")
    sub.add_parser("freeze")
    sub.add_parser("thaw")
    sub.add_parser("list-commands")

    p_snap = sub.add_parser("snapshot")
    p_snap.add_argument("--label", default="manual")

    p_repair = sub.add_parser("repair")
    p_repair.add_argument("--strategy", default="lint", choices=["lint", "refactor", "regen"])

    # make-agent (scaffold by explicit kind)
    p_make = sub.add_parser("make-agent")
    p_make.add_argument("--name", required=True)
    p_make.add_argument("--kind", default="generic", choices=["generic", "game", "tv", "music"])

    # create (prompt-driven agent creation)
    p_create = sub.add_parser("create")
    p_create.add_argument("prompt", help="Describe the agent you want to create")

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
    elif args.cmd == "make-agent":
        path = scaffold_agent(args.name, args.kind)
        log("forge", "make_agent", json.dumps({"name": args.name, "kind": args.kind, "path": path}))
        print(f"Agent created: {path}")
    elif args.cmd == "create":
        info = interpret_and_create(args.prompt)
        log("forge", "create_agent", json.dumps(info))
        print(f"Created {info['kind']} agent '{info['name']}' at {info['path']}")
    elif args.cmd == "test":
        ok = run_tests()
        print("ALL TESTS", "PASS" if ok else "FAIL")
        sys.exit(0 if ok else 1)
    else:
        ap.print_help()

if __name__ == "__main__":
    main()
