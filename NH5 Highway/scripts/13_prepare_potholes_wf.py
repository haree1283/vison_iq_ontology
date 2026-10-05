#!/usr/bin/env python3
"""Collect the water-filled/dry potholes pool (already YOLO format, single
class 0), remap to unified class 6, copy into a flat pool:
datasets/raw/potholes_wf_yolo/{images,labels}.
"""
import shutil
from pathlib import Path

RAW = Path(__file__).resolve().parent.parent / "datasets" / "raw"
SRC_DIR = RAW / "potholes_wf"
OUT_DIR = RAW / "potholes_wf_yolo"
OUT_IMAGES = OUT_DIR / "images"
OUT_LABELS = OUT_DIR / "labels"

UNIFIED_CLASS_ID = 6  # pothole


def main():
    # full clean regeneration each run -- otherwise a shrinking MAX_IMAGES/cap
    # (or any other change that reduces the kept count) leaves stale orphan
    # files behind from the previous, larger run
    shutil.rmtree(OUT_DIR, ignore_errors=True)
    OUT_IMAGES.mkdir(parents=True, exist_ok=True)
    OUT_LABELS.mkdir(parents=True, exist_ok=True)

    img_dir = SRC_DIR / "IMG"
    lbl_dir = SRC_DIR / "TXT"

    kept = 0
    dropped_boxes = 0
    for img_path in sorted(img_dir.glob("*.jpg")):
        label_path = lbl_dir / (img_path.stem + ".txt")
        if not label_path.exists():
            continue

        new_lines = []
        for line in label_path.read_text().strip().splitlines():
            parts = line.split()
            if len(parts) != 4 and len(parts) != 5:
                continue
            # some rows may lack a leading class id (single-class dataset); handle both
            coords = parts[-4:]
            cx, cy, w, h = (float(v) for v in coords)
            # a handful of source files (e.g. Pothole-261/262/268/271) have
            # corrupted coordinates wildly outside the normalized 0-1 range
            # (cx up to 6.3) -- not rounding noise, genuinely wrong ground
            # truth, so drop the box rather than fabricate a clamped one
            if not (0 <= cx <= 1 and 0 <= cy <= 1 and 0 < w <= 1 and 0 < h <= 1):
                dropped_boxes += 1
                continue
            new_lines.append(f"{UNIFIED_CLASS_ID} {cx} {cy} {w} {h}")

        if not new_lines:
            continue

        dest_name = f"potholewf_{kept:05d}.jpg"
        shutil.copy(img_path, OUT_IMAGES / dest_name)
        (OUT_LABELS / (Path(dest_name).stem + ".txt")).write_text("\n".join(new_lines) + "\n")
        kept += 1

    print(f"Kept {kept} water-filled/dry pothole image/label pairs -> {OUT_DIR}")
    if dropped_boxes:
        print(f"Dropped {dropped_boxes} boxes with out-of-range coordinates (corrupted source labels)")


if __name__ == "__main__":
    main()
