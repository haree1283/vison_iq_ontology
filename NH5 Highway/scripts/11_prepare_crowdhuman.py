#!/usr/bin/env python3
"""Collect a subsample of CrowdHuman (dense/occluded person detection) to
boost our weak person class. Single-class dataset (person=0, matches our
unified class 0 directly) but with scattered stray non-zero class ids in a
handful of files (likely conversion noise) -- filtered out, keeping only
class 0 lines.

CrowdHuman averages many people per image (crowded scenes), so a modest
subsample of its train split is plenty -- using all ~12,000 would swamp
every other class in the merged dataset.
"""
import random
import shutil
from pathlib import Path

RAW = Path(__file__).resolve().parent.parent / "datasets" / "raw"
SRC_DIR = RAW / "crowdhuman" / "CrowdHuman dataset" / "dataset" / "train"
OUT_DIR = RAW / "crowdhuman_yolo"
OUT_IMAGES = OUT_DIR / "images"
OUT_LABELS = OUT_DIR / "labels"

SOURCE_PERSON_CLASS_ID = "0"
UNIFIED_CLASS_ID = 0  # person
MAX_IMAGES = 4500  # was 7000 -- dialed back after that pushed person to 44% of all boxes dataset-wide
                    # (CrowdHuman's crowd density means even moderate image counts produce huge box counts);
                    # still well above the original 3500 for the requested extra distance/scale variety
SEED = 42
IMG_EXTS = {".jpg", ".jpeg", ".png"}


def main():
    # full clean regeneration each run -- otherwise a shrinking MAX_IMAGES/cap
    # (or any other change that reduces the kept count) leaves stale orphan
    # files behind from the previous, larger run
    shutil.rmtree(OUT_DIR, ignore_errors=True)
    OUT_IMAGES.mkdir(parents=True, exist_ok=True)
    OUT_LABELS.mkdir(parents=True, exist_ok=True)

    img_dir = SRC_DIR / "images"
    lbl_dir = SRC_DIR / "labels"

    all_images = [p for p in img_dir.iterdir() if p.suffix.lower() in IMG_EXTS]
    random.seed(SEED)
    random.shuffle(all_images)
    if len(all_images) > MAX_IMAGES:
        all_images = all_images[:MAX_IMAGES]

    kept = 0
    for img_path in all_images:
        label_path = lbl_dir / (img_path.stem + ".txt")
        if not label_path.exists():
            continue

        new_lines = []
        for line in label_path.read_text().strip().splitlines():
            parts = line.split()
            if len(parts) != 5 or parts[0] != SOURCE_PERSON_CLASS_ID:
                continue
            _, cx, cy, w, h = parts
            new_lines.append(f"{UNIFIED_CLASS_ID} {cx} {cy} {w} {h}")

        if not new_lines:
            continue

        dest_name = f"crowdhuman_{kept:05d}{img_path.suffix.lower()}"
        shutil.copy(img_path, OUT_IMAGES / dest_name)
        (OUT_LABELS / (Path(dest_name).stem + ".txt")).write_text("\n".join(new_lines) + "\n")
        kept += 1

    print(f"Kept {kept} CrowdHuman image/label pairs -> {OUT_DIR}")


if __name__ == "__main__":
    main()
