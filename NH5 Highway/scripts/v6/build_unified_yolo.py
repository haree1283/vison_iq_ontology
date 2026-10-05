#!/usr/bin/env python3
"""Merge categories_yolo (13 technical object classes, full multi-box labels) and scene_yolo
(the user's 15 scene/event classes) into ONE unified training set -- NOT a concatenation
(their class ids mean different things in each set and can't just be mixed), a real merge:

  - shared real objects (bicycle, car, motorcycle, bus, truck, auto, license_plate) -> one class
  - generic "person" boxes get replaced by the specific behavior class wherever
    sort_scene_categories.py's persons task already classified that exact box (crossing_at_zebra,
    crossing_without_zebra, walking_on_footpath, walking_on_roadside); a person box with no such
    classification keeps the generic "person" class
  - generic "pothole" boxes are replaced the same way by pothole_road_damage / _rainwater /
    _construction wherever known
  - damaged_vehicle (a technical object box) and road_accidents (a scene/whole-frame box) are the
    same real concept -- one class, using the tighter box when both exist for an image
  - traffic_cone, barricade, zebra_crossing, road_construction -- only ever came from the
    technical/scene sets respectively, kept as-is

Train-only 3x augmentation is re-applied to whatever ends up under AUGMENT_BELOW in the merged
counts (same recipe as build_scene_class_yolo.py).

Usage:
  python scripts/v6/build_unified_yolo.py
"""
import csv
import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path

import cv2

from build_v6_dataset import label_for
from classes import CLASS_IDS

ROOT = Path(__file__).resolve().parents[2]
CATEGORIES = ROOT / "datasets" / "v6" / "categories"
IDX = CATEGORIES / "_index"
OUT = ROOT / "datasets" / "v6" / "training" / "unified_yolo"
AUGMENT_BELOW = 1000
AUGMENT_MAX_REPEAT = 3
SEED = 20260917

UNIFIED_CLASSES = [
    "person", "crossing_at_zebra", "crossing_without_zebra", "walking_on_footpath", "walking_on_roadside",
    "bicycle", "car", "motorcycle", "bus", "truck", "auto",
    "pothole",
    "license_plate", "road_accidents", "traffic_cone", "barricade", "zebra_crossing", "road_construction",
]
UID = {name: i for i, name in enumerate(UNIFIED_CLASSES)}

# v6 technical class id -> unified class name (for boxes with no more specific scene label)
V6_TO_UNIFIED = {
    CLASS_IDS["person"]: "person", CLASS_IDS["bicycle"]: "bicycle", CLASS_IDS["car"]: "car",
    CLASS_IDS["motorcycle"]: "motorcycle", CLASS_IDS["bus"]: "bus", CLASS_IDS["truck"]: "truck",
    CLASS_IDS["auto"]: "auto", CLASS_IDS["license_plate"]: "license_plate",
    CLASS_IDS["damaged_vehicle"]: "road_accidents", CLASS_IDS["traffic_cone"]: "traffic_cone",
    CLASS_IDS["barricade"]: "barricade", CLASS_IDS["zebra_crossing"]: "zebra_crossing",
    # pothole (id 6) is intentionally absent: every real pothole box is already covered by
    # 03_potholes/single+multiple -> pothole_road_damage below, so it's never left generic
}
PERSON_FOLDER_TO_SCENE = {
    "crossing_at_zebra_crossing": "crossing_at_zebra", "crossing_without_zebra_crossing": "crossing_without_zebra",
    "walking_on_footpath": "walking_on_footpath", "walking_on_roadside": "walking_on_roadside",
}

boxes_by_image = defaultdict(list)
# (source_image, rounded box) -> True once a specific label has claimed that exact box, so the
# generic pass doesn't ALSO add a duplicate generic box on top of it
claimed = set()


def add(source_image, scene_class, cx, cy, w, h, mark_claimed=False):
    key = (source_image, round(cx, 4), round(cy, 4), round(w, 4), round(h, 4))
    boxes_by_image[source_image].append((UID[scene_class], cx, cy, w, h))
    if mark_claimed:
        claimed.add(key)


def specific_person_and_pothole_boxes():
    """The exact boxes sort_scene_categories.py already classified -- claimed first, so the
    generic pass below skips them instead of double-boxing the same object."""
    for csv_name, folder_to_scene in (
        ("candidates_persons.csv", lambda f: PERSON_FOLDER_TO_SCENE.get(f.split("/")[-1])),
        ("candidates_potholes.csv", lambda f: "pothole" if f == "03_potholes/rainwater_filled" else None),
        ("candidates_construction.csv", lambda f:
         "road_construction" if f == "05_road_construction" else
         "pothole" if f == "03_potholes/construction_holes" else None),
    ):
        path = IDX / csv_name
        if not path.is_file():
            continue
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                scene = folder_to_scene(row["folder"])
                if scene is None:
                    continue
                x0, y0, x1, y1 = map(float, row["box_xyxyn"].split(","))
                # claim it: person-behavior classes can collide with the generic technical person
                # pass, and pothole (rainwater/construction subtypes) can collide with a direct-scan
                # source (sample_potholes_v2) that also treats the same box as generic pothole
                add(row["source_image"], scene, (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0,
                    mark_claimed=(scene != "road_construction"))


def pothole_road_damage():
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
                if parts and int(parts[0]) == CLASS_IDS["pothole"]:
                    cx, cy, w, h = map(float, parts[1:5])
                    add(row["source_image"], "pothole", cx, cy, w, h, mark_claimed=True)


def road_accidents_whole_frame():
    path = IDX / "candidates_accidents.csv"
    if not path.is_file():
        return
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            if not row["folder"].startswith("06_road_accidents"):
                continue
            x0, y0, x1, y1 = map(float, row["box_xyxyn"].split(","))
            cx, cy, w, h = (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0
            key = (row["source_image"], round(cx, 4), round(cy, 4), round(w, 4), round(h, 4))
            if key in claimed:
                continue  # a damaged_vehicle box for this exact region already covers it
            add(row["source_image"], "road_accidents", cx, cy, w, h)


def direct_source_scan(source_name, v6_class, scene_class):
    """A source that isn't part of the reviewed categories/ tree (dropped straight in for one
    class) needs its own direct pass instead of going through categories.csv."""
    base = ROOT / "datasets" / "v6" / "sources" / source_name
    if not base.is_dir():
        return
    for split_dir in sorted(p for p in base.iterdir() if (p / "images").is_dir()):
        for lbl in sorted((split_dir / "labels").glob("*.txt")):
            img = next((p for ext in (".jpg", ".jpeg", ".png")
                       if (p := split_dir / "images" / f"{lbl.stem}{ext}").is_file()), None)
            if img is None:
                continue
            source_image = str(img.relative_to(ROOT))
            for line in lbl.read_text().splitlines():
                parts = line.split()
                if parts and int(parts[0]) == v6_class:
                    cx, cy, w, h = map(float, parts[1:5])
                    add(source_image, scene_class, cx, cy, w, h)


def sample_barricades():
    direct_source_scan("sample_barricades", CLASS_IDS["barricade"], "barricade")


def sample_zebra_crossing():
    direct_source_scan("sample_zebra_crossing", CLASS_IDS["zebra_crossing"], "zebra_crossing")


def sample_potholes_v2():
    # generic pothole boxes -> the single "pothole" class, unless a specific box was already
    # claimed by the SigLIP subtyping pass (run separately, then this source also appears in
    # categories.csv candidates_*.csv)
    direct_source_scan("sample_potholes_v2", CLASS_IDS["pothole"], "pothole")


def sample_zebra_crossing_v2():
    # a second user-collected export, class "crosswalk" -> the same zebra_crossing marking class
    # (it only has crosswalk boxes, no person boxes, so it can't feed crossing_at_zebra)
    direct_source_scan("sample_zebra_crossing_v2", CLASS_IDS["zebra_crossing"], "zebra_crossing")


def every_technical_box():
    """Every remaining real box across ALL sources (via categories.csv, which only lists images
    already in the human-reviewable tree) -- generic person/vehicles/plate/cone/barricade/zebra,
    skipping anything a specific pass above already claimed."""
    seen_images = set()
    with open(IDX / "categories.csv", newline="") as f:
        for row in csv.DictReader(f):
            if row["source_image"] in seen_images:
                continue
            seen_images.add(row["source_image"])
            img = ROOT / row["source_image"]
            lbl = label_for(img.parent.parent, img.stem)[0]
            if lbl is None:
                continue
            for line in lbl.read_text().splitlines():
                parts = line.split()
                if not parts:
                    continue
                v6 = int(parts[0])
                unified = V6_TO_UNIFIED.get(v6)
                if unified is None:
                    continue
                cx, cy, w, h = map(float, parts[1:5])
                key = (row["source_image"], round(cx, 4), round(cy, 4), round(w, 4), round(h, 4))
                if key in claimed:
                    continue
                add(row["source_image"], unified, cx, cy, w, h)


def augment(image, variant, rng):
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
    weak = {UID[name] for name, n in class_counts.items() if n < AUGMENT_BELOW}
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
                added[UNIFIED_CLASSES[cid]] += 1
    return dict(added)


def main():
    specific_person_and_pothole_boxes()
    pothole_road_damage()
    road_accidents_whole_frame()
    sample_barricades()
    sample_zebra_crossing()
    sample_potholes_v2()
    sample_zebra_crossing_v2()
    every_technical_box()

    print(f"images with at least one box: {len(boxes_by_image)}")
    for d in ("train", "val", "test"):
        (OUT / d / "images").mkdir(parents=True, exist_ok=True)
        (OUT / d / "labels").mkdir(parents=True, exist_ok=True)

    counts = {"train": 0, "val": 0, "test": 0}
    class_counts = defaultdict(int)
    train_stems = {}
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
            class_counts[UNIFIED_CLASSES[cid]] += 1
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
        f"nc: {len(UNIFIED_CLASSES)}\nnames: {UNIFIED_CLASSES}\n"
    )
    print("boxes per class (final):", dict(class_counts))
    (OUT / "build_report.json").write_text(json.dumps(
        {"images": counts, "boxes_final": dict(class_counts)}, indent=2))


if __name__ == "__main__":
    main()
