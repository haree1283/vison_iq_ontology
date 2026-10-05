#!/usr/bin/env python3
"""Oversample under-represented/under-performing classes in processed_v2_plus_v6_v3's train split:
fire_accident (1,509 train images), bicycle (2,586), bus (3,503) and accident_scene (6,810) are
drowned out by car (21,091) and person (14,486) in the loss even though their raw counts aren't
tiny; pothole isn't scarce but its recall (0.557 in the v3_13class run) shows it needs more
gradient signal too. Makes REPEAT copies (mirror + crop + brightness jitter, same recipe as
oversample_pothole.py) of every train image containing a box of each target class, so the class
shows up more often per epoch without touching val/test (evaluation must stay on real,
non-duplicated images).

An image with boxes from more than one target class is only oversampled once, under whichever
target class is rarest overall, so it isn't multiplied twice.

Usage:
  python scripts/v6/balance_v3_train_classes.py
"""
import random
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "datasets" / "processed_v2_plus_v6_v3"
SEED = 20260922

# class id -> (short tag for filenames, extra copies per image), rarest first
TARGETS = {
    12: ("fire", 4),  # fire_accident
    1: ("bike", 2),   # bicycle
    4: ("bus", 1),    # bus
    10: ("acc", 1),   # accident_scene
    6: ("pot", 2),    # pothole -- not scarce (15,044 train images) but recall was only 0.557 in
                       # v3_13class: low-contrast, irregular-shaped, easily confused with shadows/
                       # patches, so it needs more gradient signal per epoch, not just more raw data
}


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
    img_dir, lbl_dir = D / "images" / "train", D / "labels" / "train"
    rng = random.Random(SEED)
    suffixes = tuple(f"_bal{tag}{i}" for tag, _ in TARGETS.values() for i in range(1, 6))

    per_class = {cid: [] for cid in TARGETS}
    for lbl in sorted(lbl_dir.glob("*.txt")):
        if lbl.stem.endswith(suffixes):
            continue  # don't re-oversample an already-oversampled copy
        lines = [l for l in lbl.read_text().splitlines() if l.strip()]
        if not lines:
            continue
        classes = {int(l.split()[0]) for l in lines}
        present = [c for c in TARGETS if c in classes]
        if present:
            per_class[present[0]].append((lbl, lines))  # TARGETS is ordered rarest first

    for cid, (tag, repeat) in TARGETS.items():
        targets = per_class[cid]
        print(f"{tag}: {len(targets)} train images claimed, adding up to {repeat} copies each")
        added = 0
        for lbl, lines in targets:
            img_path = next((p for ext in (".jpg", ".jpeg", ".png")
                              if (p := img_dir / f"{lbl.stem}{ext}").is_file()), None)
            if img_path is None:
                continue
            image = cv2.imread(str(img_path))
            if image is None:
                continue
            for variant in range(1, repeat + 1):
                aug_stem = f"{lbl.stem}_bal{tag}{variant}"
                if (img_dir / f"{aug_stem}{img_path.suffix}").exists():
                    continue  # already done in a previous run
                out = augment(image, variant, rng)
                cv2.imwrite(str(img_dir / f"{aug_stem}{img_path.suffix}"), out,
                            [int(cv2.IMWRITE_JPEG_QUALITY), 90])
                mirrored = []
                for line in lines:
                    parts = line.split()
                    c, cx, cy, w, h = int(parts[0]), *map(float, parts[1:5])
                    mirrored.append(f"{c} {1 - cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
                (lbl_dir / f"{aug_stem}.txt").write_text("\n".join(mirrored) + "\n")
                added += 1
        print(f"{tag}: {added} copies added")


if __name__ == "__main__":
    main()
