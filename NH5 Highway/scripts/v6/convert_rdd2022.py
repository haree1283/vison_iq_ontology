#!/usr/bin/env python3
"""RDD2022 India subset -> pothole (class 6) YOLO labels under
datasets/v6/sources/rdd2022_india/train/{images,labels}.

Reads straight from the 13 GB release zip: only India/train members are
extracted, the other countries never touch disk. India/test has no labels,
so it isn't used.

Only D40 (pothole) is kept; D00/D10/D20 (cracks) are dropped. Images whose
only damage is cracks become background negatives, kept up to
--negative-ratio x the number of pothole images so the set isn't mostly road
surface with nothing to find.

Usage:
  python scripts/v6/convert_rdd2022.py
  python scripts/v6/convert_rdd2022.py --negative-ratio 0.1
"""
import argparse
import io
import json
import random
import xml.etree.ElementTree as ET
import zipfile
from pathlib import PurePosixPath, Path

import cv2
import numpy as np

from classes import CLASS_IDS

ROOT = Path(__file__).resolve().parents[2]
ZIP_PATH = ROOT / "datasets" / "v6" / "raw" / "rdd2022" / "RDD2022_released_through_CRDDC2022.zip"
OUT = ROOT / "datasets" / "v6" / "sources" / "rdd2022_india" / "train"
POTHOLE_CODE = "D40"
MIN_BOX_PX = 4
SEED = 42
XML_DIR_MARKER = "India/train/annotations/xmls/"


def open_india_archive(zf):
    """The release zip either holds the RDD2022/<Country>/... tree directly or
    one nested zip per country -- return a ZipFile that has India/train in it."""
    if any(XML_DIR_MARKER in name for name in zf.namelist()):
        return zf
    nested = [n for n in zf.namelist() if n.lower().endswith(".zip") and "india" in n.lower()]
    for name in nested:
        inner = zipfile.ZipFile(io.BytesIO(zf.read(name)))
        if any(XML_DIR_MARKER in n for n in inner.namelist()):
            return inner
    raise SystemExit(f"no '{XML_DIR_MARKER}' found in {ZIP_PATH.name} (or a nested India zip)")


def pothole_lines(xml_bytes, image_bytes):
    root = ET.fromstring(xml_bytes)
    size = root.find("size")
    w = float(size.findtext("width") or 0) if size is not None else 0.0
    h = float(size.findtext("height") or 0) if size is not None else 0.0
    if w <= 0 or h <= 0:  # some VOC files carry 0x0 sizes -- read the real size from the image
        img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
        h, w = img.shape[:2]

    lines = []
    for obj in root.iter("object"):
        if (obj.findtext("name") or "").strip() != POTHOLE_CODE:
            continue
        bb = obj.find("bndbox")
        x0, y0, x1, y1 = (float(bb.findtext(k)) for k in ("xmin", "ymin", "xmax", "ymax"))
        x0, y0, x1, y1 = max(0.0, x0), max(0.0, y0), min(w, x1), min(h, y1)
        if x1 - x0 < MIN_BOX_PX or y1 - y0 < MIN_BOX_PX:
            continue
        lines.append(f"{CLASS_IDS['pothole']} {(x0 + x1) / 2 / w:.6f} {(y0 + y1) / 2 / h:.6f} "
                     f"{(x1 - x0) / w:.6f} {(y1 - y0) / h:.6f}")
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--negative-ratio", type=float, default=0.25)
    args = ap.parse_args()

    zf = open_india_archive(zipfile.ZipFile(ZIP_PATH))
    xml_members = sorted(n for n in zf.namelist() if XML_DIR_MARKER in n and n.endswith(".xml"))
    names = set(zf.namelist())

    positives, negatives, missing_images = [], [], 0
    for xml_name in xml_members:
        stem = PurePosixPath(xml_name).stem
        img_name = xml_name.replace("annotations/xmls/", "images/")[:-4] + ".jpg"
        if img_name not in names:
            missing_images += 1
            continue
        image_bytes = zf.read(img_name)
        lines = pothole_lines(zf.read(xml_name), image_bytes)
        (positives if lines else negatives).append((stem, image_bytes, lines))

    random.Random(SEED).shuffle(negatives)
    negatives = negatives[:int(len(positives) * args.negative_ratio)]

    (OUT / "images").mkdir(parents=True, exist_ok=True)
    (OUT / "labels").mkdir(parents=True, exist_ok=True)
    boxes = 0
    for stem, image_bytes, lines in positives + negatives:
        out_stem = f"rdd2022_{stem}"
        (OUT / "images" / f"{out_stem}.jpg").write_bytes(image_bytes)
        (OUT / "labels" / f"{out_stem}.txt").write_text("\n".join(lines) + ("\n" if lines else ""))
        boxes += len(lines)

    stats = {"xml_files": len(xml_members), "missing_images": missing_images,
             "pothole_images": len(positives), "pothole_boxes": boxes,
             "negative_images_kept": len(negatives), "negative_ratio": args.negative_ratio}
    print(json.dumps(stats, indent=2))
    (OUT.parent / "conversion_stats.json").write_text(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
