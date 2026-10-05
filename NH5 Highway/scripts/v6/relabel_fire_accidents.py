#!/usr/bin/env python3
"""Among existing accident_scene(10) images in v3, find those showing FIRE (CLIP zero-shot) and
relabel their class-10 boxes to fire_accident(12). --preview: contact sheet + count only."""
import os, sys, numpy as np, cv2, torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor
V3 = "/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway/datasets/processed_v2_plus_v6_v3"
P = ["a vehicle burning with flames and smoke after a crash", "a car on fire on a road", "a crashed car or truck or bus with fire",
     "a wildfire in a forest or hills", "a building on fire", "close-up of flames and smoke with no vehicle", "firefighters at a fire",
     "a car accident with damaged vehicles and no fire", "vehicles crashed on a road", "a normal road with traffic", "people gathered around a crashed car", "a damaged motorcycle after a collision",
     "a heavily wrecked vehicle with no flames", "a crushed car with metal debris", "a bus or truck accident with no fire"]
NF, NN = 3, 7   # P[:3] vehicle fire; P[3:7] non-vehicle fire (wildfire/building/flames)
dev = "cuda"
clip = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to(dev).half().eval()
proc = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
tin = proc(text=P, return_tensors="pt", padding=True).to(dev)
items = []
for sp in ("train", "val", "test"):
    for f in os.listdir(f"{V3}/labels/{sp}"):
        if f.startswith("fireacc_"): continue
        if any(l.startswith("10 ") for l in open(f"{V3}/labels/{sp}/{f}")):
            items.append((sp, f[:-4]))
if "--preview" in sys.argv: items = items[:1500]
hits = []
B = 64
for i in range(0, len(items), B):
    ims, ok = [], []
    for sp, s in items[i:i+B]:
        p = next((f"{V3}/images/{sp}/{s}{e}" for e in (".jpg", ".jpeg", ".png") if os.path.exists(f"{V3}/images/{sp}/{s}{e}")), None)
        if p:
            try: ims.append(Image.open(p).convert("RGB")); ok.append((sp, s, p))
            except Exception: pass
    with torch.no_grad():
        x = proc(images=ims, return_tensors="pt").to(dev)
        lg = clip(input_ids=tin["input_ids"], attention_mask=tin["attention_mask"], pixel_values=x["pixel_values"].half()).logits_per_image
        sm = lg.float().softmax(-1)
        pr = np.stack([sm[:, :NF].sum(-1).cpu().numpy(), sm[:, NF:NN].sum(-1).cpu().numpy()], 1)
    hits += [(o, q) for o, q in zip(ok, pr) if q[0] > 0.85 or q[1] > 0.85]
veh = [h for h in hits if h[1][0] > 0.85]; other = [h for h in hits if h[1][1] > 0.85]
print("scanned", len(items), "vehicle-fire", len(veh), "non-vehicle fire (wildfire/building)", len(other))
if "--preview" in sys.argv:
    t = [cv2.resize(cv2.imread(o[2]), (320, 240)) for o, _ in veh[:16]]
    while len(t) % 4: t.append(np.zeros((240, 320, 3), np.uint8))
    cv2.imwrite("/tmp/fp.jpg", np.vstack([np.hstack(t[i:i+4]) for i in range(0, len(t), 4)])); sys.exit()
for (sp, s, p), _ in veh:
    lf = f"{V3}/labels/{sp}/{s}.txt"
    open(lf, "w").writelines([("12" + l[2:]) if l.startswith("10 ") else l for l in open(lf)])
for (sp, s, p), _ in other:   # wildfire/building fire wrongly labelled accident_scene: drop that box
    lf = f"{V3}/labels/{sp}/{s}.txt"
    open(lf, "w").writelines([l for l in open(lf) if not l.startswith("10 ")])
print("relabelled to fire_accident", len(veh), "| removed wrong accident_scene box from", len(other))
