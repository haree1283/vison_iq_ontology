#!/usr/bin/env python3
"""Sample frames from our own real project footage and label them using the
current best model's own confident predictions (pseudo-labeling), so the
training set includes examples at OUR actual camera's real distance, angle,
and image quality -- something no third-party dataset (CCPD, heterotraffic,
etc.) can provide, since they're all shot on different cameras/roads.

IMPORTANT LIMITATION: this can only reinforce classes the current model
*already* detects with high confidence. It cannot correct an existing
misclassification (e.g. a van the model currently calls "truck") -- doing
that would bake the error into the training set as if it were ground truth.
High CONF_THRESHOLD keeps most such errors out (confident wrong answers are
rarer than confident right ones), but this is a domain-adaptation pass, not
a substitute for actually-corrected labels.

Usage:
  python 18_pseudo_label_real_footage.py --model models/nh5_v2_best.pt --source test_videos/nh5_test_source.mp4 --stride 10
"""
import argparse
from pathlib import Path

import cv2

RAW = Path(__file__).resolve().parent.parent / "datasets" / "raw"
OUT_DIR = RAW / "real_footage_yolo"

# car, motorcycle, bus, truck, bicycle, person -- NOT pothole/license_plate/auto:
# plate boxes from stage-1 are known-unreliable (see 9_plate_pipeline.py), auto
# isn't a class the current deployed model can predict at all, and pothole
# false positives on ordinary road texture are a known risk at low volume review.
PSEUDO_LABEL_CLASSES = {0, 1, 2, 3, 4, 5}
CONF_THRESHOLD = 0.5


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="models/nh5_v2_best.pt")
    ap.add_argument("--source", required=True, help="video file to sample frames from")
    ap.add_argument("--stride", type=int, default=10, help="keep every Nth frame")
    ap.add_argument("--tag", default=None, help="filename prefix (default: derived from source name)")
    args = ap.parse_args()

    from ultralytics import YOLO
    model = YOLO(args.model)

    tag = args.tag or Path(args.source).stem
    img_dir = OUT_DIR / "images"
    lbl_dir = OUT_DIR / "labels"
    img_dir.mkdir(parents=True, exist_ok=True)
    lbl_dir.mkdir(parents=True, exist_ok=True)

    existing = len(list(img_dir.glob(f"{tag}_*.jpg")))
    print(f"{existing} existing frames already saved for tag '{tag}' (will not be overwritten/duplicated)")

    cap = cv2.VideoCapture(args.source)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_idx = 0
    kept = 0
    labeled_boxes = 0

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if frame_idx % args.stride == 0:
            out_name = f"{tag}_{frame_idx:06d}"
            img_path = img_dir / f"{out_name}.jpg"
            if not img_path.exists():
                result = model.predict(frame, conf=CONF_THRESHOLD, classes=list(PSEUDO_LABEL_CLASSES), verbose=False)[0]
                if result.boxes is not None and len(result.boxes) > 0:
                    lines = []
                    for box in result.boxes:
                        cls = int(box.cls[0])
                        cx, cy, w, h = box.xywhn[0].tolist()
                        lines.append(f"{cls} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
                    cv2.imwrite(str(img_path), frame)
                    (lbl_dir / f"{out_name}.txt").write_text("\n".join(lines) + "\n")
                    kept += 1
                    labeled_boxes += len(lines)
        frame_idx += 1
        if frame_idx % 300 == 0:
            print(f"  {frame_idx}/{total} frames scanned, {kept} kept so far")

    cap.release()
    print(f"done. {kept} new frames, {labeled_boxes} pseudo-label boxes -> {OUT_DIR}")


if __name__ == "__main__":
    main()
