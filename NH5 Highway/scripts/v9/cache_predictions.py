#!/usr/bin/env python3
"""One pass over the v9 dataset copy: v8 predictions (all classes, conf >= 0.10) + a 64-bit dHash per image.
Writes runs/v9_audit/cache_<split>.jsonl: {"img", "w", "h", "hash", "preds": [[cls, conf, x0, y0, x1, y1], ...]}
(boxes in pixels). Read-only on the dataset. Resumable: skips images already in the cache."""
import json, os, sys
from pathlib import Path
import cv2, numpy as np
from ultralytics import YOLO

ROOT = Path("/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway")
D = ROOT / "datasets/processed_v9"
OUT = ROOT / "runs/v9_audit"
model = YOLO(str(ROOT / "models/nh5_v8_final_ep100.pt"))


def dhash(img):
    g = cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (9, 8), interpolation=cv2.INTER_AREA)
    bits = (g[:, 1:] > g[:, :-1]).flatten()
    return int("".join("1" if b else "0" for b in bits), 2)


for split in (sys.argv[1:] or ["val", "test", "train"]):
    cache = OUT / f"cache_{split}.jsonl"
    done = set()
    if cache.exists():
        done = {json.loads(l)["img"] for l in cache.open()}
    imgs = [p for p in sorted((D / "images" / split).iterdir()) if p.name not in done]
    print(f"{split}: {len(imgs)} to do ({len(done)} cached)", flush=True)
    with cache.open("a") as fh:
        for k in range(0, len(imgs), 32):
            batch = imgs[k:k + 32]
            arrs = [cv2.imread(str(p)) for p in batch]
            ok = [(p, a) for p, a in zip(batch, arrs) if a is not None]
            if not ok:
                continue
            res = model.predict([a for _, a in ok], imgsz=960, conf=0.10, verbose=False, device=0, batch=32)
            for (p, a), r in zip(ok, res):
                preds = [[int(b.cls), round(float(b.conf), 3), *[round(v, 1) for v in b.xyxy[0].tolist()]] for b in r.boxes]
                fh.write(json.dumps({"img": p.name, "w": a.shape[1], "h": a.shape[0], "hash": dhash(a), "preds": preds}) + "\n")
            if (k // 32) % 100 == 0:
                print(f"  {split} {k + len(batch)}/{len(imgs)}", flush=True)
print("CACHE_DONE", flush=True)
