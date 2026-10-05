#!/usr/bin/env python3
"""Run the trained model on a video and save two things to an output folder:

  annotated.mp4        the input video with YOLO boxes/labels drawn on every frame
  number_plates/        one cropped JPG per unique license plate text read

Reuses the two-stage detect-then-OCR logic from 9_plate_pipeline.py (see that
file's docstring for why plates are read via OCR on vehicle crops rather than
the model's own license_plate class). OCR is the slow part on CPU, so it only
runs every --ocr-stride frames per vehicle; YOLO detection + annotation still
happens on every frame, written straight to the output video (no per-frame
image files). Each newly-recognized plate text is saved once, the first time
it's read, to avoid saving near-duplicate crops of the same plate across
consecutive frames.

Usage:
  python 15_video_to_annotated_and_plates.py --model models/nh5_v2_best.pt --source test_videos/nh5_test_source.mp4 --out-dir video_tests/nh5_run1
"""
import argparse
import importlib.util
import json
from pathlib import Path

import cv2

PIPELINE_PATH = Path(__file__).resolve().parent / "9_plate_pipeline.py"
_spec = importlib.util.spec_from_file_location("plate_pipeline", PIPELINE_PATH)
pipeline = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pipeline)


class _NullOCR:
    """Stand-in reader for frames we skip OCR on (see --ocr-stride) -- returns
    no text so pipeline.find_plate_candidate exits immediately without doing
    any real (slow) OCR work."""
    def readtext(self, *_args, **_kwargs):
        return []


SIDEBAR_WIDTH = 320
SIDEBAR_BG = (32, 32, 32)


def add_plate_sidebar(frame, plate_list, current_frame_plates):
    """Return a wider frame with a dark panel on the right listing every
    unique plate read so far in this video, newest at top. Plates read in
    the CURRENT frame are highlighted so it's clear what's being detected
    right now vs. what was found earlier."""
    h, w = frame.shape[:2]
    canvas = cv2.copyMakeBorder(frame, 0, 0, 0, SIDEBAR_WIDTH, cv2.BORDER_CONSTANT, value=SIDEBAR_BG)

    font = cv2.FONT_HERSHEY_SIMPLEX
    x0 = w + 16
    y = 34
    cv2.putText(canvas, "PLATES DETECTED", (x0, y), font, 0.65, (255, 255, 255), 2, cv2.LINE_AA)
    y += 14
    cv2.line(canvas, (x0, y), (w + SIDEBAR_WIDTH - 16, y), (90, 90, 90), 1)
    y += 34

    row_h = 30
    max_rows = max(0, (h - y) // row_h)
    for text in plate_list[:max_rows]:
        is_current = text in current_frame_plates
        color = (90, 230, 90) if is_current else (200, 200, 200)
        marker = ">" if is_current else " "
        cv2.putText(canvas, f"{marker} {text}", (x0, y), font, 0.6, color, 2 if is_current else 1, cv2.LINE_AA)
        y += row_h

    if len(plate_list) > max_rows:
        cv2.putText(canvas, f"...+{len(plate_list) - max_rows} more", (x0, y), font, 0.5, (140, 140, 140), 1, cv2.LINE_AA)

    return canvas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="models/nh5_v2_best.pt", help="path to trained .pt weights")
    ap.add_argument("--source", required=True, help="input video path")
    ap.add_argument("--out-dir", required=True, help="folder to save annotated.mp4 and number_plates/ into")
    ap.add_argument("--conf", type=float, default=0.25, help="YOLO detection confidence threshold")
    ap.add_argument("--ocr-stride", type=int, default=5,
                     help="run plate OCR every N frames per vehicle (default 5; OCR is the slow part on CPU)")
    ap.add_argument("--max-frames", type=int, default=None, help="stop after this many frames (for quick tests)")
    ap.add_argument("--ocr-engine", choices=["easyocr", "paddleocr"], default="easyocr")
    ap.add_argument("--tag", default=None,
                     help="filename prefix for outputs, e.g. 'front_' -- lets multiple runs share one --out-dir "
                          "(same folder as the source video) without overwriting each other")
    args = ap.parse_args()
    tag = args.tag or ""

    pipeline.STAGE1_CONF = args.conf

    import torch
    use_gpu = torch.cuda.is_available()
    print(f"device: {'cuda' if use_gpu else 'cpu'}")

    out_dir = Path(args.out_dir)
    plates_dir = out_dir / f"{tag}number_plates"
    out_dir.mkdir(parents=True, exist_ok=True)
    plates_dir.mkdir(parents=True, exist_ok=True)
    video_out_path = out_dir / f"{tag}annotated.mp4"

    print("loading model + OCR reader...")
    model = pipeline.load_model(args.model)
    ocr_reader = pipeline.load_ocr_reader(use_gpu=use_gpu, engine=args.ocr_engine)
    null_ocr = _NullOCR()

    cap = cv2.VideoCapture(args.source)
    if not cap.isOpened():
        raise SystemExit(f"could not open video: {args.source}")
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    writer = cv2.VideoWriter(str(video_out_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w + SIDEBAR_WIDTH, h))
    print(f"processing {args.source} ({total} frames) -> {video_out_path}")

    seen_plate_texts = set()
    plate_order = []  # newest first, for the sidebar
    frame_log = []
    frame_idx = 0

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if args.max_frames is not None and frame_idx >= args.max_frames:
            break

        reader = ocr_reader if frame_idx % args.ocr_stride == 0 else null_ocr
        annotated, detections = pipeline.process_frame(model, reader, frame)

        current_frame_plates = {p["text"] for p in detections["plate"]}
        for plate in detections["plate"]:
            text = plate["text"]
            if text in seen_plate_texts:
                continue
            seen_plate_texts.add(text)
            plate_order.insert(0, text)
            x0, y0, x1, y1 = [int(v) for v in plate["box"]]
            crop = frame[max(0, y0):y1, max(0, x0):x1]
            if crop.size == 0:
                continue
            cv2.imwrite(str(plates_dir / f"{text}_frame{frame_idx:06d}.jpg"), crop)
            print(f"  new plate saved: {text} (frame {frame_idx})")

        writer.write(add_plate_sidebar(annotated, plate_order, current_frame_plates))

        frame_log.append({
            "frame": frame_idx,
            "person": len(detections["person"]),
            "bicycle": len(detections["bicycle"]),
            "vehicle": len(detections["vehicle"]),
            "pothole": len(detections["pothole"]),
            "plates": [p["text"] for p in detections["plate"]],
        })

        frame_idx += 1
        if frame_idx % 30 == 0:
            print(f"  frame {frame_idx}/{total} processed ({len(seen_plate_texts)} unique plates so far)")

    cap.release()
    writer.release()

    (out_dir / f"{tag}detections.json").write_text(json.dumps(frame_log, indent=2))
    (out_dir / f"{tag}plates_found.txt").write_text(
        "\n".join(sorted(seen_plate_texts)) + ("\n" if seen_plate_texts else "")
    )

    print(f"done. {frame_idx} frames -> {video_out_path}")
    print(f"{len(seen_plate_texts)} unique plates -> {plates_dir}")
    print(f"log: {out_dir / 'detections.json'}")


if __name__ == "__main__":
    main()
