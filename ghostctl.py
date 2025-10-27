#!/usr/bin/env python3
import argparse, subprocess, sys
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent
FORGE = ROOT / "forge.py"
AGENTS = ROOT / "agents"
DIST = ROOT / "dist"

def spawn(name: str, kind: str):
    cmd = [sys.executable, str(FORGE), "make-agent", "--name", name, "--kind", kind]
    subprocess.check_call(cmd)

def pack(name: str, version: str = "0.1"):
    agent_dir = AGENTS / name
    if not agent_dir.exists():
        sys.exit(f"Agent not found: {agent_dir}")
    DIST.mkdir(exist_ok=True)
    out = DIST / f"{name}_v{version}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in agent_dir.rglob("*"):
            if "__pycache__" in p.parts:
                continue
            # store paths relative to project root so unzip recreates agents/<Name>/...
            z.write(p, p.relative_to(ROOT))
    print(out)

def main():
    ap = argparse.ArgumentParser(prog="ghostctl", description="Ghost control CLI")
    sub = ap.add_subparsers(dest="cmd")

    p_spawn = sub.add_parser("spawn")
    p_spawn.add_argument("name")
    p_spawn.add_argument("--kind", default="generic", choices=["generic","game","tv","music"])

    p_pack = sub.add_parser("pack")
    p_pack.add_argument("name")
    p_pack.add_argument("--version", default="0.1")

    args = ap.parse_args()
    if args.cmd == "spawn":
        spawn(args.name, args.kind)
    elif args.cmd == "pack":
        pack(args.name, args.version)
    else:
        ap.print_help()

if __name__ == "__main__":
    main()
