#!/usr/bin/env python3
"""Convert the dataclusterlabs/jcb-image-dataset (201 real photos of excavators actively working
on Indian roads/streets, Pascal VOC XML boxes) into a v6 source. "road_construction" isn't one of
the 13 base technical classes in classes.py -- it's a scene-level class assembled later in
build_unified_yolo.py. So, like sample_barricades/sample_zebra_crossing before it, this source
stores its boxes under a carrier technical class id (damaged_vehicle, chosen only because this
source is never read by every_technical_box() -- it's picked up solely by a dedicated
direct_source_scan() call added to build_unified_yolo.py, so the carrier id can't collide with
anything) which that build step then remaps to the real "road_construction" scene class.

Usage:
  python scripts/v6/convert_jcb_excavator.py
"""
import xml.etree.ElementTree as ET
from pathlib import Path

from classes import CLASS_IDS

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "datasets" / "v6" / "raw" / "kaggle" / "jcb-image-dataset" / "extracted"
ANN = RAW / "Annotations" / "Annotations"
OUT = ROOT / "datasets" / "v6" / "sources" / "jcb_excavator" / "train"


def main():
    (OUT / "images").mkdir(parents=True, exist_ok=True)
    (OUT / "labels").mkdir(parents=True, exist_ok=True)

    images, boxes = 0, 0
    for xml_path in sorted(ANN.glob("*.xml")):
        root = ET.parse(xml_path).getroot()
        img_name = root.findtext("filename")
        img_path = RAW / img_name
        if not img_path.is_file():
            continue
        w = float(root.find("size/width").text)
        h = float(root.find("size/height").text)

        lines = []
        for obj in root.findall("object"):
            if obj.findtext("name") != "excavator":
                continue
            box = obj.find("bndbox")
            x1, y1 = float(box.findtext("xmin")), float(box.findtext("ymin"))
            x2, y2 = float(box.findtext("xmax")), float(box.findtext("ymax"))
            cx, cy = (x1 + x2) / 2 / w, (y1 + y2) / 2 / h
            bw, bh = (x2 - x1) / w, (y2 - y1) / h
            lines.append(f"{CLASS_IDS['damaged_vehicle']} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
            boxes += 1
        if not lines:
            continue

        stem = f"jcb_{img_path.stem}"
        (OUT / "images" / f"{stem}.jpg").write_bytes(img_path.read_bytes())
        (OUT / "labels" / f"{stem}.txt").write_text("\n".join(lines) + "\n")
        images += 1

    print(f"images: {images}, boxes: {boxes}")


if __name__ == "__main__":
    main()
