#!/usr/bin/env python3
"""Convert the thirdeyelabs/indian-road-dataset sample (15 WebDataset tar shards downloaded to
datasets/v6/raw/indian_road_dataset/data/) into a v6 source: real Indian road footage (CP PLUS
CCTV + dashcam clips) with machine-generated (not human-verified) BDD100K-style boxes -- the exact
dense mixed-traffic scene composition (multiple small/distant motorcycles, autos, pedestrians per
frame) that v6's own curated sources are thin on.

Each tar member is <clip_uuid>_<frame>.{jpg,png,json}; the .png segmentation mask is ignored here
(detection only). Box confidence < MIN_CONF is dropped as a quality filter since these are
auto-generated labels, not ground truth.

Usage:
  python scripts/v6/convert_indian_road_dataset.py
"""
import json
import tarfile
from collections import Counter
from pathlib import Path

from PIL import Image

from classes import CLASS_IDS

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "datasets" / "v6" / "raw" / "indian_road_dataset" / "data"
OUT = ROOT / "datasets" / "v6" / "sources" / "indian_road_dataset" / "train"
MIN_CONF = 0.5

CATEGORY_MAP = {
    "person": "person", "rider": "person",
    "car": "car", "truck": "truck", "bus": "bus",
    "motorcycle": "motorcycle", "bicycle": "bicycle", "autorickshaw": "auto",
    # dropped (no v6 equivalent): animal, vehicle fallback, traffic light, traffic sign
}


def main():
    (OUT / "images").mkdir(parents=True, exist_ok=True)
    (OUT / "labels").mkdir(parents=True, exist_ok=True)

    box_counts = Counter()
    images_written = 0
    shards = sorted(RAW.glob("train-*.tar"))
    for shard in shards:
        with tarfile.open(shard) as tf:
            members = {m.name: m for m in tf.getmembers()}
            stems = sorted({n[:-5] for n in members if n.endswith(".json")})
            for stem in stems:
                jpg_name, json_name = f"{stem}.jpg", f"{stem}.json"
                if jpg_name not in members:
                    continue
                data = json.loads(tf.extractfile(members[json_name]).read())
                lines = []
                for label in data.get("labels", []):
                    v6_name = CATEGORY_MAP.get(label["category"])
                    if v6_name is None:
                        continue
                    if label.get("confidence", 1.0) < MIN_CONF:
                        continue
                    box = label["box2d"]
                    lines.append((CLASS_IDS[v6_name], box["x1"], box["y1"], box["x2"], box["y2"]))
                if not lines:
                    continue

                jpg_bytes = tf.extractfile(members[jpg_name]).read()
                out_stem = f"indianroad_{stem.replace('/', '_')}"
                img_path = OUT / "images" / f"{out_stem}.jpg"
                img_path.write_bytes(jpg_bytes)
                w, h = Image.open(img_path).size

                label_lines = []
                for cid, x1, y1, x2, y2 in lines:
                    cx, cy = (x1 + x2) / 2 / w, (y1 + y2) / 2 / h
                    bw, bh = (x2 - x1) / w, (y2 - y1) / h
                    label_lines.append(f"{cid} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
                (OUT / "labels" / f"{out_stem}.txt").write_text("\n".join(label_lines) + "\n")
                images_written += 1
                for cid, *_ in lines:
                    name = next(n for n, i in CLASS_IDS.items() if i == cid)
                    box_counts[name] += 1
        print(f"[{shard.name}] done, running total images={images_written}")

    print(f"\nimages written: {images_written}")
    print("boxes per class:", dict(box_counts))


if __name__ == "__main__":
    main()
