#!/usr/bin/env python3
"""Build a YOLO training set directly from the curated datasets/v6/categories/ selection
(not the generic balanced training/detector_yolo/ set): every image a human would find by
browsing categories/ -- across every folder, both the label-decided ones (categories.csv)
and the SigLIP-picked ones (_index/candidates_*.csv) -- pulled in with its FULL original
label (every box, not just the one class its category folder represents). This naturally
gives better coverage of classes that only ever appear alongside another one (traffic_cone
and barricade in 05_road_construction images, damaged_vehicle in 06_road_accidents,
zebra_crossing in 04_persons/crossing_at_zebra_crossing) than balancing by primary class alone.

Same source image listed under several category folders (e.g. a car photo that also has a
plate) is included once, with its one real label file -- no duplication.

Usage:
  python scripts/v6/build_yolo_from_categories.py
"""
import csv
import hashlib
import json
from pathlib import Path

from build_v6_dataset import label_for as _label_for

ROOT = Path(__file__).resolve().parents[2]
CATEGORIES = ROOT / "datasets" / "v6" / "categories"
OUT = ROOT / "datasets" / "v6" / "training" / "categories_yolo"
INDEX_FILES = ["categories.csv", "candidates_persons.csv", "candidates_construction.csv",
               "candidates_accidents.csv", "candidates_potholes.csv"]
CLASSES = ["person", "bicycle", "car", "motorcycle", "bus", "truck", "pothole", "license_plate",
           "auto", "damaged_vehicle", "traffic_cone", "barricade", "zebra_crossing"]


def label_for(source_image):
    """The real, full label file for a source image -- reviewed labels win (build_v6_dataset's
    own helper, so this matches the convention the rest of v6 already uses)."""
    img = ROOT / source_image
    lbl, _ = _label_for(img.parent.parent, img.stem)
    return lbl


def main():
    unique = {}  # source_image -> Path (first image file found for it, any extension)
    for name in INDEX_FILES:
        path = CATEGORIES / "_index" / name
        if not path.is_file():
            print(f"[skip] {name} not found")
            continue
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                unique.setdefault(row["source_image"], row["source_image"])
    print(f"unique source images across all category folders: {len(unique)}")

    out_img_dirs = {s: OUT / s / "images" for s in ("train", "val", "test")}
    out_lbl_dirs = {s: OUT / s / "labels" for s in ("train", "val", "test")}
    for d in list(out_img_dirs.values()) + list(out_lbl_dirs.values()):
        d.mkdir(parents=True, exist_ok=True)

    counts = {"train": 0, "val": 0, "test": 0, "no_label": 0}
    for source_image in unique:
        img = ROOT / source_image
        if not img.is_file():
            continue
        lbl = label_for(source_image)
        lines = lbl.read_text().splitlines() if lbl else []
        if lbl is None:
            counts["no_label"] += 1

        bucket = int(hashlib.md5(source_image.encode()).hexdigest(), 16) % 10
        split = "val" if bucket == 8 else "test" if bucket == 9 else "train"
        stem = img.stem.replace(" ", "_").replace("(", "").replace(")", "")
        dest_img = out_img_dirs[split] / f"{stem}{img.suffix.lower()}"
        if dest_img.exists():
            continue  # two source images share a stem after sanitizing -- keep the first
        try:
            dest_img.write_bytes(img.read_bytes())
        except OSError:
            continue
        (out_lbl_dirs[split] / f"{stem}.txt").write_text("\n".join(lines) + ("\n" if lines else ""))
        counts[split] += 1

    (OUT / "data.yaml").write_text(
        "train: train/images\nval: val/images\ntest: test/images\n"
        f"nc: {len(CLASSES)}\nnames: {CLASSES}\n"
    )
    print(counts)
    (OUT / "build_report.json").write_text(json.dumps(counts, indent=2))


if __name__ == "__main__":
    main()
