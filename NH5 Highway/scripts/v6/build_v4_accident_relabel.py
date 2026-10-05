"""Build datasets/processed_v2_plus_v6_v4: same as v3 (hardlinked images, copied labels), but accident_scene
images that lack vehicle/person labels get them auto-labeled by COCO yolov8l. Uses only training-dataset images."""
import os, glob, shutil, json, sys
from ultralytics import YOLO

SRC = "/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway/datasets/processed_v2_plus_v6_v3"
DST = "/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway/datasets/processed_v2_plus_v6_v4"
COCO = "/media/nikhil/New Volume/Nikhil/yolov8l.pt"
COCO2OURS = {0: 0, 1: 1, 2: 2, 3: 3, 5: 4, 7: 5}  # person,bicycle,car,motorcycle,bus,truck
CONF, MIN_AREA = 0.35, 0.0004
ACC, VEH = '10', {'0', '1', '2', '3', '4', '5'}

for split in ('train', 'val', 'test'):
    os.makedirs(f"{DST}/images/{split}", exist_ok=True)
    os.makedirs(f"{DST}/labels/{split}", exist_ok=True)
    for f in os.listdir(f"{SRC}/images/{split}"):
        d = f"{DST}/images/{split}/{f}"
        if not os.path.exists(d):
            os.link(f"{SRC}/images/{split}/{f}", d)
    for f in os.listdir(f"{SRC}/labels/{split}"):
        shutil.copy2(f"{SRC}/labels/{split}/{f}", f"{DST}/labels/{split}/{f}")
for extra in ("data.yaml",):
    txt = open(f"{SRC}/{extra}").read().replace("processed_v2_plus_v6_v3", "processed_v2_plus_v6_v4")
    open(f"{DST}/{extra}", "w").write(txt)
print("linked/copied base dataset", flush=True)

todo = []
for split in ('train', 'val', 'test'):
    for lf in glob.glob(f"{DST}/labels/{split}/*.txt"):
        L = [l.split() for l in open(lf) if l.strip()]
        cls = {l[0] for l in L}
        if ACC in cls and not (cls & VEH):
            stem = os.path.basename(lf)[:-4]
            img = next((f"{DST}/images/{split}/{stem}{e}" for e in ('.jpg', '.png', '.jpeg') if os.path.exists(f"{DST}/images/{split}/{stem}{e}")), None)
            if img:
                todo.append((split, lf, img))
print("accident images to relabel:", len(todo), flush=True)

model = YOLO(COCO)
added = {}
stats = {k: 0 for k in COCO2OURS.values()}
imgs = [t[2] for t in todo]
B = 64
for i in range(0, len(todo), B):
    chunk = todo[i:i + B]
    res = model.predict([c[2] for c in chunk], imgsz=960, conf=CONF, classes=list(COCO2OURS), verbose=False, device=0)
    for (split, lf, img), r in zip(chunk, res):
        lines = []
        for b, c in zip(r.boxes.xywhn.tolist(), r.boxes.cls.tolist()):
            if b[2] * b[3] < MIN_AREA:
                continue
            k = COCO2OURS[int(c)]
            stats[k] += 1
            lines.append(f"{k} {b[0]:.6f} {b[1]:.6f} {b[2]:.6f} {b[3]:.6f}\n")
        if lines:
            # os.link'd label files are copies (copy2), so appending is safe
            with open(lf, "a") as fh:
                fh.writelines(lines)
            added[lf] = len(lines)
    if (i // B) % 20 == 0:
        print(f"{i}/{len(todo)}", flush=True)

json.dump({"relabeled_files": len(added), "boxes_added_by_class": stats}, open(f"{DST}/relabel_report.json", "w"), indent=1)
print("DONE files with added boxes:", len(added), "class stats:", stats, flush=True)
