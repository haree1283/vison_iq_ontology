#!/usr/bin/env python3
"""Add scene images with SMALL (distant) license_plate boxes + vehicles into v3 train, from non-accident
v6 sources (accident sources skipped: their crash labels would conflict with accident_scene data already in
pv2). Keeps ids 0-8 only (v6 ids == pv2 ids there); drops damaged_vehicle/etc. Skips images already present
in pv2 as v6_<stem> or uvh26d_/sqifeng_ additions."""
import shutil
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[2]
SRCS = ["obstacle_detection", "open_images", "uvh26", "bapatla_plates", "gate_plates",
        "two_wheeler_plates", "dashcam", "indian_license_plates", "indian_plates_extra"]
DST = ROOT / "datasets/processed_v2_plus_v6_v3"
have = {p.stem for p in (DST / "images/train").iterdir()}
n, boxes, per = 0, Counter(), Counter()
for s in SRCS:
    for lbl in (ROOT / "datasets/v6/sources" / s).glob("*/labels/*.txt"):
        rows = [l.split() for l in lbl.read_text().splitlines() if l.split()]
        keep = [r for r in rows if int(r[0]) <= 8]
        plates = [r for r in keep if r[0] == "7"]
        if not any(float(r[4]) < 0.05 and float(r[3]) < 0.15 for r in plates): continue
        if not any(int(r[0]) in (2, 3, 4, 5, 8) for r in keep): continue
        if f"v6_{lbl.stem}" in have or f"uvh26d_{lbl.stem}" in have: continue
        split_dir = lbl.parent.parent
        img = next((split_dir / "images" / f"{lbl.stem}{e}" for e in (".jpg", ".jpeg", ".png") if (split_dir / "images" / f"{lbl.stem}{e}").is_file()), None)
        if img is None: continue
        out = f"platefar_{s}_{lbl.stem}"
        shutil.copy2(img, DST / "images/train" / f"{out}{img.suffix}")
        (DST / "labels/train" / f"{out}.txt").write_text("\n".join(" ".join(r[:5]) for r in keep) + "\n")
        n += 1; per[s] += 1
        for r in keep: boxes[int(r[0])] += 1
print("added:", n, dict(per)); print("boxes by id:", dict(boxes))
