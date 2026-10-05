#!/usr/bin/env python3
"""FireNET fire images -> fire_accident(12). The detector can't see burning vehicles (known weakness),
so vehicle-fire images are picked with CLIP zero-shot ("burning vehicle on a road" vs. building/
wildfire/kitchen/candle/etc). Label = ONE scene box = union of that image's labelled fire boxes,
padded 50% wide, 40% tall to include the vehicle (same whole-scene convention as accident_scene). --preview writes a contact sheet only."""
import glob, hashlib, shutil, sys, xml.etree.ElementTree as ET
from pathlib import Path
import cv2, numpy as np, torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor
B = Path(__file__).resolve().parents[2]
SRC = B / "datasets/v6/raw/fire/fn/fire-dataset"
V3 = B / "datasets/processed_v2_plus_v6_v3"
PROMPTS = ["a burning car or vehicle on a road after an accident", "a burning bus or truck on a road",
           "a wildfire in a forest", "a building on fire", "a kitchen or stove flame", "a candle or lighter or cigarette",
           "a bonfire or campfire", "an explosion", "a fire with people"]
NV = 2
clip = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").eval(); proc = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
kept = []
for x in sorted(glob.glob(str(SRC / "*/annotations/*.xml"))):
    r = ET.parse(x).getroot()
    img = Path(x).parent.parent / "images" / r.findtext("filename")
    if not img.exists(): continue
    W, H = int(r.findtext("size/width")), int(r.findtext("size/height"))
    with torch.no_grad():
        p = clip(**proc(text=PROMPTS, images=Image.open(img).convert("RGB"), return_tensors="pt", padding=True)).logits_per_image.softmax(-1)[0]
    if float(p[:NV].sum()) < 0.6: continue
    fs = [tuple(float(o.findtext(f"bndbox/{k}")) for k in ("xmin", "ymin", "xmax", "ymax")) for o in r.findall("object")]
    x0, y0, x1, y1 = min(f[0] for f in fs), min(f[1] for f in fs), max(f[2] for f in fs), max(f[3] for f in fs)
    pw, ph = .5 * (x1 - x0), .4 * (y1 - y0)
    x0, y0, x1, y1 = max(0, x0-pw), max(0, y0-ph), min(W, x1+pw), min(H, y1+ph)
    kept.append((img, (x0, y0, x1, y1), (W, H)))
print("kept", len(kept))
if "--preview" in sys.argv:
    t = []
    for img, b, _ in kept[:16]:
        im = cv2.imread(str(img)); cv2.rectangle(im, (int(b[0]), int(b[1])), (int(b[2]), int(b[3])), (0, 0, 255), 3); t.append(cv2.resize(im, (320, 240)))
    while len(t) % 4: t.append(np.zeros((240, 320, 3), np.uint8))
    cv2.imwrite("/tmp/fire_prev.jpg", np.vstack([np.hstack(t[i:i+4]) for i in range(0, len(t), 4)])); sys.exit()
c = {"train": 0, "val": 0, "test": 0}
for img, (x0, y0, x1, y1), (W, H) in kept:
    sp = ["val", "test"][int(hashlib.md5(img.name.encode()).hexdigest(), 16) % 10] if int(hashlib.md5(img.name.encode()).hexdigest(), 16) % 10 < 2 else "train"
    n = "fireacc_" + hashlib.md5(str(img).encode()).hexdigest()[:10]
    shutil.copy(img, V3 / f"images/{sp}/{n}.jpg")
    (V3 / f"labels/{sp}/{n}.txt").write_text(f"12 {(x0+x1)/2/W:.6f} {(y0+y1)/2/H:.6f} {(x1-x0)/W:.6f} {(y1-y0)/H:.6f}\n"); c[sp] += 1
print(c)
