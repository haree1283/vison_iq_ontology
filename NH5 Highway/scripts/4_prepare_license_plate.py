#!/usr/bin/env python3
"""Collect license plate image/label pairs from the Zenodo ANPR dataset
(train/valid/test already split inside), keep only class 0 ("plate"),
drop the stray "toyota" class, remap to unified class id 7, and copy
into a flat pool: datasets/raw/license_plate_yolo/{images,labels}.
"""
import shutil
from pathlib import Path

RAW = Path(__file__).resolve().parent.parent / "datasets" / "raw"
SRC_DIR = RAW / "license_plate"
OUT_DIR = RAW / "license_plate_yolo"
OUT_IMAGES = OUT_DIR / "images"
OUT_LABELS = OUT_DIR / "labels"

SOURCE_PLATE_CLASS_ID = "0"
UNIFIED_CLASS_ID = 7  # license_plate
IMG_EXTS = {".jpg", ".jpeg", ".png"}


def main():
    # full clean regeneration each run -- otherwise a shrinking MAX_IMAGES/cap
    # (or any other change that reduces the kept count) leaves stale orphan
    # files behind from the previous, larger run
    shutil.rmtree(OUT_DIR, ignore_errors=True)
    OUT_IMAGES.mkdir(parents=True, exist_ok=True)
    OUT_LABELS.mkdir(parents=True, exist_ok=True)

    kept = 0
    for split in ("train", "valid", "test"):
        img_dir = SRC_DIR / split / "images"
        lbl_dir = SRC_DIR / split / "labels"
        if not img_dir.exists():
            continue
        for img_path in sorted(img_dir.iterdir()):
            if img_path.suffix.lower() not in IMG_EXTS:
                continue
            label_path = lbl_dir / (img_path.stem + ".txt")
            if not label_path.exists():
                continue

            new_lines = []
            for line in label_path.read_text().strip().splitlines():
                parts = line.split()
                if len(parts) != 5 or parts[0] != SOURCE_PLATE_CLASS_ID:
                    continue
                _, cx, cy, w, h = parts
                new_lines.append(f"{UNIFIED_CLASS_ID} {cx} {cy} {w} {h}")

            if not new_lines:
                continue

            dest_name = f"plate_{kept:05d}{img_path.suffix.lower()}"
            shutil.copy(img_path, OUT_IMAGES / dest_name)
            (OUT_LABELS / (Path(dest_name).stem + ".txt")).write_text("\n".join(new_lines) + "\n")
            kept += 1

    print(f"Kept {kept} license plate image/label pairs -> {OUT_DIR}")


if __name__ == "__main__":
    main()
