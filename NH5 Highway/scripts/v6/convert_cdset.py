#!/usr/bin/env python3
"""CDSet-3434 (already YOLO format) -> v6 class ids under
datasets/v6/sources/cdset/{train,val}/{images,labels}.

crosswalk -> zebra_crossing; guide arrows are dropped (see classes.CDSET_MAP).
CDSet's own test split becomes val here; the final train/val/test split of the
merged v6 dataset is done later, per source video/sequence.

Usage:
  python scripts/v6/convert_cdset.py
"""
import json
import shutil
from collections import Counter
from pathlib import Path

from classes import CDSET_MAP, CLASS_IDS

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "datasets" / "v6" / "raw" / "cdset_crosswalk" / "CDSet" / "dataset_YOLO_format_3434"
OUT = ROOT / "datasets" / "v6" / "sources" / "cdset"
SPLITS = {"train": "train", "test": "val"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png"}


def main():
    stats = {}
    for src_split, dst_split in SPLITS.items():
        img_dir, lbl_dir = RAW / "images" / src_split, RAW / "labels" / src_split
        out_img, out_lbl = OUT / dst_split / "images", OUT / dst_split / "labels"
        out_img.mkdir(parents=True, exist_ok=True)
        out_lbl.mkdir(parents=True, exist_ok=True)

        counts = Counter()
        for img in sorted(p for p in img_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS):
            src_lbl = lbl_dir / f"{img.stem}.txt"
            lines = []
            if src_lbl.is_file():
                for raw_line in src_lbl.read_text().splitlines():
                    parts = raw_line.split()
                    if len(parts) != 5:
                        continue
                    v6_name = CDSET_MAP[int(parts[0])]
                    if v6_name is None:
                        continue
                    lines.append(" ".join([str(CLASS_IDS[v6_name])] + parts[1:]))
                    counts[v6_name] += 1
            stem = f"cdset_{img.stem}"
            shutil.copy2(img, out_img / f"{stem}{img.suffix.lower()}")
            (out_lbl / f"{stem}.txt").write_text("\n".join(lines) + ("\n" if lines else ""))
            counts["_images"] += 1
        stats[dst_split] = dict(counts)
        print(f"[{dst_split}] {stats[dst_split]}")

    (OUT / "conversion_stats.json").write_text(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
