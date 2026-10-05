#!/usr/bin/env python3
"""Collect pothole image/label pairs (already YOLO format, single class 0)
from wherever they landed in the extracted zip, remap class id to 6,
and copy into a flat pool: datasets/raw/pothole_yolo/{images,labels}.
"""
import shutil
from pathlib import Path

RAW = Path(__file__).resolve().parent.parent / "datasets" / "raw"
SRC_DIR = RAW / "pothole"
OUT_DIR = RAW / "pothole_yolo"
OUT_IMAGES = OUT_DIR / "images"
OUT_LABELS = OUT_DIR / "labels"

UNIFIED_CLASS_ID = 6  # pothole
IMG_EXTS = {".jpg", ".jpeg", ".png"}


def main():
    # full clean regeneration each run -- otherwise a shrinking MAX_IMAGES/cap
    # (or any other change that reduces the kept count) leaves stale orphan
    # files behind from the previous, larger run
    shutil.rmtree(OUT_DIR, ignore_errors=True)
    OUT_IMAGES.mkdir(parents=True, exist_ok=True)
    OUT_LABELS.mkdir(parents=True, exist_ok=True)

    all_images = [p for p in SRC_DIR.rglob("*") if p.suffix.lower() in IMG_EXTS]
    kept = 0
    dropped_boxes = 0
    for img_path in all_images:
        label_path = img_path.with_suffix(".txt")
        if not label_path.exists():
            continue

        new_lines = []
        for line in label_path.read_text().strip().splitlines():
            parts = line.split()
            if len(parts) != 5:
                continue
            _, cx, cy, w, h = parts
            cx, cy, w, h = (float(cx), float(cy), float(w), float(h))
            # a degenerate zero-width/zero-height box exists in the source
            # for at least one image -- worthless for training, drop it
            if not (0 <= cx <= 1 and 0 <= cy <= 1 and w > 0 and h > 0):
                dropped_boxes += 1
                continue
            new_lines.append(f"{UNIFIED_CLASS_ID} {cx} {cy} {w} {h}")

        if not new_lines:
            continue

        # avoid filename collisions across subfolders
        dest_name = f"pothole_{kept:05d}{img_path.suffix.lower()}"
        shutil.copy(img_path, OUT_IMAGES / dest_name)
        (OUT_LABELS / (Path(dest_name).stem + ".txt")).write_text("\n".join(new_lines) + "\n")
        kept += 1

    print(f"Kept {kept} pothole image/label pairs -> {OUT_DIR}")
    if dropped_boxes:
        print(f"Dropped {dropped_boxes} degenerate zero-size boxes")


if __name__ == "__main__":
    main()
