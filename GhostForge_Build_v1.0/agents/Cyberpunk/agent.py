from pathlib import Path
import json, sys, time

class Agent:
    def __init__(self, name="Cyberpunk", kind="game"):
        self.name = name
        self.kind = kind
        self.root = Path(__file__).resolve().parent
        self.mem_path = self.root / "memory.json"
        self._mem = self._load()

    def _load(self):
        if self.mem_path.exists():
            try:
                return json.loads(self.mem_path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save(self):
        self.mem_path.write_text(json.dumps(self._mem, indent=2), encoding="utf-8")

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
        result = {
            "agent": self.name,
            "kind": self.kind,
            "goal": goal,
            "steps": steps,
            "result": "[demo] " + self.kind + " agent processed goal",
            "ts": int(time.time())
        }
        # remember last 20 runs
        hist = self._mem.get("history", [])
        hist.append({"goal": goal, "steps": steps[:3], "ts": result["ts"]})
        self._mem["history"] = hist[-20:]
        self._save()
        return result

if __name__ == "__main__":
    goal = " ".join(sys.argv[1:]) or "demo goal"
    print(json.dumps(Agent().run(goal), indent=2))

