#!/usr/bin/env python3
"""Copy datasets/processed_v2 (the older 11-class dataset processed_v2/data.yaml, 38k images) to
datasets/processed_v2_plus_v6, then add v6's license_plate / road_accidents / road_construction
data into it -- ONLY those 3 classes' boxes (not v6's other classes), remapped to processed_v2's
class ids, since processed_v2 already has its own person/car/etc. data and this is meant to
supplement just these 3.

Usage:
  python scripts/v6/merge_into_processed_v2.py
"""
import json
import shutil
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "datasets" / "processed_v2"
DST = ROOT / "datasets" / "processed_v2_plus_v6"
V6 = ROOT / "datasets" / "v6" / "training" / "unified_yolo"

PROCESSED_V2_CLASSES = ["person", "bicycle", "car", "motorcycle", "bus", "truck", "pothole",
                         "license_plate", "auto", "road_construction", "accident_scene"]
PV2_ID = {name: i for i, name in enumerate(PROCESSED_V2_CLASSES)}

UNIFIED_CLASSES = ["person", "crossing_at_zebra", "crossing_without_zebra", "walking_on_footpath",
                    "walking_on_roadside", "bicycle", "car", "motorcycle", "bus", "truck", "auto",
                    "pothole", "license_plate", "road_accidents", "traffic_cone", "barricade",
                    "zebra_crossing", "road_construction"]
V6_ID = {name: i for i, name in enumerate(UNIFIED_CLASSES)}

# v6 unified class id -> processed_v2 class id, for only the 3 classes being added
WANTED = {
    V6_ID["license_plate"]: PV2_ID["license_plate"],
    V6_ID["road_accidents"]: PV2_ID["accident_scene"],
    V6_ID["road_construction"]: PV2_ID["road_construction"],
}


def main():
    if DST.exists():
        print(f"{DST} already exists -- delete it first if you want a clean re-copy")
        return
    print(f"copying {SRC} -> {DST} ...")
    shutil.copytree(SRC, DST)

    added = defaultdict(int)
    images_added = 0
    for split in ("train", "val", "test"):
        lbl_dir = V6 / split / "labels"
        img_dir = V6 / split / "images"
        if not lbl_dir.is_dir():
            continue
        out_img_dir = DST / "images" / split
        out_lbl_dir = DST / "labels" / split
        for lbl in lbl_dir.glob("*.txt"):
            lines = []
            for line in lbl.read_text().splitlines():
                parts = line.split()
                if not parts:
                    continue
                v6_id = int(parts[0])
                if v6_id not in WANTED:
                    continue
                pv2_id = WANTED[v6_id]
                lines.append(f"{pv2_id} {' '.join(parts[1:5])}")
                added[PROCESSED_V2_CLASSES[pv2_id]] += 1
            if not lines:
                continue
            img = next((p for ext in (".jpg", ".jpeg", ".png")
                        if (p := img_dir / f"{lbl.stem}{ext}").is_file()), None)
            if img is None:
                continue
            stem = f"v6_{lbl.stem}"
            shutil.copy2(img, out_img_dir / f"{stem}{img.suffix}")
            (out_lbl_dir / f"{stem}.txt").write_text("\n".join(lines) + "\n")
            images_added += 1

    print(f"added {images_added} images from v6 (license_plate/road_construction/road_accidents only)")
    print("boxes added per class:", dict(added))

    counts = defaultdict(int)
    for split in ("train", "val", "test"):
        for lbl in (DST / "labels" / split).glob("*.txt"):
            for line in lbl.read_text().splitlines():
                parts = line.split()
                if parts:
                    counts[PROCESSED_V2_CLASSES[int(parts[0])]] += 1
    print("final combined counts per class:", dict(counts))
    (DST / "merge_report.json").write_text(json.dumps(
        {"images_added_from_v6": images_added, "boxes_added_from_v6": dict(added),
         "final_counts": dict(counts)}, indent=2))


if __name__ == "__main__":
    main()
