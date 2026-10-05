#!/usr/bin/env python3
"""Run the trained detector on a video and overlay EasyOCR-read text on every license_plate box,
saving an annotated copy for review.

Usage:
  python scripts/v6/test_with_ocr.py --weights <best.pt> --video <path> [--video <path2> ...] --out-dir <dir>
"""
import argparse
from pathlib import Path

import cv2
import easyocr
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[2]


def read_plate(reader, crop):
    if crop.size == 0:
        return ""
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    results = reader.readtext(gray, detail=1)
    if not results:
        return ""
    return max(results, key=lambda r: r[2])[1].upper().replace(" ", "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", required=True)
    ap.add_argument("--video", action="append", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--conf", type=float, default=0.35)
    ap.add_argument("--ocr-every", type=int, default=5, help="run OCR every N frames per track to save time")
    args = ap.parse_args()

    model = YOLO(args.weights)
    plate_id = next(i for i, n in model.names.items() if n == "license_plate")
    reader = easyocr.Reader(["en"], gpu=True)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for video in args.video:
        video = Path(video)
        cap = cv2.VideoCapture(str(video))
        fps = cap.get(cv2.CAP_PROP_FPS) or 25
        w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        out_path = out_dir / f"{video.stem}_ocr.mp4"
        writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))

        last_text = {}  # track_id -> last read text, so we don't re-OCR every frame
        frame_idx = 0
        for result in model.track(str(video), conf=args.conf, persist=True, stream=True, verbose=False):
            frame = result.orig_img.copy()
            boxes = result.boxes
            if boxes is not None:
                for box in boxes:
                    cls_id = int(box.cls[0])
                    x0, y0, x1, y1 = map(int, box.xyxy[0].tolist())
                    label = model.names[cls_id]
                    conf = float(box.conf[0])
                    color = (0, 255, 255) if cls_id == plate_id else (0, 200, 0)
                    cv2.rectangle(frame, (x0, y0), (x1, y1), color, 2)
                    text = f"{label} {conf:.2f}"
                    if cls_id == plate_id:
                        tid = int(box.id[0]) if box.id is not None else -1
                        if tid not in last_text or frame_idx % args.ocr_every == 0:
                            crop = result.orig_img[max(0, y0):y1, max(0, x0):x1]
                            last_text[tid] = read_plate(reader, crop) or last_text.get(tid, "")
                        if last_text.get(tid):
                            text = f"{last_text[tid]}"
                    cv2.putText(frame, text, (x0, max(0, y0 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
            writer.write(frame)
            frame_idx += 1
        writer.release()
        cap.release()
        print(f"[{video.name}] -> {out_path}")


if __name__ == "__main__":
    main()
