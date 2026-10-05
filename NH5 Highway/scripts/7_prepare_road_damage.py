#!/usr/bin/env python3
"""Collect Road Damage Dataset image/label pairs, keep only class 0 (Pothole)
and drop Crack(1)/Manhole(2), remap to unified class id 6, copy into a flat
pool: datasets/raw/road_damage_yolo/{images,labels}.

Labels are in YOLO *polygon* format (class + Nx[x,y] points), not plain
bbox — each line is converted to an axis-aligned bounding box.
"""
import shutil
from pathlib import Path

RAW = Path(__file__).resolve().parent.parent / "datasets" / "raw"
SRC_DIR = RAW / "road_damage" / "data"
OUT_DIR = RAW / "road_damage_yolo"
OUT_IMAGES = OUT_DIR / "images"
OUT_LABELS = OUT_DIR / "labels"

SOURCE_POTHOLE_CLASS_ID = "0"
UNIFIED_CLASS_ID = 6  # pothole
IMG_EXTS = {".jpg", ".jpeg", ".png"}


def main():
    # full clean regeneration each run -- otherwise a shrinking MAX_IMAGES/cap
    # (or any other change that reduces the kept count) leaves stale orphan
    # files behind from the previous, larger run
    shutil.rmtree(OUT_DIR, ignore_errors=True)
    OUT_IMAGES.mkdir(parents=True, exist_ok=True)
    OUT_LABELS.mkdir(parents=True, exist_ok=True)

    img_dir = SRC_DIR / "images"
    lbl_dir = SRC_DIR / "labels"

    kept = 0
    for img_path in sorted(img_dir.iterdir()):
        if img_path.suffix.lower() not in IMG_EXTS:
            continue
        label_path = lbl_dir / (img_path.stem + ".txt")
        if not label_path.exists():
            continue

        new_lines = []
        for line in label_path.read_text().strip().splitlines():
            parts = line.split()
            if len(parts) < 7 or len(parts) % 2 == 0 or parts[0] != SOURCE_POTHOLE_CLASS_ID:
                continue
            coords = [float(v) for v in parts[1:]]
            xs = coords[0::2]
            ys = coords[1::2]
            x_min, x_max = min(xs), max(xs)
            y_min, y_max = min(ys), max(ys)
            cx = (x_min + x_max) / 2
            cy = (y_min + y_max) / 2
            w = x_max - x_min
            h = y_max - y_min
            # defensive: polygon vertices outside 0-1 or degenerate (zero
            # area) would otherwise produce an invalid box silently
            cx, cy = min(1.0, max(0.0, cx)), min(1.0, max(0.0, cy))
            w, h = min(1.0, w), min(1.0, h)
            if w <= 0 or h <= 0:
                continue
            new_lines.append(f"{UNIFIED_CLASS_ID} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")

        if not new_lines:
            continue

        dest_name = f"roaddmg_{kept:05d}{img_path.suffix.lower()}"
        shutil.copy(img_path, OUT_IMAGES / dest_name)
        (OUT_LABELS / (Path(dest_name).stem + ".txt")).write_text("\n".join(new_lines) + "\n")
        kept += 1

    print(f"Kept {kept} road-damage (pothole-only) image/label pairs -> {OUT_DIR}")


if __name__ == "__main__":
    main()
