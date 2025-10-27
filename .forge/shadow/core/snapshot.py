
import os, json, zipfile
from pathlib import Path
from datetime import datetime

def create_snapshot(root: Path, outdir: Path, label: str = "manual"):
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    outdir.mkdir(parents=True, exist_ok=True)
    zip_path = outdir / f"{ts}_{label}.zip"
    manifest = {"ts": ts, "label": label, "root": str(root), "included": []}
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for folder, _, files in os.walk(root):
            if Path(folder).resolve() == outdir.resolve():
                continue
            for file in files:
                full = Path(folder) / file
                if full.is_file() and outdir not in full.parents:
                    rel = full.relative_to(root)
                    z.write(full, rel.as_posix())
                    manifest["included"].append(rel.as_posix())
    return zip_path, manifest
