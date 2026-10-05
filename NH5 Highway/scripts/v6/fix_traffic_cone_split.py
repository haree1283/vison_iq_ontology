#!/usr/bin/env python3
"""traffic_cone (and barricade, wherever present) currently sits entirely in the train split --
it was added via merge_new_sources_into_pv2.py, which always writes to images/train. That means
there's no held-out signal for how well the model actually learns it. Move a held-out slice of
cone-containing train images into val and test (deterministic by filename hash, so it's stable
across reruns) so future validation actually measures this class.

Usage:
  python scripts/v6/fix_traffic_cone_split.py
"""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "datasets" / "processed_v2_plus_v6"
CONE_ID = 11
VAL_FRACTION = 0.1
TEST_FRACTION = 0.1


def main():
    img_dir, lbl_dir = D / "images" / "train", D / "labels" / "train"
    moved = {"val": 0, "test": 0}
    for lbl in list(lbl_dir.glob("*.txt")):
        lines = lbl.read_text().splitlines()
        if not any(line.split() and int(line.split()[0]) == CONE_ID for line in lines):
            continue
        img_path = next((p for ext in (".jpg", ".jpeg", ".png")
                          if (p := img_dir / f"{lbl.stem}{ext}").is_file()), None)
        if img_path is None:
            continue
        bucket = int(hashlib.md5(lbl.stem.encode()).hexdigest(), 16) % 100
        split = "val" if bucket < VAL_FRACTION * 100 else \
                "test" if bucket < (VAL_FRACTION + TEST_FRACTION) * 100 else None
        if split is None:
            continue
        dest_img_dir, dest_lbl_dir = D / "images" / split, D / "labels" / split
        dest_img_dir.mkdir(parents=True, exist_ok=True)
        dest_lbl_dir.mkdir(parents=True, exist_ok=True)
        img_path.rename(dest_img_dir / img_path.name)
        lbl.rename(dest_lbl_dir / lbl.name)
        moved[split] += 1

    print("moved to val:", moved["val"])
    print("moved to test:", moved["test"])


if __name__ == "__main__":
    main()
