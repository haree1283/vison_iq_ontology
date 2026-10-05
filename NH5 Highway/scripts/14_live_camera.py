#!/usr/bin/env python3
"""Live camera monitoring: opens a window, continuously reads frames from the
connected camera, runs the trained YOLO model on every frame (person /
vehicle / pothole), and reads license plate text off detected vehicles.
Everything updates automatically -- no manual step per frame. Close the
window, press 'q', or Ctrl+C to stop.

Plate OCR (EasyOCR) is too slow to run inline in the display loop on CPU
(1-3+ seconds per vehicle crop) -- doing so blocks frame capture/imshow long
enough that the window manager marks the window "not responding" and shows
it as black. So OCR runs on a separate background thread instead: the main
loop only does YOLO detection (fast) and stays responsive every frame, while
the OCR thread continuously re-scans every vehicle currently in view and
publishes results the main loop overlays on the next frame. This also means
every vehicle gets its plate read, not just whichever one happened to be
scanned in a throttled pass.

Every run also records the annotated video and a per-frame detection log
into a timestamped folder (default: live_sessions/<timestamp>/):
  annotated.mp4      -- the video exactly as shown on screen, with boxes/labels
  detections.json     -- per-frame list of person/vehicle/pothole/plate detections
  plates_found.txt    -- unique plate texts read during the session, in order

Usage:
  python 14_live_camera.py --model models/nh5_v8_final_ep100.pt
  python 14_live_camera.py --model models/nh5_v8_final_ep100.pt --camera 0
  python 14_live_camera.py --model models/nh5_v8_final_ep100.pt --out-dir live_sessions/run1
"""
import argparse
import importlib.util
import json
import signal
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2

PIPELINE_PATH = Path(__file__).resolve().parent / "9_plate_pipeline.py"
_spec = importlib.util.spec_from_file_location("plate_pipeline", PIPELINE_PATH)
pipeline = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pipeline)


class _NullOCR:
    """Stand-in OCR reader for the main loop's detection-only pass -- returns
    no text so pipeline.process_frame skips the expensive OCR work there;
    real OCR happens on OCRWorker's own thread instead."""
    def readtext(self, *_args, **_kwargs):
        return []


class OCRWorker:
    """Continuously re-reads plate text for every vehicle box handed to it,
    independent of the display loop's frame rate. Always works off the most
    recently published frame + vehicle boxes, so it never falls behind by
    queuing stale work -- it just does the best it can, as fast as it can."""

    def __init__(self, ocr_reader):
        self.ocr_reader = ocr_reader
        self._lock = threading.Lock()
        self._frame = None
        self._vehicle_boxes = []  # list of (x0, y0, x1, y1, class_name)
        self._plates = []  # list of {box, text, ocr_conf, vehicle_class}
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        # give any in-flight OCR call a moment to finish naturally rather than
        # tearing the thread down mid-call, which can abort the interpreter
        self._thread.join(timeout=5)

    def update_input(self, frame, vehicle_boxes):
        with self._lock:
            self._frame = frame
            self._vehicle_boxes = vehicle_boxes

    def get_plates(self):
        with self._lock:
            return list(self._plates)

    def _run(self):
        while not self._stop.is_set():
            with self._lock:
                frame = self._frame
                boxes = list(self._vehicle_boxes)
            if frame is None or not boxes:
                time.sleep(0.05)
                continue

            h, w = frame.shape[:2]
            new_plates = []
            for x0, y0, x1, y1, name in boxes:
                if self._stop.is_set():
                    break
                bw, bh = x1 - x0, y1 - y0
                px0, py0, px1, py1 = pipeline.clamp_box(
                    x0 - bw * pipeline.CROP_PAD_FRAC, y0 - bh * pipeline.CROP_PAD_FRAC,
                    x1 + bw * pipeline.CROP_PAD_FRAC, y1 + bh * pipeline.CROP_PAD_FRAC, w, h,
                )
                crop = frame[py0:py1, px0:px1]
                if crop.size == 0:
                    continue
                candidate, _, scale = pipeline.find_plate_candidate(self.ocr_reader, crop)
                if candidate is None:
                    continue
                qx0, qy0, qx1, qy1, text, conf = candidate
                fx0, fy0 = px0 + qx0 / scale, py0 + qy0 / scale
                fx1, fy1 = px0 + qx1 / scale, py0 + qy1 / scale
                new_plates.append({
                    "box": [fx0, fy0, fx1, fy1],
                    "text": text,
                    "ocr_conf": conf,
                    "vehicle_class": name,
                })
                print(f"    plate found: {text}  (ocr_conf={conf:.2f}, vehicle={name})")

            with self._lock:
                self._plates = new_plates


def find_camera(preferred_index=None, max_index=5):
    indices = [preferred_index] if preferred_index is not None else range(max_index)
    for idx in indices:
        cap = cv2.VideoCapture(idx)
        if cap.isOpened():
            ok, _ = cap.read()
            if ok:
                return cap, idx
        cap.release()
    return None, None


def _device_name(idx):
    """Human-readable device name (e.g. 'Integrated Camera', 'USB2.0 HD UVC WebCam') read
    from V4L2's sysfs entry, so the UI can tell a laptop's built-in cam apart from a USB one
    without guessing from the index alone. Falls back to a generic label if unavailable
    (non-Linux, or the sysfs entry doesn't exist)."""
    name_path = Path(f"/sys/class/video4linux/video{idx}/name")
    try:
        return name_path.read_text().strip()
    except OSError:
        return f"Camera {idx}"


def list_cameras(max_index=5):
    """Probe indices 0..max_index-1 and report which ones actually produce a real frame, with a
    human-readable name for each -- lets the caller offer a choice between multiple attached
    cameras (e.g. built-in webcam vs. USB webcam) instead of silently picking the first one.

    Some UVC webcams expose a second, non-capture /dev/videoN node (metadata/frame-sync) under
    the same device name -- it opens and even reads "successfully" but only ever produces a
    black/empty frame. The brightness check below (same threshold set_resolution uses) filters
    those out so they don't show up as a bogus second camera."""
    cameras = []
    for idx in range(max_index):
        cap = cv2.VideoCapture(idx)
        if cap.isOpened():
            ok, frame = cap.read()
            if ok and frame is not None and frame.size > 0 and frame.mean() > BLACK_FRAME_MEAN_THRESHOLD:
                cameras.append({"index": idx, "name": _device_name(idx)})
        cap.release()
    return cameras


BLACK_FRAME_MEAN_THRESHOLD = 3.0  # below this average brightness, treat the frame as a failed mode-set
FALLBACK_RESOLUTIONS = [(640, 480), (800, 600), (352, 288)]


def set_resolution(cap, width, height):
    """Request a resolution and verify it actually produces a real (non-black)
    frame -- many USB webcams silently return corrupted all-black frames when
    asked for a resolution they don't support, instead of failing outright.
    Falls back through known-safe resolutions until one works."""
    for w, h in [(width, height)] + FALLBACK_RESOLUTIONS:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        ok, frame = cap.read()
        if ok and frame is not None and frame.mean() > BLACK_FRAME_MEAN_THRESHOLD:
            return int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"  {w}x{h} produced a black/corrupt frame, trying a different resolution...")
    # nothing worked -- report whatever the camera is currently set to
    return int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="path to trained .pt weights")
    ap.add_argument("--camera", type=int, default=None, help="camera index (auto-detects if omitted)")
    ap.add_argument("--list-cameras", action="store_true",
                     help="list attached cameras (index + name) and exit, e.g. to tell a built-in "
                          "webcam apart from a USB one")
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--out-dir", default=None,
                     help="folder to save annotated.mp4 + detections.json (default: live_sessions/<timestamp>/)")
    ap.add_argument("--conf", type=float, default=0.4,
                     help="detection confidence threshold (default 0.4, higher than the batch pipeline's 0.25 -- "
                          "live webcam footage tends to be noisier/more distorted, so this cuts weak false positives)")
    args = ap.parse_args()

    if args.list_cameras:
        cameras = list_cameras()
        if not cameras:
            print("no working cameras found.")
        for cam in cameras:
            print(f"  --camera {cam['index']}  ({cam['name']})")
        return

    pipeline.STAGE1_CONF = args.conf
    print(f"confidence threshold: {args.conf}")

    out_dir = Path(args.out_dir) if args.out_dir else \
        Path(__file__).resolve().parent.parent / "live_sessions" / datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"saving to: {out_dir}")

    print("checking camera availability...")
    cap, cam_idx = find_camera(args.camera)
    if cap is None:
        print("no working camera found. Check the connection and try --camera <index>.")
        return
    print(f"using camera index {cam_idx}")

    actual_w, actual_h = set_resolution(cap, args.width, args.height)
    print(f"resolution: {actual_w}x{actual_h}")
    cam_fps = cap.get(cv2.CAP_PROP_FPS) or 15.0

    video_path = out_dir / "annotated.mp4"
    writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), cam_fps, (actual_w, actual_h))

    import torch
    use_gpu = torch.cuda.is_available()
    print(f"device: {'cuda' if use_gpu else 'cpu'}")

    print("loading model + OCR reader...")
    model = pipeline.load_model(args.model)
    ocr_reader = pipeline.load_ocr_reader(use_gpu=use_gpu)

    ocr_worker = OCRWorker(ocr_reader)
    ocr_worker.start()

    window = "NH5 Highway - Live Detection"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)

    frame_idx = 0
    fps_t0 = time.time()
    fps_count = 0
    fps_display = 0.0
    session_start = time.time()
    frame_log = []
    seen_plates = []  # unique plate texts, in first-seen order

    stop = {"flag": False}

    def _request_stop(_signum, _frame):
        stop["flag"] = True

    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)

    print("running. Press 'q', close the window, or Ctrl+C to stop (saves cleanly either way).")
    try:
        while not stop["flag"]:
            ok, frame = cap.read()
            if not ok:
                print("camera read failed, stopping.")
                break

            # detection only here (fast, every frame) -- keeps the window responsive.
            annotated, detections = pipeline.process_frame(model, _NullOCR(), frame)

            vehicle_boxes = [(v["box"][0], v["box"][1], v["box"][2], v["box"][3], v["class"])
                              for v in detections["vehicle"]]
            ocr_worker.update_input(frame, vehicle_boxes)

            plates = ocr_worker.get_plates()
            detections["plate"] = plates
            for p in plates:
                x0, y0, x1, y1 = [int(v) for v in p["box"]]
                color = pipeline.COLORS[pipeline.PLATE_CLASS_ID]
                cv2.rectangle(annotated, (x0, y0), (x1, y1), color, 2)
                pipeline.draw_label(annotated, x0, y0, p["text"], color)
                if p["text"] not in seen_plates:
                    seen_plates.append(p["text"])

            fps_count += 1
            if time.time() - fps_t0 >= 1.0:
                fps_display = fps_count / (time.time() - fps_t0)
                fps_count = 0
                fps_t0 = time.time()
            cv2.putText(annotated, f"{fps_display:.1f} fps", (10, 24),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2, cv2.LINE_AA)

            writer.write(annotated)
            frame_log.append({
                "frame": frame_idx,
                "t": round(time.time() - session_start, 2),
                "person": len(detections["person"]),
                "bicycle": len(detections["bicycle"]),
                "vehicle": len(detections["vehicle"]),
                "pothole": len(detections["pothole"]),
                "plates": [p["text"] for p in detections["plate"]],
            })

            cv2.imshow(window, annotated)
            frame_idx += 1

            key = cv2.waitKey(1) & 0xFF
            try:
                window_closed = cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1
            except cv2.error:
                window_closed = True  # OS "X" button can tear down the window before this check runs
            if key == ord("q") or window_closed:
                break
    finally:
        ocr_worker.stop()
        cap.release()
        writer.release()
        cv2.destroyAllWindows()
        (out_dir / "detections.json").write_text(json.dumps(frame_log, indent=2))
        (out_dir / "plates_found.txt").write_text("\n".join(seen_plates) + ("\n" if seen_plates else ""))
        print(f"saved video:      {video_path}")
        print(f"saved detections: {out_dir / 'detections.json'}")
        print(f"saved plates:     {out_dir / 'plates_found.txt'} ({len(seen_plates)} unique)")
    print("stopped.")


if __name__ == "__main__":
    main()
