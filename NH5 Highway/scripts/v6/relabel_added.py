"""Append COCO-detected persons/vehicles (yolov8l, conf>=0.5) to newly added public images so fire images do not teach 'no vehicles here'.
Usage: relabel_added.py <added.json>   (list of 'split/name.ext' under datasets/processed_v2_plus_v6_v4). Skips background-only images."""
import sys, json, os
from ultralytics import YOLO
DST = "/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway/datasets/processed_v2_plus_v6_v4"
MAP = {0: 0, 1: 1, 2: 2, 3: 3, 5: 4, 7: 5}
m = YOLO("/media/nikhil/New Volume/Nikhil/yolov8l.pt")
items = [i for i in json.load(open(sys.argv[1]))]
todo = []
for it in items:
    sp, fn = it.split('/', 1)
    lf = f"{DST}/labels/{sp}/{os.path.splitext(fn)[0]}.txt"
    if os.path.exists(lf) and os.path.getsize(lf) > 0:
        todo.append((f"{DST}/images/{sp}/{fn}", lf))
print("to relabel", len(todo), flush=True)
stats = {k: 0 for k in MAP.values()}
for i in range(0, len(todo), 8):
    chunk = todo[i:i + 8]
    for (img, lf), r in zip(chunk, m.predict([c[0] for c in chunk], imgsz=960, conf=0.5, classes=list(MAP), verbose=False)):
        add = []
        for b, c in zip(r.boxes.xywhn.tolist(), r.boxes.cls.tolist()):
            if b[2] * b[3] < 0.0004: continue
            k = MAP[int(c)]; stats[k] += 1
            add.append(f"{k} {b[0]:.6f} {b[1]:.6f} {b[2]:.6f} {b[3]:.6f}\n")
        if add:
            with open(lf, "a") as fh: fh.writelines(add)
    if (i // 8) % 200 == 0: print(i, "/", len(todo), flush=True)
print("DONE", stats, flush=True)
