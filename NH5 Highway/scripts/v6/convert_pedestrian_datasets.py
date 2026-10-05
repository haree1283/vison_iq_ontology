#!/usr/bin/env python3
"""Two Roboflow YOLO pedestrian datasets found sitting unconverted under
datasets/v6/categories/04_persons/walking/pedestrain/ -> proper v6 sources
(all classes map to person; the "crossing the road" dataset's classes are a
person's pose/behavior, not a different object, so looking/not crossing/not
looking/standing/walking all collapse to one person box):

  pedestrian_crossing   "pedestrain crossing" (project-5wrkt/crossing-the-road, 5 pose classes)
  pedestrian_generic    "Pedestrain.v1i.yolov8" (atharva-patil-utmpt/pedestrain-mungn, 1 class)

Output: datasets/v6/sources/<name>/train/{images,labels}. Run
sort_scene_categories.py persons afterwards (with these two added to PERSON_SOURCES) to sort
into 04_persons/<where they walk> by SigLIP.

Usage:
  python scripts/v6/convert_pedestrian_datasets.py
"""
import json
from collections import Counter
from pathlib import Path

from classes import CLASS_IDS

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "datasets" / "v6" / "categories" / "04_persons" / "walking" / "pedestrain"
OUT = ROOT / "datasets" / "v6" / "sources"
PERSON = CLASS_IDS["person"]
IMAGE_EXTS = (".jpg", ".jpeg", ".png")

SOURCES = {
    "pedestrian_crossing": RAW / "pedestrain crossing",
    "pedestrian_generic": RAW / "Pedestrain.v1i.yolov8",
}


def main():
    for name, folder in SOURCES.items():
        out_img, out_lbl = OUT / name / "train" / "images", OUT / name / "train" / "labels"
        out_img.mkdir(parents=True, exist_ok=True)
        out_lbl.mkdir(parents=True, exist_ok=True)

        counts = Counter()
        for lbl in sorted((folder / "labels").glob("*.txt")):
            img = next((p for ext in IMAGE_EXTS if (p := folder / "images" / f"{lbl.stem}{ext}").is_file()), None)
            if img is None:
                continue
            lines = []
            for raw_line in lbl.read_text().splitlines():
                parts = raw_line.split()
                if len(parts) != 5:
                    continue
                lines.append(" ".join([str(PERSON)] + parts[1:]))
            if not lines:
                continue
            stem = f"{name}_{img.stem}"
            (out_img / f"{stem}{img.suffix.lower()}").write_bytes(img.read_bytes())
            (out_lbl / f"{stem}.txt").write_text("\n".join(lines) + "\n")
            counts["_images"] += 1
            counts["person"] += len(lines)

        print(f"[{name}] {dict(counts)}")
        (OUT / name / "conversion_stats.json").write_text(json.dumps(dict(counts), indent=2))


if __name__ == "__main__":
    main()
