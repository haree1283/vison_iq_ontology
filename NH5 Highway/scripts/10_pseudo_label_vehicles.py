#!/usr/bin/env python3
"""Fix a labeling gap in the license_plate_yolo pool: those source images
(Zenodo ANPR) only ever had plate boxes annotated, never the vehicles
carrying them, even though cars fill most of these frames. That taught the
model an implicit "no car here" signal on exactly the close-up-vehicle
images where the two-stage plate pipeline needs a vehicle box to trigger.

Fix: run our own just-trained model (already 0.84-0.88 mAP50 on car/truck/
bus/motorcycle) over these images and append its vehicle detections to the
existing label files as pseudo-labels. High confidence threshold to keep
noise low, since this becomes training data.
"""
from pathlib import Path

from ultralytics import YOLO

RAW = Path(__file__).resolve().parent.parent / "datasets" / "raw"
POOL_DIR = RAW / "license_plate_yolo"
MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "nh5_v4_best.pt"

VEHICLE_CLASS_IDS = {2, 3, 4, 5}  # car, motorcycle, bus, truck
CONF_THRESHOLD = 0.45


def main():
    model = YOLO(str(MODEL_PATH))
    img_dir = POOL_DIR / "images"
    lbl_dir = POOL_DIR / "labels"

    images = sorted(img_dir.iterdir())
    added_boxes = 0
    touched_images = 0

    for i, img_path in enumerate(images):
        result = model.predict(str(img_path), conf=CONF_THRESHOLD, classes=list(VEHICLE_CLASS_IDS), verbose=False)[0]
        if result.boxes is None or len(result.boxes) == 0:
            continue

        lbl_path = lbl_dir / (img_path.stem + ".txt")
        existing = lbl_path.read_text().strip() if lbl_path.exists() else ""
        new_lines = []
        for box in result.boxes:
            cls = int(box.cls[0])
            cx, cy, w, h = box.xywhn[0].tolist()
            new_lines.append(f"{cls} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")

        combined = (existing + "\n" + "\n".join(new_lines)).strip() if existing else "\n".join(new_lines)
        lbl_path.write_text(combined + "\n")
        added_boxes += len(new_lines)
        touched_images += 1

        if (i + 1) % 100 == 0:
            print(f"  {i + 1}/{len(images)} images processed, {added_boxes} vehicle boxes added so far")

    print(f"Done: added {added_boxes} vehicle pseudo-labels across {touched_images}/{len(images)} images")


if __name__ == "__main__":
    main()
