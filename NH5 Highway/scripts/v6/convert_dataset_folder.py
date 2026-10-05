#!/usr/bin/env python3
"""One-off: convert the Roboflow exports the user dropped in datasets/v6/dataset/ (organized
by the user into folders matching our own category names) into proper v6 sources.

Skips two "road accidents" exports that are exact duplicates of sources already converted
this project (same Roboflow workspace/project, confirmed by data.yaml's roboflow.url):
hackcimat/accidents-slk5t (-> accidents_hackcimat) and ai-challenge-sbskb/accidents-amxaw
(-> accidents_ai_challenge).

Several "road construction" exports have corrupted class lists (Roboflow platform
description text where real class names should be -- a common export bug when a project
has just one real class); the images themselves are still real construction photos, so
they're registered as label-less sources for sort_scene_categories.py's whole-image
"construction" SigLIP task, not for box-based conversion.

Usage:
  python scripts/v6/convert_dataset_folder.py
"""
import json
import re
from collections import Counter
from pathlib import Path

import yaml

from classes import CLASS_IDS
from convert_yolo_sources import _roboflow_originals, convert_label

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "datasets" / "v6" / "dataset"
OUT = ROOT / "datasets" / "v6" / "sources"

# name -> (folder, {class index: v6 name or None})
BOXED_SOURCES = {
    "dataset_vehicles_coco": (D / "01_vehicles" / "Vehicles-coco.v2i.yolov8",
                              {0: "bus", 1: "car", 2: "motorcycle", 3: "truck"}),
    "dataset_auto_rickshaw": (D / "01_vehicles" / "Auto-Rickshaw.v3-augmented-images-4514-3x.yolov8",
                              {0: "auto"}),
    "dataset_cycle": (D / "01_vehicles" / "Cycle Detection.v1i.yolov8", {0: "bicycle"}),
    "dataset_pothole_road": (D / "pothole" / "Road.v1i.yolov8", {0: None, 1: "pothole", 2: None}),
    "dataset_pothole_18": (D / "pothole" / "pothole.v18i.yolov8", {0: "pothole"}),
    "dataset_pothole_det7": (D / "pothole" / "pothole detection.v7i.yolov8", {0: "pothole"}),
    "dataset_plates_license3": (D / "number plate" / "License Plate Detection.v3i.yolov8",
                                {0: None, 1: "license_plate"}),
    "dataset_plates_bike": (D / "number plate" / "bike number plate.v1i.yolov8",
                            {0: None, 1: "license_plate"}),
    "dataset_plates_generic": (D / "number plate" / "Number Plates.v1i.yolov8", {0: "license_plate"}),
    "dataset_plates_experiment": (D / "number plate" / "experiment-plates.v1i.yolov8", {0: "license_plate"}),
    "dataset_plates_auto": (D / "number plate" / "AUTO Number plate.v3i.yolov8", {0: "license_plate"}),
    "dataset_road_accident_v1": (D / "road accidents" / "Road Accident.v1-1.yolov8", {0: "damaged_vehicle"}),
}

# name -> folder; images only, no usable class labels -- feeds sort_scene_categories.py's
# whole-image "construction" SigLIP task instead of box-based conversion
IMAGE_ONLY_SOURCES = {
    "dataset_construction_a": D / "road construction" / "construction.v1i.yolov8",
    "dataset_construction_b": D / "road construction" / "construction.v1i.yolov8 (1)",
    "dataset_construction_c": D / "road construction" / "construction.v1i.yolov8 (2)",
    "dataset_construction_d": D / "road construction" / "Road-Construction.v4i.yolov8",
}

SKIPPED_DUPLICATES = [
    D / "road accidents" / "Accidents.v1i.yolov8 (1)",   # == accidents_hackcimat
    D / "road accidents" / "Accidents.v1i.yolov8",        # == accidents_ai_challenge
]

IMAGE_EXTS = (".jpg", ".jpeg", ".png")


def convert_boxed(name, folder, class_map):
    if not folder.is_dir():
        print(f"[{name}] {folder} not found -- skipped")
        return
    pairs = list(_roboflow_originals(folder))  # dedupes augmented copies back to one per original
    out_root = OUT / name
    stats = Counter()
    id_to_name = {v: k for k, v in CLASS_IDS.items()}
    for split, img, lbl, _ in pairs:
        split = "val" if split == "valid" else split
        lines, dropped = convert_label(lbl, class_map)
        if not lines:
            stats[split + "_skipped_no_box"] += 1
            continue
        out_img, out_lbl = out_root / split / "images", out_root / split / "labels"
        out_img.mkdir(parents=True, exist_ok=True)
        out_lbl.mkdir(parents=True, exist_ok=True)
        stem = f"{name}_{img.stem}"
        (out_img / f"{stem}{img.suffix.lower()}").write_bytes(img.read_bytes())
        (out_lbl / f"{stem}.txt").write_text("\n".join(lines) + "\n")
        stats[split + "_images"] += 1
        for l in lines:
            stats[id_to_name[int(l.split()[0])]] += 1
    print(f"[{name}] {dict(stats)}")


def convert_image_only(name, folder):
    if not folder.is_dir():
        print(f"[{name}] {folder} not found -- skipped")
        return
    out_img, out_lbl = OUT / name / "train" / "images", OUT / name / "train" / "labels"
    out_img.mkdir(parents=True, exist_ok=True)
    out_lbl.mkdir(parents=True, exist_ok=True)
    n = 0
    for split_dir in ("train", "valid", "test"):
        img_dir = folder / split_dir / "images"
        if not img_dir.is_dir():
            continue
        for img in sorted(p for p in img_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS):
            original = re.sub(r"\.rf\.[0-9a-f]+$", "", img.stem)
            stem = f"{name}_{original}"
            dest = out_img / f"{stem}{img.suffix.lower()}"
            if dest.is_file():
                continue  # same original photo already copied from another split
            dest.write_bytes(img.read_bytes())
            (out_lbl / f"{stem}.txt").touch()
            n += 1
    print(f"[{name}] {n} images (label-less, for whole-image scene scoring)")


def main():
    for path in SKIPPED_DUPLICATES:
        print(f"[skip] {path.name}: duplicate of an already-converted source")
    for name, (folder, class_map) in BOXED_SOURCES.items():
        convert_boxed(name, folder, class_map)
    for name, folder in IMAGE_ONLY_SOURCES.items():
        convert_image_only(name, folder)


if __name__ == "__main__":
    main()
