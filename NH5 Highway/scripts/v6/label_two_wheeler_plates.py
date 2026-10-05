#!/usr/bin/env python3
"""sureshmecad/number-plate-two-wheeler (Kaggle, 750 images, zero existing annotations) --
run nh5_v5 fresh for motorcycle/bicycle + license_plate, since nothing else labels this source
at all. Targets the auto/motorcycle number-plate shortfall with real two-wheeler+plate photos.

Usage:
  python scripts/v6/label_two_wheeler_plates.py
"""
from collections import Counter
from pathlib import Path

from ultralytics import YOLO

from classes import CLASS_IDS

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "datasets" / "v6" / "raw" / "kaggle" / "number-plate-two-wheeler" / "train"
OUT = ROOT / "datasets" / "v6" / "sources" / "two_wheeler_plates" / "train"
MODEL = ROOT / "models" / "nh5_v5_best.pt"
WANTED = {"motorcycle", "bicycle", "license_plate"}
CONF = 0.35
IMAGE_EXTS = (".jpg", ".jpeg", ".png")


def main():
    (OUT / "images").mkdir(parents=True, exist_ok=True)
    (OUT / "labels").mkdir(parents=True, exist_ok=True)

    model = YOLO(str(MODEL))
    v5_to_v6 = {i: CLASS_IDS[n] for i, n in model.names.items() if n in WANTED}
    images = sorted(p for p in RAW.iterdir() if p.suffix.lower() in IMAGE_EXTS)

    counts = Counter()
    for i in range(0, len(images), 32):
        chunk = images[i:i + 32]
        results = model.predict(source=[str(p) for p in chunk], stream=True, conf=CONF,
                                classes=list(v5_to_v6), imgsz=1280, verbose=False)
        for img, res in zip(chunk, results):
            lines = []
            if res.boxes is not None:
                for cls, (cx, cy, w, h) in zip(res.boxes.cls.tolist(), res.boxes.xywhn.tolist()):
                    v6 = v5_to_v6[int(cls)]
                    lines.append(f"{v6} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
            if not any(l.split()[0] != str(CLASS_IDS["license_plate"]) for l in lines):
                continue  # keep only images where a two-wheeler was actually found (not just a plate)
            stem = f"two_wheeler_{img.stem}"
            (OUT / "images" / f"{stem}{img.suffix.lower()}").write_bytes(img.read_bytes())
            (OUT / "labels" / f"{stem}.txt").write_text("\n".join(lines) + ("\n" if lines else ""))
            counts["_images"] += 1
            id_to_name = {v: k for k, v in CLASS_IDS.items()}
            for l in lines:
                counts[id_to_name[int(l.split()[0])]] += 1

    print(dict(counts))


if __name__ == "__main__":
    main()
