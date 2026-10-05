#!/usr/bin/env python3
"""Convert the CMU ROADWork dataset (anuragxel/roadwork-dataset on HuggingFace -- 5,318 real
human-annotated work-zone images, COCO format, 17 categories) into a v6 source.

Cone/Barricade map directly onto v6's existing traffic_cone/barricade technical classes. Everything
else that represents active roadwork (Worker, Work Vehicle, Work Equipment, Drum, Fence, Barrier,
Vertical Panel, Tubular Marker, Arrow Board, Other Roadwork Objects, Temporary Traffic Control
Sign/Message Board) is stored under a carrier id (damaged_vehicle, same convention as
jcb_excavator) that build_unified_yolo.py remaps to the "road_construction" scene class. Police
Officer/Vehicle and Bike Lane are dropped -- no v6 equivalent, not roadwork-specific.

Usage:
  python scripts/v6/convert_roadwork_cmu.py
"""
import json
from collections import Counter
from pathlib import Path

from classes import CLASS_IDS

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "datasets" / "v6" / "raw" / "roadwork_cmu"
ANNOTATIONS = RAW / "annotations_extracted" / "annotations" / "instances_train_gps_split.json"
IMAGES_DIR = RAW / "images_extracted" / "images"
OUT = ROOT / "datasets" / "v6" / "sources" / "roadwork_cmu" / "train"

# category name -> v6 class name ("road_construction" is a carrier -> remapped later in
# build_unified_yolo.py, exactly like jcb_excavator's damaged_vehicle carrier)
CATEGORY_MAP = {
    "Cone": "traffic_cone",
    "Barricade": "barricade",
    "Worker": "road_construction", "Work Vehicle": "road_construction",
    "Work Equipment": "road_construction", "Drum": "road_construction",
    "Fence": "road_construction", "Barrier": "road_construction",
    "Vertical Panel": "road_construction", "Tubular Marker": "road_construction",
    "Arrow Board": "road_construction", "Other Roadwork Objects": "road_construction",
    "Temporary Traffic Control Sign": "road_construction",
    "Temporary Traffic Control Message Board": "road_construction",
    # dropped: Police Officer, Police Vehicle, Bike Lane
}
CARRIER_ID = CLASS_IDS["damaged_vehicle"]  # stands in for "road_construction" until remapped


def main():
    (OUT / "images").mkdir(parents=True, exist_ok=True)
    (OUT / "labels").mkdir(parents=True, exist_ok=True)

    data = json.loads(ANNOTATIONS.read_text())
    cat_id_to_name = {c["id"]: c["name"] for c in data["categories"]}
    images_by_id = {im["id"]: im for im in data["images"]}

    anns_by_image = {}
    for ann in data["annotations"]:
        anns_by_image.setdefault(ann["image_id"], []).append(ann)

    box_counts = Counter()
    images_written = 0
    for image_id, anns in anns_by_image.items():
        img_meta = images_by_id[image_id]
        img_path = IMAGES_DIR / img_meta["file_name"]
        if not img_path.is_file():
            continue
        w, h = img_meta["width"], img_meta["height"]

        lines = []
        for ann in anns:
            cat_name = cat_id_to_name[ann["category_id"]]
            v6_name = CATEGORY_MAP.get(cat_name)
            if v6_name is None:
                continue
            x, y, bw, bh = ann["bbox"]  # COCO bbox: [x_min, y_min, width, height], absolute px
            cx, cy = (x + bw / 2) / w, (y + bh / 2) / h
            nw, nh = bw / w, bh / h
            cid = CARRIER_ID if v6_name == "road_construction" else CLASS_IDS[v6_name]
            lines.append(f"{cid} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")
            box_counts[v6_name] += 1
        if not lines:
            continue

        stem = f"roadworkcmu_{Path(img_meta['file_name']).stem}"
        (OUT / "images" / f"{stem}.jpg").write_bytes(img_path.read_bytes())
        (OUT / "labels" / f"{stem}.txt").write_text("\n".join(lines) + "\n")
        images_written += 1

    print(f"images written: {images_written}")
    print("boxes per v6 class:", dict(box_counts))


if __name__ == "__main__":
    main()
