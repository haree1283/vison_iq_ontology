#!/usr/bin/env python3
"""Oversample pothole-containing train images in processed_v2_plus_v6: pothole (9,680 boxes) is
drowned out by person (58,108) and car (49,801) in the loss, so the model rarely gets gradient
signal for it per epoch even though the raw count isn't tiny. This makes REPEAT copies (mirror +
crop + brightness jitter, same recipe used elsewhere in this project for under-represented
classes) of every train image containing a pothole box, so the class shows up more often per
epoch without touching val/test (evaluation must stay on real, non-duplicated images).

Usage:
  python scripts/v6/oversample_pothole.py [--repeat 3]
"""
import argparse
import random
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "datasets" / "processed_v2_plus_v6"
POTHOLE_ID = 6
SEED = 20260918


def augment(image, variant, rng):
    out = cv2.flip(image, 1)
    if variant > 1:
        h, w = out.shape[:2]
        scale = rng.uniform(0.85, 0.95)
        ch, cw = int(h * scale), int(w * scale)
        y, x = rng.randint(0, h - ch), rng.randint(0, w - cw)
        out = cv2.resize(out[y:y + ch, x:x + cw], (w, h))
        out = cv2.convertScaleAbs(out, alpha=rng.uniform(0.8, 1.2), beta=rng.uniform(-25, 25))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", type=int, default=3, help="extra copies per pothole image")
    args = ap.parse_args()

    img_dir, lbl_dir = D / "images" / "train", D / "labels" / "train"
    rng = random.Random(SEED)

    targets = []
    for lbl in lbl_dir.glob("*.txt"):
        if lbl.stem.endswith(tuple(f"_pothaug{i}" for i in range(1, args.repeat + 1))):
            continue  # don't re-oversample an already-oversampled copy
        lines = lbl.read_text().splitlines()
        if any(line.split() and int(line.split()[0]) == POTHOLE_ID for line in lines):
            targets.append((lbl, lines))

    print(f"pothole-containing train images found: {len(targets)}")
    added = 0
    for lbl, lines in targets:
        img_path = next((p for ext in (".jpg", ".jpeg", ".png")
                          if (p := img_dir / f"{lbl.stem}{ext}").is_file()), None)
        if img_path is None:
            continue
        image = cv2.imread(str(img_path))
        if image is None:
            continue
        for variant in range(1, args.repeat + 1):
            aug_stem = f"{lbl.stem}_pothaug{variant}"
            if (img_dir / f"{aug_stem}{img_path.suffix}").exists():
                continue  # already done in a previous run
            flipped = augment(image, variant, rng)
            cv2.imwrite(str(img_dir / f"{aug_stem}{img_path.suffix}"), flipped,
                        [int(cv2.IMWRITE_JPEG_QUALITY), 90])
            mirrored = []
            for line in lines:
                parts = line.split()
                if not parts:
                    continue
                cid, cx, cy, w, h = int(parts[0]), *map(float, parts[1:5])
                mirrored.append(f"{cid} {1 - cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
            (lbl_dir / f"{aug_stem}.txt").write_text("\n".join(mirrored) + "\n")
            added += 1

    print(f"oversampled copies added: {added}")


if __name__ == "__main__":
    main()
