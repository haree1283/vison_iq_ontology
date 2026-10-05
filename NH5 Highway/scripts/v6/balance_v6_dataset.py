#!/usr/bin/env python3
"""Class-balanced v6 training set under datasets/v6/training/detector_yolo/: up to --target
images per class, shared evenly across each class's sub-folders.

Why: in the plain merge (build_v6_dataset.py) motorcycle is in ~9k train images
and barricade in 32, so the detector practises one ~300x more than the other.
Here every class aims at the same image count.

Rules (decided 2026-09-15):
- an image counts for a class when it has a visible box of it (MIN_BOX_AREA)
- classes with more than --target images are cut down to --target
- inside a class, sub-folders (see subfolder_options) get equal shares; a short
  sub-folder uses all of its images and its siblings share the rest
- classes with fewer than --target real images use all of them and, in train
  only, repeat images up to --max-repeat times (default 3). More copies than
  that and the model memorises those few images instead of learning the class,
  so the report lists each class's shortfall -- that gap needs new labeled
  images, not copies. A copy repeats every class in the image, so copies stop
  as soon as any class in it reaches --target (a rare class that always shares
  frames with a common one can't be copied far).
- val/test are balanced to --val-target with no repeats, so every class's mAP
  is measured on a similar number of images
- an image usually holds several classes (a UVH-26 frame has cars, autos and
  motorcycles). Rarest classes pick first and later picks prefer images that
  don't add to classes already at target, but common classes can still end up
  above target through images chosen for other classes -- dropping those boxes
  instead would teach the detector that the objects are background.
- empty images (background) are capped per source at --neg-ratio x its chosen
  images, as in build_v6_dataset.py

Output under training/detector_yolo/ (hard links, so almost no extra disk):
  {train,val,test}/{images,labels}   repeats get an _rN suffix
  data.yaml, balance_report.json
  selection.csv                      chosen image -> class, sub-folder, copies (build_categories.py reads it)
To move it to the GPU machine, tar it (tar keeps the hard links, so repeats aren't
stored twice; scp -r would copy every repeat as a full file).

Usage:
  python scripts/v6/balance_v6_dataset.py
  python scripts/v6/balance_v6_dataset.py --target 10000 --max-repeat 3 --val-target 1000
  python scripts/v6/balance_v6_dataset.py --release     # refuses while review is unfinished
"""
import argparse
import csv
import json
import math
import os
import random
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from build_v6_dataset import IMAGE_EXTS, REVIEW_EVERY_IMAGE, SEED, label_for, unreviewed
from classes import CLASS_IDS, CLASSES, RAQABAH_SEVERITY, UVH26_MAP
from convert_uvh26 import RAW as UVH26_RAW, SPLITS as UVH26_SPLITS

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ROOT / "datasets" / "v6" / "sources"
OUT = ROOT / "datasets" / "v6" / "training" / "detector_yolo"
RAQABAH_RAW = ROOT / "datasets" / "v6" / "raw" / "kaggle" / "raqabah-multi-severity-car-accident-dataset" \
    / "Raqabah_Car_Accident_Dataset"

DEFAULT_MIN_BOX_AREA = 0.001               # fraction of the image, ~45x45 px at 1080p
MIN_BOX_AREA = {"license_plate": 0.0002}   # plates are small even up close


def min_area(cls_name):
    return MIN_BOX_AREA.get(cls_name, DEFAULT_MIN_BOX_AREA)


def slug(name):
    return name.lower().replace("-", "_")


@dataclass
class Item:
    source: str
    split: str
    image: Path
    lines: list
    options: dict = field(default_factory=dict)  # class id -> sub-folders this image could fill
    sub: dict = field(default_factory=dict)      # class id -> the one sub-folder it fills


def uvh26_subtypes():
    """uvh26 image stem -> {class id: UVH-26 sub-types with a visible box}, for classes
    that merge several UVH-26 categories (car = hatchback/sedan/suv/muv/van, ...)."""
    merged = Counter(v for v in UVH26_MAP.values() if v)
    out = defaultdict(lambda: defaultdict(set))
    for folder, ann_file in UVH26_SPLITS.values():
        path = UVH26_RAW / folder / ann_file
        if not path.is_file():
            continue
        coco = json.loads(path.read_text())
        cats = {c["id"]: c["name"] for c in coco["categories"]}
        images = {im["id"]: im for im in coco["images"]}
        for ann in coco["annotations"]:
            name = cats[ann["category_id"]]
            v6 = UVH26_MAP.get(name)
            if not v6 or merged[v6] < 2:
                continue
            im = images[ann["image_id"]]
            if ann["bbox"][2] * ann["bbox"][3] >= min_area(v6) * im["width"] * im["height"]:
                out[f"uvh26_{Path(im['file_name']).stem}"][CLASS_IDS[v6]].add(slug(name))
    return out


def raqabah_severity():
    return {f"raqabah_{p.stem}": folder for raw_folder, folder in RAQABAH_SEVERITY.items()
            for p in (RAQABAH_RAW / raw_folder).rglob("*") if p.suffix.lower() in IMAGE_EXTS}


def subfolder_options(item, boxes, uvh26, severity):
    """class id -> set of sub-folders, from the image's visible boxes."""
    options = {}
    for cls, count in Counter(b for b in boxes).items():
        name = CLASSES[cls]
        if name == "pothole":
            options[cls] = {"single" if count == 1 else "multiple"}
        elif name == "damaged_vehicle" and item.image.stem in severity:
            options[cls] = {severity[item.image.stem]}
        else:
            options[cls] = uvh26.get(item.image.stem, {}).get(cls) or {item.source}
    return options


def load_split_items(names, uvh26, severity):
    """split -> ([items with a visible box], {source: [empty items]})"""
    labeled, empty = defaultdict(list), defaultdict(lambda: defaultdict(list))
    for name in names:
        src_root = SOURCES / name
        skip = unreviewed(src_root, name) if name in REVIEW_EVERY_IMAGE else set()
        for split_dir in sorted(p for p in src_root.iterdir() if (p / "images").is_dir()):
            split = split_dir.name
            for img in sorted(p for p in (split_dir / "images").iterdir() if p.suffix.lower() in IMAGE_EXTS):
                if (split, img.stem) in skip:
                    continue  # placeholder labels, the classes in it aren't drawn yet
                lbl, _ = label_for(split_dir, img.stem)
                lines = [l for l in lbl.read_text().splitlines() if l.strip()] if lbl else []
                item = Item(name, split, img, lines)
                if not lines:
                    empty[split][name].append(item)
                    continue
                rows = [l.split() for l in lines]
                visible = [int(r[0]) for r in rows
                           if float(r[3]) * float(r[4]) >= min_area(CLASSES[int(r[0])])]
                item.options = subfolder_options(item, visible, uvh26, severity)
                if item.options:
                    labeled[split].append(item)

    # an image that fits several sub-folders (a hatchback and a van) fills the rarest one
    for items in labeled.values():
        freq = defaultdict(Counter)
        for it in items:
            for cls, subs in it.options.items():
                freq[cls].update(subs)
        for it in items:
            it.sub = {cls: min(subs, key=lambda s: (freq[cls][s], s)) for cls, subs in it.options.items()}
    return labeled, empty


def waterfill(total, capacity):
    """Share total across groups as evenly as capacity allows: a group that can't
    take its share keeps all it has and the rest is split among the others."""
    quota, left = {}, total
    groups = sorted(capacity, key=lambda g: (capacity[g], g))
    for i, g in enumerate(groups):
        quota[g] = min(capacity[g], left // (len(groups) - i))
        left -= quota[g]
    return quota


def select(items, target, rng):
    """Indices of the chosen items, rarest class first."""
    by_class = defaultdict(lambda: defaultdict(list))
    for i, it in enumerate(items):
        for cls, sub in it.sub.items():
            by_class[cls][sub].append(i)

    chosen, count = set(), Counter()
    for cls in sorted(by_class, key=lambda c: sum(map(len, by_class[c].values()))):
        quota = waterfill(target, {s: len(idx) for s, idx in by_class[cls].items()})
        full = {c for c, n in count.items() if n >= target}
        for sub, idx in by_class[cls].items():
            need = quota[sub] - sum(i in chosen for i in idx)
            if need <= 0:
                continue
            fresh = [i for i in idx if i not in chosen]
            rng.shuffle(fresh)
            fresh.sort(key=lambda i: len(items[i].sub.keys() & full))  # stable sort keeps the shuffle as tie-break
            for i in fresh[:need]:
                chosen.add(i)
                count.update(items[i].sub.keys())
    return chosen


def repeat_copies(items, chosen, target, max_repeat, rng):
    """item index -> copies (>= 1). Short classes, rarest first, get extra copies of
    their images up to max_repeat in all, one round at a time so the copies spread
    over every image, and split so the sub-folders stay as even as possible.
    A copy is added only while every class in the image is below target: copying a
    bus frame also copies its cars and motorcycles, and those mustn't overshoot."""
    copies = {i: 1 for i in chosen}
    total, sub_total = Counter(), defaultdict(Counter)
    by_class = defaultdict(lambda: defaultdict(list))
    for i in chosen:
        for cls, sub in items[i].sub.items():
            by_class[cls][sub].append(i)
            total[cls] += 1
            sub_total[cls][sub] += 1

    for cls in sorted(by_class, key=lambda c: total[c]):
        if total[cls] >= target:
            continue
        subs = by_class[cls]
        quota = waterfill(target, {s: int(len(idx) * max_repeat) for s, idx in subs.items()})
        for rnd in range(1, math.ceil(max_repeat)):
            for sub, idx in subs.items():
                order = idx[:]
                rng.shuffle(order)
                for i in order:
                    if sub_total[cls][sub] >= quota[sub]:
                        break
                    if copies[i] > rnd or copies[i] + 1 > max_repeat:
                        continue
                    if any(total[k] >= target for k in items[i].sub):
                        continue
                    copies[i] += 1
                    for k, s in items[i].sub.items():
                        total[k] += 1
                        sub_total[k][s] += 1
    return copies


def link(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and dst.samefile(src):
        return  # a previous run already linked this exact file here
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def build_split(split, items, empties, target, max_repeat, neg_ratio, rng, selection):
    chosen = select(items, target, rng)
    copies = repeat_copies(items, chosen, target, max_repeat, rng) if max_repeat > 1 else {i: 1 for i in chosen}

    per_source = Counter(items[i].source for i in chosen)
    negatives = []
    for source, pool in empties.items():
        pool = pool[:]
        rng.shuffle(pool)
        negatives += pool[:int(per_source[source] * neg_ratio)]

    available = defaultdict(Counter)
    for it in items:
        for cls, sub in it.sub.items():
            available[cls][sub] += 1
    distinct, effective = defaultdict(Counter), Counter()

    img_dir, lbl_dir = OUT / split / "images", OUT / split / "labels"
    for i in sorted(chosen, key=lambda i: items[i].image.name):
        it = items[i]
        for k in range(copies[i]):
            stem = it.image.stem if k == 0 else f"{it.image.stem}_r{k}"
            link(it.image, img_dir / f"{stem}{it.image.suffix}")
            (lbl_dir / f"{stem}.txt").write_text("\n".join(it.lines) + "\n")
        for cls, sub in it.sub.items():
            distinct[cls][sub] += 1
            effective[cls] += copies[i]
            selection.append({"split": split, "image": str(it.image.relative_to(ROOT)), "class": CLASSES[cls],
                              "subfolder": sub, "copies": copies[i]})
    for it in negatives:
        link(it.image, img_dir / it.image.name)
        (lbl_dir / f"{it.image.stem}.txt").write_text("")

    report = {"target": target, "images": sum(1 for _ in img_dir.iterdir()) if img_dir.is_dir() else 0,
              "distinct_labeled_images": len(chosen), "background_images": len(negatives), "classes": {}}
    for cls, name in enumerate(CLASSES):
        n = sum(distinct[cls].values())
        report["classes"][name] = {
            "available": sum(available[cls].values()), "distinct": n, "with_repeats": effective[cls],
            "shortfall": max(0, target - n),
            "subfolders": {s: {"available": available[cls][s], "chosen": distinct[cls][s]}
                           for s in sorted(available[cls])},
        }
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=10000, help="images per class in train")
    ap.add_argument("--max-repeat", type=float, default=3.0, help="most copies of an image in a short class")
    ap.add_argument("--val-target", type=int, default=1000, help="images per class in val and test (no repeats)")
    ap.add_argument("--neg-ratio", type=float, default=0.15)
    ap.add_argument("--sources", nargs="*", help="default: every converted source")
    ap.add_argument("--release", action="store_true")
    args = ap.parse_args()

    names = args.sources or sorted(p.name for p in SOURCES.iterdir()
                                   if p.is_dir() and any((p / s / "images").is_dir() for s in ("train", "val", "test")))
    pending = {n: c for n in names if (c := len(unreviewed(SOURCES / n, n)))}
    if pending:
        msg = "unreviewed images: " + ", ".join(f"{n} {c}" for n, c in pending.items())
        if args.release:
            raise SystemExit(f"--release refused, {msg}")
        print(f"DRAFT build -- {msg} (pre-labels used as-is; don't ship a model trained on this)")

    labeled, empty = load_split_items(names, uvh26_subtypes(), raqabah_severity())
    shutil.rmtree(OUT, ignore_errors=True)
    rng, selection = random.Random(SEED), []
    report = {"draft": bool(pending), "unreviewed": pending, "max_repeat": args.max_repeat,
              "neg_ratio": args.neg_ratio, "splits": {}}
    for split in ("train", "val", "test"):
        (OUT / split / "images").mkdir(parents=True, exist_ok=True)
        (OUT / split / "labels").mkdir(parents=True, exist_ok=True)
        train = split == "train"
        report["splits"][split] = build_split(split, labeled[split], empty[split],
                                              args.target if train else args.val_target,
                                              args.max_repeat if train else 1, args.neg_ratio, rng, selection)

    (OUT / "data.yaml").write_text(  # no path: ultralytics then resolves from this file's folder, wherever it's copied
        "train: train/images\nval: val/images\ntest: test/images\n"
        f"nc: {len(CLASSES)}\nnames: {CLASSES}\n")
    (OUT / "balance_report.json").write_text(json.dumps(report, indent=2))
    with open(OUT / "selection.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["split", "image", "class", "subfolder", "copies"])
        writer.writeheader()
        writer.writerows(selection)

    for split, rep in report["splits"].items():
        print(f"\n[{split}] target {rep['target']} per class -- {rep['images']} images "
              f"({rep['distinct_labeled_images']} labeled + {rep['background_images']} background)")
        print(f"  {'class':<16}{'available':>10}{'chosen':>9}{'w/ repeats':>11}{'shortfall':>10}  sub-folders (chosen/available)")
        for name, c in rep["classes"].items():
            subs = ", ".join(f"{s} {v['chosen']}/{v['available']}" for s, v in c["subfolders"].items())
            print(f"  {name:<16}{c['available']:>10}{c['distinct']:>9}{c['with_repeats']:>11}{c['shortfall']:>10}  {subs}")


if __name__ == "__main__":
    main()
