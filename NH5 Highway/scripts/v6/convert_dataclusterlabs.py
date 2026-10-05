#!/usr/bin/env python3
"""Three Kaggle Pascal-VOC-XML datasets, all real Indian photos, one class per
<object><name> (an XML <attributes> block also uses <name> for things like
'rotation'/'number_plate_text' -- these are attributes, not classes, and are
ignored) -> datasets/v6/sources/<name>/train/{images,labels}.

  indian_vehicle_dataset    dataclusterlabs/indian-vehicle-dataset (100 images, mixed vehicle types)
  bicycle_dataset           dataclusterlabs/bicycle-image-dataset-vehicle-dataset (208 images, bicycle only)
  indian_number_plates      dataclusterlabs/indian-number-plates-dataset (47 images, plate only;
                            each plate's ground-truth text is in the XML but not used here)

Usage:
  python scripts/v6/convert_dataclusterlabs.py
"""
import json
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from classes import CLASS_IDS

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "datasets" / "v6" / "raw" / "kaggle"
OUT = ROOT / "datasets" / "v6" / "sources"
IMAGE_EXTS = (".jpg", ".jpeg", ".png")

# source class name (as it appears in <object><name>) -> v6 class, or None to drop
VEHICLE_MAP = {
    "two_wheelers": "motorcycle", "auto": "auto", "car": "car", "bus": "bus", "bicycle": "bicycle",
    "vehicle_truck": "truck", "truck_tanker": "truck", "concrete_mixer": "truck",
    "tempo": "truck",  # Indian "tempo" = light goods carrier, closest v6 fit is truck
    "tractor": None,  # agricultural, no v6 class
}
BICYCLE_MAP = {"Bicycle": "bicycle"}
PLATE_MAP = {"number_plate": "license_plate"}
AUTO_MAP = {"autorickshaw": "auto"}
POTHOLE_MAP = {"pothole": "pothole", "potholes": "pothole"}
PERSON_MAP = {"person-like": "person"}

PLATES_ROOT = RAW / "indian-number-plates-dataset"
# same folder holds images+xml together, except this dataset which splits them into two labeled
# sets with images and annotations in separate directories (paired by file stem)
SOURCES = {
    "indian_vehicle_dataset": [(RAW / "indian-vehicle-dataset" / "Indian_vehicle_dataset", None, VEHICLE_MAP)],
    "bicycle_dataset": [(RAW / "bicycle-image-dataset-vehicle-dataset" / "dataset" / "Bicycle annotated",
                         None, BICYCLE_MAP)],
    "indian_number_plates": [
        (PLATES_ROOT / "Indian_Number_Plates" / "Sample_Images", PLATES_ROOT / "Annotations" / "Annotations",
         PLATE_MAP),
        (PLATES_ROOT / "number_plate_images_ocr" / "number_plate_images_ocr",
         PLATES_ROOT / "number_plate_annos_ocr" / "number_plate_annos_ocr", PLATE_MAP),
    ],
    "autorickshaw_dataset": [
        (RAW / "autorickshaw-image-dataset-niche-vehicle-dataset" / "auto" / "auto",
         RAW / "autorickshaw-image-dataset-niche-vehicle-dataset" / "Annotations" / "Annotations", AUTO_MAP),
    ],
    "pothole_annotated": [(RAW / "annotated-potholes-dataset" / "annotated-images", None, POTHOLE_MAP)],
    # pothole-detection (andrewmvd) skipped: same 665 images/1739 boxes as pothole_annotated,
    # a duplicate re-upload of the same underlying dataset by a different Kaggle user
    "pothole_cracks_dcl": [(RAW / "potholes-or-cracks-on-road-image-dataset" / "dataset" / "potholes bat├зh 1",
                            None, POTHOLE_MAP)],
    "pedestrian_detection_kaggle": [
        (RAW / "pedestrian-detection" / split / split / "JPEGImages",
         RAW / "pedestrian-detection" / split / split / "Annotations", PERSON_MAP)
        for split in ("Train", "Val", "Test")
    ],
}


def voc_boxes(xml_path, class_map):
    root = ET.parse(xml_path).getroot()
    w = float(root.findtext("size/width"))
    h = float(root.findtext("size/height"))
    if w <= 0 or h <= 0:
        return []  # a few exports have corrupt/missing size metadata
    lines = []
    for obj in root.findall("object"):
        v6 = class_map.get(obj.findtext("name"))
        if v6 is None:
            continue
        box = obj.find("bndbox")
        x0, y0 = float(box.findtext("xmin")), float(box.findtext("ymin"))
        x1, y1 = float(box.findtext("xmax")), float(box.findtext("ymax"))
        x0, y0, x1, y1 = max(0.0, x0) / w, max(0.0, y0) / h, min(w, x1) / w, min(h, y1) / h
        if x1 - x0 < 0.002 or y1 - y0 < 0.002:
            continue
        lines.append(f"{CLASS_IDS[v6]} {(x0 + x1) / 2:.6f} {(y0 + y1) / 2:.6f} {x1 - x0:.6f} {y1 - y0:.6f}")
    return lines


def main():
    id_to_name = {v: k for k, v in CLASS_IDS.items()}
    for name, groups in SOURCES.items():
        out_img, out_lbl = OUT / name / "train" / "images", OUT / name / "train" / "labels"
        out_img.mkdir(parents=True, exist_ok=True)
        out_lbl.mkdir(parents=True, exist_ok=True)

        counts = Counter()
        for img_dir, lbl_dir, class_map in groups:
            lbl_dir = lbl_dir or img_dir  # images and xml share a folder unless told otherwise
            if not img_dir.is_dir() or not lbl_dir.is_dir():
                print(f"[{name}] {img_dir if not img_dir.is_dir() else lbl_dir} not found -- skipped")
                continue
            for xml_path in sorted(lbl_dir.glob("*.xml")):
                img = next((p for ext in IMAGE_EXTS if (p := img_dir / f"{xml_path.stem}{ext}").is_file()), None)
                if img is None:
                    continue
                lines = voc_boxes(xml_path, class_map)
                if not lines:
                    continue
                stem = f"{name}_{img.stem}".replace(" ", "_").replace("(", "").replace(")", "")
                (out_img / f"{stem}{img.suffix.lower()}").write_bytes(img.read_bytes())
                (out_lbl / f"{stem}.txt").write_text("\n".join(lines) + "\n")
                counts["_images"] += 1
                for line in lines:
                    counts[id_to_name[int(line.split()[0])]] += 1
        print(f"[{name}] {dict(counts)}")
        (OUT / name / "conversion_stats.json").write_text(json.dumps(dict(counts), indent=2))


if __name__ == "__main__":
    main()
