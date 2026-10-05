#!/usr/bin/env python3
"""Ensure the expanded dataset skeleton at `datasets/processed_v2` exists and
its data.yaml carries the detector classes: the original 9 plus
- road_construction
- accident_scene

wrong_side_driving and lane_change are NOT detector classes -- a single frame
can't show direction of travel or a lane crossing, so they're produced by the
tracking-based event rules instead of the YOLO model.

Non-destructive: never deletes or copies images. The images/labels themselves
are (re)built by 5_unify_and_split.py.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "datasets" / "processed_v2"

BASE_CLASSES = [
    "person",
    "bicycle",
    "car",
    "motorcycle",
    "bus",
    "truck",
    "pothole",
    "license_plate",
    "auto",
]

NEW_CLASSES = [
    "road_construction",
    "accident_scene",
]

CLASS_NAMES = BASE_CLASSES + NEW_CLASSES
SPLITS = ["train", "val", "test"]


def ensure_split_dirs():
    for split in SPLITS:
        (TARGET / "images" / split).mkdir(parents=True, exist_ok=True)
        (TARGET / "labels" / split).mkdir(parents=True, exist_ok=True)


def write_yaml():
    yaml_text = (
        "path: " + str(TARGET) + "\n"
        "train: images/train\n"
        "val: images/val\n"
        "test: images/test\n"
        f"nc: {len(CLASS_NAMES)}\n"
        f"names: {CLASS_NAMES}\n"
    )
    (TARGET / "data.yaml").write_text(yaml_text, encoding="utf-8")


def main():
    ensure_split_dirs()
    write_yaml()
    print(f"Dataset skeleton ready at: {TARGET}")
    print(f"Classes: {CLASS_NAMES}")


if __name__ == "__main__":
    main()
