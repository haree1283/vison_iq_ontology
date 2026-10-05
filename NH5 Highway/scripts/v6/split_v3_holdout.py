#!/usr/bin/env python3
"""Move ~10% of the newly added elevated/distant images (sqifeng_*, uvh26d_*) from v3 train into
val and ~10% into test (deterministic by filename hash) so the elevated-view gain is measurable."""
import hashlib
from pathlib import Path
from collections import defaultdict

D = Path(__file__).resolve().parents[2] / "datasets/processed_v2_plus_v6_v3"
names = ['person','bicycle','car','motorcycle','bus','truck','pothole','license_plate','auto','road_construction','accident_scene','traffic_cone']
moved = {"val": 0, "test": 0}
for lbl in list((D / "labels/train").glob("*.txt")):
    if not lbl.stem.startswith(("sqifeng_", "uvh26d_")):
        continue
    b = int(hashlib.md5(lbl.stem.encode()).hexdigest(), 16) % 100
    split = "val" if b < 10 else "test" if b < 20 else None
    if split is None:
        continue
    img = next((D / "images/train" / f"{lbl.stem}{e}" for e in (".jpg", ".jpeg", ".png") if (D / "images/train" / f"{lbl.stem}{e}").is_file()), None)
    if img is None:
        continue
    for sub in ("images", "labels"):
        (D / sub / split).mkdir(parents=True, exist_ok=True)
    img.rename(D / "images" / split / img.name)
    lbl.rename(D / "labels" / split / lbl.name)
    moved[split] += 1
print("moved:", moved)
c = defaultdict(lambda: defaultdict(int)); n = {}
for s in ("train", "val", "test"):
    fs = list((D / "labels" / s).glob("*.txt")); n[s] = len(fs)
    for f in fs:
        for l in f.read_text().splitlines():
            p = l.split()
            if p: c[names[int(p[0])]][s] += 1
print("images:", n)
for k in names: print(f"{k}: train={c[k]['train']} val={c[k]['val']} test={c[k]['test']}")
