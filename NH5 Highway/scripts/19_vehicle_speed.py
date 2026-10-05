#!/usr/bin/env python3
"""Track vehicles across a video and estimate their speed.

Two separate pieces:
  1. Tracking -- ultralytics' built-in ByteTrack (model.track(persist=True))
     assigns each vehicle a consistent ID across frames, so we know "this
     box in frame N is the same car as that box in frame N-5."
  2. Speed -- pixel displacement of a tracked vehicle's center, divided by
     elapsed time, converted to real-world units via --meters-per-pixel.

IMPORTANT -- the calibration is a PLACEHOLDER, not a real measurement:
--meters-per-pixel is a single constant applied uniformly across the whole
frame. In a real (non-overhead) camera view this is wrong by construction --
a vehicle near the camera covers many pixels per real meter, one far away
covers few, so one constant can't be correct in both places at once. This
script exists to prove the tracking + speed *mechanism* works; the speed
numbers it prints are NOT trustworthy until calibrated against the real
installed camera (e.g. by measuring a known real-world distance -- a lane
width, a pole spacing -- visible in the actual footage, or by using two
fixed reference lines a known distance apart and timing crossings between
them, the way real non-radar speed cameras do it).

Usage:
  python 19_vehicle_speed.py --model models/nh5_v4_best.pt --source video.mp4 --out-dir results/ --meters-per-pixel 0.05
"""
import argparse
import json
from collections import defaultdict, deque
from pathlib import Path

import cv2

NAMES = ["person", "bicycle", "car", "motorcycle", "bus", "truck", "pothole", "license_plate", "auto"]
VEHICLE_CLASS_IDS = {2, 3, 4, 5, 8}
COLORS = {2: (0, 204, 255), 3: (100, 217, 76), 4: (250, 200, 90), 5: (255, 122, 0), 8: (180, 105, 255)}

SMOOTH_WINDOW = 8  # average speed over this many recent track points, to reduce frame-to-frame jitter


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--conf", type=float, default=0.3)
    ap.add_argument("--meters-per-pixel", type=float, required=True,
                     help="PLACEHOLDER calibration constant -- see module docstring. Not accurate until "
                          "calibrated against the real camera.")
    ap.add_argument("--max-frames", type=int, default=None)
    args = ap.parse_args()

    from ultralytics import YOLO
    model = YOLO(args.model)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    video_out_path = out_dir / "speed_annotated.mp4"

    cap = cv2.VideoCapture(args.source)
    if not cap.isOpened():
        raise SystemExit(f"could not open video: {args.source}")
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    writer = cv2.VideoWriter(str(video_out_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    print(f"processing {args.source} ({total} frames, {fps:.1f} fps) -> {video_out_path}")
    print(f"WARNING: --meters-per-pixel={args.meters_per_pixel} is a placeholder, not a real calibration "
          f"(see script docstring). Treat speeds as illustrative only.")

    track_history = defaultdict(lambda: deque(maxlen=SMOOTH_WINDOW))  # track_id -> deque[(frame_idx, cx, cy)]
    track_class = {}
    max_speed_seen = {}  # track_id -> (kmh, frame_idx)
    frame_idx = 0

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if args.max_frames is not None and frame_idx >= args.max_frames:
            break

        results = model.track(frame, conf=args.conf, classes=list(VEHICLE_CLASS_IDS),
                               persist=True, verbose=False, tracker="bytetrack.yaml")[0]
        annotated = frame.copy()

        if results.boxes is not None and results.boxes.id is not None:
            for box, track_id in zip(results.boxes, results.boxes.id):
                track_id = int(track_id)
                cls = int(box.cls[0])
                x0, y0, x1, y1 = box.xyxy[0].tolist()
                cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                track_class[track_id] = cls

                hist = track_history[track_id]
                hist.append((frame_idx, cx, cy))

                speed_kmh = None
                if len(hist) >= 2:
                    f0, x0h, y0h = hist[0]
                    f1, x1h, y1h = hist[-1]
                    dt = (f1 - f0) / fps
                    if dt > 0:
                        px_dist = ((x1h - x0h) ** 2 + (y1h - y0h) ** 2) ** 0.5
                        meters = px_dist * args.meters_per_pixel
                        speed_kmh = (meters / dt) * 3.6
                        prev = max_speed_seen.get(track_id, (0, 0))
                        if speed_kmh > prev[0]:
                            max_speed_seen[track_id] = (speed_kmh, frame_idx)

                color = COLORS.get(cls, (200, 200, 200))
                cv2.rectangle(annotated, (int(x0), int(y0)), (int(x1), int(y1)), color, 2)
                label = f"#{track_id} {NAMES[cls]}"
                if speed_kmh is not None:
                    label += f" ~{speed_kmh:.0f} km/h"
                (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                ty = max(th + 6, int(y0))
                cv2.rectangle(annotated, (int(x0), ty - th - 6), (int(x0) + tw + 6, ty), color, -1)
                cv2.putText(annotated, label, (int(x0) + 3, ty - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                            (255, 255, 255), 1, cv2.LINE_AA)

        writer.write(annotated)
        frame_idx += 1
        if frame_idx % 30 == 0:
            print(f"  frame {frame_idx}/{total} processed")

    cap.release()
    writer.release()

    summary = {
        int(tid): {"class": NAMES[track_class[tid]], "max_speed_kmh": round(v[0], 1), "frame": v[1]}
        for tid, v in max_speed_seen.items()
    }
    (out_dir / "speed_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"done. {frame_idx} frames -> {video_out_path}")
    print(f"{len(summary)} tracked vehicles -> {out_dir / 'speed_summary.json'}")
    print("REMINDER: speeds use a placeholder meters-per-pixel constant -- calibrate against the real "
          "camera before trusting these numbers.")


if __name__ == "__main__":
    main()
