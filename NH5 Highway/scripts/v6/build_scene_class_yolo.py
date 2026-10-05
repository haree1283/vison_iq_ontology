#!/usr/bin/env python3
"""YOLO detection set for the user's own 14 scene/event classes (not the technical object
classes): each box is the SAME box precision each existing v6 stage already computed for its
purpose, just relabeled --

  crossing_at_zebra, crossing_without_zebra, walking_on_footpath, walking_on_roadside
      -- the exact person box sort_scene_categories.py's "persons" task already classified
         (candidates_persons.csv box_xyxyn)
  bus, car, truck, bike, auto
      -- every real vehicle-type box already in a 01_vehicles image's own source label
  pothole_road_damage    -- real pothole boxes from 03_potholes/single+multiple (label-decided)
  pothole_rainwater, pothole_construction
      -- the exact pothole crop candidates_potholes.csv classified
  road_construction       -- candidates_construction.csv's whole-image box (05_road_construction rows)
  road_accidents          -- candidates_accidents.csv's box (a damaged_vehicle box, or whole image
                             for the fire/raqabah rows that were only ever scored as whole images)

One image can end up with boxes from several of these (e.g. a car photo that's also a
construction-zone frame) -- all merged into one label file per image, image copied once.

Usage:
  python scripts/v6/build_scene_class_yolo.py
"""
import csv
import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path

import cv2

from build_v6_dataset import label_for

AUGMENT_BELOW = 1000  # a class under this real count gets 3x augmented copies (mirror; the
                       # 2nd copy also cropped 85-95% and re-lit) -- same technique and repeat
                       # cap build_categories.py already uses elsewhere in this project
AUGMENT_MAX_REPEAT = 3
SEED = 20260917

ROOT = Path(__file__).resolve().parents[2]
CATEGORIES = ROOT / "datasets" / "v6" / "categories"
IDX = CATEGORIES / "_index"
OUT = ROOT / "datasets" / "v6" / "training" / "scene_yolo"

SCENE_CLASSES = [
    "crossing_at_zebra", "crossing_without_zebra", "walking_on_footpath", "walking_on_roadside",
    "bus", "car", "truck", "bike", "auto",
    "pothole_road_damage", "pothole_rainwater", "pothole_construction",
    "road_construction", "road_accidents", "license_plate",
]
SID = {name: i for i, name in enumerate(SCENE_CLASSES)}
VEHICLE_V6_TO_SCENE = {4: "bus", 2: "car", 5: "truck", 3: "bike", 8: "auto"}  # v6 class id -> scene class
PERSON_FOLDER_TO_SCENE = {
    "crossing_at_zebra_crossing": "crossing_at_zebra",
    "crossing_without_zebra_crossing": "crossing_without_zebra",
    "walking_on_footpath": "walking_on_footpath",
    "walking_on_roadside": "walking_on_roadside",
}

boxes_by_image = defaultdict(list)  # source_image (repo-relative str) -> [(scene_class, cx,cy,w,h), ...]


def add(source_image, scene_class, cx, cy, w, h):
    boxes_by_image[source_image].append((SID[scene_class], cx, cy, w, h))


def vehicles_from_categories_csv():
    with open(IDX / "categories.csv", newline="") as f:
        for row in csv.DictReader(f):
            if not row["folder"].startswith("01_vehicles/"):
                continue
            img = ROOT / row["source_image"]
            lbl = label_for(img.parent.parent, img.stem)[0]
            if lbl is None:
                continue
            for line in lbl.read_text().splitlines():
                parts = line.split()
                if not parts:
                    continue
                v6 = int(parts[0])
                scene = VEHICLE_V6_TO_SCENE.get(v6)
                if scene:
                    add(row["source_image"], scene, *map(float, parts[1:5]))


def plates_from_categories_csv():
    with open(IDX / "categories.csv", newline="") as f:
        for row in csv.DictReader(f):
            if not row["folder"].startswith("02_number_plates"):
                continue
            img = ROOT / row["source_image"]
            lbl = label_for(img.parent.parent, img.stem)[0]
            if lbl is None:
                continue
            for line in lbl.read_text().splitlines():
                parts = line.split()
                if parts and parts[0] == "7":  # license_plate
                    add(row["source_image"], "license_plate", *map(float, parts[1:5]))


def pothole_road_damage_from_categories_csv():
    with open(IDX / "categories.csv", newline="") as f:
        for row in csv.DictReader(f):
            if row["folder"] not in ("03_potholes/single", "03_potholes/multiple"):
                continue
            img = ROOT / row["source_image"]
            lbl = label_for(img.parent.parent, img.stem)[0]
            if lbl is None:
                continue
            for line in lbl.read_text().splitlines():
                parts = line.split()
                if parts and parts[0] == "6":  # pothole
                    add(row["source_image"], "pothole_road_damage", *map(float, parts[1:5]))


def from_candidates(csv_name, folder_to_scene):
    path = IDX / csv_name
    if not path.is_file():
        print(f"[skip] {csv_name} not found")
        return
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            scene = folder_to_scene(row["folder"])
            if scene is None:
                continue
            x0, y0, x1, y1 = map(float, row["box_xyxyn"].split(","))
            add(row["source_image"], scene, (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0)


def augment(image, variant, rng):
    """A visibly different copy: copy 1 is mirrored; later copies also cropped to 85-95% and
    re-lit (same recipe as build_categories.py's augment(), for the same reason)."""
    out = cv2.flip(image, 1)
    if variant > 1:
        h, w = out.shape[:2]
        scale = rng.uniform(0.85, 0.95)
        ch, cw = int(h * scale), int(w * scale)
        y, x = rng.randint(0, h - ch), rng.randint(0, w - cw)
        out = cv2.resize(out[y:y + ch, x:x + cw], (w, h))
        out = cv2.convertScaleAbs(out, alpha=rng.uniform(0.8, 1.2), beta=rng.uniform(-25, 25))
    return out


def augment_under_represented(class_counts, train_stems):
    """Train-split images holding a box of a class short of AUGMENT_BELOW get up to
    AUGMENT_MAX_REPEAT-1 extra mirrored copies (boxes' x mirrored with them). Val/test are
    never augmented, so evaluation only ever measures real images."""
    weak = {SID[name] for name, n in class_counts.items() if n < AUGMENT_BELOW}
    if not weak:
        return {}
    rng = random.Random(SEED)
    added = defaultdict(int)
    for stem, source_image in train_stems.items():
        boxes = boxes_by_image[source_image]
        if not any(cid in weak for cid, *_ in boxes):
            continue
        img_path = next((OUT / "train" / "images").glob(f"{stem}.*"))
        image = cv2.imread(str(img_path))
        if image is None:
            continue
        for variant in range(1, AUGMENT_MAX_REPEAT):
            flipped = augment(image, variant, rng)
            aug_stem = f"{stem}_aug{variant}"
            cv2.imwrite(str(OUT / "train" / "images" / f"{aug_stem}{img_path.suffix}"), flipped,
                        [int(cv2.IMWRITE_JPEG_QUALITY), 90])
            lines = [f"{cid} {1 - cx:.6f} {cy:.6f} {w:.6f} {h:.6f}" for cid, cx, cy, w, h in boxes]
            (OUT / "train" / "labels" / f"{aug_stem}.txt").write_text("\n".join(lines) + "\n")
            for cid, *_ in boxes:
                added[SCENE_CLASSES[cid]] += 1
    return dict(added)


def main():
    vehicles_from_categories_csv()
    plates_from_categories_csv()
    pothole_road_damage_from_categories_csv()
    from_candidates("candidates_persons.csv", lambda f: PERSON_FOLDER_TO_SCENE.get(f.split("/")[-1]))
    from_candidates("candidates_potholes.csv", lambda f:
                     "pothole_rainwater" if f == "03_potholes/rainwater_filled" else None)
    from_candidates("candidates_construction.csv", lambda f:
                     "road_construction" if f == "05_road_construction" else
                     "pothole_construction" if f == "03_potholes/construction_holes" else None)
    from_candidates("candidates_accidents.csv", lambda f: "road_accidents" if f.startswith("06_road_accidents") else None)

    print(f"images with at least one scene-class box: {len(boxes_by_image)}")

    for d in ("train", "val", "test"):
        (OUT / d / "images").mkdir(parents=True, exist_ok=True)
        (OUT / d / "labels").mkdir(parents=True, exist_ok=True)

    counts = {"train": 0, "val": 0, "test": 0}
    class_counts = defaultdict(int)
    train_stems = {}  # stem -> source_image, for the augmentation pass below
    for source_image, boxes in boxes_by_image.items():
        img = ROOT / source_image
        if not img.is_file():
            continue
        bucket = int(hashlib.md5(source_image.encode()).hexdigest(), 16) % 10
        split = "val" if bucket == 8 else "test" if bucket == 9 else "train"
        stem = img.stem.replace(" ", "_").replace("(", "").replace(")", "")
        dest_img = OUT / split / "images" / f"{stem}{img.suffix.lower()}"
        if dest_img.exists():
            continue
        dest_img.write_bytes(img.read_bytes())
        lines = [f"{cid} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}" for cid, cx, cy, w, h in boxes]
        (OUT / split / "labels" / f"{stem}.txt").write_text("\n".join(lines) + "\n")
        counts[split] += 1
        for cid, *_ in boxes:
            class_counts[SCENE_CLASSES[cid]] += 1
        if split == "train":
            train_stems[stem] = source_image

    print("images per split (real only):", counts)
    print("boxes per class (real only):", dict(class_counts))

    added = augment_under_represented(class_counts, train_stems)
    if added:
        print(f"augmented (train only, classes under {AUGMENT_BELOW}):", added)
        for name, n in added.items():
            class_counts[name] += n

    (OUT / "data.yaml").write_text(
        "train: train/images\nval: val/images\ntest: test/images\n"
        f"nc: {len(SCENE_CLASSES)}\nnames: {SCENE_CLASSES}\n"
    )
    print("boxes per class (final, incl. augmented):", dict(class_counts))
    (OUT / "build_report.json").write_text(json.dumps(
        {"images": counts, "boxes_real": {k: v - added.get(k, 0) for k, v in class_counts.items()},
         "boxes_augmented": added, "boxes_final": dict(class_counts)}, indent=2))


if __name__ == "__main__":
    main()
