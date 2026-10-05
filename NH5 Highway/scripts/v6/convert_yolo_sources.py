#!/usr/bin/env python3
"""Convert the downloaded YOLO-format sources to v6 class ids under
datasets/v6/sources/<name>/{train,val,test}/{images,labels}.

Handles what these public exports actually contain:
- polygon rows (class x1 y1 x2 y2 ...) mixed in with box rows -> enclosing box
- one group (video / capture session) landing in several splits -> the whole
  group is moved to train, so val/test never contain a near-copy of a training image
- sources with no split at all -> split 80/10/10 by group, never by single frame
Images are hard-linked (no extra disk) with a copy fallback. Re-running
rebuilds the source folder from scratch.

Accident exports: every Roboflow YOLO zip dropped in "datasets/car accidents/" is unzipped once into
raw/user_accidents/ and registered as source accidents_rf_<workspace>_<project>; its class names are
mapped by classes.ACCIDENT_CLASS_RULES, and a vehicle type in a class name ("bus_accident") is written
to damaged_vehicle_types_source.jsonl for build_categories.py.

Usage:
  python scripts/v6/convert_yolo_sources.py            # all sources whose download is present
  python scripts/v6/convert_yolo_sources.py dashcam raqabah
  python scripts/v6/convert_yolo_sources.py inbox      # every accident export dropped in datasets/car accidents/
"""
import hashlib
import json
import os
import re
import shutil
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np
import yaml

from classes import (ACCIDENT_CLASS_RULES, ACCIDENT_MAP, ACCIDENT_SEVERITY_BY_CLASS, ACCIDENT_VEHICLE_HINTS, CLASS_IDS,
                     CUBEAI_CRASH_TYPES, CUBEAI_MAP, DASHCAM_MAP, PAMPANA_CRASH_TYPES, PAMPANA_MAP, PLATE_MAP)

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "datasets" / "v6" / "raw" / "kaggle"
USER_ACCIDENTS = ROOT / "datasets" / "v6" / "raw" / "user_accidents"  # unzipped from datasets/car accidents/
OUT = ROOT / "datasets" / "v6" / "sources"
IMAGE_EXTS = (".jpg", ".jpeg", ".png")
MIN_SIDE = 0.002  # normalized; drops degenerate boxes


def _image_for(label, image_dir):
    for ext in IMAGE_EXTS:
        p = image_dir / f"{label.stem}{ext}"
        if p.is_file():
            return p
    return None


def pairs_gujarat_plates():
    root = RAW / "gujarat-vehicle-number-plates-yolo-ready" / "Gujarat_Vehicle_Dataset"
    for split in ("train", "val"):
        for lbl in sorted((root / "labels" / split).glob("*.txt")):
            img = _image_for(lbl, root / "images" / split)
            if img:
                yield split, img, lbl, lbl.stem  # distinct photos


def pairs_video_plates():
    root = RAW / "indian-vehicle-number-plate-yolo-annotation"
    for video in sorted(p for p in root.iterdir() if p.is_dir()):
        for lbl in sorted(video.glob("*.txt")):
            img = _image_for(lbl, video)
            if img and lbl.stem != "classes":
                yield None, img, lbl, video.name  # frames of one video stay together


def pairs_gate_plates():
    root = RAW / "indian-number-plate-images"
    for lbl in sorted((root / "yolo_labels").glob("*.txt")):
        img = _image_for(lbl, root / "images" / "images")
        if img and lbl.stem != "classes":
            yield None, img, lbl, lbl.stem[:8]  # capture date (YYYYMMDD) = one session at the gate


NOT_OWN_FOOTAGE = ("Dashcam_videos_recommendations", "Unconfirmed_")  # browser screenshots, unnamed downloads


def pairs_dashcam():
    """Only the author's own dashcam frames, named
    <uuid>-<video>_-_VLC_media_player_<date>_<h>_<m>_<s>_<AM|PM> -- unsplit, grouped by video +
    capture minute so neighbouring frames stay together.

    Dropped, because the CC BY 4.0 / Apache-2.0 / CC0 grants can't cover images the uploaders
    didn't take:
    - pothole_* / barricade_*: bundled Roboflow sets full of web photos (Alamy and
      picture-alliance watermarks, barrier vendor sites)
    - browser screenshots of third-party videos and half-downloaded files"""
    root = RAW / "dashcam-pov-potholes-and-barricades-for-yolo26n" / "label_studio_dataset"
    for lbl in sorted((root / "labels").glob("*.txt")):
        img = _image_for(lbl, root / "images")
        if img is None or lbl.stem.startswith(("pothole_", "barricade_")):
            continue
        name = lbl.stem.split("-", 1)[1]
        if name.startswith(NOT_OWN_FOOTAGE):
            continue
        video, _, captured = name.partition("_-_VLC_media_player_")
        yield None, img, lbl, f"{video}_{captured.rsplit('_', 2)[0]}"


def pairs_raqabah():
    """Accident images with image-level severity only -- no boxes. Images come
    in with empty labels: prelabel_missing.py proposes the vehicles, and the
    CVAT reviewer re-classes the crashed ones as damaged_vehicle. Normal/ stays
    as negatives.

    Mostly AI-generated (synthetic) scenes, so everything goes to train: val and
    test must measure the model on real footage, not on generated images."""
    root = RAW / "raqabah-multi-severity-car-accident-dataset" / "Raqabah_Car_Accident_Dataset"
    for img in sorted(p for p in root.rglob("*") if p.suffix.lower() in IMAGE_EXTS):
        yield "train", img, None, img.stem


def mask_generator_watermark(img):
    """Raqabah's generated images carry an image-generator sparkle in the
    bottom-right corner, only on the accident-style scenes -- left in, the
    detector can learn "sparkle = accident". Inpaint that corner away."""
    h, w = img.shape[:2]
    side = int(0.09 * min(h, w))
    mask = np.zeros((h, w), np.uint8)
    mask[h - side:, w - side:] = 255
    return cv2.inpaint(img, mask, 5, cv2.INPAINT_TELEA)


PREPARE = {"raqabah": mask_generator_watermark}  # sources whose images are rewritten instead of hard-linked


def _roboflow_originals(root):
    """One (split, image, label, original name) per original photo of a Roboflow export.
    Roboflow stores each augmented copy as <original>_<ext>.rf.<hash>; copies differ only by
    noise / rotation, so keep the smallest file (salt-and-pepper noise inflates JPEG size).
    Keeping one copy also stops a copy in val/test sitting next to its twin in train."""
    best = {}
    for split in ("train", "valid", "test"):
        for lbl in sorted((root / split / "labels").glob("*.txt")):
            img = _image_for(lbl, root / split / "images")
            if img is None:
                continue
            original = re.sub(r"\.rf\.[0-9a-f]+$", "", lbl.stem)
            if original not in best or img.stat().st_size < best[original][1].stat().st_size:
                best[original] = ("val" if split == "valid" else split, img, lbl)
    for original, (split, img, lbl) in sorted(best.items()):
        yield split, img, lbl, original


GAME_RENDERS = ("semi-realisticvd", "accidentframe", "traffic_img")  # simulator / video-game crash frames


def pairs_accidents_hackcimat():
    """Roboflow 'hackcimat/accidents-slk5t' (Public Domain as published). Mixes CCTV frames, news
    photos and game renders; renders go to train so val/test measure real crashes."""
    for split, img, lbl, original in _roboflow_originals(USER_ACCIDENTS / "hackcimat_accidents_fire"):
        yield ("train" if original.lower().startswith(GAME_RENDERS) else split), img, lbl, original


def pairs_accidents_ai_challenge():
    """Roboflow 'ai-challenge-sbskb/accidents-amxaw' (CC BY 4.0 as published): news / social-media crash photos."""
    yield from _roboflow_originals(USER_ACCIDENTS / "ai_challenge_accidents")


def pairs_accidents_collision():
    """Roboflow 'car-accidents-pxuzi' v20, license 'Private' in the export: web crash photos (stock watermarks seen)."""
    yield from _roboflow_originals(USER_ACCIDENTS / "car_accidents_colision")


def pairs_accidents_amedeograndi():
    """Kaggle amedeograndi/accidents-detection-dataset (no license stated): Roboflow export whose two
    classes are crash severities ('moderate', 'severe'). Shares images with accidents_hackcimat --
    build_categories.py drops the copies by image hash."""
    yield from _roboflow_originals(RAW / "accidents-detection-dataset" / "AccidentsDetectionYOLOv8")


def pairs_construction_site_safety():
    """Roboflow Construction Site Safety (PPE) -- real active construction-site photos, most with
    no vehicle/road-user box at all; kept anyway (not in DROP_UNLABELED) so the whole scene is
    available to sort_scene_categories.py's construction task, which scores whole images."""
    yield from _roboflow_originals(RAW / "construction-site-safety-image-dataset-roboflow" / "css-data")


def pairs_obstacle_detection():
    """Roboflow Road Obstacle Detection (ROD) -- street-level photos with traffic cones, barrels,
    guard rails, crosswalks; same reasoning as above, kept unlabeled-or-not for whole-scene scoring."""
    yield from _roboflow_originals(RAW / "obstacle-detection-dataset" / "ROD-Dataset" / "dataset")


def pairs_accidents_pampana():
    """Kaggle pampanadeepakbabu/road-accident-anamoly-dataset (no license stated): images/<split> and
    labels/<split> with bike and car crash classes alongside plain vehicles (classes.PAMPANA_MAP)."""
    root = RAW / "road-accident-anamoly-dataset" / "road_traffic_anamoly_dataset"
    for split in ("train", "val", "test"):
        for lbl in sorted((root / "labels" / split).glob("*.txt")):
            img = _image_for(lbl, root / "images" / split)
            if img:
                yield split, img, lbl, re.sub(r"\.rf\.[0-9a-f]+$", "", lbl.stem)


def pairs_accidents_nardengerges():
    """Kaggle nardengerges/accident-no-accident-detection (no license stated): Roboflow export,
    classes 'Accident' / 'Non Accident'. 33k frames but only a few thousand originals -- the copies
    go in _roboflow_originals, the images it shares with other exports in build_categories.py."""
    yield from _roboflow_originals(RAW / "accident-no-accident-detection" / "AN-Data")


def pairs_accidents_cubeai():
    """Kaggle cubeai/traffic-accident-detection-for-yolov8 (no license stated): a Roboflow export with
    bicycle / car crash boxes plus plain bicycle, car and person boxes (classes.CUBEAI_MAP)."""
    yield from _roboflow_originals(RAW / "traffic-accident-detection-for-yolov8")


DROP_UNLABELED = {"accidents_hackcimat", "accidents_ai_challenge", "accidents_collision",
                  "accidents_amedeograndi", "accidents_nardengerges"}  # fire-only / no-accident scenes aren't road negatives

INBOX = ROOT / "datasets" / "car accidents"  # the user drops Roboflow YOLO exports (.zip) of accident data here
REVIEWED_PROJECTS = {  # exports with the hand-written generators above (their class names needed a look at the images)
    "hackcimat/accidents-slk5t", "ai-challenge-sbskb/accidents-amxaw", "car-accidents-pxuzi/car-accidents-4ujhq"}
CLASS_TYPES = {"accidents_cubeai": CUBEAI_CRASH_TYPES,  # source -> {export class id: vehicle type named in that class}
               "accidents_pampana": PAMPANA_CRASH_TYPES}


def accident_class(name):
    """Export class name -> (v6 class or None, vehicle type named in it or None)."""
    low = name.lower()
    for words, v6 in ACCIDENT_CLASS_RULES:
        if any(w in low for w in words):
            return v6, next((k for hint, k in ACCIDENT_VEHICLE_HINTS if hint in low), None) if v6 else None
    return None, None


def register_inbox():
    """Unzip each Roboflow export in INBOX once and register it as a source. An export without
    data.yaml class names, or without any accident-like class, is skipped with a message."""
    for zip_path in sorted(INBOX.glob("*.zip")):
        with zipfile.ZipFile(zip_path) as zf:
            meta = yaml.safe_load(zf.read("data.yaml")) if "data.yaml" in zf.namelist() else None
            if not isinstance(meta, dict) or "names" not in meta:
                print(f"[inbox] {zip_path.name}: no data.yaml with class names -- not a YOLO export, skipped")
                continue
            rf = meta.get("roboflow") or {}
            project = f"{rf.get('workspace', '')}/{rf.get('project', zip_path.stem)}"
            if project in REVIEWED_PROJECTS:
                continue
            names = meta["names"] if isinstance(meta["names"], list) else [meta["names"][k] for k in sorted(meta["names"])]
            mapping = {i: accident_class(str(n)) for i, n in enumerate(names)}
            if not any(v6 for v6, _ in mapping.values()):
                # exports of one unnamed class ('0', '-', 'object') carry the meaning in the project name
                unnamed = len(names) == 1 and str(names[0]).strip().lower() in {"0", "1", "-", "object", "objects"}
                from_project = accident_class(f"{project} {zip_path.stem}") if unnamed else (None, None)
                if not from_project[0]:
                    print(f"[inbox] {zip_path.name}: no accident class in {names} -- skipped")
                    continue
                print(f"[inbox] {zip_path.name}: class {names[0]!r} unnamed, taken as {from_project} from '{project}'")
                mapping = {0: from_project}
            name = "accidents_rf_" + re.sub(r"[^a-z0-9]+", "_", project.lower()).strip("_")[:48]
            folder = USER_ACCIDENTS / name
            if not (folder / ".done").is_file():
                print(f"[inbox] unzipping {zip_path.name} -> {folder.relative_to(ROOT)}")
                zf.extractall(folder)
                (folder / "export_info.json").write_text(json.dumps(
                    {"zip": zip_path.name, "project": project, "license": rf.get("license"), "url": rf.get("url"),
                     "names": names, "mapping": {n: v for n, v in zip(names, mapping.values())}}, indent=2))
                (folder / ".done").touch()
        CLASS_TYPES[name] = {i: kind for i, (v6, kind) in mapping.items() if v6 and kind}
        SOURCES[name] = (lambda f=folder: _roboflow_originals(f), {i: v6 for i, (v6, _) in mapping.items() if v6}, folder)
        DROP_UNLABELED.add(name)


SOURCES = {  # name -> (pair generator, class map, raw folder whose download must be complete)
    "gujarat_plates": (pairs_gujarat_plates, PLATE_MAP, RAW / "gujarat-vehicle-number-plates-yolo-ready"),
    "video_plates": (pairs_video_plates, PLATE_MAP, RAW / "indian-vehicle-number-plate-yolo-annotation"),
    "gate_plates": (pairs_gate_plates, PLATE_MAP, RAW / "indian-number-plate-images"),
    "raqabah": (pairs_raqabah, {}, RAW / "raqabah-multi-severity-car-accident-dataset"),
    "dashcam": (pairs_dashcam, DASHCAM_MAP, RAW / "dashcam-pov-potholes-and-barricades-for-yolo26n"),
    "accidents_hackcimat": (pairs_accidents_hackcimat, ACCIDENT_MAP, USER_ACCIDENTS / "hackcimat_accidents_fire"),
    "accidents_ai_challenge": (pairs_accidents_ai_challenge, ACCIDENT_MAP, USER_ACCIDENTS / "ai_challenge_accidents"),
    "accidents_collision": (pairs_accidents_collision, ACCIDENT_MAP, USER_ACCIDENTS / "car_accidents_colision"),
    "accidents_cubeai": (pairs_accidents_cubeai, CUBEAI_MAP, RAW / "traffic-accident-detection-for-yolov8"),
    "accidents_amedeograndi": (pairs_accidents_amedeograndi, {0: "damaged_vehicle", 1: "damaged_vehicle"},
                               RAW / "accidents-detection-dataset"),
    "accidents_nardengerges": (pairs_accidents_nardengerges, {0: "damaged_vehicle"},  # 1 = 'Non Accident'
                               RAW / "accident-no-accident-detection"),
    "accidents_pampana": (pairs_accidents_pampana, PAMPANA_MAP, RAW / "road-accident-anamoly-dataset"),
    # [Hardhat, Mask, NO-Hardhat, NO-Mask, NO-Safety Vest, Person, Safety Cone, Safety Vest, machinery, vehicle]
    "construction_site_safety": (pairs_construction_site_safety, {5: "person", 6: "traffic_cone"},
                                 RAW / "construction-site-safety-image-dataset-roboflow"),
    # ['Bike','Building','Car','Person','Stairs','Traffic sign','Electrical Pole','Road','Motorcycle','Dustbin',
    #  'Dog','Manhole','Tree','Guard rail','Pedestrian crosswalk','Truck','Bus','Bench','Traffic Cone',
    #  'Fire hydrant','Teraffic Barrel'(sic),'Plant Pot','Electrical Box','Chair','Bicycle Rack']
    "obstacle_detection": (pairs_obstacle_detection,
                           {0: "bicycle", 2: "car", 3: "person", 8: "motorcycle", 14: "zebra_crossing",
                            15: "truck", 16: "bus", 18: "traffic_cone", 20: "barricade"},
                           RAW / "obstacle-detection-dataset"),
}


def convert_label(path, class_map):
    lines, dropped = [], 0
    for raw in path.read_text(errors="replace").splitlines():
        parts = raw.split()
        if len(parts) < 5:
            continue
        name = class_map.get(int(float(parts[0])))
        if name is None:
            dropped += 1
            continue
        vals = [float(v) for v in parts[1:]]
        if len(vals) == 4:
            cx, cy, w, h = vals
            x0, y0, x1, y1 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
        elif len(vals) >= 6 and len(vals) % 2 == 0:  # polygon
            xs, ys = vals[0::2], vals[1::2]
            x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
        else:
            dropped += 1
            continue
        x0, y0, x1, y1 = max(0.0, x0), max(0.0, y0), min(1.0, x1), min(1.0, y1)
        if x1 - x0 < MIN_SIDE or y1 - y0 < MIN_SIDE:
            dropped += 1
            continue
        lines.append(f"{CLASS_IDS[name]} {(x0 + x1) / 2:.6f} {(y0 + y1) / 2:.6f} {x1 - x0:.6f} {y1 - y0:.6f}")
    return lines, dropped


def assign_splits(pairs):
    """Groups seen in several splits go to train; unsplit groups get a stable 80/10/10 split."""
    splits_of = defaultdict(set)
    for split, _, _, group in pairs:
        splits_of[group].add(split)
    moved = 0
    out = []
    for split, img, lbl, group in pairs:
        seen = splits_of[group]
        if None in seen:
            bucket = int(hashlib.md5(group.encode()).hexdigest(), 16) % 10
            final = "val" if bucket == 8 else "test" if bucket == 9 else "train"
        elif len(seen) > 1:
            final = "train"
            moved += split != "train"
        else:
            final = split
        out.append((final, img, lbl, group))
    return out, moved


def link(src, dst):
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def convert(name):
    gen, class_map, raw_dir = SOURCES[name]
    if not (raw_dir / ".done").is_file():
        print(f"[{name}] download not complete -- skipped")
        return None
    pairs, moved = assign_splits(list(gen()))
    out_root = OUT / name
    shutil.rmtree(out_root, ignore_errors=True)
    out_root.mkdir(parents=True)
    types = CLASS_TYPES.get(name, {})
    typed = open(out_root / "damaged_vehicle_types_source.jsonl", "w") if types else None
    severities = ACCIDENT_SEVERITY_BY_CLASS.get(name, {})
    severity_out = open(out_root / "accident_severity_source.jsonl", "w") if severities else None

    stats = defaultdict(Counter)
    for split, img, lbl, _ in pairs:
        lines, dropped = convert_label(lbl, class_map) if lbl is not None else ([], 0)
        if not lines and name in DROP_UNLABELED:
            stats[split]["_skipped_no_box"] += 1
            continue
        (out_root / split / "images").mkdir(parents=True, exist_ok=True)
        (out_root / split / "labels").mkdir(parents=True, exist_ok=True)
        stem = f"{name}_{img.stem}"
        if name in PREPARE:
            cv2.imwrite(str(out_root / split / "images" / f"{stem}.jpg"), PREPARE[name](cv2.imread(str(img))),
                        [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        else:
            link(img, out_root / split / "images" / f"{stem}{img.suffix.lower()}")
        (out_root / split / "labels" / f"{stem}.txt").write_text("\n".join(lines) + ("\n" if lines else ""))
        if (typed or severity_out) and lbl is not None:
            ids = {int(float(r.split()[0])) for r in lbl.read_text(errors="replace").splitlines() if r.split()}
            for kind in sorted({types[i] for i in ids if i in types}) if typed else []:
                typed.write(json.dumps({"split": split, "image": stem, "vehicle": kind}) + "\n")
            # worst wins: an image labelled both moderate and severe is severe, and any fire box makes it fire
            named = [severities[i] for i in ids if i in severities]
            if named:
                worst = "fire" if "fire" in named else "severe" if "severe" in named else named[0]
                severity_out.write(json.dumps({"split": split, "image": stem, "severity": worst}) + "\n")
        s = stats[split]
        s["_images"] += 1
        s["_empty_images"] += not lines
        s["_dropped_rows"] += dropped
        s.update(CLASS_IDS_TO_NAME[int(l.split()[0])] for l in lines)

    for handle in (typed, severity_out):
        if handle:
            handle.close()
    result = {"groups_moved_to_train": moved, "splits": {k: dict(v) for k, v in sorted(stats.items())}}
    (out_root / "conversion_stats.json").write_text(json.dumps(result, indent=2))
    print(f"[{name}] {json.dumps(result)}")
    return result


CLASS_IDS_TO_NAME = {i: n for n, i in CLASS_IDS.items()}


def main():
    register_inbox()
    args = sys.argv[1:]
    names = [n for n in SOURCES if n.startswith("accidents_rf_")] if args == ["inbox"] else args or list(SOURCES)
    unknown = set(names) - set(SOURCES)
    if unknown:
        raise SystemExit(f"unknown sources {sorted(unknown)}; choose from {list(SOURCES)}")
    for name in names:
        convert(name)


if __name__ == "__main__":
    main()
