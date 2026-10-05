#!/usr/bin/env python3
"""Add SQiFeng/traffic-vehicle-detection (elevated fixed CCTV, DETRAC-style; 971 labeled test
images) straight into datasets/processed_v2_plus_v6_v3 train split -- targets the elevated /
high-angle camera blind spot. Source ids follow Roboflow alphabetical order (data.yaml names list is misleading): 0 bus, 1 car, 2 truck, 3 van -> pv2 bus/car/truck/car."""
import shutil
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "datasets/v6/raw/traffic_vehicle_detection/test"
DST = ROOT / "datasets/processed_v2_plus_v6_v3"
MAP = {0: 4, 1: 2, 2: 5, 3: 2}
n_img, boxes = 0, Counter()
for lbl in (SRC / "labels").glob("*.txt"):
    img = SRC / "images" / f"{lbl.stem}.jpg"
    lines = []
    for line in lbl.read_text().splitlines():
        p = line.split()
        if p and int(p[0]) in MAP:
            lines.append(f"{MAP[int(p[0])]} {' '.join(p[1:5])}"); boxes[MAP[int(p[0])]] += 1
    if not lines or not img.is_file():
        continue
    stem = f"sqifeng_{lbl.stem}"
    shutil.copy2(img, DST / "images/train" / f"{stem}.jpg")
    (DST / "labels/train" / f"{stem}.txt").write_text("\n".join(lines) + "\n")
    n_img += 1
print("images added:", n_img, "boxes (pv2 class id):", dict(boxes))
