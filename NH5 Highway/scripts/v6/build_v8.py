"""v8 = 12 classes: traffic_cone merged into road_construction (one work-zone class), plus lots of new public road-work data.
Only public datasets, nothing from vedios/. Usage:
  build_v8.py new discovered,autonomos,german     add new road-work sources (COCO auto-labels vehicles/persons)
  build_v8.py new starline
  build_v8.py base                                 hardlink v6, remap 11(cone)->zone box, 12(fire)->11, cap cone-only images
"""
import os, sys, io, re, glob, json, hashlib, random, shutil, collections, zipfile
import numpy as np, cv2
from ultralytics import YOLO
random.seed(8)
V6 = "datasets/processed_v2_plus_v6_v6"; D = "datasets/processed_v2_plus_v6_v8"
PR = "datasets/v6/public_roadwork"; ANN = f"{PR}/anuragxel__roadwork"
NAMES = ['person','bicycle','car','motorcycle','bus','truck','pothole','license_plate','auto','road_construction','accident_scene','fire_accident']
COCO2OURS = {0: 0, 1: 1, 2: 2, 3: 3, 5: 4, 7: 5}
ZONE_CATS = {'Cone','Vertical Panel','Temporary Traffic Control Sign','Tubular Marker','Drum','Work Vehicle','Barricade','Barrier','Work Equipment','Fence','Arrow Board','Temporary Traffic Control Message Board','Other Roadwork Objects'}
for sp in ("train", "val", "test"):
    os.makedirs(f"{D}/images/{sp}", exist_ok=True); os.makedirs(f"{D}/labels/{sp}", exist_ok=True)
_coco = None
def coco():
    global _coco
    if _coco is None: _coco = YOLO("/media/nikhil/New Volume/Nikhil/yolov8l.pt")
    return _coco
def hsplit(key, val=5, test=5):
    h = int(hashlib.md5(key.encode()).hexdigest(), 16) % 100
    return "val" if h < val else "test" if h < val + test else "train"
def zone_line(boxes, W, H, pad=0.02):  # boxes: list of xyxy pixels
    x1 = min(b[0] for b in boxes); y1 = min(b[1] for b in boxes); x2 = max(b[2] for b in boxes); y2 = max(b[3] for b in boxes)
    pw, ph = (x2 - x1) * pad, (y2 - y1) * pad; x1, y1, x2, y2 = max(0, x1 - pw), max(0, y1 - ph), min(W, x2 + pw), min(H, y2 + ph)
    if (x2 - x1) * (y2 - y1) / (W * H) < 0.002: return None
    return f"9 {(x1+x2)/2/W:.6f} {(y1+y2)/2/H:.6f} {(x2-x1)/W:.6f} {(y2-y1)/H:.6f}"
def flush(items, stats, tag):
    """items: list of (split, stem, bgr_image, zone_line) -> save images, auto-label vehicles/persons, write labels"""
    if not items: return
    tmp = []
    for sp, stem, img, zl in items:
        p = f"{D}/images/{sp}/{stem}.jpg"; cv2.imwrite(p, img, [cv2.IMWRITE_JPEG_QUALITY, 92]); tmp.append((sp, stem, p, zl))
    for i in range(0, len(tmp), 16):
        ch = tmp[i:i+16]
        for (sp, stem, p, zl), r in zip(ch, coco().predict([c[2] for c in ch], imgsz=960, conf=0.5, classes=list(COCO2OURS), verbose=False)):
            L = [zl]
            for b, c in zip(r.boxes.xywhn.tolist(), r.boxes.cls.tolist()):
                if b[2] * b[3] >= 0.0004: L.append(f"{COCO2OURS[int(c)]} {b[0]:.6f} {b[1]:.6f} {b[2]:.6f} {b[3]:.6f}")
            open(f"{D}/labels/{sp}/{stem}.txt", "w").write("\n".join(L) + "\n"); stats[f"{tag} {sp}"] += 1
def existing_stems():
    s = set()
    for sp in ("train", "val", "test"):
        for f in os.listdir(f"{V6}/labels/{sp}"):
            m = re.sub(r"^roadwork_(cmu_roadworkcmu_)?", "", f[:-4]); s.add(m)
    return s
stats = collections.Counter(); stage = sys.argv[1]
if stage == "new":
    for src in sys.argv[2].split(","):
        items = []
        def push(sp, stem, img, zl):
            items.append((sp, stem, img, zl))
            if len(items) >= 256: flush(items, stats, src); items.clear()
        if src == "discovered":
            for jf in sorted(glob.glob(f"{ANN}/x_disc/roadwork_discovered_subsets/*/annotations/instances_default.json")):
                sub = jf.split("/")[-3]; d = json.load(open(jf)); cats = {c["id"]: c["name"] for c in d["categories"]}; per = collections.defaultdict(list)
                for a in d["annotations"]:
                    if cats[a["category_id"]] in ZONE_CATS: x, y, w, h = a["bbox"]; per[a["image_id"]].append([x, y, x + w, y + h])
                for im in d["images"]:
                    bx = per.get(im["id"]);
                    if not bx: continue
                    img = cv2.imread(f"{ANN}/x_disc/roadwork_discovered_subsets/{sub}/images/{im['file_name']}")
                    if img is None: continue
                    H, W = img.shape[:2]; sx, sy = W / im["width"], H / im["height"]
                    zl = zone_line([[b[0]*sx, b[1]*sy, b[2]*sx, b[3]*sy] for b in bx], W, H)
                    if zl is None: continue
                    sp = "test" if sub == "tesla" else "val" if sub == "arizona" else "train"
                    push(sp, f"pubrw_disc_{sub}_{os.path.splitext(im['file_name'])[0]}", img, zl)
        elif src == "autonomos":
            z = zipfile.ZipFile(f"{ANN}/german/AutoNOMOS_Labs_dataset.zip"); names = z.namelist(); lab = [n for n in names if "/labels/" in n and n.endswith(".txt")]
            for ln in lab:
                imn = ln.replace("/labels/", "/images/"); imn = next((imn[:-4] + e for e in (".jpg", ".png", ".jpeg", ".JPG") if imn[:-4] + e in names), None)
                if imn is None: continue
                rows = [l.split() for l in z.read(ln).decode().splitlines() if l.strip()]
                if not rows: continue
                img = cv2.imdecode(np.frombuffer(z.read(imn), np.uint8), 1)
                if img is None: continue
                H, W = img.shape[:2]; bx = [[(float(r[1])-float(r[3])/2)*W, (float(r[2])-float(r[4])/2)*H, (float(r[1])+float(r[3])/2)*W, (float(r[2])+float(r[4])/2)*H] for r in rows]
                zl = zone_line(bx, W, H)
                if zl is None: continue
                base = os.path.basename(ln)[:-4]; grp = re.sub(r"_frame.*|\d{4,}$", "", base)
                push(hsplit(grp), f"pubrw_auto_{ln.split('/')[1]}_{base}"[:120], img, zl)
        elif src == "german":
            have = existing_stems(); z = zipfile.ZipFile(f"{ANN}/german/ROADWork_German_objects_extended.zip"); names = set(z.namelist())
            for ln in sorted(n for n in names if "/labels/" in n and n.endswith(".txt")):
                base = os.path.basename(ln)[:-4]
                if base in have or any(base in h for h in ()): stats["german skipped (already in dataset)"] += 1; continue
                imn = next((ln.replace("/labels/", "/images/")[:-4] + e for e in (".jpg", ".png", ".jpeg") if ln.replace("/labels/", "/images/")[:-4] + e in names), None)
                rows = [l.split() for l in z.read(ln).decode().splitlines() if l.strip()]
                if imn is None or not rows: continue
                img = cv2.imdecode(np.frombuffer(z.read(imn), np.uint8), 1); H, W = img.shape[:2]
                bx = [[(float(r[1])-float(r[3])/2)*W, (float(r[2])-float(r[4])/2)*H, (float(r[1])+float(r[3])/2)*W, (float(r[2])+float(r[4])/2)*H] for r in rows]
                zl = zone_line(bx, W, H)
                if zl: push("train", f"pubrw_ger_{base}"[:120], img, zl)
        elif src == "starline":
            import pyarrow.parquet as pq
            root = f"{PR}/StarLine__Roadwork_Cones"; zp = glob.glob(f"{root}/*.zip")
            if zp and not os.path.isdir(f"{root}/x"): zipfile.ZipFile(zp[0]).extractall(f"{root}/x")
            for pf in glob.glob(f"{root}/x/**/*.parquet", recursive=True):
                t = pq.read_table(pf).to_pandas(); per = collections.defaultdict(list)
                for _, r in t.iterrows(): x, y, w, h = r["bbox_coords"]; per[r["image_path"]].append([x, y, x + w, y + h])
                for rel, bx in per.items():
                    sp0 = "train" if rel.startswith("train") else "test"; p = os.path.join(os.path.dirname(pf), rel)
                    img = cv2.imread(p)
                    if img is None: stats["starline missing image"] += 1; continue
                    H, W = img.shape[:2]; zl = zone_line(bx, W, H)
                    if zl: push("train" if sp0 == "train" else hsplit(rel, 50, 50), f"pubrw_star_{sp0}_{os.path.splitext(os.path.basename(rel))[0]}"[:120], img, zl)
        flush(items, stats, src); items.clear()
elif stage == "base":
    new_rc = sum(1 for sp in ("train",) for f in glob.glob(f"{D}/labels/{sp}/pubrw_*.txt"))
    have_rc = 0; cone_only = []; keep = []
    for sp in ("train", "val", "test"):
        for f in glob.glob(f"{V6}/labels/{sp}/*.txt"):
            rows = [l.split() for l in open(f) if l.strip()]; cls = {r[0] for r in rows}
            if "11" in cls and "9" not in cls: cone_only.append((sp, f))
            elif "9" in cls: have_rc += (sp == "train")
    total_rc = have_rc + new_rc; cap = int(0.5 * total_rc)
    random.shuffle(cone_only); allowed = set(f for _, f in cone_only[:cap])
    print(f"road-work zone images: existing {have_rc} + new {new_rc} = {total_rc}; cone-only images available {len(cone_only)}, cap {cap}", flush=True)
    for sp in ("train", "val", "test"):
        for f in glob.glob(f"{V6}/labels/{sp}/*.txt"):
            stem = os.path.basename(f)[:-4]; rows = [l.split() for l in open(f) if l.strip()]; cls = {r[0] for r in rows}
            if "11" in cls and "9" not in cls and f not in allowed: stats["cone-only images dropped (cap)"] += 1; continue
            img = next((e for e in (".jpg", ".png", ".jpeg") if os.path.exists(f"{V6}/images/{sp}/{stem}{e}")), None)
            if img is None: continue
            out = [r for r in rows if r[0] not in ("9", "11", "12")]
            zb = [r for r in rows if r[0] in ("9", "11")]
            if zb:
                x1 = min(float(r[1]) - float(r[3]) / 2 for r in zb); x2 = max(float(r[1]) + float(r[3]) / 2 for r in zb)
                y1 = min(float(r[2]) - float(r[4]) / 2 for r in zb); y2 = max(float(r[2]) + float(r[4]) / 2 for r in zb)
                pw, ph = (x2 - x1) * 0.02, (y2 - y1) * 0.02; x1, y1, x2, y2 = max(0, x1 - pw), max(0, y1 - ph), min(1, x2 + pw), min(1, y2 + ph)
                out.append(["9", f"{(x1+x2)/2:.6f}", f"{(y1+y2)/2:.6f}", f"{x2-x1:.6f}", f"{y2-y1:.6f}"]); stats["images with a zone box"] += 1
            out += [["11"] + r[1:] for r in rows if r[0] == "12"]
            if not os.path.exists(f"{D}/images/{sp}/{stem}{img}"): os.link(f"{V6}/images/{sp}/{stem}{img}", f"{D}/images/{sp}/{stem}{img}")
            open(f"{D}/labels/{sp}/{stem}.txt", "w").write("\n".join(" ".join(r) for r in out) + ("\n" if out else "")); stats[f"base {sp}"] += 1
    open(f"{D}/data.yaml", "w").write(f"path: {os.path.abspath(D)}\ntrain: images/train\nval: images/val\ntest: images/test\nnc: 12\nnames: {NAMES}\n")
json.dump(dict(stats), open(f"{D}/report_{stage}.json", "w"), indent=1)
for k, v in sorted(stats.items()): print(f"{v:7d}  {k}")
