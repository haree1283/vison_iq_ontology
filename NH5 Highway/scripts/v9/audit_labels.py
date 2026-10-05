#!/usr/bin/env python3
"""Label audit (read-only): v8 predictions vs labels on the val split, for the weak classes.

For each focus class, per image:
  - missed label  : a labelled box the model does not find at all (IoU>=0.3, conf>=0.10) -> hard case or wrong label
  - missing label : a confident prediction (conf>=0.50) with no labelled box of that class -> likely unlabelled object
Writes runs/v9_audit/<class>_{missed,unlabelled}.txt (per image, with source) and review sheets (label = green,
prediction = red) for visual checking. Nothing in the dataset is modified.
"""
import collections, json, os, random, re, sys
from pathlib import Path
import cv2, numpy as np
from ultralytics import YOLO

ROOT = Path("/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway")
D = ROOT / "datasets/processed_v2_plus_v6_v8"
OUT = ROOT / "runs/v9_audit"; OUT.mkdir(parents=True, exist_ok=True)
FOCUS = {6: "pothole", 9: "road_construction", 10: "accident_scene", 11: "fire_accident"}
SPLIT = sys.argv[1] if len(sys.argv) > 1 else "val"
model = YOLO(str(ROOT / "models/nh5_v8_final_ep100.pt"))


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0, min(a[3], b[3]) - max(a[1], b[1])); i = ix * iy
    return i / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i + 1e-9)


def gt_boxes(lbl, w, h):
    out = []
    if lbl.exists():
        for l in lbl.read_text().split("\n"):
            p = l.split()
            if len(p) == 5:
                c, x, y, bw, bh = int(p[0]), *map(float, p[1:])
                out.append((c, ((x - bw / 2) * w, (y - bh / 2) * h, (x + bw / 2) * w, (y + bh / 2) * h)))
    return out


imgs = sorted((D / "images" / SPLIT).iterdir())
missed = collections.defaultdict(list); unlab = collections.defaultdict(list)
stats = collections.defaultdict(collections.Counter)
for k, ip in enumerate(imgs):
    img = cv2.imread(str(ip))
    if img is None:
        continue
    h, w = img.shape[:2]
    gts = gt_boxes(D / "labels" / SPLIT / (ip.stem + ".txt"), w, h)
    r = model.predict(img, imgsz=960, conf=0.10, verbose=False, device=0)[0]
    preds = [(int(b.cls), float(b.conf), tuple(b.xyxy[0].tolist())) for b in r.boxes]
    src = re.split(r"[_\-]", ip.stem)[0]
    for c, name in FOCUS.items():
        g = [b for cc, b in gts if cc == c]; p = [(cf, b) for cc, cf, b in preds if cc == c]
        stats[name]["label_boxes"] += len(g)
        for gb in g:
            if not any(iou(gb, pb) >= 0.3 for _, pb in p):
                missed[name].append((ip.name, src, gb)); stats[name]["missed"] += 1
        for cf, pb in p:
            if cf >= 0.5 and not any(iou(gb, pb) >= 0.3 for gb in g):
                unlab[name].append((ip.name, src, pb, cf)); stats[name]["unlabelled_confident"] += 1
    if k % 2000 == 0:
        print(f"  {k}/{len(imgs)}", flush=True)

summary = {}
for name in FOCUS.values():
    s = stats[name]
    summary[name] = dict(s, missed_by_source=collections.Counter(x[1] for x in missed[name]).most_common(8),
                         unlabelled_by_source=collections.Counter(x[1] for x in unlab[name]).most_common(8))
    with open(OUT / f"{name}_missed.txt", "w") as f:
        for n, src, b in missed[name]: f.write(f"{n}\t{src}\t{[round(v) for v in b]}\n")
    with open(OUT / f"{name}_unlabelled.txt", "w") as f:
        for n, src, b, cf in unlab[name]: f.write(f"{n}\t{src}\t{cf:.2f}\t{[round(v) for v in b]}\n")
    # review sheets: 24 random examples of each kind
    for kind, items in (("missed", missed[name]), ("unlabelled", unlab[name])):
        random.seed(0); pick = random.sample(items, min(24, len(items))); tiles = []
        for it in pick:
            ip = D / "images" / SPLIT / it[0]; img = cv2.imread(str(ip)); h, w = img.shape[:2]
            for cc, gb in gt_boxes(D / "labels" / SPLIT / (ip.stem + ".txt"), w, h):
                if cc in FOCUS:
                    cv2.rectangle(img, tuple(map(int, gb[:2])), tuple(map(int, gb[2:])), (0, 220, 0), max(2, w // 300))
            b = it[2]; cv2.rectangle(img, tuple(map(int, b[:2])), tuple(map(int, b[2:])), (0, 0, 255), max(2, w // 300))
            t = cv2.resize(img, (320, 240)); cv2.putText(t, it[1][:14], (4, 18), 0, 0.55, (255, 255, 0), 2); tiles.append(t)
        while len(tiles) % 6: tiles.append(np.zeros((240, 320, 3), np.uint8))
        if tiles:
            cv2.imwrite(str(OUT / f"sheet_{name}_{kind}.jpg"), cv2.vconcat([cv2.hconcat(tiles[i:i + 6]) for i in range(0, len(tiles), 6)]))
json.dump(summary, open(OUT / f"summary_{SPLIT}.json", "w"), indent=1)
for n, s in summary.items():
    print(n, json.dumps(s))
