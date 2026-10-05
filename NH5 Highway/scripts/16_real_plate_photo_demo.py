#!/usr/bin/env python3
"""Detect + read REAL, non-fabricated license plates from a video built out of
real close-up car photos (datasets/raw/license_plate/). No plate text is
pasted anywhere here -- every plate read is whatever OCR actually sees on the
real photo.

Differs from 9_plate_pipeline.py in two ways, both because this source is
close-up ANPR-style photos rather than highway/dashcam footage:

  1. Detection uses the model's own `license_plate` class directly. On this
     source the model reliably finds the plate box itself (confirmed: 14/15
     sampled real photos), but rarely finds a `car` box in this close-up
     framing -- so 9_plate_pipeline.py's vehicle-gated stage 2 would never
     trigger here. That gating exists for a different, valid reason (a raw
     highway-distance plate-class box is usually too coarse -- see that
     file's docstring); it just doesn't apply to this close-up source.

  2. Plate-text validation uses a generic shape/length check instead of
     9_plate_pipeline.py's strict Indian-format regex, because this dataset
     is Indonesian plates (confirmed: format "B 1492 YQ", not the Indian
     AA00A0000 pattern). No format is enforced -- whatever OCR reads is what
     gets reported.

Usage:
  python 16_real_plate_photo_demo.py --model models/nh5_v2_best.pt --source video_tests/real_plates_demo/source.mp4 --out-dir video_tests/real_plates_demo/run1
"""
import argparse
import json
import re
from pathlib import Path

import cv2

PLATE_CLS = 7
DETECT_CONF = 0.4
CROP_PAD_FRAC = 0.25
CROP_MIN_SIDE = 400
MIN_OCR_CONF = 0.25
TEXT_LEN_RANGE = (4, 12)


def load_model(weights_path):
    from ultralytics import YOLO
    return YOLO(weights_path)


def load_ocr_reader(use_gpu=False):
    import easyocr
    return easyocr.Reader(["en"], gpu=use_gpu)


def clamp_box(x0, y0, x1, y1, w, h):
    return max(0, int(x0)), max(0, int(y0)), min(w, int(x1)), min(h, int(y1))


def read_plate_text(reader, crop_bgr):
    """Run OCR on a plate crop and return (text, conf) for the best candidate
    text region, using only a generic length/alphanumeric shape check --
    no country-specific format is enforced."""
    h, w = crop_bgr.shape[:2]
    scale = max(1.0, CROP_MIN_SIDE / min(h, w))
    if scale > 1.0:
        crop_bgr = cv2.resize(crop_bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)

    raw = reader.readtext(crop_bgr)
    best = None
    for _bbox, text, conf in raw:
        clean = re.sub(r"[^A-Z0-9]", "", text.upper())
        if not (TEXT_LEN_RANGE[0] <= len(clean) <= TEXT_LEN_RANGE[1]):
            continue
        if conf < MIN_OCR_CONF:
            continue
        if best is None or conf > best[1]:
            best = (clean, conf)
    return best


def draw_label(img, x0, y0, text, color=(85, 45, 255)):
    font = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), _ = cv2.getTextSize(text, font, 0.5, 1)
    y0 = max(th + 6, y0)
    cv2.rectangle(img, (x0, y0 - th - 6), (x0 + tw + 6, y0), color, -1)
    cv2.putText(img, text, (x0 + 3, y0 - 4), font, 0.5, (255, 255, 255), 1, cv2.LINE_AA)


def process_frame(model, ocr_reader, frame_bgr):
    h, w = frame_bgr.shape[:2]
    annotated = frame_bgr.copy()
    plates = []

    result = model.predict(frame_bgr, conf=DETECT_CONF, verbose=False)[0]
    if result.boxes is None:
        return annotated, plates

    for box in result.boxes:
        if int(box.cls[0]) != PLATE_CLS:
            continue
        x0, y0, x1, y1 = box.xyxy[0].tolist()
        det_conf = float(box.conf[0])
        bw, bh = x1 - x0, y1 - y0
        px0, py0, px1, py1 = clamp_box(
            x0 - bw * CROP_PAD_FRAC, y0 - bh * CROP_PAD_FRAC,
            x1 + bw * CROP_PAD_FRAC, y1 + bh * CROP_PAD_FRAC, w, h,
        )
        crop = frame_bgr[py0:py1, px0:px1]
        if crop.size == 0:
            continue

        found = read_plate_text(ocr_reader, crop)
        color = (85, 45, 255)
        cv2.rectangle(annotated, (int(x0), int(y0)), (int(x1), int(y1)), color, 2)
        if found:
            text, ocr_conf = found
            draw_label(annotated, int(x0), int(y0), f"{text} ({ocr_conf:.2f})", color)
            plates.append({"box": [x0, y0, x1, y1], "text": text, "ocr_conf": ocr_conf, "det_conf": det_conf})
        else:
            draw_label(annotated, int(x0), int(y0), f"plate {det_conf:.2f}", color)

    return annotated, plates


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="models/nh5_v2_best.pt")
    ap.add_argument("--source", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    import torch
    use_gpu = torch.cuda.is_available()
    print(f"device: {'cuda' if use_gpu else 'cpu'}")

    out_dir = Path(args.out_dir)
    plates_dir = out_dir / "number_plates"
    out_dir.mkdir(parents=True, exist_ok=True)
    plates_dir.mkdir(parents=True, exist_ok=True)

    print("loading model + OCR reader...")
    model = load_model(args.model)
    ocr_reader = load_ocr_reader(use_gpu=use_gpu)

    cap = cv2.VideoCapture(args.source)
    if not cap.isOpened():
        raise SystemExit(f"could not open video: {args.source}")
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    writer = cv2.VideoWriter(str(out_dir / "annotated.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    print(f"processing {args.source} ({total} frames) -> {out_dir / 'annotated.mp4'}")

    seen_texts = set()
    frame_log = []
    frame_idx = 0

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        annotated, plates = process_frame(model, ocr_reader, frame)
        writer.write(annotated)

        for p in plates:
            text = p["text"]
            if text in seen_texts:
                continue
            seen_texts.add(text)
            x0, y0, x1, y1 = [int(v) for v in p["box"]]
            crop = frame[max(0, y0):y1, max(0, x0):x1]
            if crop.size == 0:
                continue
            cv2.imwrite(str(plates_dir / f"{text}_frame{frame_idx:06d}.jpg"), crop)
            print(f"  new plate read: {text}  (ocr_conf={p['ocr_conf']:.2f}, det_conf={p['det_conf']:.2f})")

        frame_log.append({"frame": frame_idx, "plates": [p["text"] for p in plates]})
        frame_idx += 1
        if frame_idx % 30 == 0:
            print(f"  frame {frame_idx}/{total} ({len(seen_texts)} unique plates so far)")

    cap.release()
    writer.release()

    (out_dir / "detections.json").write_text(json.dumps(frame_log, indent=2))
    (out_dir / "plates_found.txt").write_text("\n".join(sorted(seen_texts)) + ("\n" if seen_texts else ""))

    print(f"done. {frame_idx} frames -> {out_dir / 'annotated.mp4'}")
    print(f"{len(seen_texts)} unique plates -> {plates_dir}")


if __name__ == "__main__":
    main()
