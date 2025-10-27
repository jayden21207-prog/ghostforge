from pathlib import Path
import json, sys

class Agent:
    def __init__(self, name="TVPlotter", kind="tv"):
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
        return {
            "agent": self.name,
            "kind": self.kind,
            "goal": goal,
            "steps": steps,
            "result": "[demo] " + self.kind + " agent processed goal"
        }

if __name__ == "__main__":
    goal = " ".join(sys.argv[1:]) or "demo goal"
    print(json.dumps(Agent().run(goal), indent=2))
