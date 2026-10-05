#!/usr/bin/env python3
"""Clean the fireacc_k_* fire/smoke images in v3: Roboflow exports contain many augmented copies (rotated, noised,
black-wedge shadows) of the same base photo. Re-derive each file's source name (md5 of its original path, as
add_fire_accident_kaggle_to_v3.py named them), group copies by source photo (name before '.rf.'), keep ONE per group
(least black border, least noise), then drop indoor/kitchen/candle/bonfire-type images (CLIP > 0.5).
Real burning-vehicle images (fireacc_ + 10-hex names, recovered v6 fire rows) are untouched."""
import glob, hashlib, os, cv2, numpy as np, torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor
B = "/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway/"; V3 = B + "datasets/processed_v2_plus_v6_v3"; R = B + "datasets/v6/raw/fireacc2/"
paths = glob.glob(R + "b/dataset/*/images/*") + glob.glob(R + "a/*/images/*")
name2src = {"fireacc_k_" + hashlib.md5(p.encode()).hexdigest()[:10]: p for p in paths}
have = {}
for sp in ("train", "val", "test"):
    for f in os.listdir(f"{V3}/images/{sp}"):
        if f.startswith("fireacc_k_"): have[f.rsplit(".", 1)[0]] = (sp, f)
print("fireacc_k in v3", len(have), "matched to source", sum(n in name2src for n in have))
groups = {}
for n, (sp, f) in have.items():
    if n in name2src: groups.setdefault(os.path.basename(name2src[n]).split(".rf.")[0], []).append((n, sp, f))
def score(sp, f):
    im = cv2.imread(f"{V3}/images/{sp}/{f}", 0)
    if im is None: return 9e9
    return float((im < 8).mean()) * 1000 + float(cv2.Laplacian(im, cv2.CV_64F).var()) / 100
keep = set()
for g, L in groups.items():
    keep.add(min(L, key=lambda t: score(t[1], t[2]))[0])
drop = {n for n in have if n not in keep}
print("source photos", len(groups), "keeping", len(keep), "dropping augmented copies", len(drop))
PR = ["a fire inside a room or kitchen", "a candle or lighter or cigarette or stove", "a bonfire or campfire", "a house or building interior with flames",
      "a burning vehicle on a road", "smoke or fire on a road or highway", "a wildfire in a forest", "a building on fire from outside", "a crashed car on a road", "an explosion near a road"]
clip = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to("cuda").half().eval(); proc = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
tin = proc(text=PR, return_tensors="pt", padding=True).to("cuda")
ks = sorted(keep); indoor = set()
for i in range(0, len(ks), 64):
    ch = ks[i:i+64]; ims = [Image.open(f"{V3}/images/{have[n][0]}/{have[n][1]}").convert("RGB") for n in ch]
    with torch.no_grad():
        x = proc(images=ims, return_tensors="pt").to("cuda")
        sm = clip(input_ids=tin["input_ids"], attention_mask=tin["attention_mask"], pixel_values=x["pixel_values"].half()).logits_per_image.float().softmax(-1)
        p = sm[:, :4].sum(-1).cpu().numpy()
    indoor |= {n for n, q in zip(ch, p) if q > 0.5}
print("dropping indoor/kitchen/candle/bonfire", len(indoor))
for n in drop | indoor:
    sp, f = have[n]; os.remove(f"{V3}/images/{sp}/{f}"); os.remove(f"{V3}/labels/{sp}/{n}.txt")
for f in glob.glob(V3 + "/labels/*.cache"): os.remove(f)
c = {sp: sum(1 for f in os.listdir(f"{V3}/labels/{sp}") if any(l.startswith("12 ") for l in open(f"{V3}/labels/{sp}/{f}"))) for sp in ("train", "val", "test")}
print("fire_accident images now", c, sum(c.values()))
