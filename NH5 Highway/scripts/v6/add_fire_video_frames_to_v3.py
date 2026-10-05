#!/usr/bin/env python3
"""Fire/accident videos (Kaggle ahmedosman3) -> fire_accident(12) frames. Frames every 0.5 s,
kept only if CLIP says vehicle-fire > 0.85 (same prompts as relabel_fire_accidents.py), near-duplicates
(dhash within 6 bits of a kept frame from the same video) dropped, label = whole-image box
(v6 fire rows' convention). Split by VIDEO so val/test frames never come from a train video."""
import glob, hashlib, os, sys, cv2, numpy as np, torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor
B = "/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway/"; V3 = B + "datasets/processed_v2_plus_v6_v3"
SRC = B + "datasets/v6/raw/firevid/x/All Data"
P = open(B + "scripts/v6/relabel_fire_accidents.py").read(); ns = {}; exec(P[P.index("P = ["):P.index("dev = ")], ns)
PR, NF = ns["P"], ns["NF"]
dev = "cuda"; clip = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to(dev).half().eval(); proc = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
tin = proc(text=PR, return_tensors="pt", padding=True).to(dev)
def dhash(im):
    g = cv2.resize(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY), (9, 8)); return (g[:, 1:] > g[:, :-1]).flatten()
vids = sorted(glob.glob(SRC + "/fire/*") + glob.glob(SRC + "/accident/*"))
stats = {"train": 0, "val": 0, "test": 0}; per_vid = 0; used_vids = 0
for v in vids:
    cap = cv2.VideoCapture(v); fps = cap.get(cv2.CAP_PROP_FPS) or 25; step = max(1, int(fps * 0.5))
    frames = []; i = 0
    while True:
        ok, fr = cap.read()
        if not ok: break
        if i % step == 0: frames.append(fr)
        i += 1
    cap.release()
    if not frames: continue
    keep = []
    for j in range(0, len(frames), 32):
        ch = frames[j:j+32]
        with torch.no_grad():
            x = proc(images=[Image.fromarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB)) for f in ch], return_tensors="pt").to(dev)
            sm = clip(input_ids=tin["input_ids"], attention_mask=tin["attention_mask"], pixel_values=x["pixel_values"].half()).logits_per_image.float().softmax(-1)
            pr = sm[:, :NF].sum(-1).cpu().numpy()
        keep += [f for f, q in zip(ch, pr) if q > 0.85]
    hs, out = [], []
    for f in keep:
        h = dhash(f)
        if all((h != k).sum() > 6 for k in hs): hs.append(h); out.append(f)
    if not out: continue
    used_vids += 1
    hv = int(hashlib.md5(os.path.basename(v).encode()).hexdigest(), 16) % 10
    sp = "val" if hv == 0 else "test" if hv == 1 else "train"
    tag = hashlib.md5(v.encode()).hexdigest()[:8]
    for k, f in enumerate(out):
        n = f"fireacc_vid_{tag}_{k:04d}"
        cv2.imwrite(f"{V3}/images/{sp}/{n}.jpg", f, [cv2.IMWRITE_JPEG_QUALITY, 92])
        open(f"{V3}/labels/{sp}/{n}.txt", "w").write("12 0.500000 0.500000 1.000000 1.000000\n"); stats[sp] += 1
print("videos scanned", len(vids), "videos contributing", used_vids, stats)
