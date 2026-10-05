#!/usr/bin/env python3
"""Gather images that may show a burning vehicle into datasets/v6/sources/fire_images/train/images/,
so sort_scene_categories.py accidents can score them for categories/06_road_accidents/fire.

Sources already on disk:
- the fire class of the hackcimat / ai-challenge exports: images conversion dropped because they have a
  fire box but no crash box (most are wildfires and burning buildings -- SigLIP sorts the vehicles out)
- the Fire / ROAD VEHICLE FIRE folders of the two RAD downloads (Pakistan CCTV)

Labels are empty on purpose: these are candidates for the browsable folder, not detector training data.
Re-runnable; images are hard links.
"""
import os
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "datasets" / "v6" / "raw"
OUT = ROOT / "datasets" / "v6" / "sources" / "fire_images" / "train"
FIRE_CLASS = "1"  # hackcimat / ai-challenge: class 1 = fire
EXPORTS = [RAW / "user_accidents" / "hackcimat_accidents_fire", RAW / "user_accidents" / "ai_challenge_accidents"]
RAD_DIRS = [RAW / "kaggle" / "road-anomaly-dataset", RAW / "kaggle" / "road-anomaly-detection"]


def link(src, name):
    dst = OUT / "images" / name
    if not dst.exists():
        try:
            os.link(src, dst)
        except OSError:
            shutil.copy2(src, dst)
    (OUT / "labels" / f"{Path(name).stem}.txt").write_text("")


def main():
    (OUT / "images").mkdir(parents=True, exist_ok=True)
    (OUT / "labels").mkdir(parents=True, exist_ok=True)
    kept = {}
    for root in EXPORTS:
        for lbl in root.rglob("labels/*.txt"):
            ids = {r.split()[0] for r in lbl.read_text(errors="replace").splitlines() if r.split()}
            if FIRE_CLASS not in ids:
                continue
            img = next((p for p in (lbl.parent.parent / "images").glob(lbl.stem + ".*")), None)
            original = re.sub(r"\.rf\.[0-9a-f]+$", "", lbl.stem)  # keep one Roboflow copy per original
            if img and original not in kept:
                kept[original] = True
                link(img, f"fire_{root.name[:12]}_{img.name}")
    n_export = len(kept)

    n_rad = 0
    for root in RAD_DIRS:
        for img in root.rglob("*"):
            if img.suffix.lower() in (".jpg", ".jpeg", ".png") and "fire" in img.parent.name.lower():
                link(img, f"fire_rad_{img.parent.parent.name[:8]}_{img.name}")
                n_rad += 1
    print(f"fire candidates: {n_export} from the accident exports, {n_rad} from RAD -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
