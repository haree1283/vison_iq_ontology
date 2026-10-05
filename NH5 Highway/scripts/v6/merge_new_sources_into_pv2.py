#!/usr/bin/env python3
"""Add the two newest v6 sources -- indian_road_dataset (13,421 real Indian road images) and
jcb_excavator (201 real road-construction excavator images) -- into the existing
datasets/processed_v2_plus_v6, remapping each source's v6 technical class ids to processed_v2's
11-class scheme by name (not by matching index, since the two schemes don't share numbering).

Usage:
  python scripts/v6/merge_new_sources_into_pv2.py
"""
import json
from collections import defaultdict
from pathlib import Path

from classes import CLASSES as V6_CLASSES

ROOT = Path(__file__).resolve().parents[2]
DST = ROOT / "datasets" / "processed_v2_plus_v6"
SOURCES_DIR = ROOT / "datasets" / "v6" / "sources"

PROCESSED_V2_CLASSES = ["person", "bicycle", "car", "motorcycle", "bus", "truck", "pothole",
                         "license_plate", "auto", "road_construction", "accident_scene",
                         "traffic_cone"]
PV2_ID = {name: i for i, name in enumerate(PROCESSED_V2_CLASSES)}

# each source: which of its v6-technical-class-id boxes to keep, and what pv2 class name each
# v6 class name maps to (a source can store a "carrier" label under an unrelated v6 name, as
# jcb_excavator does with damaged_vehicle -> road_construction). Re-running an already-merged
# source is safe: same deterministic {source}_{stem} filenames just get overwritten with a
# possibly fuller label set, not duplicated.
SOURCES = {
    "roadwork_cmu": {
        "damaged_vehicle": "road_construction",
        "traffic_cone": "traffic_cone",  # now that pv2 has this class too
        # barricade intentionally still excluded: pv2 has no such class
    },
    "rdd2022_india": {
        "pothole": "pothole",
    },
}


def main():
    added = defaultdict(int)
    images_added = 0
    for source_name, v6_to_pv2_name in SOURCES.items():
        base = SOURCES_DIR / source_name / "train"
        lbl_dir, img_dir = base / "labels", base / "images"
        if not lbl_dir.is_dir():
            print(f"skip {source_name}: not found")
            continue
        for lbl in lbl_dir.glob("*.txt"):
            lines = []
            for line in lbl.read_text().splitlines():
                parts = line.split()
                if not parts:
                    continue
                v6_name = V6_CLASSES[int(parts[0])]
                pv2_name = v6_to_pv2_name.get(v6_name)
                if pv2_name is None:
                    continue
                lines.append(f"{PV2_ID[pv2_name]} {' '.join(parts[1:5])}")
                added[pv2_name] += 1
            if not lines:
                continue
            img = next((p for ext in (".jpg", ".jpeg", ".png")
                        if (p := img_dir / f"{lbl.stem}{ext}").is_file()), None)
            if img is None:
                continue
            stem = f"{source_name}_{lbl.stem}"
            (DST / "images" / "train" / f"{stem}{img.suffix}").write_bytes(img.read_bytes())
            (DST / "labels" / "train" / f"{stem}.txt").write_text("\n".join(lines) + "\n")
            images_added += 1

    print(f"images added: {images_added}")
    print("boxes added per class:", dict(added))

    counts = defaultdict(int)
    for split in ("train", "val", "test"):
        for lbl in (DST / "labels" / split).glob("*.txt"):
            for line in lbl.read_text().splitlines():
                parts = line.split()
                if parts:
                    counts[PROCESSED_V2_CLASSES[int(parts[0])]] += 1
    print("final combined counts per class:", dict(counts))
    report_path = DST / "merge_report.json"
    prev = json.loads(report_path.read_text()) if report_path.is_file() else {}
    prev.setdefault("additional_merges", []).append(
        {"sources": list(SOURCES), "images_added": images_added, "boxes_added": dict(added)})
    prev["final_counts"] = dict(counts)
    report_path.write_text(json.dumps(prev, indent=2))


if __name__ == "__main__":
    main()
