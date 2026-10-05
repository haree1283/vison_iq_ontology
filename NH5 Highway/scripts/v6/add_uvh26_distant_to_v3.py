#!/usr/bin/env python3
"""Add distant/small motorcycle + auto-rich UVH-26 (Bengaluru elevated CCTV) images into
datasets/processed_v2_plus_v6_v3 train. UVH-26 v6 class ids already equal pv2 ids for
person/bicycle/car/motorcycle/bus/truck/auto/license_plate, so labels are copied unchanged
(ALL boxes kept per image so visible vehicles never become background)."""
import shutil
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "datasets/v6/sources/uvh26/train"
DST = ROOT / "datasets/processed_v2_plus_v6_v3"
CAP, SMALL_H = 3000, 0.10
cands = []
for lbl in (SRC / "labels").glob("*.txt"):
    rows = [l.split() for l in lbl.read_text().splitlines() if l.split()]
    tgt = [float(r[4]) for r in rows if int(r[0]) in (3, 8)]
    if len(tgt) < 2:
        continue
    frac_small = sum(h < SMALL_H for h in tgt) / len(tgt)
    if frac_small >= 0.5:
        cands.append((frac_small * len(tgt), lbl.stem, rows))
cands.sort(reverse=True)
boxes, n = Counter(), 0
for _, stem, rows in cands[:CAP]:
    img = next((SRC / "images" / f"{stem}{e}" for e in (".jpg", ".jpeg", ".png") if (SRC / "images" / f"{stem}{e}").is_file()), None)
    if img is None:
        continue
    out = f"uvh26d_{stem}"
    dst = DST / "images/train" / f"{out}{img.suffix}"
    if not dst.exists():
        shutil.copy2(img, dst)
    (DST / "labels/train" / f"{out}.txt").write_text("\n".join(" ".join(r[:5]) for r in rows) + "\n")
    for r in rows: boxes[int(r[0])] += 1
    n += 1
print("candidates:", len(cands), "added:", n, "boxes by pv2 id:", dict(boxes))
