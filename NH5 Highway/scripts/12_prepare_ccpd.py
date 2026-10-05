#!/usr/bin/env python3
"""Collect plate boxes from CCPD2020 (Chinese City Parking Dataset).

Unlike every other source so far, CCPD has no label files at all -- each
image's bounding box, tilt, plate text, brightness, and blur are all encoded
directly in the filename. We only need the bounding box (field index 2):

  <area>-<tilt>-<x1>&<y1>_<x2>&<y2>-<vertices>-<platetext>-<brightness>-<blur>.jpg

We don't care about reading the (Chinese) plate text -- these images exist
purely to teach the model what a plate looks like in a realistic vehicle
scene at realistic distance, closing the domain gap the close-up ANPR
dataset left (see scripts/4_prepare_license_plate.py). If this pool has far
more images than we need, take a random seeded subsample rather than all of
it, to avoid this one source dominating the plate class.
"""
import random
import shutil
from pathlib import Path

from PIL import Image

RAW = Path(__file__).resolve().parent.parent / "datasets" / "raw"
SRC_DIR = RAW / "ccpd2020"
OUT_DIR = RAW / "ccpd_yolo"
OUT_IMAGES = OUT_DIR / "images"
OUT_LABELS = OUT_DIR / "labels"

UNIFIED_CLASS_ID = 7  # license_plate
MAX_IMAGES = 12000  # raised from 4000: only ~11.8k CCPD images are on disk, so this now uses effectively all of them
SEED = 42


def parse_bbox_from_filename(filename: str):
    parts = filename.split("-")
    if len(parts) < 3:
        return None
    bbox_field = parts[2]  # "x1&y1_x2&y2"
    try:
        p1, p2 = bbox_field.split("_")
        x1, y1 = (float(v) for v in p1.split("&"))
        x2, y2 = (float(v) for v in p2.split("&"))
    except ValueError:
        return None
    return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)


def main():
    # full clean regeneration each run -- otherwise a shrinking MAX_IMAGES/cap
    # (or any other change that reduces the kept count) leaves stale orphan
    # files behind from the previous, larger run
    shutil.rmtree(OUT_DIR, ignore_errors=True)
    OUT_IMAGES.mkdir(parents=True, exist_ok=True)
    OUT_LABELS.mkdir(parents=True, exist_ok=True)

    all_images = [p for p in SRC_DIR.rglob("*.jpg")]
    print(f"found {len(all_images)} CCPD images")

    random.seed(SEED)
    random.shuffle(all_images)
    if len(all_images) > MAX_IMAGES:
        all_images = all_images[:MAX_IMAGES]
        print(f"subsampled to {MAX_IMAGES}")

    kept = 0
    for img_path in all_images:
        bbox = parse_bbox_from_filename(img_path.name)
        if bbox is None:
            continue
        x1, y1, x2, y2 = bbox

        try:
            with Image.open(img_path) as im:
                w, h = im.size
        except Exception:
            continue

        cx = ((x1 + x2) / 2) / w
        cy = ((y1 + y2) / 2) / h
        bw = (x2 - x1) / w
        bh = (y2 - y1) / h
        if not (0 < bw < 1 and 0 < bh < 1):
            continue

        dest_name = f"ccpd_{kept:05d}.jpg"
        shutil.copy(img_path, OUT_IMAGES / dest_name)
        (OUT_LABELS / (Path(dest_name).stem + ".txt")).write_text(
            f"{UNIFIED_CLASS_ID} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}\n"
        )
        kept += 1

        if kept % 500 == 0:
            print(f"  {kept} processed")

    print(f"Kept {kept} CCPD plate image/label pairs -> {OUT_DIR}")


if __name__ == "__main__":
    main()
