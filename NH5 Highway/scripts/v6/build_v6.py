"""v6 = v5 + public accident CCTV (justjuu, CC0) + public pothole photos (manot). v5 untouched (images hardlinked, labels copied).
 - justjuu: 'accident' boxes -> class 10 (already tight on the vehicles involved); vehicles/persons auto-labeled by COCO yolov8l (conf>=0.5)
 - manot: pothole boxes -> class 6, near-duplicates of existing pothole images skipped (dHash); vehicles auto-labeled the same way
Only public datasets; nothing from vedios/."""
import os, io, glob, json, shutil, collections
import numpy as np, cv2, pyarrow.parquet as pq
from PIL import Image
from ultralytics import YOLO
S = "datasets/processed_v2_plus_v6_v5"; D = "datasets/processed_v2_plus_v6_v6"
JJ = "datasets/v6/public_accident/justjuu__traffic-accident-cctv-object-detection/data"
MA = "datasets/v6/public_pothole/manot__pothole-segmentation/data"
MAP = {0: 0, 1: 1, 2: 2, 3: 3, 5: 4, 7: 5}
n = collections.Counter()
for sp in ("train", "val", "test"):
    os.makedirs(f"{D}/images/{sp}", exist_ok=True); os.makedirs(f"{D}/labels/{sp}", exist_ok=True)
    for f in os.listdir(f"{S}/images/{sp}"):
        if not os.path.exists(f"{D}/images/{sp}/{f}"): os.link(f"{S}/images/{sp}/{f}", f"{D}/images/{sp}/{f}")
    for f in os.listdir(f"{S}/labels/{sp}"): shutil.copy2(f"{S}/labels/{sp}/{f}", f"{D}/labels/{sp}/{f}")
open(f"{D}/data.yaml", "w").write(open(f"{S}/data.yaml").read().replace("processed_v2_plus_v6_v5", "processed_v2_plus_v6_v6"))
print("base copied", flush=True)
coco = YOLO("/media/nikhil/New Volume/Nikhil/yolov8l.pt")
def dhash(img):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    s = cv2.resize(g, (9, 8), interpolation=cv2.INTER_AREA); return (s[:, 1:] > s[:, :-1]).flatten()
def vehicle_lines(paths):
    out = []
    for i in range(0, len(paths), 16):
        for r in coco.predict(paths[i:i+16], imgsz=960, conf=0.5, classes=list(MAP), verbose=False):
            L = []
            for b, c in zip(r.boxes.xywhn.tolist(), r.boxes.cls.tolist()):
                if b[2] * b[3] >= 0.0004: L.append(f"{MAP[int(c)]} {b[0]:.6f} {b[1]:.6f} {b[2]:.6f} {b[3]:.6f}")
            out.append(L)
    return out
def save(sp, stem, img_bgr, lines, cls_lines):
    p = f"{D}/images/{sp}/{stem}.jpg"; cv2.imwrite(p, img_bgr, [cv2.IMWRITE_JPEG_QUALITY, 92])
    return p, lines
# ---- justjuu accident
for f in sorted(glob.glob(f"{JJ}/*.parquet")):
    sp = {"train": "train", "validation": "val", "test": "test"}[os.path.basename(f).split("-")[0]]
    pf = pq.ParquetFile(f); k = 0
    for rg in range(pf.num_row_groups):
        rows = pf.read_row_group(rg).to_pylist(); items = []
        for r in rows:
            im = cv2.cvtColor(np.array(Image.open(io.BytesIO(r["image"]["bytes"])).convert("RGB")), cv2.COLOR_RGB2BGR); H, W = im.shape[:2]
            acc = []
            for b, c in zip(r["objects"]["bbox"], r["objects"]["category"]):
                if c != 0: continue
                x, y, w, h = b; x1, y1, x2, y2 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
                if x2 > x1 and y2 > y1: acc.append(f"10 {(x1+x2)/2/W:.6f} {(y1+y2)/2/H:.6f} {(x2-x1)/W:.6f} {(y2-y1)/H:.6f}")
            stem = f"pubacc_jj_{sp}_{os.path.basename(f)[-22:-8].replace('-', '')}_{rg}_{k}"; k += 1
            p = f"{D}/images/{sp}/{stem}.jpg"; cv2.imwrite(p, im, [cv2.IMWRITE_JPEG_QUALITY, 92]); items.append((p, stem, acc))
        veh = vehicle_lines([i[0] for i in items])
        for (p, stem, acc), v in zip(items, veh):
            open(f"{D}/labels/{sp}/{stem}.txt", "w").write("\n".join(acc + v) + ("\n" if acc or v else "")); n[f"justjuu {sp}: images"] += 1; n[f"justjuu {sp}: accident boxes"] += len(acc)
print("justjuu done", dict(n), flush=True)
# ---- manot potholes with dHash dedupe against existing pothole images
existing = []
for sp in ("train", "val", "test"):
    for lf in glob.glob(f"{S}/labels/{sp}/*.txt"):
        if any(l.split() and l.split()[0] == "6" for l in open(lf)):
            b = os.path.basename(lf)[:-4]; p = next((f"{S}/images/{sp}/{b}{e}" for e in (".jpg", ".png", ".jpeg") if os.path.exists(f"{S}/images/{sp}/{b}{e}")), None)
            if p: im = cv2.imread(p);  existing.append(dhash(im)) if im is not None else None
E = np.array(existing); print("existing pothole hashes:", len(E), flush=True)
for zsp, sp in (("train", "train"), ("valid", "val"), ("test", "test")):
    fj = glob.glob(f"{MA}/x_{zsp}/**/_annotations.coco.json", recursive=True)[0]; d = json.load(open(fj)); root = os.path.dirname(fj)
    cats = {c["id"]: c["name"] for c in d["categories"]}; per = collections.defaultdict(list)
    for a in d["annotations"]:
        if cats[a["category_id"]] != "object": per[a["image_id"]].append(a["bbox"])
    items = []
    for im_ in d["images"]:
        boxes = per.get(im_["id"]); 
        if not boxes: continue
        img = cv2.imread(os.path.join(root, im_["file_name"])); 
        if img is None: continue
        if len(E) and (np.count_nonzero(E != dhash(img), axis=1).min() <= 6): n["manot skipped as near-duplicate"] += 1; continue
        H, W = img.shape[:2]; lines = []
        for x, y, w, h in boxes:
            x1, y1, x2, y2 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
            if x2 > x1 and y2 > y1: lines.append(f"6 {(x1+x2)/2/W:.6f} {(y1+y2)/2/H:.6f} {(x2-x1)/W:.6f} {(y2-y1)/H:.6f}")
        stem = f"pubpot_manot_{sp}_{im_['id']}"; p = f"{D}/images/{sp}/{stem}.jpg"; cv2.imwrite(p, img, [cv2.IMWRITE_JPEG_QUALITY, 92]); items.append((p, stem, lines))
    veh = vehicle_lines([i[0] for i in items]) if items else []
    for (p, stem, lines), v in zip(items, veh):
        open(f"{D}/labels/{sp}/{stem}.txt", "w").write("\n".join(lines + v) + "\n"); n[f"manot {sp}: images"] += 1; n[f"manot {sp}: pothole boxes"] += len(lines)
json.dump(dict(n), open(f"{D}/build_report.json", "w"), indent=1)
for k, v in sorted(n.items()): print(f"{v:6d}  {k}")
