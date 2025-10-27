
#!/usr/bin/env python3
from pathlib import Path
import argparse, zipfile, sys

ROOT = Path(__file__).resolve().parent
AGENTS = ROOT / "agents"
DIST = ROOT / "dist"

def pack_agent(agent_dir: Path, version: str):
    out = DIST / f"{agent_dir.name}_v{version}.zip"
    DIST.mkdir(exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in agent_dir.rglob("*"):
            if "__pycache__" in p.parts:
                continue
            if p.name == "memory.json":
                continue
            z.write(p, p.relative_to(ROOT))
    return out

def main():
    ap = argparse.ArgumentParser(description="Pack all agents into zips")
    ap.add_argument("--version", default="0.1", help="version label for zip names")
    args = ap.parse_args()

    if not AGENTS.exists():
        sys.exit("No agents directory found.")
    agents = [d for d in AGENTS.iterdir() if (d / "agent.py").exists()]
    if not agents:
        sys.exit("No agents to pack (no agent.py found).")

    outs = []
    for d in agents:
        out = pack_agent(d, args.version)
        print(out)
        outs.append(out)

    print(f"\nPacked {len(outs)} agent(s) to {DIST}")
if __name__ == "__main__":
    main()
