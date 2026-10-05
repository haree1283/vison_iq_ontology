#!/usr/bin/env python3
"""Pool all prepared YOLO image/label pairs (coco_yolo, pothole_yolo, license_plate_yolo)
and split into train/val/test (80/10/10) under datasets/processed_v2/.
"""
import random
import shutil
from pathlib import Path

RAW = Path(__file__).resolve().parent.parent / "datasets" / "raw"
PROCESSED = Path(__file__).resolve().parent.parent / "datasets" / "processed_v2"

POOLS = [
    "coco_yolo",
    "pothole_yolo",
    "license_plate_yolo",
    "heterotraffic_yolo",
    "road_damage_yolo",
    "crowdhuman_yolo",
    "potholes_wf_yolo",
    "ccpd_yolo",
    "real_footage_yolo",
    "real_corrections_yolo",
]
SPLIT_RATIOS = {"train": 0.8, "val": 0.1, "test": 0.1}
SEED = 42

CLASS_NAMES = [
    "person",
    "bicycle",
    "car",
    "motorcycle",
    "bus",
    "truck",
    "pothole",
    "license_plate",
    "auto",
    "road_construction",
    "accident_scene",
]


def gather_pairs():
    pairs = []
    for pool in POOLS:
        img_dir = RAW / pool / "images"
        lbl_dir = RAW / pool / "labels"
        if not img_dir.exists():
            print(f"skip (missing): {img_dir}")
            continue
        for img_path in sorted(img_dir.iterdir()):
            lbl_path = lbl_dir / (img_path.stem + ".txt")
            if lbl_path.exists():
                pairs.append((img_path, lbl_path))
    return pairs


def main():
    # Every run reshuffles and re-splits the full pool from scratch, so a
    # pair that lands in a different split than last time needs its old
    # copy removed -- otherwise stale copies accumulate across runs and can
    # leave the same image in two splits at once (train/val leakage).
    for split in SPLIT_RATIOS:
        shutil.rmtree(PROCESSED / "images" / split, ignore_errors=True)
        shutil.rmtree(PROCESSED / "labels" / split, ignore_errors=True)
        (PROCESSED / "images" / split).mkdir(parents=True, exist_ok=True)
        (PROCESSED / "labels" / split).mkdir(parents=True, exist_ok=True)

    pairs = gather_pairs()
    print(f"Total image/label pairs: {len(pairs)}")

    random.seed(SEED)
    random.shuffle(pairs)

    n = len(pairs)
    n_train = int(n * SPLIT_RATIOS["train"])
    n_val = int(n * SPLIT_RATIOS["val"])

    splits = {
        "train": pairs[:n_train],
        "val": pairs[n_train:n_train + n_val],
        "test": pairs[n_train + n_val:],
    }

    for split, split_pairs in splits.items():
        for img_path, lbl_path in split_pairs:
            shutil.copy(img_path, PROCESSED / "images" / split / img_path.name)
            shutil.copy(lbl_path, PROCESSED / "labels" / split / lbl_path.name)
        print(f"{split}: {len(split_pairs)} images")

    data_yaml = PROCESSED / "data.yaml"
    data_yaml.write_text(
        "path: " + str(PROCESSED) + "\n"
        "train: images/train\n"
        "val: images/val\n"
        "test: images/test\n"
        f"nc: {len(CLASS_NAMES)}\n"
        f"names: {CLASS_NAMES}\n"
    )
    print(f"Wrote {data_yaml}")


if __name__ == "__main__":
    main()
