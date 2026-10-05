#!/usr/bin/env python3
"""Kaggle fire sets (awaissaddiqui 'fire/smoke/accident/pothole' + ankan1998 'fire') -> fire_accident(12).
Candidate = image with >=1 labelled fire box; kept if CLIP says vehicle-fire > THR (same prompts as
relabel_fire_accidents.py), near-duplicates dropped (dhash <=6 bits vs a kept image). Scene box = union of
the fire boxes + vehicle boxes touching them, padded 30%; if no vehicle box, fire boxes padded 50%x40%.
--preview: contact sheet + counts only."""
import glob, hashlib, os, shutil, sys, cv2, numpy as np, torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor
B = "/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway/"; V3 = B + "datasets/processed_v2_plus_v6_v3"; R = B + "datasets/v6/raw/fireacc2/"
THR = 0.85
P = open(B + "scripts/v6/relabel_fire_accidents.py").read(); ns = {}; exec(P[P.index("P = ["):P.index("dev = ")], ns); PR, NF = ns["P"], ns["NF"]
dev = "cuda"; clip = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to(dev).half().eval(); proc = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
tin = proc(text=PR, return_tensors="pt", padding=True).to(dev)
def dhash(im): g = cv2.resize(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY), (9, 8)); return (g[:, 1:] > g[:, :-1]).flatten()
def ov(a, b): return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])
cands = []  # (img path, fire class id, vehicle class id or None, label path)
for sp in ("train", "valid"):
    for lf in glob.glob(R + f"b/dataset/{sp}/labels/*.txt"):
        L = [l.split() for l in open(lf) if l.strip()]
        if any(l[0] in ("3", "4") for l in L):
            ip = next((lf.replace("/labels/", "/images/")[:-4] + e for e in (".jpg", ".jpeg", ".png") if os.path.exists(lf.replace("/labels/", "/images/")[:-4] + e)), None)
            if ip: cands.append((ip, "3", "1", lf))
for sp in ("train", "valid", "test"):
    for lf in glob.glob(R + f"a/{sp}/labels/*.txt"):
        ip = next((lf.replace("/labels/", "/images/")[:-4] + e for e in (".jpg", ".jpeg", ".png") if os.path.exists(lf.replace("/labels/", "/images/")[:-4] + e)), None)
        if ip: cands.append((ip, "0", None, lf))
print("fire candidates", len(cands))
kept, hs = [], []
for c in cands:
    im = cv2.imread(c[0])
    if im is None or min(im.shape[:2]) < 100: continue
    h = dhash(im)
    if any((h != k).sum() <= 2 for k in hs[-4000:]): continue
    hs.append(h); kept.append((c, im))
print("kept fire/smoke images (deduped)", len(kept))
def scene_box(c, im):
    H, W = im.shape[:2]; L = [l for l in open(c[3]).read().splitlines() if l.strip()]
    def xy(l): x, y, w, h = map(float, l.split()[1:5]); return ((x-w/2)*W, (y-h/2)*H, (x+w/2)*W, (y+h/2)*H)
    fires = [xy(l) for l in L if l.split()[0] == c[1] or (c[2] and l.split()[0] == "4")]; veh = [xy(l) for l in L if c[2] and l.split()[0] == c[2]]
    if not fires: return None
    tv = [v for v in veh if any(ov(v, f) for f in fires)]
    bx = fires + tv
    x0, y0, x1, y1 = min(b[0] for b in bx), min(b[1] for b in bx), max(b[2] for b in bx), max(b[3] for b in bx)
    px, py = (.3 if tv else .15) * (x1-x0), (.3 if tv else .15) * (y1-y0)
    return max(0, x0-px), max(0, y0-py), min(W, x1+px), min(H, y1+py)
if "--preview" in sys.argv:
    t = []
    for c, im in kept[::max(1, len(kept)//16)][:16]:
        b = scene_box(c, im); im = im.copy()
        if b: cv2.rectangle(im, (int(b[0]), int(b[1])), (int(b[2]), int(b[3])), (0, 0, 255), 4)
        t.append(cv2.resize(im, (320, 240)))
    while len(t) % 4: t.append(np.zeros((240, 320, 3), np.uint8))
    cv2.imwrite("/tmp/fk.jpg", np.vstack([np.hstack(t[i:i+4]) for i in range(0, len(t), 4)])); sys.exit()
cnt = {"train": 0, "val": 0, "test": 0}
for c, im in kept:
    b = scene_box(c, im)
    if not b: continue
    H, W = im.shape[:2]; x0, y0, x1, y1 = b
    grp = os.path.basename(c[0]).split(".rf.")[0]; hv = int(hashlib.md5(grp.encode()).hexdigest(), 16) % 10
    sp = "val" if hv == 0 else "test" if hv == 1 else "train"
    n = "fireacc_k_" + hashlib.md5(c[0].encode()).hexdigest()[:10]
    cv2.imwrite(f"{V3}/images/{sp}/{n}.jpg", im, [cv2.IMWRITE_JPEG_QUALITY, 92])
    open(f"{V3}/labels/{sp}/{n}.txt", "w").write(f"12 {(x0+x1)/2/W:.6f} {(y0+y1)/2/H:.6f} {(x1-x0)/W:.6f} {(y1-y0)/H:.6f}\n"); cnt[sp] += 1
print("added", cnt)
