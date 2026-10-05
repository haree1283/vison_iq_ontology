#!/usr/bin/env python3
"""sachinpatel21/pothole-image-dataset: flat pothole photos, no boxes at all -- run nh5_v5's
own pothole detector to get real boxes (same pattern as label_bapatla_plates.py).

Usage:
  python scripts/v6/label_pothole_image_data.py
"""
from pathlib import Path

from ultralytics import YOLO

from classes import CLASS_IDS

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "datasets" / "v6" / "raw" / "kaggle" / "pothole-image-dataset" / "pothole_image_data" / "Pothole_Image_Data"
OUT = ROOT / "datasets" / "v6" / "sources" / "pothole_image_data" / "train"
MODEL = ROOT / "models" / "nh5_v5_best.pt"
POTHOLE = CLASS_IDS["pothole"]
IMAGE_EXTS = (".jpg", ".jpeg", ".png")


def main():
    (OUT / "images").mkdir(parents=True, exist_ok=True)
    (OUT / "labels").mkdir(parents=True, exist_ok=True)
    model = YOLO(str(MODEL))
    images = sorted(p for p in RAW.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    n, boxes_n = 0, 0
    for i in range(0, len(images), 32):
        chunk = images[i:i + 32]
        results = model.predict(source=[str(p) for p in chunk], stream=True, conf=0.35,
                                classes=[POTHOLE], imgsz=1280, verbose=False)
        for img, res in zip(chunk, results):
            lines = []
            if res.boxes is not None:
                for cx, cy, w, h in res.boxes.xywhn.tolist():
                    lines.append(f"{POTHOLE} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
            if not lines:
                continue
            stem = f"pothole_image_data_{img.stem}"
            (OUT / "images" / f"{stem}{img.suffix.lower()}").write_bytes(img.read_bytes())
            (OUT / "labels" / f"{stem}.txt").write_text("\n".join(lines) + "\n")
            n += 1
            boxes_n += len(lines)
    print(f"images: {n}, pothole boxes: {boxes_n}")


if __name__ == "__main__":
    main()
