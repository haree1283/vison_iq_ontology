#!/usr/bin/env python3
"""Open Images V7 street scenes -> v6 YOLO labels under
datasets/v6/sources/open_images/{train,val}/{images,labels}.

Replaces ROD / Construction Site Safety as the person source (see SOURCES.md):
every Open Images photo carries its own Flickr license and author, so
provenance is checked image by image.

Selection, from the validation + test subsets (train's 2 GB box CSV isn't needed yet):
- license is CC BY 2.0; attribution.csv lists author and page of every kept image
- at least one person box AND one vehicle box: portraits and indoor photos
  don't help a road camera
- images with an IsGroupOf or IsDepiction box of a mapped class are skipped: a
  single box around a crowd or a car park leaves the objects inside unlabeled,
  and posters/toys aren't road users
- images with a non-zero Rotation are skipped (boxes and stored pixels disagree)

Split: validation -> val, test -> train. Images come from the public
open-images-dataset S3 bucket without an account; the metadata CSVs from
storage.googleapis.com. Re-running skips images already on disk.

Open Images has no auto / cone / barricade classes and its vehicle boxes aren't
exhaustive -- run prelabel_missing.py open_images afterwards.

Usage:
  python scripts/v6/convert_open_images.py --list-only     # selection counts, no image download
  python scripts/v6/convert_open_images.py --max-images 50
  python scripts/v6/convert_open_images.py
"""
import argparse
import csv
import json
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import boto3
from botocore import UNSIGNED
from botocore.config import Config

from classes import CLASS_IDS, OPEN_IMAGES_MAP

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "datasets" / "v6" / "raw" / "open_images"
OUT = ROOT / "datasets" / "v6" / "sources" / "open_images"
SUBSETS = {"validation": "val", "test": "train"}
METADATA = {
    "oidv7-class-descriptions-boxable.csv": "v7/oidv7-class-descriptions-boxable.csv",
    "validation-annotations-bbox.csv": "v5/validation-annotations-bbox.csv",
    "test-annotations-bbox.csv": "v5/test-annotations-bbox.csv",
    "validation-images-with-rotation.csv": "2018_04/validation/validation-images-with-rotation.csv",
    "test-images-with-rotation.csv": "2018_04/test/test-images-with-rotation.csv",
}
CC_BY = "https://creativecommons.org/licenses/by/2.0/"
VEHICLES = {"bicycle", "car", "motorcycle", "bus", "truck"}
BUCKET = "open-images-dataset"
MIN_SIDE = 0.002  # normalized; drops degenerate boxes


def fetch_metadata():
    RAW.mkdir(parents=True, exist_ok=True)
    for name, path in METADATA.items():
        if not (RAW / name).is_file():
            print(f"downloading {name}")
            part = RAW / f"{name}.part"
            urllib.request.urlretrieve(f"https://storage.googleapis.com/openimages/{path}", part)
            part.rename(RAW / name)


def label_ids():
    """Open Images label id (/m/...) -> v6 class name."""
    with open(RAW / "oidv7-class-descriptions-boxable.csv", newline="") as f:
        mids = {name: mid for mid, name in csv.reader(f)}
    missing = set(OPEN_IMAGES_MAP) - set(mids)
    if missing:
        raise SystemExit(f"not Open Images boxable classes: {sorted(missing)}")
    return {mids[name]: v6 for name, v6 in OPEN_IMAGES_MAP.items()}


def select(subset, mid_to_v6):
    meta = {}
    with open(RAW / f"{subset}-images-with-rotation.csv", newline="") as f:
        for row in csv.DictReader(f):
            if row["License"] == CC_BY and row["Rotation"] in ("", "0", "0.0"):
                meta[row["ImageID"]] = row

    boxes, rejected = defaultdict(list), set()
    with open(RAW / f"{subset}-annotations-bbox.csv", newline="") as f:
        for row in csv.DictReader(f):
            v6 = mid_to_v6.get(row["LabelName"])
            if v6 is None or row["ImageID"] not in meta:
                continue
            if row["IsGroupOf"] == "1" or row["IsDepiction"] == "1":
                rejected.add(row["ImageID"])
                continue
            x0, x1, y0, y1 = (float(row[k]) for k in ("XMin", "XMax", "YMin", "YMax"))
            if x1 - x0 >= MIN_SIDE and y1 - y0 >= MIN_SIDE:
                boxes[row["ImageID"]].append((v6, x0, y0, x1, y1))

    kept = {}
    for image_id, image_boxes in boxes.items():
        names = {b[0] for b in image_boxes}
        if image_id not in rejected and "person" in names and names & VEHICLES:
            kept[image_id] = image_boxes
    return kept, meta


def download(job):
    s3, subset, image_id, dst = job
    if dst.is_file():
        return "exists"
    part = dst.with_suffix(".part")
    try:
        s3.download_file(BUCKET, f"{subset}/{image_id}.jpg", str(part))
    except Exception:
        part.unlink(missing_ok=True)
        return "failed"
    part.rename(dst)
    return "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-images", type=int, default=None, help="per subset (smoke test)")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--list-only", action="store_true")
    args = ap.parse_args()

    fetch_metadata()
    mid_to_v6 = label_ids()
    s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED, max_pool_connections=args.workers * 2))
    stats, attribution = {}, []

    for subset, split in SUBSETS.items():
        kept, meta = select(subset, mid_to_v6)
        ids = sorted(kept)[:args.max_images]
        stats[split] = {"images_selected": len(ids),
                        "boxes": dict(Counter(b[0] for i in ids for b in kept[i]).most_common())}
        print(f"[{subset} -> {split}] {json.dumps(stats[split])}")
        if args.list_only:
            continue

        img_dir, lbl_dir = OUT / split / "images", OUT / split / "labels"
        img_dir.mkdir(parents=True, exist_ok=True)
        lbl_dir.mkdir(parents=True, exist_ok=True)
        jobs = [(s3, subset, i, img_dir / f"open_images_{i}.jpg") for i in ids]
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            results = list(pool.map(download, jobs))
        stats[split]["download"] = dict(Counter(results))

        for image_id, result in zip(ids, results):
            if result == "failed":
                continue
            lines = [f"{CLASS_IDS[v6]} {(x0 + x1) / 2:.6f} {(y0 + y1) / 2:.6f} {x1 - x0:.6f} {y1 - y0:.6f}"
                     for v6, x0, y0, x1, y1 in kept[image_id]]
            (lbl_dir / f"open_images_{image_id}.txt").write_text("\n".join(lines) + "\n")
            m = meta[image_id]
            attribution.append({"image": f"open_images_{image_id}.jpg", "split": split, "title": m["Title"],
                                "author": m["Author"], "author_url": m["AuthorProfileURL"],
                                "source_url": m["OriginalLandingURL"], "license": m["License"]})
        print(f"[{split}] download {stats[split]['download']}")

    if not args.list_only:
        with open(OUT / "attribution.csv", "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(attribution[0]))
            writer.writeheader()
            writer.writerows(attribution)
        (OUT / "conversion_stats.json").write_text(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
