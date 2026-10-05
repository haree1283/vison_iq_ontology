#!/usr/bin/env python3
"""Make DISTANT-plate training images from real, correctly boxed plate scenes already in v3 train:
shrink the whole image (all boxes scale with it) so the plate lands at 1.5-5% of frame height, pasted at a
random spot on a heavily blurred, stretched copy of itself (no extra unlabeled objects). Exact labels, no
new data. ~10% go to val / ~10% to test so far-plate detection is measurable (SYNTHETIC -- note when reading
val scores). Source: v3 train images having a license_plate box (6-30% of frame height) plus a vehicle box."""
import hashlib, random
from pathlib import Path
import cv2, numpy as np

D = Path(__file__).resolve().parents[2] / "datasets/processed_v2_plus_v6_v3"
CAP, rng = 3000, random.Random(20260921)
cands = []
for lbl in (D / "labels/train").glob("*.txt"):
    if lbl.stem.startswith(("synfar_", "sqifeng_", "uvh26d_")): continue
    rows = [l.split() for l in lbl.read_text().splitlines() if l.split()]
    if any(r[0] == "7" and 0.05 <= float(r[4]) <= 0.50 for r in rows):
        cands.append((lbl.stem, rows))
rng.shuffle(cands)
print("candidates:", len(cands))
n = {"train": 0, "val": 0, "test": 0}
for stem, rows in cands:
    if sum(n.values()) >= CAP: break
    img = next((D / "images/train" / f"{stem}{e}" for e in (".jpg", ".jpeg", ".png") if (D / "images/train" / f"{stem}{e}").is_file()), None)
    im = cv2.imread(str(img)) if img else None
    if im is None: continue
    H, W = im.shape[:2]
    ph = max(float(r[4]) for r in rows if r[0] == "7")
    s = min(0.6, max(0.1, rng.uniform(0.015, 0.05) / ph))
    nw, nh = max(8, int(W * s)), max(8, int(H * s))
    small = cv2.resize(im, (nw, nh), interpolation=cv2.INTER_AREA)
    bg = cv2.GaussianBlur(cv2.resize(cv2.resize(im, (16, 16)), (W, H), interpolation=cv2.INTER_CUBIC), (0, 0), 25)
    ox, oy = rng.randint(0, W - nw), rng.randint(0, H - nh)
    bg[oy:oy+nh, ox:ox+nw] = small
    out = []
    for r in rows:
        c, x, y, w, h = int(r[0]), *map(float, r[1:5])
        out.append(f"{c} {(ox + x*nw)/W:.6f} {(oy + y*nh)/H:.6f} {w*s:.6f} {h*s:.6f}")
    b = int(hashlib.md5(stem.encode()).hexdigest(), 16) % 100
    sp = "val" if b < 10 else "test" if b < 20 else "train"
    (D / "images" / sp).mkdir(parents=True, exist_ok=True); (D / "labels" / sp).mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(D / "images" / sp / f"synfar_{stem}.jpg"), bg, [cv2.IMWRITE_JPEG_QUALITY, 90])
    (D / "labels" / sp / f"synfar_{stem}.txt").write_text("\n".join(out) + "\n")
    n[sp] += 1
print("created:", n)
