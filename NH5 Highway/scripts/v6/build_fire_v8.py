"""Add real (non-augmented) vehicle-context fire/smoke images to v8 as class 11 (fire_accident), one combined box per image.
FASDD (CC BY 4.0): dedupe Roboflow augmented copies by base id, keep only images where fire/smoke touches a COCO-detected vehicle.
Also removes augmented copies (*balfire*) of existing fire images from v8. Only public data; nothing from vedios/."""
import os, re, glob, zipfile, collections, json
import numpy as np, cv2
from ultralytics import YOLO
D = "datasets/processed_v2_plus_v6_v8"; ZP = "datasets/v6/public_fire2/seawsurf__fire_smoke_dataset_fasdd_cv/FASDD_CV.zip"
MAP = {0: 0, 1: 1, 2: 2, 3: 3, 5: 4, 7: 5}; VEH = {2, 3, 5, 7}
stats = collections.Counter(); m = YOLO("/media/nikhil/New Volume/Nikhil/yolov8l.pt")
# 1. drop augmented copies of fire images already in v8
for sp in ("train", "val", "test"):
    for f in glob.glob(f"{D}/labels/{sp}/*balfire*.txt"):
        stem = os.path.basename(f)[:-4]
        for e in (".jpg", ".png", ".jpeg"):
            p = f"{D}/images/{sp}/{stem}{e}"
            if os.path.exists(p): os.remove(p)
        os.remove(f); stats["augmented fire copies removed"] += 1
print(dict(stats), flush=True)
# 2. FASDD
z = zipfile.ZipFile(ZP); names = z.namelist(); seen = set(); cand = []
for n in names:
    m0 = re.match(r"^(train|valid|test)/labels/(.+)\.txt$", n)
    if not m0: continue
    base = re.sub(r"_(jpg|png|jpeg)\.rf\.[0-9a-f]+$", "", m0.group(2), flags=re.I)
    if base in seen: stats["FASDD augmented duplicate skipped"] += 1; continue
    rows = [l.split() for l in z.read(n).decode().splitlines() if l.strip()]
    if not rows: continue
    seen.add(base); ip = n.replace("/labels/", "/images/")[:-4] + ".jpg"
    if ip not in names: continue
    bx = [[float(r[1]) - float(r[3]) / 2, float(r[2]) - float(r[4]) / 2, float(r[1]) + float(r[3]) / 2, float(r[2]) + float(r[4]) / 2] for r in rows]
    u = [min(b[0] for b in bx), min(b[1] for b in bx), max(b[2] for b in bx), max(b[3] for b in bx)]
    if (u[2] - u[0]) * (u[3] - u[1]) < 0.004: continue
    cand.append(({"train": "train", "valid": "val", "test": "test"}[m0.group(1)], base, ip, u))
print("FASDD unique labeled candidates:", len(cand), flush=True)
def touches(v, u): return min(v[2], u[2]) > max(v[0], u[0]) and min(v[3], u[3]) > max(v[1], u[1])
for i in range(0, len(cand), 64):
    ch = cand[i:i+64]; imgs = []
    for sp, base, ip, u in ch: imgs.append(cv2.imdecode(np.frombuffer(z.read(ip), np.uint8), 1))
    ok = [k for k, im in enumerate(imgs) if im is not None]
    res = m.predict([imgs[k] for k in ok], imgsz=640, conf=0.4, classes=list(MAP), verbose=False)
    for k, r in zip(ok, res):
        sp, base, ip, u = ch[k]; im = imgs[k]
        pad = 0.05; w_, h_ = u[2] - u[0], u[3] - u[1]; uu = [max(0, u[0] - pad * w_), max(0, u[1] - pad * h_), min(1, u[2] + pad * w_), min(1, u[3] + pad * h_)]
        veh = [b for b, c in zip(r.boxes.xyxyn.tolist(), r.boxes.cls.tolist()) if int(c) in VEH and (b[2] - b[0]) * (b[3] - b[1]) >= 0.002]
        if not any(touches(v, uu) for v in veh): stats["FASDD no vehicle at the fire (skipped)"] += 1; continue
        L = [f"11 {(uu[0]+uu[2])/2:.6f} {(uu[1]+uu[3])/2:.6f} {uu[2]-uu[0]:.6f} {uu[3]-uu[1]:.6f}"]
        for b, c, s in zip(r.boxes.xywhn.tolist(), r.boxes.cls.tolist(), r.boxes.conf.tolist()):
            if s >= 0.5 and b[2] * b[3] >= 0.0004: L.append(f"{MAP[int(c)]} {b[0]:.6f} {b[1]:.6f} {b[2]:.6f} {b[3]:.6f}")
        H, W = im.shape[:2]; s_ = 1280 / max(H, W)
        if s_ < 1: im = cv2.resize(im, (int(W * s_), int(H * s_)), interpolation=cv2.INTER_AREA)
        stem = f"pubfire_fasdd_{base}"[:120]; cv2.imwrite(f"{D}/images/{sp}/{stem}.jpg", im, [cv2.IMWRITE_JPEG_QUALITY, 92])
        open(f"{D}/labels/{sp}/{stem}.txt", "w").write("\n".join(L) + "\n"); stats[f"FASDD kept {sp}"] += 1
    if (i // 64) % 25 == 0: print(i, "/", len(cand), {k: v for k, v in stats.items() if "kept" in k}, flush=True)
json.dump(dict(stats), open(f"{D}/report_fire.json", "w"), indent=1)
for k, v in sorted(stats.items()): print(f"{v:7d}  {k}")
