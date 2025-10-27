
import json
from pathlib import Path

def apply(plan_path: Path, target_file: Path):
    # placeholder; the actual apply is orchestrated by forge.py
    return {"status": "noop", "plan": str(plan_path), "target": str(target_file)}
