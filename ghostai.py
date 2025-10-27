#!/usr/bin/env python3
import argparse, json, sys
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parent
AGENTS_DIR = ROOT / "agents"

def find_agent(name: str):
    path = AGENTS_DIR / name / "agent.py"
    if not path.exists():
        sys.exit(f"Agent not found: {path}")
    spec = importlib.util.spec_from_file_location(f"agents.{name}.agent", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    if not hasattr(mod, "Agent"):
        sys.exit("agent.py missing class Agent")
    return mod.Agent

def list_agents():
    if not AGENTS_DIR.exists():
        return []
    return [p.name for p in AGENTS_DIR.iterdir() if (p / "agent.py").exists()]

def run_agent(agent_name: str, goal: str):
    Agent = find_agent(agent_name)
    agent = Agent()
    result = agent.run(goal)
    print(json.dumps(result, indent=2))

def export_agent(agent_name: str, goal: str, out_dir: Path):
    Agent = find_agent(agent_name)
    agent = Agent()
    result = agent.run(goal)
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"{agent_name}_{result.get('ts', 0)}.md"
    lines = [
        f"# {agent_name} — run",
        f"- kind: {result['kind']}",
        f"- goal: {result['goal']}",
        "",
        "## Plan",
    ] + [f"- {s}" for s in result["steps"]] + [
        "",
        "## Result",
        result["result"],
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(md_path)

def info(agent_name: str):
    Agent = find_agent(agent_name)
    agent = Agent()
    print(json.dumps({
        "name": getattr(agent, "name", agent_name),
        "kind": getattr(agent, "kind", "unknown"),
        "path": str((AGENTS_DIR / agent_name).resolve())
    }, indent=2))

def history(agent_name: str, limit: int = 10):
    path = AGENTS_DIR / agent_name / "memory.json"
    if not path.exists():
        print("[]")
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    hist = (data.get("history") or [])[-limit:]
    print(json.dumps(hist, indent=2))

def main():
    ap = argparse.ArgumentParser(prog="ghostai", description="GhostAI runtime")
    sub = ap.add_subparsers(dest="cmd")
    
    # run
    p_run = sub.add_parser("run")
    p_run.add_argument("--agent", required=True)
    p_run.add_argument("--goal", default="demo goal")

    # list
    sub.add_parser("list")

    # info
    p_info = sub.add_parser("info")
    p_info.add_argument("--agent", required=True)

    # export
    p_exp = sub.add_parser("export")
    p_exp.add_argument("--agent", required=True)
    p_exp.add_argument("--goal", default="demo goal")
    p_exp.add_argument("--out", default="runs")

    # history
    p_hist = sub.add_parser("history")
    p_hist.add_argument("--agent", required=True)
    p_hist.add_argument("--limit", type=int, default=10)

    args = ap.parse_args()
    if args.cmd == "run":
        run_agent(args.agent, args.goal)
    elif args.cmd == "list":
        for name in list_agents():
            print(name)
    elif args.cmd == "info":
        info(args.agent)
    elif args.cmd == "export":
        export_agent(args.agent, args.goal, (ROOT / args.out))
    elif args.cmd == "history":
        history(args.agent, args.limit) 
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
