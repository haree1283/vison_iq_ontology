#!/usr/bin/env python3
"""Collect HeteroTraffic (highway/roadside) image/label pairs, remap its 17
classes onto our unified 9-class schema, drop region-specific non-highway
vehicle types with no clean equivalent, and copy into a flat pool:
datasets/raw/heterotraffic_yolo/{images,labels}.

CNG and Easybike (Bangladeshi auto-rickshaw types -- CNG runs on compressed
natural gas, Easybike is the electric variant) are visually the same class
of vehicle as the Indian auto-rickshaw ("auto") the model was confusing for
car -- mapped to a new unified class 8 rather than dropped.
"""
import shutil
from pathlib import Path

RAW = Path(__file__).resolve().parent.parent / "datasets" / "raw"
SRC_DIR = RAW / "heterotraffic" / "roadvision_blur"
OUT_DIR = RAW / "heterotraffic_yolo"
OUT_IMAGES = OUT_DIR / "images"
OUT_LABELS = OUT_DIR / "labels"

IMG_EXTS = {".jpg", ".jpeg", ".png"}

# HeteroTraffic source class id -> name (from its data.yaml, alphabetical order)
SOURCE_NAMES = [
    "Bicycle", "Bus", "Bhotbhoti", "Car", "CNG", "Easybike", "Leguna",
    "Motorbike", "MPV", "Pedestrian", "Pickup", "PowerTiller", "Rickshaw",
    "ShoppingVan", "Truck", "Van", "Wheelbarrow",
]

# unified class ids: person=0 bicycle=1 car=2 motorcycle=3 bus=4 truck=5 ... auto=8
NAME_TO_UNIFIED = {
    "Pedestrian": 0,
    "Bicycle": 1,
    "Car": 2,
    "MPV": 2,
    "Van": 2,
    "Leguna": 2,
    "Motorbike": 3,
    "Bus": 4,
    "Truck": 5,
    "Pickup": 5,
    "ShoppingVan": 5,
    "CNG": 8,
    "Easybike": 8,
    # still dropped (no clean equivalent): Bhotbhoti, PowerTiller, Rickshaw, Wheelbarrow
}


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
            if len(parts) != 5:
                continue
            src_id, cx, cy, w, h = parts
            src_name = SOURCE_NAMES[int(src_id)]
            if src_name not in NAME_TO_UNIFIED:
                continue
            unified_id = NAME_TO_UNIFIED[src_name]
            # a small number of source boxes run up to ~0.7% past the frame
            # edge (annotation rounding, not corrupted data) -- clamp rather
            # than drop, since the box itself is still a genuine detection
            cx, cy, w, h = (float(cx), float(cy), float(w), float(h))
            x0, y0 = cx - w / 2, cy - h / 2
            x1, y1 = cx + w / 2, cy + h / 2
            x0, y0, x1, y1 = max(0.0, x0), max(0.0, y0), min(1.0, x1), min(1.0, y1)
            cx, cy, w, h = (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0
            if w <= 0 or h <= 0:
                continue
            new_lines.append(f"{unified_id} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")

        if not new_lines:
            continue

        dest_name = f"hetero_{kept:05d}{img_path.suffix.lower()}"
        shutil.copy(img_path, OUT_IMAGES / dest_name)
        (OUT_LABELS / (Path(dest_name).stem + ".txt")).write_text("\n".join(new_lines) + "\n")
        kept += 1

    print(f"Kept {kept} HeteroTraffic image/label pairs -> {OUT_DIR}")


if __name__ == "__main__":
    main()
