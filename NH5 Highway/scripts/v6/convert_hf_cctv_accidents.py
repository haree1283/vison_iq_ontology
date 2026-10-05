#!/usr/bin/env python3
"""CCTV Traffic Accident Object Detection (Hugging Face justjuu/traffic-accident-cctv-object-detection,
CC0 as published -- a re-upload of the Roboflow Universe "Accident and Non-accident label Image Dataset")
-> datasets/v6/sources/accidents_cctv/{train,val,test}/{images,labels}.

- category 0 'accident' -> damaged_vehicle; 'non_accident' boxes are dropped, and so are images left
  with no accident box (normal-traffic CCTV frames, which other sources already cover)
- bbox is COCO [x, y, w, h] in pixels of the 640x640 image
- the upload has no file names and is Roboflow-augmented (~1,485 originals expanded to 2,763), so
  copies are found by a 64-bit difference hash of the grayscale image: one copy per hash is kept,
  and a hash seen in several splits goes to train so val/test never hold a twin of a training
  image. Flipped or heavily noised copies hash differently and stay -- they act as augmentation.

Usage:
  python scripts/v6/convert_hf_cctv_accidents.py
"""
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np
import pyarrow.parquet as pq

from classes import CLASS_IDS

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "datasets" / "v6" / "raw" / "hf_cctv_accidents"
OUT = ROOT / "datasets" / "v6" / "sources" / "accidents_cctv"
SPLITS = {"train": "train", "validation": "val", "test": "test"}  # parquet file prefix -> v6 split
ACCIDENT = 0
MIN_SIDE = 0.002  # normalized; drops degenerate boxes
JPEG_QUALITY = 92


def rows():
    """(split, encoded image bytes, objects) without loading a whole parquet file into memory."""
    for path in sorted(RAW.glob("data/*.parquet")):
        split = SPLITS[path.name.split("-")[0]]
        for batch in pq.ParquetFile(path).iter_batches(batch_size=64, columns=["image", "objects"]):
            for row in batch.to_pylist():
                yield split, row["image"]["bytes"], row["objects"]


def dhash(image):
    small = cv2.resize(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), (9, 8), interpolation=cv2.INTER_AREA)
    return int("".join("1" if bit else "0" for bit in (small[:, 1:] > small[:, :-1]).flatten()), 2)


def accident_lines(objects, w, h):
    lines = []
    for (x, y, bw, bh), cat in zip(objects["bbox"], objects["category"]):
        if cat != ACCIDENT:
            continue
        x0, y0, x1, y1 = max(0.0, x) / w, max(0.0, y) / h, min(float(w), x + bw) / w, min(float(h), y + bh) / h
        if x1 - x0 >= MIN_SIDE and y1 - y0 >= MIN_SIDE:
            lines.append(f"{CLASS_IDS['damaged_vehicle']} {(x0 + x1) / 2:.6f} {(y0 + y1) / 2:.6f} "
                         f"{x1 - x0:.6f} {y1 - y0:.6f}")
    return lines


def main():
    if not (RAW / ".done").is_file():
        raise SystemExit(f"{RAW.relative_to(ROOT)} download not complete")

    # pass 1: which splits each image hash appears in (no image bytes kept in memory)
    splits_of = defaultdict(set)
    for split, data, objects in rows():
        image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if image is not None and accident_lines(objects, image.shape[1], image.shape[0]):
            splits_of[dhash(image)].add(split)

    # pass 2: write one copy per hash
    shutil.rmtree(OUT, ignore_errors=True)
    written, stats = set(), defaultdict(Counter)
    for split, data, objects in rows():
        image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            stats[split]["_unreadable"] += 1
            continue
        lines = accident_lines(objects, image.shape[1], image.shape[0])
        if not lines:
            stats[split]["_skipped_no_accident_box"] += 1
            continue
        key = dhash(image)
        if key in written:
            stats[split]["_duplicate_copies_dropped"] += 1
            continue
        written.add(key)
        final = "train" if len(splits_of[key]) > 1 else split
        stem = f"accidents_cctv_{key:016x}"
        (OUT / final / "images").mkdir(parents=True, exist_ok=True)
        (OUT / final / "labels").mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(OUT / final / "images" / f"{stem}.jpg"), image, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
        (OUT / final / "labels" / f"{stem}.txt").write_text("\n".join(lines) + "\n")
        stats[final]["_images"] += 1
        stats[final]["damaged_vehicle"] += len(lines)

    result = {"unique_images": len(written), "splits": {k: dict(v) for k, v in sorted(stats.items())}}
    (OUT / "conversion_stats.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
