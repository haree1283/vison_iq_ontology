#!/usr/bin/env python3
"""UVH-26 (COCO JSON + 1080p PNG) -> YOLO labels + JPEG images under
datasets/v6/sources/uvh26/{train,val}/{images,labels}.

Uses the majority-vote (MV) annotation set. PNGs are re-encoded as JPEG
(quality 92): ~10x smaller on disk and faster to load during training, and
the production camera stream is compressed video anyway.

Re-runnable while the download is still in progress: images not on disk yet
are skipped and counted, and already-converted images are skipped unless
--overwrite is given.

Note: UVH-26 labels vehicles only. Persons in these images are still
unlabeled -- run the pre-labeling step before training, or the model learns
that pedestrians are background.

Usage:
  python scripts/v6/convert_uvh26.py
  python scripts/v6/convert_uvh26.py --max-images 200 --workers 4
"""
import argparse
import json
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2

from classes import CLASS_IDS, CLASSES, UVH26_MAP

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "datasets" / "v6" / "raw" / "uvh26"
OUT = ROOT / "datasets" / "v6" / "sources" / "uvh26"
SPLITS = {"train": ("UVH-26-Train", "UVH-26-MV-Train.json"), "val": ("UVH-26-Val", "UVH-26-MV-Val.json")}
MIN_BOX_PX = 4       # drop degenerate boxes narrower/shorter than this
JPEG_QUALITY = 92


def yolo_lines(annotations, width, height):
    lines = []
    for ann in annotations:
        v6_name = UVH26_MAP[ann["category"]]
        if v6_name is None:
            continue
        x, y, w, h = ann["bbox"]
        x0, y0 = max(0.0, x), max(0.0, y)
        x1, y1 = min(float(width), x + w), min(float(height), y + h)
        if x1 - x0 < MIN_BOX_PX or y1 - y0 < MIN_BOX_PX:
            continue
        cx, cy = (x0 + x1) / 2 / width, (y0 + y1) / 2 / height
        bw, bh = (x1 - x0) / width, (y1 - y0) / height
        lines.append(f"{CLASS_IDS[v6_name]} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
    return lines


def convert_one(job):
    src, img_out, lbl_out, lines = job
    img = cv2.imread(str(src))
    if img is None:
        return "unreadable"
    img_out.parent.mkdir(parents=True, exist_ok=True)
    lbl_out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(img_out), img, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
    lbl_out.write_text("\n".join(lines) + ("\n" if lines else ""))
    return "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-images", type=int, default=None, help="convert at most this many per split (smoke test)")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    stats = {}
    for split, (folder, ann_file) in SPLITS.items():
        ann_path = RAW / folder / ann_file
        if not ann_path.is_file():
            print(f"[{split}] {ann_path.relative_to(ROOT)} not downloaded yet -- skipping split")
            continue

        coco = json.loads(ann_path.read_text())
        cat_names = {c["id"]: c["name"] for c in coco["categories"]}
        unknown = set(cat_names.values()) - set(UVH26_MAP)
        if unknown:
            raise SystemExit(f"UVH-26 categories missing from UVH26_MAP: {sorted(unknown)}")

        anns_by_image = defaultdict(list)
        for ann in coco["annotations"]:
            anns_by_image[ann["image_id"]].append({"category": cat_names[ann["category_id"]], "bbox": ann["bbox"]})

        # file_name is flat ("356278.png") but files sit in sharded subfolders (data/000/...)
        on_disk = {p.name: p for p in (RAW / folder).rglob("*.png")}

        jobs, missing, skipped, class_counts = [], 0, 0, Counter()
        for image in coco["images"]:
            src = on_disk.get(image["file_name"])
            if src is None:
                missing += 1
                continue
            stem = f"uvh26_{Path(image['file_name']).stem}"
            img_out = OUT / split / "images" / f"{stem}.jpg"
            lbl_out = OUT / split / "labels" / f"{stem}.txt"
            lines = yolo_lines(anns_by_image[image["id"]], image["width"], image["height"])
            class_counts.update(CLASSES[int(line.split()[0])] for line in lines)
            if img_out.is_file() and lbl_out.is_file() and not args.overwrite:
                skipped += 1
                continue
            jobs.append((src, img_out, lbl_out, lines))
            if args.max_images is not None and len(jobs) >= args.max_images:
                break

        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            results = Counter(pool.map(convert_one, jobs, chunksize=16))

        stats[split] = {
            "images_in_annotations": len(coco["images"]),
            "converted": results.get("ok", 0),
            "unreadable": results.get("unreadable", 0),
            "already_converted": skipped,
            "not_downloaded_yet": missing,
            "boxes_by_class": dict(class_counts.most_common()),
        }
        print(f"[{split}] {json.dumps(stats[split], indent=2)}")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "conversion_stats.json").write_text(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
