#!/usr/bin/env python3
"""ROADWork (CMU) -> v3. Per image: one road_construction(9) box = union of worker/work vehicle/
equipment/barrier/barricade/drum/fence/arrow-board boxes; each Cone/Tubular Marker -> traffic_cone(11).
Only images with >=2 roadwork objects. Prefix roadwork_; split from the dataset's own train/val."""
import json, zipfile, hashlib
from pathlib import Path
R = Path(__file__).resolve().parents[2] / "datasets"
raw, V3 = R / "v6/raw/roadwork", R / "processed_v2_plus_v6_v3"
WORK = {14, 8, 13, 7, 6, 5, 4, 11, 15}   # worker, work vehicle, equipment, barrier, barricade, drum, fence, arrow board, other
CONE = {3, 10}
zf = zipfile.ZipFile(raw / "images.zip")
names = {Path(n).name: n for n in zf.namelist() if n.lower().endswith(".jpg")}
n = {"train": 0, "val": 0, "test": 0}
for js, dsplit in (("instances_train_gps_split.json", "train"), ("instances_val_gps_split.json", "val")):
    d = json.load(open(raw / "annotations" / js))
    anns = {}
    for a in d["annotations"]:
        anns.setdefault(a["image_id"], []).append(a)
    for im in d["images"]:
        fn = Path(im["file_name"]).name
        A = anns.get(im["id"], [])
        work = [a for a in A if a["category_id"] in WORK]
        if len(work) < 2 or fn not in names:
            continue
        W, H = im["width"], im["height"]
        bx = [a["bbox"] for a in work]
        x0, y0 = min(b[0] for b in bx), min(b[1] for b in bx)
        x1, y1 = max(b[0] + b[2] for b in bx), max(b[1] + b[3] for b in bx)
        if (x1 - x0) * (y1 - y0) < 0.03 * W * H:
            continue
        lines = [f"9 {(x0+x1)/2/W:.6f} {(y0+y1)/2/H:.6f} {(x1-x0)/W:.6f} {(y1-y0)/H:.6f}"]
        for a in A:
            if a["category_id"] in CONE:
                x, y, w, h = a["bbox"]
                if w * h > 0:
                    lines.append(f"11 {(x+w/2)/W:.6f} {(y+h/2)/H:.6f} {w/W:.6f} {h/H:.6f}")
        sp = dsplit
        if dsplit == "train" and int(hashlib.md5(fn.encode()).hexdigest(), 16) % 10 == 0:
            sp = "test"
        stem = "roadwork_" + Path(fn).stem
        (V3 / "images" / sp).mkdir(parents=True, exist_ok=True)
        (V3 / "images" / sp / f"{stem}.jpg").write_bytes(zf.read(names[fn]))
        (V3 / "labels" / sp / f"{stem}.txt").write_text("\n".join(lines) + "\n")
        n[sp] += 1
print(n)
