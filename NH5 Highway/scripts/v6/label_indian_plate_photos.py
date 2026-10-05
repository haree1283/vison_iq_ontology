#!/usr/bin/env python3
"""Auto-label an Indian plate photo collection that has no source annotations at all
(Bapatla Number Plate: state-coded filenames AP/AN/...; indian_plates_extra: kedarsai +
dataclusterlabs + saisirishan's video/google-image folders) -> datasets/v6/sources/<name>/train/{images,labels}.

Unlike prelabel_missing.py (which only fills classes a source's own labels miss) this runs
nh5_v5 fresh for every class it knows, including license_plate itself -- the whole point of
collecting these sources.

Usage:
  python scripts/v6/label_bapatla_plates.py bapatla_plates datasets/v6/raw/bapatla_plates/extracted/images
  python scripts/v6/label_bapatla_plates.py indian_plates_extra datasets/v6/raw/indian_plates_extra/images
"""
import sys
from collections import Counter
from pathlib import Path

from ultralytics import YOLO

from classes import CLASS_IDS

ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "models" / "nh5_v5_best.pt"
WANTED = {"person", "bicycle", "car", "motorcycle", "bus", "truck", "auto", "license_plate"}
CONF = 0.35
IMAGE_EXTS = (".jpg", ".jpeg", ".png")


def main():
    name, raw_dir = sys.argv[1], Path(sys.argv[2])
    out = ROOT / "datasets" / "v6" / "sources" / name / "train"
    (out / "images").mkdir(parents=True, exist_ok=True)
    (out / "labels").mkdir(parents=True, exist_ok=True)

    model = YOLO(str(MODEL))
    v5_to_v6 = {i: CLASS_IDS[n] for i, n in model.names.items() if n in WANTED}
    images = sorted(p for p in raw_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS)

    counts = Counter()
    for i in range(0, len(images), 32):
        chunk = images[i:i + 32]
        results = model.predict(source=[str(p) for p in chunk], stream=True, conf=CONF,
                                classes=list(v5_to_v6), imgsz=1280, verbose=False)
        for img, res in zip(chunk, results):  # stream=True preserves input order
            lines = []
            if res.boxes is not None:
                for cls, (cx, cy, w, h) in zip(res.boxes.cls.tolist(), res.boxes.xywhn.tolist()):
                    v6 = v5_to_v6[int(cls)]
                    lines.append(f"{v6} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
            stem = f"{name}_{img.stem.replace(' ', '_').replace('(', '').replace(')', '')}"
            (out / "images" / f"{stem}{img.suffix.lower()}").write_bytes(img.read_bytes())
            (out / "labels" / f"{stem}.txt").write_text("\n".join(lines) + ("\n" if lines else ""))
            counts["_images"] += 1
            counts["_with_plate"] += any(l.startswith(f"{CLASS_IDS['license_plate']} ") for l in lines)
            for cname in WANTED:
                counts[cname] += sum(l.startswith(f"{CLASS_IDS[cname]} ") for l in lines)
        print(f"  {min(i + 32, len(images))}/{len(images)} images, {dict(counts)}")

    print(dict(counts))


if __name__ == "__main__":
    main()
