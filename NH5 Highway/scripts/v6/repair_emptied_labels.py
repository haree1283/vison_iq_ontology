#!/usr/bin/env python3
"""Repair the v6_* label files emptied by the relabel_fire_accidents.py truncation bug.
Base labels: v6 fire/raqabah rows were whole-image '10 0.5 0.5 1 1'; other accident sources are rebuilt
from datasets/v6/sources labels (class 9 damaged_vehicle -> 10). The ORIGINAL processed_v2_plus_v6 file
(shared hard link) is healed in place with the base labels; then v3 gets a NEW file (unlink + write) with
the fire decision applied: vehicle-fire (CLIP > 0.85) -> class 12, wildfire/building fire (> 0.85) -> class-10 box dropped."""
import os, numpy as np, torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor
B = "/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway/"; D = B + "datasets/"; V3 = D + "processed_v2_plus_v6_v3"; O = D + "processed_v2_plus_v6"
P = open(B + "scripts/v6/relabel_fire_accidents.py").read(); ns = {}; exec(P[P.index("P = ["):P.index("dev = ")], ns); PR, NF, NN = ns["P"], ns["NF"], ns["NN"]
src = {}
for r, _, fs in os.walk(D + "v6/sources"):
    for f in fs:
        if f.endswith(".txt"): src.setdefault(f, []).append(os.path.join(r, f))
dev = "cuda"; clip = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to(dev).half().eval(); proc = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
tin = proc(text=PR, return_tensors="pt", padding=True).to(dev)
E = [(sp, f[:-4]) for sp in ("train", "val", "test") for f in os.listdir(f"{V3}/labels/{sp}") if f.startswith("v6_") and os.path.getsize(f"{V3}/labels/{sp}/{f}") == 0]
print("emptied", len(E)); nveh = noth = nsrc = nnosrc = 0
for i in range(0, len(E), 64):
    ims, ok = [], []
    for sp, s in E[i:i+64]:
        p = next(f"{V3}/images/{sp}/{s}{e}" for e in (".jpg", ".jpeg", ".png") if os.path.exists(f"{V3}/images/{sp}/{s}{e}"))
        ims.append(Image.open(p).convert("RGB")); ok.append((sp, s))
    with torch.no_grad():
        x = proc(images=ims, return_tensors="pt").to(dev)
        sm = clip(input_ids=tin["input_ids"], attention_mask=tin["attention_mask"], pixel_values=x["pixel_values"].half()).logits_per_image.float().softmax(-1)
        va, vb = sm[:, :NF].sum(-1).cpu().numpy(), sm[:, NF:NN].sum(-1).cpu().numpy()
    for (sp, s), a, b in zip(ok, va, vb):
        if s.startswith("v6_fire") or s.startswith("v6_raqabah"):
            base = ["10 0.500000 0.500000 1.000000 1.000000\n"]
        else:
            cand = src.get(s[3:] + ".txt") or [p for k, v in src.items() if k.endswith(s[3:] + ".txt") or (s[3:] + ".txt").endswith(k) for p in v]
            base = [("10" + l[1:]) if l.startswith("9 ") else l for l in open(cand[0])] if cand else []
            nsrc += bool(cand); nnosrc += not cand
        lf, of = f"{V3}/labels/{sp}/{s}.txt", f"{O}/labels/{sp}/{s}.txt"
        if os.path.exists(of) and os.stat(of).st_ino == os.stat(lf).st_ino:
            open(of, "w").writelines(base)          # heal the original in place
        final = [("12" + l[2:]) if (l.startswith("10 ") and a > 0.85) else l for l in base]
        if b > 0.85: final = [l for l in final if not l.startswith("10 ")]
        os.unlink(lf); open(lf, "w").writelines(final)   # v3 gets its own new file
        nveh += a > 0.85; noth += b > 0.85
print("vehicle-fire ->12:", nveh, "| wildfire/building (accident box dropped):", noth, "| rebuilt from source:", nsrc, "| no source found:", nnosrc)
