#!/usr/bin/env python3
"""3 barricade Roboflow exports the user collected in datasets/v6/training/sample/ ->
sources/sample_barricades/{train,val,test}/{images,labels}. Deletes the sample folder once
converted, per the user's request (add then delete).

Usage:
  python scripts/v6/convert_sample_barricades.py
"""
import shutil
from collections import Counter
from pathlib import Path

from classes import CLASS_IDS
from convert_yolo_sources import _roboflow_originals, convert_label

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "datasets" / "v6" / "training" / "sample"
OUT = ROOT / "datasets" / "v6" / "sources" / "sample_barricades"

SOURCES = {
    "barricade_v7": (D / "barricade.v7i.yolov8", {0: "barricade"}),
    "barricade_barrier": (D / "Barricade-barrier.v1i.yolov8", {0: "barricade", 1: "barricade"}),
    "barricade_detection_v10": (D / "Barricade detection.v10i.yolov8", {0: "barricade"}),
}


def main():
    id_to_name = {v: k for k, v in CLASS_IDS.items()}
    stats = Counter()
    for name, (folder, class_map) in SOURCES.items():
        for split, img, lbl, _ in _roboflow_originals(folder):
            split = "val" if split == "valid" else split
            lines, dropped = convert_label(lbl, class_map)
            if not lines:
                continue
            out_img, out_lbl = OUT / split / "images", OUT / split / "labels"
            out_img.mkdir(parents=True, exist_ok=True)
            out_lbl.mkdir(parents=True, exist_ok=True)
            stem = f"{name}_{img.stem}"
            (out_img / f"{stem}{img.suffix.lower()}").write_bytes(img.read_bytes())
            (out_lbl / f"{stem}.txt").write_text("\n".join(lines) + "\n")
            stats["_images"] += 1
            for line in lines:
                stats[id_to_name[int(line.split()[0])]] += 1

    print(dict(stats))
    shutil.rmtree(D, ignore_errors=True)
    print(f"deleted {D}")


if __name__ == "__main__":
    main()
