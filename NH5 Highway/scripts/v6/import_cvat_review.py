#!/usr/bin/env python3
"""Bring reviewed labels back from a CVAT "YOLO 1.1" export.

Reviewed labels go to <source>/<split>/labels_reviewed/<stem>.txt (the
human-checked truth, never overwritten by pre-labeling) and replace
labels/<stem>.txt. build_v6_dataset.py always prefers labels_reviewed/.

Refuses to import if the export's class list doesn't match classes.CLASSES
(a reordered label list in CVAT would silently shift every class id).

Usage:
  python scripts/v6/import_cvat_review.py raqabah task_raqabah_review_001-yolo.zip
"""
import argparse
import json
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath

from classes import CLASSES

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ROOT / "datasets" / "v6" / "sources"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("exports", nargs="+", type=Path, help="zip(s) exported from CVAT as YOLO 1.1")
    args = ap.parse_args()

    src_root = SOURCES / args.source
    log_path = src_root / "review_log.json"
    log = json.loads(log_path.read_text()) if log_path.is_file() else []

    for export in args.exports:
        with zipfile.ZipFile(export) as zf:
            names_file = next((n for n in zf.namelist() if n.endswith("obj.names")), None)
            if names_file is None:
                raise SystemExit(f"{export}: no obj.names -- was it exported as 'YOLO 1.1'?")
            exported = [l.strip() for l in zf.read(names_file).decode().splitlines() if l.strip()]
            if exported != CLASSES:
                raise SystemExit(f"{export}: CVAT label list {exported} differs from classes.CLASSES {CLASSES} -- "
                                 "fix the label order in the CVAT project before exporting")

            imported, skipped = 0, []
            for member in zf.namelist():
                path = PurePosixPath(member)
                if path.suffix != ".txt" or "obj_train_data" not in path.parts:
                    continue
                split, sep, stem = path.stem.partition("__")
                images = src_root / split / "images"
                if not sep or not images.is_dir() or not any(images.glob(f"{stem}.*")):
                    skipped.append(path.stem)
                    continue
                text = zf.read(member).decode()
                for d in ("labels_reviewed", "labels"):
                    (src_root / split / d).mkdir(exist_ok=True)
                    (src_root / split / d / f"{stem}.txt").write_text(text)
                imported += 1

        log.append({"export": export.name, "imported": imported, "skipped": len(skipped),
                    "at": datetime.now().isoformat(timespec="seconds")})
        print(f"{export.name}: {imported} reviewed labels imported"
              + (f", {len(skipped)} skipped (unknown image), e.g. {skipped[:3]}" if skipped else ""))
    log_path.write_text(json.dumps(log, indent=2))


if __name__ == "__main__":
    main()
