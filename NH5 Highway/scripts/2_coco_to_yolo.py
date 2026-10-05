#!/usr/bin/env python3
"""Filter COCO val2017 to person/vehicle classes and convert to YOLO txt labels.

Only images containing at least one target-class annotation are kept.
Output: datasets/raw/coco_yolo/images/*.jpg, datasets/raw/coco_yolo/labels/*.txt
"""
import json
import shutil
from pathlib import Path

RAW = Path(__file__).resolve().parent.parent / "datasets" / "raw"
COCO_DIR = RAW / "coco"
IMAGES_DIR = COCO_DIR / "val2017"
ANN_FILE = COCO_DIR / "annotations" / "instances_val2017.json"

OUT_DIR = RAW / "coco_yolo"
OUT_IMAGES = OUT_DIR / "images"
OUT_LABELS = OUT_DIR / "labels"

# Unified class id mapping (must match final data.yaml)
TARGET_CLASSES = {
    "person": 0,
    "bicycle": 1,
    "car": 2,
    "motorcycle": 3,
    "bus": 4,
    "truck": 5,
}


def main():
    # full clean regeneration each run -- otherwise a shrinking MAX_IMAGES/cap
    # (or any other change that reduces the kept count) leaves stale orphan
    # files behind from the previous, larger run
    shutil.rmtree(OUT_DIR, ignore_errors=True)
    OUT_IMAGES.mkdir(parents=True, exist_ok=True)
    OUT_LABELS.mkdir(parents=True, exist_ok=True)

    with open(ANN_FILE) as f:
        coco = json.load(f)

    cat_id_to_name = {c["id"]: c["name"] for c in coco["categories"]}
    target_cat_ids = {cid for cid, name in cat_id_to_name.items() if name in TARGET_CLASSES}

    images_by_id = {img["id"]: img for img in coco["images"]}

    anns_by_image = {}
    for ann in coco["annotations"]:
        if ann["category_id"] not in target_cat_ids:
            continue
        anns_by_image.setdefault(ann["image_id"], []).append(ann)

    kept = 0
    for image_id, anns in anns_by_image.items():
        img_info = images_by_id[image_id]
        w, h = img_info["width"], img_info["height"]
        filename = img_info["file_name"]

        src_img = IMAGES_DIR / filename
        if not src_img.exists():
            continue

        lines = []
        for ann in anns:
            x, y, bw, bh = ann["bbox"]  # COCO: top-left x,y,width,height (absolute px)
            cx = (x + bw / 2) / w
            cy = (y + bh / 2) / h
            nw = bw / w
            nh = bh / h
            cls = TARGET_CLASSES[cat_id_to_name[ann["category_id"]]]
            lines.append(f"{cls} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")

        shutil.copy(src_img, OUT_IMAGES / filename)
        (OUT_LABELS / (Path(filename).stem + ".txt")).write_text("\n".join(lines) + "\n")
        kept += 1

    print(f"Kept {kept} images with person/vehicle annotations -> {OUT_DIR}")


if __name__ == "__main__":
    main()
