#!/usr/bin/env python3
"""The NH5 dataset as one browsable tree, datasets/v6/categories/: a numbered folder per
requirement, --target images per category (10k; road accidents 20k), split EQUALLY across the
category's sub-folders.

A sub-folder short of its share keeps all its real images and is topped up with augmented copies
(mirrored; later copies also cropped and re-lit) up to --max-repeat x its real images -- the same
3x limit as the detector set, because more copies of too few photos teach the model those photos,
not the scene. Whatever is still missing after that is listed in README.md: it needs new images.

  01_vehicles/<type>/[<sub-type>/]      images the balanced detector set uses (training/detector_yolo/selection.csv);
                                        car / bus / truck by UVH-26 sub-type, "unspecified" = sources without one
  02_number_plates/<vehicle type>/      images whose plate box sits inside a vehicle box of that type
  03_potholes/single, multiple/         by pothole box count
  03_potholes/rainwater_filled, construction_holes/   candidates from sort_scene_categories.py
  04_persons/<where the person walks>/  candidates from sort_scene_categories.py
  05_road_construction/                 candidates from sort_scene_categories.py
  06_road_accidents/moderate, severe, fire/   crash images sorted by how bad the crash is (20k, ~6.6k each):
                                        an export's own severity class or Raqabah's folder wins, the rest are
                                        scored by SigLIP (sort_scene_categories.py accidents)
  07_lane_change/, 08_wrong_side_driving/   video clips (extract_lane_change_clips.py / event engine)
  09_roadside_parked_vehicles/          candidates from sort_scene_categories.py

This script rebuilds the folders decided by labels (01, 02, 03 single/multiple, 06). Candidate and
clip folders belong to the scripts that fill them and are only counted, never augmented (they are
for review). Writes README.md and _index/categories.csv. Real images are hard links into
datasets/v6/sources/; augmented copies are new JPEGs named <image>_augN.jpg.

Usage (after balance_v6_dataset.py, and after sort_scene_categories.py for the candidate folders):
  python scripts/v6/build_categories.py
  python scripts/v6/build_categories.py --target 10000 --max-repeat 3
"""
import argparse
import csv
import json
import random
import shutil
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import cv2

from balance_v6_dataset import link, raqabah_severity, slug
from build_v6_dataset import IMAGE_EXTS, SEED, label_for
from classes import CLASS_IDS, CLASSES, UVH26_MAP

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ROOT / "datasets" / "v6" / "sources"
OUT = ROOT / "datasets" / "v6" / "categories"
SELECTION = ROOT / "datasets" / "v6" / "training" / "detector_yolo" / "selection.csv"
CACHE = ROOT / "datasets" / "v6" / "cache"
TARGET = 10000
TARGETS = {"06_road_accidents": 10000,  # ~3,333 in each of moderate / severe / fire
           "05_road_construction": 5000,  # real data is scarce here
           # truck/bus/auto/motorcycle/bicycle are maxed at their real ceiling (345/320/4/18/6);
           # only car (3,496 real) and no_vehicle_box (5,712 real) have headroom, so this quota
           # (15,078/7=2,154) is sized to let those two absorb enough to reach ~5k total
           "02_number_plates": 15078,
           # frozen at their original target so a --target passed for 01_vehicles/02/05 doesn't
           # change these too (03/04/09 have no overrides of their own otherwise)
           "03_potholes": 10000, "09_roadside_parked_vehicles": 10000,
           "04_persons": 5000}
AUGMENT_CANDIDATES = set()  # unique images only -- no augmented copies in the accident folders
MAX_REPEAT = 3

VEHICLES = ["auto", "motorcycle", "bicycle", "bus", "truck", "car"]
# Raqabah's folder names and the severity classes of the accident exports -> the three accident folders
SEVERITY_MAP = {"minor": "moderate", "moderate": "moderate", "severe": "severe",
                "severe_car_flipped": "severe", "severe_car_fire": "fire", "fire": "fire"}
# UVH-26 sub-types of the classes that merge several of them: car, bus, truck
SUBTYPES = {v: sorted(slug(k) for k, c in UVH26_MAP.items() if c == v)
            for v in set(UVH26_MAP.values()) - {None} if list(UVH26_MAP.values()).count(v) > 1}

LABELS, CANDIDATES, CLIPS = "labels", "candidates", "clips"

# category -> {sub-folder ("" = the category folder itself): (filled from, how)}
TREE = {
    **{f"01_vehicles/{v}": ({**{s: (LABELS, f"UVH-26 '{s}' boxes") for s in SUBTYPES[v]},
                             "unspecified": (LABELS, f"{v} boxes from sources without sub-types")}
                            if v in SUBTYPES else {"": (LABELS, f"{v} boxes")})
       for v in VEHICLES},
    "02_number_plates": {**{v: (LABELS, f"license_plate box inside a {v} box") for v in VEHICLES},
                         "no_vehicle_box": (LABELS, "license_plate box with no labeled vehicle around it")},
    "03_potholes": {
        "single": (LABELS, "exactly 1 pothole box"),
        "multiple": (LABELS, "2 or more pothole boxes"),
        "rainwater_filled": (CANDIDATES, "SigLIP: pothole crop holds water"),
        "construction_holes": (CANDIDATES, "SigLIP: trench dug in the road"),
    },
    "04_persons": {
        "crossing_at_zebra_crossing": (CANDIDATES, "person's feet inside a zebra_crossing box"),
        "crossing_without_zebra_crossing": (CANDIDATES, "SigLIP: pedestrian crossing a road with no crosswalk"),
        "walking_on_roadside": (CANDIDATES, "SigLIP: pedestrian on the unpaved road edge"),
        "walking_on_footpath": (CANDIDATES, "SigLIP: pedestrian on a raised footpath"),
    },
    "05_road_construction": {"": (CANDIDATES, "SigLIP: construction work on or beside the road")},
    "06_road_accidents": {
        "moderate": (CANDIDATES, "dented / lightly damaged vehicles -- the export's own class, else SigLIP"),
        "severe": (CANDIDATES, "crushed or overturned vehicles -- the export's own class, else SigLIP"),
        "fire": (CANDIDATES, "burning vehicles -- a crash box plus a fire box, else SigLIP"),
    },
    "07_lane_change": {"": (CLIPS, "event engine lane_change on a fixed camera (extract_lane_change_clips.py)")},
    "08_wrong_side_driving": {"": (CLIPS, "event engine wrong_side_driving -- needs fixed-camera video "
                                          "with lane directions drawn on the Road Maps page")},
    "09_roadside_parked_vehicles": {"": (CANDIDATES, "SigLIP: vehicle parked at the road edge")},
}


def folder_path(category, sub):
    return f"{category}/{sub}" if sub else category


def share(folder, target=TARGET):
    """A folder's equal share of its category's target -- the cap for scripts that fill candidate folders."""
    for category, subs in TREE.items():
        if any(folder_path(category, s) == folder for s in subs):
            return TARGETS.get(category, target) // len(subs)
    raise KeyError(f"{folder} is not in build_categories.TREE")


def count(folder, kind):
    """Real items in a folder another script fills: clips count once (not their preview .jpg), and
    augmented copies this script added earlier don't count as real images."""
    ext = ".mp4" if kind == CLIPS else ".jpg"
    return sum(p.suffix.lower() == ext and "_aug" not in p.stem
               for p in folder.iterdir()) if folder.is_dir() else 0


def labeled_images():
    """(source, image, [(class id, x0, y0, x1, y1)]) for every converted image, reviewed labels first."""
    for src in sorted(p for p in SOURCES.iterdir() if p.is_dir()):
        for split_dir in sorted(p for p in src.iterdir() if (p / "images").is_dir()):
            for img in sorted(p for p in (split_dir / "images").iterdir() if p.suffix.lower() in IMAGE_EXTS):
                lbl, _ = label_for(split_dir, img.stem)
                boxes = []
                for row in (l.split() for l in (lbl.read_text().splitlines() if lbl else []) if l.strip()):
                    cx, cy, w, h = map(float, row[1:5])
                    boxes.append((int(row[0]), cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2))
                yield src.name, img, boxes


def plate_kinds(boxes):
    """Vehicle type under each plate box: the smallest vehicle box holding the plate's centre."""
    vehicles = [b for b in boxes if CLASSES[b[0]] in VEHICLES]
    kinds = set()
    for p in (b for b in boxes if b[0] == CLASS_IDS["license_plate"]):
        cx, cy = (p[1] + p[3]) / 2, (p[2] + p[4]) / 2
        around = [v for v in vehicles if v[1] <= cx <= v[3] and v[2] <= cy <= v[4]]
        kinds.add(CLASSES[min(around, key=lambda v: (v[3] - v[1]) * (v[4] - v[2]))[0]] if around
                  else "no_vehicle_box")
    return kinds


def accident_severity():
    """(source, image stem) -> 'moderate' / 'severe' / 'fire' where a source states it: an export's own
    severity classes (accident_severity_source.jsonl, convert_yolo_sources.py) and Raqabah's folders.
    Crashes no source rates are left out, for sort_scene_categories.py to score."""
    out = {}
    for path in SOURCES.glob("*/accident_severity_source.jsonl"):
        for row in map(json.loads, path.read_text().splitlines()):
            out[(path.parent.name, row["image"])] = SEVERITY_MAP[row["severity"]]
    for stem, folder in raqabah_severity().items():
        out[("raqabah", stem)] = SEVERITY_MAP[folder]
    return out


def dedupe_by_hash(images):
    """Drop copies of the same photo: the accident exports re-upload each other's images (amedeograndi
    and hackcimat share whole collections). 64-bit difference hash of the grayscale image, cached per
    file so a re-run only hashes new images. Keeps the first path in sorted order."""
    cache_path, cache, new = CACHE / "accident_hashes.jsonl", {}, []
    if cache_path.is_file():
        for row in map(json.loads, cache_path.read_text().splitlines()):
            cache[row["image"]] = row["hash"]
    for img in images:
        key = str(img.relative_to(ROOT))
        if key in cache:
            continue
        gray = cv2.imread(str(img), cv2.IMREAD_GRAYSCALE)
        if gray is None:
            continue
        small = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA)
        bits = "".join("1" if b else "0" for b in (small[:, 1:] > small[:, :-1]).flatten())
        cache[key] = f"{int(bits, 2):016x}"
        new.append({"image": key, "hash": cache[key]})
    if new:
        CACHE.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "a") as f:
            f.writelines(json.dumps(row) + "\n" for row in new)

    seen, keep = set(), []
    for img in images:
        h = cache.get(str(img.relative_to(ROOT)))
        if h is not None and h not in seen:
            seen.add(h)
            keep.append(img)
    if len(keep) < len(images):
        print(f"06_road_accidents: {len(images) - len(keep)} duplicate images dropped ({len(keep)} left)")
    return keep


def add_rarest(pool, images):
    """images: {image: (detail, {sub-folders})}. An image that fits several sub-folders fills the rarest one."""
    freq = Counter(k for _, kinds in images.values() for k in kinds)
    for img, (detail, kinds) in images.items():
        pool[min(kinds, key=lambda k: (freq[k], k))][img] = detail


def label_pools():
    """category -> sub-folder -> {image: detail}, for the folders decided by labels."""
    pools = defaultdict(lambda: defaultdict(dict))
    if SELECTION.is_file():
        with open(SELECTION, newline="") as f:
            for row in csv.DictReader(f):
                cls = row["class"]
                if cls in VEHICLES:
                    sub = row["subfolder"] if row["subfolder"] in SUBTYPES.get(cls, []) \
                        else "unspecified" if cls in SUBTYPES else ""
                    pools[f"01_vehicles/{cls}"][sub][ROOT / row["image"]] = f"{row['split']}, {row['subfolder']}"
    else:
        print(f"{SELECTION.relative_to(ROOT)} missing -- run balance_v6_dataset.py first; 01_vehicles stays empty")

    # images the scene sorter already put in a pothole candidate folder aren't repeated in single/multiple
    moved = set()
    for idx in (OUT / "_index").glob("candidates_*.csv"):
        with open(idx, newline="") as f:
            moved |= {ROOT / r["source_image"] for r in csv.DictReader(f) if r["folder"].startswith("03_potholes/")}

    plates = {}
    for source, img, boxes in labeled_images():
        kinds = plate_kinds(boxes)
        if kinds:
            plates[img] = (source, kinds)
        n = sum(b[0] == CLASS_IDS["pothole"] for b in boxes)
        if n and img not in moved:
            pools["03_potholes"]["single" if n == 1 else "multiple"][img] = f"{source}, {n} pothole boxes"

    add_rarest(pools["02_number_plates"], plates)
    return pools


def augment(image, variant, rng):
    """A visibly different copy for topping up a short sub-folder: copy 1 is mirrored; later copies
    are also cropped to 85-95% and get a brightness / contrast change."""
    out = cv2.flip(image, 1)
    if variant > 1:
        h, w = out.shape[:2]
        scale = rng.uniform(0.85, 0.95)
        ch, cw = int(h * scale), int(w * scale)
        y, x = rng.randint(0, h - ch), rng.randint(0, w - cw)
        out = cv2.resize(out[y:y + ch, x:x + cw], (w, h))
        out = cv2.convertScaleAbs(out, alpha=rng.uniform(0.8, 1.2), beta=rng.uniform(-25, 25))
    return out


def fill_labels(rel, pool, quota, max_repeat, rng, index):
    """Link up to quota real images into the folder, then augmented copies up to
    min(quota, real x max_repeat). Returns (real, augmented)."""
    folder = OUT / rel
    real = rng.sample(sorted(pool), min(len(pool), quota))
    for img in real:
        link(img, folder / img.name)
        index.append({"folder": rel, "file": img.name, "source_image": str(img.relative_to(ROOT)), "detail": pool[img]})
    copies = max(0, min(quota, int(len(real) * max_repeat)) - len(real))
    for k in range(copies):
        img = real[k % len(real)]
        variant = k // len(real) + 1
        name = f"{img.stem}_aug{variant}.jpg"
        cv2.imwrite(str(folder / name), augment(cv2.imread(str(img)), variant, rng), [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        index.append({"folder": rel, "file": name, "source_image": str(img.relative_to(ROOT)),
                      "detail": f"augmented copy {variant}"})
    return len(real), copies


def augment_folder(folder, quota, max_repeat, rng):
    """Top up a folder another script filled (AUGMENT_CANDIDATES) with augmented copies of its own
    images, to at most max_repeat x what it really has. Old copies are rebuilt every run."""
    for old in folder.glob("*_aug*.jpg"):
        old.unlink()
    real = sorted(p for p in folder.iterdir() if p.suffix.lower() == ".jpg")
    copies = max(0, min(quota, int(len(real) * max_repeat)) - len(real)) if real else 0
    for k in range(copies):
        src = real[k % len(real)]
        variant = k // len(real) + 1
        cv2.imwrite(str(folder / f"{src.stem}_aug{variant}.jpg"), augment(cv2.imread(str(src)), variant, rng),
                    [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    return copies


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=TARGET, help=f"images per category (except {list(TARGETS)})")
    ap.add_argument("--max-repeat", type=float, default=MAX_REPEAT,
                    help="a short sub-folder is topped up with augmented copies to at most this x its real images")
    args = ap.parse_args()

    rng = random.Random(SEED)
    pools = label_pools()
    index, report = [], []
    for category, subs in TREE.items():
        owned = pools.get(category, {})
        target = TARGETS.get(category, args.target)
        quota = target // len(subs)
        if all(kind == LABELS for kind, _ in subs.values()):
            shutil.rmtree(OUT / category, ignore_errors=True)  # fully rebuilt here, so no stale sub-folder survives

        rows = []
        for sub, (kind, how) in subs.items():
            rel = folder_path(category, sub)
            (OUT / rel).mkdir(parents=True, exist_ok=True)
            if kind == LABELS:
                real, aug = fill_labels(rel, owned.get(sub, {}), quota, args.max_repeat, rng, index)
            else:
                real, aug = min(count(OUT / rel, kind), quota), 0
                if category in AUGMENT_CANDIDATES:
                    aug = augment_folder(OUT / rel, quota, args.max_repeat, rng)
            if real == 0 and not any((OUT / rel).iterdir()):
                (OUT / rel / "README.txt").write_text(f"Empty -- {kind}: {how}.\n")
            rows.append((sub, real, aug, kind, how))

        unsorted = {s: pool for s, pool in owned.items() if s not in subs}  # e.g. crashes with no vehicle type
        for sub, pool in unsorted.items():
            rel = folder_path(category, sub)
            (OUT / rel).mkdir(parents=True, exist_ok=True)
            for img in sorted(pool):
                link(img, OUT / rel / img.name)
                index.append({"folder": rel, "file": img.name, "source_image": str(img.relative_to(ROOT)),
                              "detail": pool[img]})
        report.append((category, target, quota, rows, {s: len(p) for s, p in unsorted.items()}))

    (OUT / "_index").mkdir(parents=True, exist_ok=True)
    with open(OUT / "_index" / "categories.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["folder", "file", "source_image", "detail"])
        writer.writeheader()
        writer.writerows(index)

    lines = ["# NH5 dataset -- categories", "",
             f"Target: **{args.target:,} images per category** "
             f"({', '.join(f'{c}: {t:,}' for c, t in TARGETS.items())}), split **equally** across its sub-folders. "
             f"A short sub-folder is topped up with augmented copies (mirror, crop, brightness) to at most "
             f"{args.max_repeat:g}x its real images; the rest is listed as missing and needs new images.",
             f"Rebuilt {date.today()} by `scripts/v6/build_categories.py`; real images are hard links into "
             "`datasets/v6/sources/`, and `_index/` lists where every file came from.", "",
             "- **labels** -- decided by dataset boxes or labels",
             "- **candidates** -- sorted by an image-text model (red box = the reason); delete the wrong ones",
             "- **clips** -- one video clip per event; a single photo can't show direction or a lane crossing", "",
             "| folder | images | real | augmented | target | missing | filled from |",
             "|---|---:|---:|---:|---:|---:|---|"]
    print(f"{'folder':<52}{'images':>8}{'real':>8}{'aug':>8}{'target':>8}{'missing':>9}")
    for category, target, quota, rows, unsorted in report:
        real, aug = sum(r[1] for r in rows), sum(r[2] for r in rows)
        own = next((f"{kind}: {how}" for sub, _, _, kind, how in rows if not sub), "")
        lines.append(f"| **{category}** | **{real + aug:,}** | {real:,} | {aug:,} | {target:,} | "
                     f"{max(0, target - real - aug):,} | {own} |")
        print(f"{category:<52}{real + aug:>8}{real:>8}{aug:>8}{target:>8}{max(0, target - real - aug):>9}")
        for sub, r, a, kind, how in rows:
            if sub:
                lines.append(f"| &nbsp;&nbsp;&nbsp;{sub} | {r + a:,} | {r:,} | {a:,} | {quota:,} | "
                             f"{max(0, quota - r - a):,} | {kind}: {how} |")
                print(f"  {sub:<50}{r + a:>8}{r:>8}{a:>8}{quota:>8}{max(0, quota - r - a):>9}")
        for sub, n in unsorted.items():
            lines.append(f"| &nbsp;&nbsp;&nbsp;{sub} | {n:,} | {n:,} | | not counted | | vehicle type not found -- sort by hand |")
            print(f"  {sub:<50}{n:>8}  (not counted)")
    (OUT / "README.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
