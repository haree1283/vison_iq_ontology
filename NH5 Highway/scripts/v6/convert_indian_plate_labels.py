#!/usr/bin/env python3
"""kedarsai/indian-license-plates-with-labels (Kaggle, already YOLO format, single class 0 =
license plate) -> datasets/v6/sources/indian_license_plates/train/{images,labels}.

Real Indian plate photos with no vehicle-type context -- run prelabel_missing.py on this
source afterwards so build_categories.py's plate_kinds() can sort by vehicle type instead of
leaving everything in no_vehicle_box.

Usage:
  python scripts/v6/convert_indian_plate_labels.py
"""
import json
from pathlib import Path

from classes import CLASS_IDS

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "datasets" / "v6" / "raw" / "kaggle" / "indian-license-plates-with-labels"
OUT = ROOT / "datasets" / "v6" / "sources" / "indian_license_plates" / "train"
PLATE = CLASS_IDS["license_plate"]
IMAGE_EXTS = (".jpg", ".jpeg", ".png")


def main():
    (OUT / "images").mkdir(parents=True, exist_ok=True)
    (OUT / "labels").mkdir(parents=True, exist_ok=True)

    n = 0
    for lbl in sorted((RAW / "labels").glob("*.txt")):
        img = next((p for ext in IMAGE_EXTS if (p := RAW / "images" / f"{lbl.stem}{ext}").is_file()), None)
        if img is None:
            continue
        lines = []
        for raw_line in lbl.read_text().splitlines():
            parts = raw_line.split()
            if len(parts) != 5:
                continue
            lines.append(" ".join([str(PLATE)] + parts[1:]))
        if not lines:
            continue
        stem = f"indian_plate_{img.stem}".replace(" ", "_").replace("(", "").replace(")", "")
        (OUT / "images" / f"{stem}{img.suffix.lower()}").write_bytes(img.read_bytes())
        (OUT / "labels" / f"{stem}.txt").write_text("\n".join(lines) + "\n")
        n += 1

    print(f"indian_license_plates: {n} images")
    (OUT.parent / "conversion_stats.json").write_text(json.dumps({"_images": n, "license_plate": n}, indent=2))


if __name__ == "__main__":
    main()
