#!/usr/bin/env python3
"""Fill the categories/ folders that no dataset label can decide, with an image-text
model (SigLIP, Apache-2.0) scoring crops against short descriptions.

These are CANDIDATES: each output image has the deciding box drawn on it, and
categories/_index/candidates_<task>.csv has the score -- a person still has to delete
the wrong ones. Each folder gets the highest-scoring images up to its equal share of
its category's target (build_categories.share), or --per-folder.

Tasks:
  persons       person boxes from the labels -- run prelabel_missing.py first on sources that
                don't label people (riders on a motorcycle/bicycle are skipped); the
                ground around each person's feet is scored as zebra crossing / open road /
                footpath / road edge. A foot inside a labeled zebra_crossing box counts as
                crossing at the zebra crossing without asking the model.
  potholes      each labeled pothole is scored as holding water or dry
  construction  whole images scored as roadside construction / excavated hole in the road
  parked        labeled cars, autos and trucks scored as parked at the roadside or driving
  accidents     each damaged_vehicle box is scored as a burning / severely wrecked / moderately damaged
                vehicle. Where the export's own class already says it (build_categories.accident_severity)
                the model isn't asked; copies of the same crash across exports are dropped by image hash.

Model scores are cached under datasets/v6/cache/, so a re-run only scores new crops.

Usage (CPU works; a GPU machine is ~20x faster):
  python scripts/v6/sort_scene_categories.py persons --max-images 300
  python scripts/v6/sort_scene_categories.py persons potholes construction parked
  python scripts/v6/build_categories.py     # afterwards, refreshes categories/README.md
"""
import argparse
import csv
import json
import shutil
from pathlib import Path

import cv2
import torch
from PIL import Image

from build_categories import OUT as CATEGORIES, accident_severity, dedupe_by_hash, share
from classes import CLASS_IDS

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ROOT / "datasets" / "v6" / "sources"
CACHE = ROOT / "datasets" / "v6" / "cache"
MODEL_DIR = ROOT / "models" / "zero_shot" / "siglip-so400m-patch14-384"
IMAGE_EXTS = (".jpg", ".jpeg", ".png")

# folder -> descriptions; "_other" soaks up crops that fit none of the folders
PERSON_PROMPTS = {
    "04_persons/crossing_at_zebra_crossing": ["a pedestrian walking across a zebra crossing with white stripes"],
    "04_persons/crossing_without_zebra_crossing": ["a pedestrian crossing the middle of a road with no crosswalk"],
    "04_persons/walking_on_footpath": ["a pedestrian walking on a raised paved sidewalk"],
    "04_persons/walking_on_roadside": ["a pedestrian walking along the unpaved edge of a road"],
    "_other": ["a person standing inside a shop", "a person sitting", "a person riding a motorcycle",
               "a street with no people"],
}
POTHOLE_PROMPTS = {
    "03_potholes/rainwater_filled": ["a pothole filled with rainwater", "a puddle of water in a pothole"],
    "_other": ["a dry pothole in the road", "a dry patch of broken asphalt"],
}
CONSTRUCTION_PROMPTS = {
    # narrow on purpose: warning boards / barricades actually blocking part of a road -- not just
    # any construction site, which pulled in close-ups of workers/PPE with no road in frame
    "05_road_construction": ["road construction warning boards and barricades blocking part of a street",
                             "workers and cones closing off a lane of a road for construction"],
    "03_potholes/construction_holes": ["a large trench dug in the road for construction work"],
    "_other": ["a normal street with traffic", "a road with potholes", "a car accident",
              "a damaged or wrecked vehicle after a crash", "a burning vehicle",
              "emergency responders at a crash scene", "a close-up of a person or safety equipment",
              "an indoor or building construction site with no road in view"],
}
# accidents_*/fire_images/raqabah are crash-photo collections -- even a non-accident frame in them
# risks debris or a stopped vehicle that a scene classifier could confuse for a construction zone,
# so 05_road_construction only draws from sources that aren't inherently accident-themed
CONSTRUCTION_SOURCES = ("uvh26", "dashcam", "cdset", "open_images", "gate_plates", "gujarat_plates",
                        "video_plates", "construction_site_safety", "obstacle_detection",
                        "construction_site_images", "construction_drone_images")
PARKED_PROMPTS = {
    "09_roadside_parked_vehicles": ["a vehicle parked at the side of the road next to the curb"],
    "_other": ["a vehicle driving in traffic in the middle of the road"],
}
ACCIDENT_PROMPTS = {
    "06_road_accidents/fire": ["a vehicle burning after a crash, flames and smoke"],
    "06_road_accidents/severe": ["a crushed or overturned vehicle after a heavy crash",
                                 "a wrecked car torn apart in a collision"],
    "06_road_accidents/moderate": ["a car with dents and moderate collision damage",
                                   "two vehicles in a minor collision on the road"],
    "_other": ["an undamaged vehicle driving on the road", "a street with no accident"],
}
PERSON_SOURCES = ("uvh26", "dashcam", "cdset", "pedestrian_crossing", "pedestrian_generic",
                  "pedestrian_detection_kaggle")
ROAD_SOURCES = ("uvh26", "dashcam", "rdd2022_india")
PARKED_CLASSES = {CLASS_IDS[n] for n in ("car", "auto", "truck")}
RIDE_CLASSES = {CLASS_IDS[n] for n in ("motorcycle", "bicycle")}
MIN_PERSON_PX = 40


def _pooled(output):
    """get_*_features returns a tensor in older transformers, a model output with pooler_output in 5.x."""
    return output if isinstance(output, torch.Tensor) else output.pooler_output


class Scorer:
    """Softmax over prompt similarities, summed per folder."""

    def __init__(self, device, model_dir):
        from transformers import AutoModel, AutoProcessor
        self.device = device
        self.model = AutoModel.from_pretrained(model_dir).to(device).eval()
        self.processor = AutoProcessor.from_pretrained(model_dir)
        self._text = {}

    def _text_features(self, prompts):
        key = tuple(prompts)
        if key not in self._text:
            inputs = self.processor(text=list(prompts), padding="max_length", return_tensors="pt").to(self.device)
            with torch.no_grad():
                feats = _pooled(self.model.get_text_features(**inputs))
            self._text[key] = torch.nn.functional.normalize(feats, dim=-1)
        return self._text[key]

    def score(self, crops, folder_prompts):
        flat = [(folder, p) for folder, ps in folder_prompts.items() for p in ps]
        text = self._text_features([p for _, p in flat])
        inputs = self.processor(images=crops, return_tensors="pt").to(self.device)
        with torch.no_grad():
            img = torch.nn.functional.normalize(_pooled(self.model.get_image_features(**inputs)), dim=-1)
        probs = (100 * img @ text.T).softmax(dim=-1).cpu()
        out = []
        for row in probs:
            per_folder = {}
            for (folder, _), p in zip(flat, row.tolist()):
                per_folder[folder] = per_folder.get(folder, 0.0) + p
            out.append(per_folder)
        return out


def images_with_labels(sources):
    for name in sources:
        for split_dir in sorted(p for p in (SOURCES / name).glob("*") if (p / "images").is_dir()):
            for img in sorted(p for p in (split_dir / "images").iterdir() if p.suffix.lower() in IMAGE_EXTS):
                lbl = split_dir / "labels_reviewed" / f"{img.stem}.txt"
                if not lbl.is_file():
                    lbl = split_dir / "labels" / f"{img.stem}.txt"
                rows = [l.split() for l in lbl.read_text().splitlines() if l.strip()] if lbl.is_file() else []
                boxes = [(int(r[0]), *xywhn_to_xyxyn(*map(float, r[1:5]))) for r in rows]
                yield name, img, boxes


def xywhn_to_xyxyn(cx, cy, w, h):
    return cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2


def crop(image, box, grow_x, grow_up, grow_down):
    """Pixel crop around a normalized xyxy box, grown by multiples of its size."""
    h, w = image.shape[:2]
    x0, y0, x1, y1 = box[0] * w, box[1] * h, box[2] * w, box[3] * h
    bw, bh = x1 - x0, y1 - y0
    cx0, cx1 = max(0, int(x0 - grow_x * bw)), min(w, int(x1 + grow_x * bw))
    cy0, cy1 = max(0, int(y0 - grow_up * bh)), min(h, int(y1 + grow_down * bh))
    return Image.fromarray(cv2.cvtColor(image[cy0:cy1, cx0:cx1], cv2.COLOR_BGR2RGB))


def contains(outer, inner, min_share=0.5):
    ix = max(0.0, min(outer[2], inner[2]) - max(outer[0], inner[0]))
    iy = max(0.0, min(outer[3], inner[3]) - max(outer[1], inner[1]))
    area = (inner[2] - inner[0]) * (inner[3] - inner[1])
    return area > 0 and ix * iy / area >= min_share


def load_cache(path):
    return {r["key"]: r for r in map(json.loads, path.read_text().splitlines())} if path.is_file() else {}


def candidates(task, args):
    """(image path, deciding xyxyn box, crop kwargs, fixed folder or None) per crop to score."""
    if task == "persons":
        for source in PERSON_SOURCES:
            for n, (_, img, boxes) in enumerate(images_with_labels([source])):
                if args.max_images and n >= args.max_images:
                    break
                persons = [b[1:] for b in boxes if b[0] == CLASS_IDS["person"]]
                if not persons:
                    continue
                rides = [b[1:] for b in boxes if b[0] in RIDE_CLASSES]
                zebras = [b[1:] for b in boxes if b[0] == CLASS_IDS["zebra_crossing"]]
                h = cv2.imread(str(img), cv2.IMREAD_REDUCED_GRAYSCALE_4).shape[0] * 4
                for p in persons:
                    if (p[3] - p[1]) * h < MIN_PERSON_PX or any(contains(r, p, 0.4) for r in rides):
                        continue
                    foot = ((p[0] + p[2]) / 2, p[3])
                    on_zebra = any(z[0] <= foot[0] <= z[2] and z[1] <= foot[1] <= z[3] for z in zebras)
                    yield img, p, dict(grow_x=1.5, grow_up=0.3, grow_down=0.8), \
                        "04_persons/crossing_at_zebra_crossing" if on_zebra else None
    elif task == "potholes":
        for name, img, boxes in images_with_labels([p.name for p in SOURCES.iterdir() if p.is_dir()]):
            for b in boxes:
                if b[0] == CLASS_IDS["pothole"]:
                    yield img, b[1:], dict(grow_x=0.3, grow_up=0.3, grow_down=0.3), None
    elif task == "construction":
        # every non-accident source, not just ROAD_SOURCES: real roadside construction is rare, so
        # this needs a wide pool (dashcam, open_images, obstacle/construction-site photos, ...) to
        # have a chance at reaching the 20k target -- but never the accident/fire/crash collections,
        # where a wrecked vehicle or debris could be mistaken for a construction zone
        for name, img, _ in images_with_labels([n for n in CONSTRUCTION_SOURCES if (SOURCES / n).is_dir()]):
            yield img, (0.0, 0.0, 1.0, 1.0), dict(grow_x=0, grow_up=0, grow_down=0), None
    elif task == "parked":
        for name, img, boxes in images_with_labels(ROAD_SOURCES):
            for b in boxes:
                if b[0] in PARKED_CLASSES and (b[3] - b[1]) * (b[4] - b[2]) >= 0.004:
                    yield img, b[1:], dict(grow_x=1.0, grow_up=0.3, grow_down=0.6), None
    elif task == "accidents":
        severity, wanted = accident_severity(), []
        for name, img, boxes in images_with_labels([p.name for p in SOURCES.iterdir() if p.is_dir()]):
            crash = [b[1:] for b in boxes if b[0] == CLASS_IDS["damaged_vehicle"]]
            fixed = severity.get((name, img.stem))
            if name == "fire_images":  # collected burning-vehicle candidates: no boxes, SigLIP decides
                wanted.append((img, (0.0, 0.0, 1.0, 1.0), None))
                continue
            if crash or fixed:  # Raqabah has severity but no boxes yet -- score its whole image
                biggest = max(crash, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]), default=(0.0, 0.0, 1.0, 1.0))
                wanted.append((img, biggest, fixed))
        keep = set(dedupe_by_hash([img for img, _, _ in wanted]))  # the exports re-upload each other's photos
        for img, box, fixed in wanted:
            if img in keep:
                yield img, box, dict(grow_x=0.35, grow_up=0.35, grow_down=0.35), \
                    (f"06_road_accidents/{fixed}" if fixed else None)


PROMPTS = {"persons": PERSON_PROMPTS, "potholes": POTHOLE_PROMPTS, "construction": CONSTRUCTION_PROMPTS,
           "parked": PARKED_PROMPTS, "accidents": ACCIDENT_PROMPTS}


def run(task, scorer, args):
    prompts = PROMPTS[task]
    cache_path = CACHE / f"scores_{task}.jsonl"
    cache = load_cache(cache_path)
    batch, best = [], {}  # best: (folder, image) -> (score, box)

    def flush():
        crops = [crop(cv2.imread(str(img)), box, **kw) for img, box, kw, _, _ in batch]
        with open(cache_path, "a") as f:
            for (img, box, _, _, key), scores in zip(batch, scorer.score(crops, prompts)):
                cache[key] = {"key": key, "scores": scores}
                f.write(json.dumps(cache[key]) + "\n")
        batch.clear()

    items = list(candidates(task, args))
    if task in ("construction", "parked") and args.max_images:
        keep = set(sorted({img for img, *_ in items})[:args.max_images])
        items = [it for it in items if it[0] in keep]
    for n, (img, box, kw, fixed) in enumerate(items):
        key = f"{img}|{','.join(f'{v:.4f}' for v in box)}"
        if fixed is None and key not in cache:
            batch.append((img, box, kw, fixed, key))
            if len(batch) == args.batch:
                flush()
                print(f"  [{task}] scored {n + 1}/{len(items)} crops")
    if batch:
        flush()

    for img, box, kw, fixed in items:
        key = f"{img}|{','.join(f'{v:.4f}' for v in box)}"
        if fixed:
            folder, score = fixed, 1.0
        else:
            scores = {k: v for k, v in cache[key]["scores"].items() if k != "_other"}
            folder, score = max(scores.items(), key=lambda kv: kv[1])
            if score < args.min_score or score < cache[key]["scores"].get("_other", 0):
                continue
        if score > best.get((folder, img), (0,))[0]:
            best[(folder, img)] = (score, box)

    rows = []
    for folder in [f for f in prompts if f != "_other"]:
        out = CATEGORIES / folder
        out.mkdir(parents=True, exist_ok=True)
        for p in out.glob("*"):
            p.unlink()
        cap = args.per_folder or share(folder)
        ranked = sorted(((s, img, box) for (f, img), (s, box) in best.items() if f == folder), reverse=True)
        for rank, (score, img, box) in enumerate(ranked[:cap], 1):
            image = cv2.imread(str(img))
            h, w = image.shape[:2]
            if box != (0.0, 0.0, 1.0, 1.0):
                cv2.rectangle(image, (int(box[0] * w), int(box[1] * h)), (int(box[2] * w), int(box[3] * h)),
                              (0, 0, 255), max(2, w // 400))
            name = f"{rank:04d}_{img.stem}.jpg"
            cv2.imwrite(str(out / name), image, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
            rows.append({"folder": folder, "file": name, "source_image": str(img.relative_to(ROOT)),
                         "score": round(score, 3), "box_xyxyn": ",".join(f"{v:.4f}" for v in box)})
        readme = out / "README.txt"
        readme.write_text(f"CANDIDATES sorted by an image-text model (best first, red box = the reason). "
                          f"Delete wrong ones.\n{len(ranked[:cap])} images (cap {cap}), from "
                          f"{len(ranked)} above score {args.min_score}.\n")
        print(f"{folder:<45}{min(len(ranked), cap):>6} (of {len(ranked)} candidates, cap {cap})")
    (CATEGORIES / "_index").mkdir(parents=True, exist_ok=True)
    with open(CATEGORIES / "_index" / f"candidates_{task}.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["folder", "file", "source_image", "score", "box_xyxyn"])
        writer.writeheader()
        writer.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tasks", nargs="+", choices=list(PROMPTS))
    ap.add_argument("--max-images", type=int, default=None, help="per source (persons) or in total (smoke test)")
    ap.add_argument("--model", type=Path, default=MODEL_DIR,
                    help="SigLIP folder; on CPU use models/zero_shot/siglip-base-patch16-224 (the default "
                         "so400m scores ~0.4 crops/s there)")
    ap.add_argument("--per-folder", type=int, default=None,
                    help="default: the folder's equal share of its category target")
    ap.add_argument("--min-score", type=float, default=0.5)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = ap.parse_args()

    CACHE.mkdir(parents=True, exist_ok=True)
    scorer = Scorer(args.device, args.model)
    for task in args.tasks:
        run(task, scorer, args)


if __name__ == "__main__":
    main()
