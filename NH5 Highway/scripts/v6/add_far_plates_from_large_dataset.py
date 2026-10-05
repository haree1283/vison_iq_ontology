#!/usr/bin/env python3
"""Add DISTANT-plate real scenes from Kaggle 'large-license-plate-dataset' (Open Images street scenes,
single class 0 = plate -> pv2 id 7) into datasets/processed_v2_plus_v6_v3. Keeps images whose LARGEST plate
box is small (h<0.05, w<0.15), capped at CAP; ~10% -> val, ~10% -> test by filename md5. Non-Indian plates."""
import hashlib, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "datasets/v6/raw/large_plates/x"
DST = ROOT / "datasets/processed_v2_plus_v6_v3"
CAP = 3000
n = {"train": 0, "val": 0, "test": 0}
for sp in ("train", "val", "test"):
    for lbl in sorted((SRC / "labels" / sp).glob("*.txt")):
        if sum(n.values()) >= CAP: break
        rows = [l.split() for l in lbl.read_text().splitlines() if l.split()]
        if not rows or not all(float(r[4]) < 0.05 and float(r[3]) < 0.15 for r in rows): continue
        img = next((SRC / "images" / sp / f"{lbl.stem}{e}" for e in (".jpg", ".jpeg", ".png") if (SRC / "images" / sp / f"{lbl.stem}{e}").is_file()), None)
        if img is None or img.stat().st_size < 20_000 or img.stat().st_size > 3_000_000: continue
        b = int(hashlib.md5(lbl.stem.encode()).hexdigest(), 16) % 100
        out = "val" if b < 10 else "test" if b < 20 else "train"
        shutil.copy2(img, DST / "images" / out / f"farplate_{lbl.stem}{img.suffix}")
        (DST / "labels" / out / f"farplate_{lbl.stem}.txt").write_text("\n".join("7 " + " ".join(r[1:5]) for r in rows) + "\n")
        n[out] += 1
print("added:", n)
