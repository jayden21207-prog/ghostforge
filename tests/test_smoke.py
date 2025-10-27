
def run():
    # Simple invariant: core files exist
    import os
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    must_exist = [
        root / "forge.py",
        root / "core" / "scheduler.py",
        root / "core" / "registry.py",
        root / "core" / "warden.py",
        root / "core" / "snapshot.py",
    ]
    return all(p.exists() for p in must_exist)
