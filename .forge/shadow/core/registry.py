
from pathlib import Path
import json

class Registry:
    """Tracks commands, modules, and artifacts (placeholder)."""
    def __init__(self, root: Path):
        self.root = root

    def list_modules(self):
        return ["modules.rewriter", "modules.tester"]

    def list_commands(self):
        cmds = []
        for p in sorted((self.root / "commands").glob("*.yaml")):
            cmds.append(p.stem)
        return cmds

# auto-repair touch: bootstrap
