#!/usr/bin/env python3
"""Merge the converted sources into the training dataset datasets/v6/yolo/.

- per image, reviewed labels (labels_reviewed/) win over labels/
- empty images (no boxes) are capped per source at --neg-ratio x its
  labeled images -- a few hundred teach "background", thousands just dilute
- --release refuses to build while any pre-labeled image (and every image of
  sources that exist only to be hand-labeled, e.g. raqabah) is still unreviewed
- images are hard-linked, so the merged set costs almost no extra disk

Writes data.yaml (path relative to itself, so the folder can be copied to the
GPU machine as-is) and dataset_stats.json (boxes per class per split per source).

Usage:
  python scripts/v6/build_v6_dataset.py                # draft build from everything converted so far
  python scripts/v6/build_v6_dataset.py --release      # only if all review is done
  python scripts/v6/build_v6_dataset.py --sources uvh26 open_images cdset
"""
import argparse
import json
import os
import random
import shutil
from collections import Counter, defaultdict
from pathlib import Path

from classes import CLASSES

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ROOT / "datasets" / "v6" / "sources"
OUT = ROOT / "datasets" / "v6" / "training" / "detector_yolo_all"  # unbalanced; balance_v6_dataset.py writes the one to train on
IMAGE_EXTS = (".jpg", ".jpeg", ".png")
REVIEW_EVERY_IMAGE = {"raqabah", "fire_images"}  # no source boxes at all -- damaged_vehicle only exists after review
SEED = 42


def label_for(split_dir, stem):
    reviewed = split_dir / "labels_reviewed" / f"{stem}.txt"
    if reviewed.is_file():
        return reviewed, True
    plain = split_dir / "labels" / f"{stem}.txt"
    return (plain if plain.is_file() else None), False


def unreviewed(src_root, name):
    """(split, stem) pairs that still need a human look."""
    if name in REVIEW_EVERY_IMAGE:
        need = {(s.name, p.stem) for s in src_root.iterdir() if (s / "images").is_dir()
                for p in (s / "images").iterdir() if p.suffix.lower() in IMAGE_EXTS}
    else:
        boxes = src_root / "prelabel_boxes.jsonl"
        need = {(r["split"], r["image"]) for r in map(json.loads, boxes.read_text().splitlines())} \
            if boxes.is_file() else set()
    return {(split, stem) for split, stem in need if not (src_root / split / "labels_reviewed" / f"{stem}.txt").is_file()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", nargs="*", help="default: every converted source")
    ap.add_argument("--neg-ratio", type=float, default=0.15)
    ap.add_argument("--release", action="store_true")
    args = ap.parse_args()

    names = args.sources or sorted(p.name for p in SOURCES.iterdir()
                                   if p.is_dir() and any((p / s / "images").is_dir() for s in ("train", "val", "test")))
    pending = {n: len(unreviewed(SOURCES / n, n)) for n in names}
    pending = {n: c for n, c in pending.items() if c}
    if pending:
        msg = "unreviewed images: " + ", ".join(f"{n} {c}" for n, c in pending.items())
        if args.release:
            raise SystemExit(f"--release refused, {msg}")
        print(f"DRAFT build -- {msg} (pre-labels used as-is; don't ship a model trained on this)")

    shutil.rmtree(OUT, ignore_errors=True)
    rng = random.Random(SEED)
    stats = defaultdict(lambda: defaultdict(Counter))

    for name in names:
        src_root = SOURCES / name
        for split_dir in sorted(p for p in src_root.iterdir() if (p / "images").is_dir()):
            split = split_dir.name
            labeled, empty = [], []
            for img in sorted(p for p in (split_dir / "images").iterdir() if p.suffix.lower() in IMAGE_EXTS):
                lbl, reviewed = label_for(split_dir, img.stem)
                lines = [l for l in lbl.read_text().splitlines() if l.strip()] if lbl else []
                (labeled if lines else empty).append((img, lines, reviewed))
            rng.shuffle(empty)
            kept = labeled + empty[:int(len(labeled) * args.neg_ratio)]

            (OUT / split / "images").mkdir(parents=True, exist_ok=True)
            (OUT / split / "labels").mkdir(parents=True, exist_ok=True)
            s = stats[split][name]
            for img, lines, reviewed in kept:
                dst = OUT / split / "images" / img.name
                try:
                    os.link(img, dst)
                except OSError:
                    shutil.copy2(img, dst)
                (OUT / split / "labels" / f"{img.stem}.txt").write_text("\n".join(lines) + ("\n" if lines else ""))
                s["_images"] += 1
                s["_reviewed_images"] += reviewed
                s.update(CLASSES[int(l.split()[0])] for l in lines)
            s["_empty_dropped"] += len(empty) - (len(kept) - len(labeled))

    (OUT / "data.yaml").write_text(  # no path: ultralytics then resolves from this file's folder, wherever it's copied
        "train: train/images\nval: val/images\ntest: test/images\n"
        f"nc: {len(CLASSES)}\nnames: {CLASSES}\n")

    totals = {split: dict(sum((c for c in per_src.values()), Counter())) for split, per_src in stats.items()}
    report = {"draft": bool(pending), "unreviewed": pending, "neg_ratio": args.neg_ratio, "totals": totals,
              "by_source": {split: {n: dict(c) for n, c in per.items()} for split, per in stats.items()}}
    (OUT / "dataset_stats.json").write_text(json.dumps(report, indent=2))

    print(f"\n{'class':<16}" + "".join(f"{s:>10}" for s in ("train", "val", "test")))
    for cls in CLASSES + ["_images"]:
        print(f"{cls:<16}" + "".join(f"{totals.get(s, {}).get(cls, 0):>10}" for s in ("train", "val", "test")))
    missing = [c for c in CLASSES if not totals.get("val", {}).get(c)]
    if missing:
        print(f"\nno validation boxes yet for: {missing} -- their mAP can't be measured")


if __name__ == "__main__":
    main()
