#!/usr/bin/env python3
"""Two more user-collected Roboflow exports in datasets/v6/training/ -> proper sources, then
delete the zips/folders (same add-then-delete convention as convert_sample_barricades.py):

  "Zebra crossing.v1i.yolov8"  (2181 images, class 'ZebraCrossing') -> sources/sample_zebra_crossing,
      the zebra_crossing road-marking class (was only 11 real before this)
  "potholes.v2i.yolov8"        (11403 images, class '0', generic potholes) -> sources/sample_potholes_v2

The pothole set is generic, not already split into road-damage/rainwater/construction -- run
sort_scene_categories.py potholes/construction on it afterward to pull the rainwater and
construction sub-types out of this much bigger pool, same as every other pothole source.

Usage:
  python scripts/v6/convert_sample_zebra_pothole.py
"""
import shutil
from collections import Counter
from pathlib import Path

from classes import CLASS_IDS
from convert_yolo_sources import _roboflow_originals, convert_label

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "datasets" / "v6" / "training"

JOBS = {
    "sample_zebra_crossing": (D / "Zebra crossing.v1i.yolov8", {0: "zebra_crossing"},
                              [D / "Zebra crossing.v1i.yolov8.zip"]),
    "sample_potholes_v2": (D / "potholes.v2i.yolov8", {0: "pothole"}, [D / "potholes.v2i.yolov8.zip"]),
}


def main():
    id_to_name = {v: k for k, v in CLASS_IDS.items()}
    for name, (folder, class_map, extra_cleanup) in JOBS.items():
        out = ROOT / "datasets" / "v6" / "sources" / name
        stats = Counter()
        for split, img, lbl, _ in _roboflow_originals(folder):
            split = "val" if split == "valid" else split
            lines, dropped = convert_label(lbl, class_map)
            if not lines:
                continue
            out_img, out_lbl = out / split / "images", out / split / "labels"
            out_img.mkdir(parents=True, exist_ok=True)
            out_lbl.mkdir(parents=True, exist_ok=True)
            stem = f"{name}_{img.stem}"
            (out_img / f"{stem}{img.suffix.lower()}").write_bytes(img.read_bytes())
            (out_lbl / f"{stem}.txt").write_text("\n".join(lines) + "\n")
            stats["_images"] += 1
            for line in lines:
                stats[id_to_name[int(line.split()[0])]] += 1
        print(f"[{name}] {dict(stats)}")
        shutil.rmtree(folder, ignore_errors=True)
        for f in extra_cleanup:
            f.unlink(missing_ok=True)
        print(f"  deleted {folder} and its zip")


if __name__ == "__main__":
    main()
