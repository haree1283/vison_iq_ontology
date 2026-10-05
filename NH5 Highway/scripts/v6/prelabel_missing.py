#!/usr/bin/env python3
"""Fill in road users a source doesn't label, using nh5_v5 proposals.

Every public source labels only some classes: UVH-26 has vehicles but no
people, Open Images has no autos and misses some vehicles, plate photos
have only plates. Left as-is, those unlabeled objects teach the detector
they're background. For each image this adds nh5_v5 boxes for
classes.PRELABEL_CLASSES, except
- classes the source labels exhaustively (classes.FULLY_LABELED), and
- proposals overlapping a box the source already has (IoU >= 0.5 with any
  road-user box, or with a same-class person box), so partly-labeled sources
  like Open Images don't get duplicates.

These are PRE-LABELS: every image still needs human review in CVAT before
training (see export_cvat_review.py).

Reversible and re-runnable: the first run copies labels/ -> labels_source/
(the dataset's own boxes); every run rebuilds labels/ as labels_source/ +
fresh proposals, and prelabel_manifest.json records model, thresholds and
counts, plus prelabel_boxes.jsonl lists every proposed box for review.

Usage (GPU machine recommended -- ~25 img/s on a mid-range GPU, ~1 img/s on this CPU):
  python scripts/v6/prelabel_missing.py uvh26 open_images cdset gujarat_plates
  python scripts/v6/prelabel_missing.py open_images --max-images 50 --device cpu
"""
import argparse
import json
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path

from ultralytics import YOLO

from classes import CLASS_IDS, CLASSES, FULLY_LABELED, PRELABEL_CLASSES

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ROOT / "datasets" / "v6" / "sources"
ROAD_USERS = {CLASS_IDS[n] for n in ("bicycle", "car", "motorcycle", "bus", "truck", "auto")}
PERSON = CLASS_IDS["person"]
DAMAGED = CLASS_IDS["damaged_vehicle"]
DEDUP_IOU = 0.5
CRASH_IOU = 0.3  # a crash box often spans the wreck plus debris, so it overlaps its vehicle less tightly
CRASH_INSIDE = 0.6  # ...or covers two vehicles: a vehicle mostly inside the crash box belongs to it too
CRASH_TYPE_CONF = 0.2  # wrecked / overturned vehicles score low; good enough to name the crash's vehicle type


def xywh_to_xyxy(cx, cy, w, h):
    return cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2


def iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def same_group(a, b):
    return (a in ROAD_USERS and b in ROAD_USERS) or a == b


def on_crash(vehicle, crash):
    """A vehicle proposal belongs to a crash box when they overlap like one object, or when the
    vehicle sits mostly inside the crash box."""
    ix = max(0.0, min(vehicle[2], crash[2]) - max(vehicle[0], crash[0]))
    iy = max(0.0, min(vehicle[3], crash[3]) - max(vehicle[1], crash[1]))
    area = (vehicle[2] - vehicle[0]) * (vehicle[3] - vehicle[1])
    return iou(vehicle, crash) >= CRASH_IOU or (area > 0 and ix * iy / area >= CRASH_INSIDE)


PREDICT_CHUNK = 64  # images per predict() call


def predict_chunks(model, images, args, classes):
    """One predict() call over a whole source loads every image into RAM first (6 GB for 5k small
    images, which froze the machine) -- feed it a chunk at a time instead."""
    for i in range(0, len(images), PREDICT_CHUNK):
        yield from model.predict(source=[str(p) for p in images[i:i + PREDICT_CHUNK]], stream=True,
                                 conf=min(args.conf, CRASH_TYPE_CONF), classes=classes, imgsz=args.imgsz, device=args.device,
                                 verbose=False, batch=args.batch)


def prelabel_source(model, name, args, v5_to_v6):
    src_root = SOURCES / name
    split_dirs = sorted(p for p in src_root.iterdir() if (p / "images").is_dir()) if src_root.is_dir() else []
    if not split_dirs:
        print(f"[{name}] no converted splits under {src_root} -- skipped")
        return None

    wanted = [n for n in PRELABEL_CLASSES if n not in FULLY_LABELED.get(name, set())]
    v5_ids = [i for i, v6 in v5_to_v6.items() if v6 in {CLASS_IDS[n] for n in wanted}]
    summary = {"proposed_classes": wanted, "splits": {}}
    review = open(src_root / "prelabel_boxes.jsonl", "w")
    # a vehicle proposal on a damaged_vehicle box isn't added (that would label one wreck twice) -- its
    # type is recorded instead, so build_categories.py can sort crashes into car / motorcycle / bus ...
    crashes = open(src_root / "damaged_vehicle_types.jsonl", "w")

    for split_dir in split_dirs:
        labels, originals = split_dir / "labels", split_dir / "labels_source"
        if not originals.exists():
            shutil.copytree(labels, originals)
        images = sorted(p for p in (split_dir / "images").iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
        images = images[:args.max_images]
        added, skipped_dup, n = Counter(), 0, 0

        for img_path, res in zip(images, predict_chunks(model, images, args, v5_ids)):
            stem = img_path.stem  # res.path is unreliable here -- ultralytics streaming with a
                                   # path list resets to image0.jpg/image1.jpg/... per chunk
            orig = originals / f"{stem}.txt"
            lines = [ln for ln in orig.read_text().splitlines() if ln.strip()] if orig.is_file() else []
            existing = [(int(l.split()[0]), xywh_to_xyxy(*map(float, l.split()[1:5]))) for l in lines]

            if res.boxes is not None:
                for cls, conf, (cx, cy, w, h) in zip(res.boxes.cls.tolist(), res.boxes.conf.tolist(),
                                                     res.boxes.xywhn.tolist()):
                    v6 = v5_to_v6[int(cls)]
                    box = xywh_to_xyxy(cx, cy, w, h)
                    if v6 in ROAD_USERS and any(c == DAMAGED and on_crash(box, b) for c, b in existing):
                        crashes.write(json.dumps({"split": split_dir.name, "image": stem,
                                                  "vehicle": CLASSES[v6], "conf": round(conf, 3)}) + "\n")
                        skipped_dup += 1
                        continue
                    if conf < args.conf:
                        continue  # below the proposal threshold: only good for naming a crash's vehicle type
                    if any(same_group(v6, c) and iou(box, b) >= DEDUP_IOU for c, b in existing):
                        skipped_dup += 1
                        continue
                    lines.append(f"{v6} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
                    existing.append((v6, box))
                    added[v6] += 1
                    review.write(json.dumps({"split": split_dir.name, "image": stem, "class": v6,
                                             "conf": round(conf, 3), "xywhn": [round(v, 6) for v in (cx, cy, w, h)]}) + "\n")

            (labels / f"{stem}.txt").write_text("\n".join(lines) + ("\n" if lines else ""))
            n += 1
            if n % 500 == 0:
                print(f"  [{name}/{split_dir.name}] {n}/{len(images)} images, {sum(added.values())} boxes proposed")

        id_to_name = {i: k for k, i in CLASS_IDS.items()}
        summary["splits"][split_dir.name] = {
            "images": n, "boxes_proposed": {id_to_name[k]: v for k, v in added.most_common()},
            "skipped_as_duplicates": skipped_dup,
        }
        print(f"[{name}/{split_dir.name}] {summary['splits'][split_dir.name]}")

    review.close()
    crashes.close()
    manifest = {"model": Path(args.model).name, "conf": args.conf, "imgsz": args.imgsz, "dedup_iou": DEDUP_IOU,
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "status": "pre-labels -- need human review before training", **summary}
    (src_root / "prelabel_manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sources", nargs="+", help="folders under datasets/v6/sources, e.g. uvh26 open_images")
    ap.add_argument("--model", default=str(ROOT / "models" / "nh5_v5_best.pt"))
    ap.add_argument("--conf", type=float, default=0.35)
    ap.add_argument("--imgsz", type=int, default=1280, help="large: CCTV pedestrians are often small")
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--device", default=None, help="e.g. cpu, 0; default auto")
    ap.add_argument("--max-images", type=int, default=None, help="per split (smoke test)")
    args = ap.parse_args()

    model = YOLO(args.model)
    v5_to_v6 = {i: CLASS_IDS[n] for i, n in model.names.items() if n in PRELABEL_CLASSES}
    missing = set(PRELABEL_CLASSES) - {model.names[i] for i in v5_to_v6}
    if missing:
        raise SystemExit(f"{args.model} has no classes {sorted(missing)} -- can't pre-label them")
    for name in args.sources:
        prelabel_source(model, name, args, v5_to_v6)


if __name__ == "__main__":
    main()
