def run():
    import pathlib, subprocess, sys, json
    root = pathlib.Path(__file__).resolve().parents[1]
    agent = root / "agents" / "Cyberpunk" / "agent.py"
    if not agent.exists():
        return False
    out = subprocess.check_output([sys.executable, str(agent), "smoke test"]).decode("utf-8", "ignore")
    return '"result"' in out and '"steps"' in out
