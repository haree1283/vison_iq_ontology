#!/usr/bin/env python3
"""Package a v6 source for human review in CVAT (free and self-hostable:
https://github.com/cvat-ai/cvat -- no cloud account needed).

For each chunk of images it writes two zips under datasets/v6/review/<source>/:
  <source>_review_NNN_images.zip       -> create a CVAT task from this archive
  <source>_review_NNN_annotations.zip  -> in that task: Actions -> Upload annotations -> "YOLO 1.1"
Image names inside carry their split ("train__<name>.jpg") so the import can
put every reviewed label back where it came from.

After review: Actions -> Export task dataset -> "YOLO 1.1", then
  python scripts/v6/import_cvat_review.py <source> <exported zip>

Reviewer checklist (also written to REVIEW_GUIDE.md next to the zips):
every box in YOLO format looks the same whether the source drew it or the
model proposed it, so check them all -- fix class, tighten box, delete wrong
ones, add missed objects.

Usage:
  python scripts/v6/export_cvat_review.py raqabah
  python scripts/v6/export_cvat_review.py uvh26 --only-prelabeled --chunk-size 500
"""
import argparse
import json
import zipfile
from pathlib import Path

from classes import CLASSES

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ROOT / "datasets" / "v6" / "sources"
REVIEW = ROOT / "datasets" / "v6" / "review"
IMAGE_EXTS = (".jpg", ".jpeg", ".png")

GUIDE = """# Review guide

Label every visible instance of these classes (boxes tight to the visible object):

| class | rule |
|---|---|
| person | anyone on foot, standing or sitting; riders are also `person` |
| bicycle / motorcycle / auto | the vehicle only, not the rider |
| car / bus / truck | LCV and pickups are `truck`; vans and SUVs are `car` |
| license_plate | readable-size plates only (roughly 15 px tall or more) |
| pothole | a hole in the road surface, not cracks |
| damaged_vehicle | a vehicle visibly crashed, deformed, overturned or burning -- replaces its car/bus/truck box |
| traffic_cone / barricade | cones, barrels, water-filled and metal barriers placed on or beside the road |
| zebra_crossing | the painted crossing area |

Delete boxes on objects that are too blurred or small to identify. Skip nothing silently:
if an image is unusable (corrupt, not a road scene), delete all its boxes and tag it `reject`.
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--chunk-size", type=int, default=1000, help="images per CVAT task (CVAT gets slow above ~1-2k)")
    ap.add_argument("--only-prelabeled", action="store_true", help="only images that received pre-label boxes")
    args = ap.parse_args()

    src_root = SOURCES / args.source
    wanted = None
    if args.only_prelabeled:
        rows = [json.loads(l) for l in (src_root / "prelabel_boxes.jsonl").read_text().splitlines()]
        wanted = {(r["split"], r["image"]) for r in rows}

    items = []
    for split_dir in sorted(p for p in src_root.iterdir() if (p / "images").is_dir()):
        for img in sorted(p for p in (split_dir / "images").iterdir() if p.suffix.lower() in IMAGE_EXTS):
            if wanted is None or (split_dir.name, img.stem) in wanted:
                items.append((split_dir.name, img, split_dir / "labels" / f"{img.stem}.txt"))
    if not items:
        raise SystemExit(f"nothing to export from {src_root}")

    out_dir = REVIEW / args.source
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "REVIEW_GUIDE.md").write_text(GUIDE)
    for n, start in enumerate(range(0, len(items), args.chunk_size), start=1):
        chunk = items[start:start + args.chunk_size]
        base = out_dir / f"{args.source}_review_{n:03d}"
        with zipfile.ZipFile(f"{base}_images.zip", "w", zipfile.ZIP_STORED) as images_zip, \
                zipfile.ZipFile(f"{base}_annotations.zip", "w", zipfile.ZIP_DEFLATED) as ann_zip:
            ann_zip.writestr("obj.names", "\n".join(CLASSES) + "\n")
            ann_zip.writestr("obj.data", f"classes = {len(CLASSES)}\ntrain = data/train.txt\n"
                                         "names = data/obj.names\nbackup = backup/\n")
            train_txt = []
            for split, img, lbl in chunk:
                arc = f"{split}__{img.name}"
                images_zip.write(img, arc)
                ann_zip.writestr(f"obj_train_data/{Path(arc).stem}.txt", lbl.read_text() if lbl.is_file() else "")
                train_txt.append(f"data/obj_train_data/{arc}")
            ann_zip.writestr("train.txt", "\n".join(train_txt) + "\n")
        print(f"wrote {base.relative_to(ROOT)}_{{images,annotations}}.zip ({len(chunk)} images)")


if __name__ == "__main__":
    main()
