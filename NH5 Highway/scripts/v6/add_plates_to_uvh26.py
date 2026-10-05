#!/usr/bin/env python3
"""Several sources label vehicle type but were never checked for plates -- run nh5_v5's own
license_plate detector over each and merge plate boxes into the existing per-image label files
(only where a vehicle box is already present, so the plate has a type to attach to). This
targets the deficient 02_number_plates sub-classes (auto, motorcycle, bus) with real Indian
photos already on disk, instead of a dedicated auto/bike/bus plate dataset that doesn't appear
to exist publicly.

Backs up untouched originals to labels_source/ first (same convention as prelabel_missing.py),
so this is safe to inspect/revert.

Usage:
  python scripts/v6/add_plates_to_uvh26.py uvh26 indian_vehicle_dataset dashcam obstacle_detection
"""
import shutil
import sys
from collections import Counter
from pathlib import Path

from ultralytics import YOLO

from classes import CLASS_IDS

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ROOT / "datasets" / "v6" / "sources"
MODEL = ROOT / "models" / "nh5_v5_best.pt"
PLATE = CLASS_IDS["license_plate"]
CONF = 0.35
IMGSZ = 1280
BATCH = 32
VEHICLE_IDS = {CLASS_IDS[n] for n in ("auto", "motorcycle", "bus", "car", "truck", "bicycle")}


def run(model, plate_model_id, split_dir):
    labels, images, originals = split_dir / "labels", split_dir / "images", split_dir / "labels_source"
    if not originals.exists():
        shutil.copytree(labels, originals)

    img_list = sorted(p for p in images.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    counts = Counter()
    for i in range(0, len(img_list), BATCH):
        chunk = img_list[i:i + BATCH]
        results = model.predict(source=[str(p) for p in chunk], stream=True, conf=CONF,
                                classes=[plate_model_id], imgsz=IMGSZ, verbose=False, batch=BATCH)
        for img, res in zip(chunk, results):
            lbl = labels / f"{img.stem}.txt"
            lines = [l for l in lbl.read_text().splitlines() if l.strip()] if lbl.is_file() else []
            has_vehicle = any(int(l.split()[0]) in VEHICLE_IDS for l in lines)
            if not has_vehicle or res.boxes is None or len(res.boxes) == 0:
                continue  # only useful where there's a vehicle box for the plate to sit inside
            for cx, cy, w, h in res.boxes.xywhn.tolist():
                lines.append(f"{PLATE} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
                counts["plates_added"] += 1
            counts["images_with_new_plate"] += 1
            lbl.write_text("\n".join(lines) + "\n")
        counts["_scanned"] = min(i + BATCH, len(img_list))
    return counts


def main():
    model = YOLO(str(MODEL))
    plate_model_id = next(i for i, n in model.names.items() if n == "license_plate")
    for name in sys.argv[1:]:
        base = SOURCES / name
        for split_dir in sorted(p for p in base.iterdir() if (p / "images").is_dir()) if base.is_dir() else []:
            counts = run(model, plate_model_id, split_dir)
            print(f"[{name}/{split_dir.name}] {dict(counts)}")


if __name__ == "__main__":
    main()
