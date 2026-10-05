#!/usr/bin/env python3
"""keremberke/license-plate-object-detection (Hugging Face / Roboflow, CC BY 4.0) ->
datasets/v6/sources/hf_keremberke_plates/{train,val,test}/{images,labels}.

Single category (license_plate, COCO [x,y,w,h] in pixels) -- no vehicle boxes, so run
prelabel_missing.py on this source afterwards to add nh5_v5 vehicle boxes; only then can
build_categories.py's plate_kinds() sort these into 02_number_plates/<vehicle type> instead
of leaving them all in no_vehicle_box.

Usage:
  cd datasets/v6/raw/hf_keremberke_plates/data && for s in train valid test; do
    unzip -q -o $s.zip -d ../extracted/$s; done
  python scripts/v6/convert_hf_keremberke_plates.py
"""
import json
from collections import Counter
from pathlib import Path

import cv2

from classes import CLASS_IDS

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "datasets" / "v6" / "raw" / "hf_keremberke_plates" / "extracted"
OUT = ROOT / "datasets" / "v6" / "sources" / "hf_keremberke_plates"
SPLITS = {"train": "train", "valid": "val", "test": "test"}
PLATE = CLASS_IDS["license_plate"]
JPEG_QUALITY = 92


def main():
    stats = {}
    for src_split, dst_split in SPLITS.items():
        split_dir = RAW / src_split
        coco = json.loads((split_dir / "_annotations.coco.json").read_text())
        images = {im["id"]: im for im in coco["images"]}
        boxes_by_image = {}
        for ann in coco["annotations"]:
            boxes_by_image.setdefault(ann["image_id"], []).append(ann["bbox"])

        out_img, out_lbl = OUT / dst_split / "images", OUT / dst_split / "labels"
        out_img.mkdir(parents=True, exist_ok=True)
        out_lbl.mkdir(parents=True, exist_ok=True)

        counts = Counter()
        for image_id, im in images.items():
            src = split_dir / im["file_name"]
            if not src.is_file():
                continue
            w, h = im["width"], im["height"]
            lines = []
            for x, y, bw, bh in boxes_by_image.get(image_id, []):
                x0, y0 = max(0.0, x), max(0.0, y)
                x1, y1 = min(float(w), x + bw), min(float(h), y + bh)
                if x1 - x0 < 2 or y1 - y0 < 2:
                    continue
                cx, cy = (x0 + x1) / 2 / w, (y0 + y1) / 2 / h
                lines.append(f"{PLATE} {cx:.6f} {cy:.6f} {(x1 - x0) / w:.6f} {(y1 - y0) / h:.6f}")
            if not lines:
                continue  # keep only images with a real plate box -- other sources cover backgrounds

            stem = f"hf_keremberke_{Path(im['file_name']).stem}"
            image = cv2.imread(str(src))
            if image is None:
                continue
            cv2.imwrite(str(out_img / f"{stem}.jpg"), image, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
            (out_lbl / f"{stem}.txt").write_text("\n".join(lines) + "\n")
            counts["license_plate"] += len(lines)
            counts["_images"] += 1

        stats[dst_split] = dict(counts)
        print(f"[{dst_split}] {stats[dst_split]}")

    (OUT / "conversion_stats.json").write_text(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
