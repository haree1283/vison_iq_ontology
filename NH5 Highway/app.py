#!/usr/bin/env python3
"""Flask app: upload a video (or run a live camera) through the NH5 detector
+ tracker + event rules + plate OCR, and get back an annotated recording plus
a per-vehicle / per-event Excel report (photo, plate, speed, GPS, snapshots)
-- viewable in-browser or downloaded.

Reuses the detection building blocks from scripts/9_plate_pipeline.py
(COLORS, clamp_box, find_plate_candidate, ...); the behaviour rules
(roadside pedestrians, jaywalking, lane change, wrong side, ...) live in
event_engine.py, driven by a per-camera road map drawn on the Road Maps
page. The tracked-frame + events + OCR loop lives here in
process_tracked_frame, shared by VideoJob (uploaded files) and LiveCamera
(live sessions).

Live camera frames come from the VISITOR'S browser, not a server-side
camera device: the server has no camera of its own once this is hosted
off the machine you're sitting at. /live's page captures the browser's
webcam with getUserMedia, shows it locally (zero-latency local preview),
and streams JPEG frames to the /live_ws websocket (flask_sock) for
detection; the server replies with just that frame's boxes as JSON, which
the page draws on a <canvas> over the live preview -- see LiveCamera.

Usage:
  python app.py
  python app.py --model models/nh5_v8_final_ep100.pt --port 5000
"""
import argparse
import importlib.util
import json
import re
import sys
import shutil
import subprocess
import threading
import time
import uuid
from collections import Counter, defaultdict, deque
from datetime import datetime, timedelta
from pathlib import Path

import cv2
import numpy as np
import torch
import ultralytics
from flask import Flask, Response, jsonify, redirect, render_template, request, send_from_directory, url_for
from flask_sock import Sock
from simple_websocket import ConnectionClosed
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment
from openpyxl.utils import get_column_letter

from event_engine import ACCIDENT_MIN_CONF, EVENT_TYPES, EventEngine, Scene, clean_scene_data

BASE_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = BASE_DIR / "scripts"
UPLOAD_DIR = BASE_DIR / "webapp_data" / "uploads"
RESULT_DIR = BASE_DIR / "webapp_data" / "results"
SCENE_DIR = BASE_DIR / "webapp_data" / "scenes"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
RESULT_DIR.mkdir(parents=True, exist_ok=True)
SCENE_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXT = {".mp4", ".avi", ".mov", ".mkv"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp"}
SCENE_ID_RE = re.compile(r"[0-9a-f]{12}")


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# live_camera.py loads 9_plate_pipeline.py itself as `.pipeline` -- reuse
# that instance everywhere so STAGE1_CONF etc. stay consistent in one place.
livecam = _load_module("live_camera", SCRIPTS_DIR / "14_live_camera.py")
pipeline = livecam.pipeline
# what counts as a vehicle in the counts and the per-vehicle report: car, motorcycle, bus, truck, auto + bicycle.
# People and potholes are tracked for events but never counted as vehicles.
REPORT_VEHICLE_IDS = set(pipeline.VEHICLE_CLASS_IDS) | {1}


class LockedOCRReader:
    """EasyOCR's Reader isn't meant to be called from multiple threads at
    once; every VideoJob and the LiveCamera all share this one reader
    instance (loading a second copy would double the OCR model's memory
    footprint), so serialize access to it."""

    def __init__(self, reader):
        self._reader = reader
        self._lock = threading.Lock()

    def readtext(self, *args, **kwargs):
        with self._lock:
            return self._reader.readtext(*args, **kwargs)


MODEL_LOCK = threading.Lock()  # same reasoning, for the shared YOLO model
# The live camera gets its OWN model instance + lock, separate from uploaded-video jobs: they used
# to share one model/lock, so a video upload running flat-out would hold MODEL_LOCK for every one
# of its frames back-to-back and starve the live feed of GPU time behind it. The checkpoint is only
# ~20-40MB and inference memory is trivial next to a modern GPU's VRAM, so a second copy is cheap --
# far cheaper than the lock contention it removes. (Unlike OCR_READER above: EasyOCR/PaddleOCR are
# heavy enough that doubling them was the wrong trade.)
LIVE_MODEL_LOCK = threading.Lock()


SPEED_SMOOTH_WINDOW = 8  # track points kept per vehicle, for the median-of-steps speed calc below
RECENT_EVENTS_IN_STATUS = 25
SNAPSHOT_MAX_WIDTH = 1280

# plate reading: crop the model's OWN license_plate box directly (not a general text search over
# the whole vehicle) and OCR that crop every frame it's tracked in, same approach validated in
# scripts/v6/log_plates.py -- a plate is only trusted once its winning reading has recurred at
# least PLATE_MIN_VOTES times, so a one-off misread never reaches the report.
PLATE_MIN_VOTES = 5
# Indian plates only (scripts/v8/indian_plate.py, shared with the video tests): strict state/district/number
# format check, at most 2 look-alike characters corrected, anything else (foreign plates, badges, noise) rejected.
# Each crop is cleaned first (upscale, denoise, deskew, CLAHE, sharpen); two-line plates are read line by line.
sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts" / "v8"))
import indian_plate  # noqa: E402


PLATE_MIN_OCR_CONF = 0.85  # blurred plates still get a confident-looking guess repeated across frames; a reading
                           # below this confidence is dropped (same threshold as the video tests)


def _readtext_ordered(ocr_reader, img):
    """readtext -> (text in reading order: top line first, then left to right; mean confidence)."""
    results = ocr_reader.readtext(img)
    if not results:
        return "", 0.0
    items = []
    for poly, text, conf in results:
        ys = [p[1] for p in poly]; xs = [p[0] for p in poly]
        items.append((sum(ys) / len(ys), min(xs), max(ys) - min(ys), text, float(conf)))
    lh = sorted(it[2] for it in items)[len(items) // 2] or 1.0
    items.sort(key=lambda it: (round(it[0] / (0.6 * lh)), it[1]))
    return "".join(it[3] for it in items), sum(it[4] for it in items) / len(items)


def read_plate_crop(ocr_reader, crop):
    """Best Indian-format reading of one plate crop, or "" -- never a guess outside the Indian format.
    Cheapest first: the cleaned image read whole usually settles it in ONE OCR pass (a clean read with no
    corrected characters returns immediately); only then the raw image, then line-by-line for two-line plates."""
    if crop.size == 0 or crop.shape[0] < 12:
        return ""
    best = None

    def consider(raw, conf):
        nonlocal best
        n = indian_plate.normalize(raw) if raw and conf >= PLATE_MIN_OCR_CONF else None
        if n and (best is None or n[1] < best[1]):
            best = n
        return best is not None and best[1] == 0          # clean read -> stop

    enhanced, raw_up = indian_plate.enhance(crop), indian_plate._up(crop)
    for img in (enhanced, raw_up):
        if consider(*_readtext_ordered(ocr_reader, indian_plate._pad(img))):
            return best[0]
    for img in (enhanced, raw_up):                         # two-line plates (bikes/autos): top line first
        rows = indian_plate._split_rows(img)
        if rows:
            (t1, c1) = _readtext_ordered(ocr_reader, indian_plate._pad(indian_plate._up(rows[0], 96)))
            (t2, c2) = _readtext_ordered(ocr_reader, indian_plate._pad(indian_plate._up(rows[1], 96)))
            if t1 and t2 and consider(t1 + t2, (c1 + c2) / 2):
                return best[0]
    return best[0] if best else ""


def nearest_vehicle_track(plate_box, vehicle_dets):
    """The vehicle detection (this frame) whose box contains the plate box's center, preferring
    the smallest (most specific) match -- None if the plate isn't sitting inside any vehicle box."""
    px = (plate_box[0] + plate_box[2]) / 2
    py = (plate_box[1] + plate_box[3]) / 2
    candidates = [d for d in vehicle_dets
                  if d["box"][0] <= px <= d["box"][2] and d["box"][1] <= py <= d["box"][3]]
    if not candidates:
        return None
    return min(candidates, key=lambda d: (d["box"][2] - d["box"][0]) * (d["box"][3] - d["box"][1]))


# --- road maps (scenes) ---------------------------------------------------------

def _scene_dir(scene_id):
    """Resolve a road map's folder; the id format check keeps a crafted id from
    escaping SCENE_DIR."""
    if not scene_id or not SCENE_ID_RE.fullmatch(scene_id):
        return None
    d = SCENE_DIR / scene_id
    return d if (d / "scene.json").is_file() else None


def _read_scene_data(d):
    try:
        data = json.loads((d / "scene.json").read_text())
    except (json.JSONDecodeError, OSError):
        return None
    data["id"] = d.name
    return data


def list_scenes():
    scenes = []
    for d in SCENE_DIR.iterdir():
        if not SCENE_ID_RE.fullmatch(d.name) or not (d / "scene.json").is_file():
            continue
        data = _read_scene_data(d)
        if data is None:
            continue
        data["has_frame"] = (d / "frame.jpg").is_file()
        data["has_preview"] = (d / "preview.jpg").is_file()
        scenes.append(data)
    scenes.sort(key=lambda s: s.get("updated_at") or "", reverse=True)
    return scenes


def load_scene(scene_id):
    """A fresh Scene per job (Scene caches pixel geometry per frame size)."""
    d = _scene_dir(scene_id)
    data = _read_scene_data(d) if d is not None else None
    return Scene(data) if data is not None else None


def _grab_frame(path):
    """The image itself, or the frame at ~1 s of a video -- read through
    OpenCV so size and rotation match exactly what the pipeline will see."""
    if path.suffix.lower() in IMAGE_EXT:
        return cv2.imread(str(path))
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    cap.set(cv2.CAP_PROP_POS_FRAMES, min(int(fps), max(0, total - 1)))
    ok, frame = cap.read()
    cap.release()
    return frame if ok else None


def _render_scene_preview(d, data):
    frame = cv2.imread(str(d / "frame.jpg"))
    if frame is None:
        return
    Scene(data).draw(frame)
    cv2.imwrite(str(d / "preview.jpg"), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])


# --- per-frame processing ---------------------------------------------------------

def estimate_speed_kmh(history, fps, meters_per_pixel):
    """Median of per-step speeds across the track's recent history (not a
    single start-to-end displacement) -- a tracker occasionally reassigns a
    track ID to a different nearby vehicle for one frame, which shows up as
    one large position jump; the median absorbs that as one outlier among
    several instead of letting it corrupt the whole estimate."""
    if len(history) < 3:
        return None
    steps = []
    pts = list(history)
    for (f0, x0, y0), (f1, x1, y1) in zip(pts, pts[1:]):
        dt = (f1 - f0) / fps
        if dt <= 0:
            continue
        px_dist = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        steps.append((px_dist * meters_per_pixel / dt) * 3.6)
    if not steps:
        return None
    steps.sort()
    return steps[len(steps) // 2]


FIRE_MIN_FLAME = 0.012  # minimum share of flame-coloured pixels inside a fire_accident box


def flame_fraction(frame, box):
    """Share of pixels in the box that are bright orange/red/yellow (flame colours in HSV)."""
    x0, y0, x1, y1 = (int(v) for v in box)
    roi = frame[max(0, y0):y1, max(0, x0):x1]
    if roi.size == 0:
        return 0.0
    h, s, v = cv2.split(cv2.cvtColor(roi, cv2.COLOR_BGR2HSV))
    return float((((h <= 35) | (h >= 170)) & (s >= 100) & (v >= 150)).mean())


def process_tracked_frame(frame, frame_idx, track_state, plate_state, thorough, w, h, seen_plates, engine,
                           model, model_lock, plate_counts=None):
    """Shared by VideoJob and LiveCamera: tracked detection + event rules + plate OCR + annotation
    for one frame, updating track_state/plate_state (and seen_plates) in place. Returns
    (annotated_frame, counts, frame_plates, new_events).

    model/model_lock are passed in rather than read from the MODEL/MODEL_LOCK globals directly: a
    VideoJob uses the shared MODEL, LiveCamera uses its own LIVE_MODEL, so an upload running flat
    out never blocks the live feed's GPU turn behind it (see LIVE_MODEL_LOCK's comment).

    Each license_plate detection is OCR'd on its OWN tight box (PaddleOCR, via OCR_READER) and
    tracked by its own ByteTrack id in plate_state, exactly like scripts/v6/log_plates.py: a
    reading is only trusted, and only then attached to the nearest vehicle for the report, once
    it's recurred at least PLATE_MIN_VOTES times across the frames that plate was tracked in."""
    with model_lock:
        result = model.track(frame, persist=True, conf=pipeline.STAGE1_CONF, verbose=False,
                              tracker="bytetrack.yaml")[0]

    annotated = frame.copy()
    engine.draw_scene(annotated)
    # fixed keys for the grouped counts the rest of the app already relies on (report/UI columns),
    # plus a defaultdict fallback so newer classes (accident_scene, road_construction,
    # traffic_cone, ...) are tracked under their own name automatically instead of being silently
    # dropped from every summary -- that's what made a correct accident_scene detection look like
    # "nothing found" in the job status even though the box was really drawn on the frame
    counts = defaultdict(int, {"person": 0, "bicycle": 0, "vehicle": 0, "pothole": 0})
    frame_plates = []

    detections = []
    if result.boxes is not None:
        for box in result.boxes:
            cls = int(box.cls[0])
            detections.append({
                "cls_id": cls,
                "cls": MODEL.names.get(cls, str(cls)),
                "conf": float(box.conf[0]),
                "box": tuple(box.xyxy[0].tolist()),
                "track_id": int(box.id[0]) if box.id is not None else None,
            })
    # a fire box must actually contain flame colour: grey dust/debris after a crash scores up to ~0.78 as
    # fire_accident, but has <1% flame pixels where real vehicle fires have 1.6-32% (tested on 3 videos)
    detections = [d for d in detections if d["cls"] != "fire_accident" or flame_fraction(frame, d["box"]) >= FIRE_MIN_FLAME]
    new_events = engine.update(frame_idx, w, h, detections)

    vehicle_dets = [d for d in detections if d["cls_id"] in pipeline.VEHICLE_CLASS_IDS]
    # same boxes drawn onto `annotated` below, as plain JSON -- LiveCamera sends this to the
    # browser so it can draw the overlay itself instead of waiting on a re-encoded video frame
    live_boxes = []

    for det in detections:
        cls, name, conf, track_id = det["cls_id"], det["cls"], det["conf"], det["track_id"]
        x0, y0, x1, y1 = det["box"]
        color = pipeline.COLORS.get(cls, (200, 200, 200))
        if cls == pipeline.PLATE_CLASS_ID:
            continue
        if name == "accident_scene" and conf < ACCIDENT_MIN_CONF:
            continue  # too weak to count as an accident (same threshold as the alert) -> not drawn either

        status = engine.track_status(track_id) if track_id is not None else None
        label = f"{name} {conf:.2f}" + (f" | {status}" if status else "")
        # scene-level classes (road work, accident, fire) are the alerts: draw them thick so they stand out
        thick = 4 if name in ("road_construction", "accident_scene", "fire_accident") else 2
        cv2.rectangle(annotated, (int(x0), int(y0)), (int(x1), int(y1)), color, thick)
        pipeline.draw_label(annotated, int(x0), int(y0), label, color)
        live_boxes.append({"cls": name, "label": label, "box": [x0, y0, x1, y1], "track_id": track_id,
                            "color": list(color[::-1])})

        if cls == 0:
            counts["person"] += 1
        elif cls == 1:
            counts["bicycle"] += 1
        elif cls == 6:
            counts["pothole"] += 1
        elif cls in pipeline.VEHICLE_CLASS_IDS:
            counts["vehicle"] += 1
            if track_id is None:
                continue
        else:
            counts[name] += 1  # road_construction, accident_scene, traffic_cone, ...
            continue

        if track_id is None or cls not in REPORT_VEHICLE_IDS:
            continue
        st = track_state.setdefault(track_id, {
            "class": name, "best_area": 0.0, "best_crop": None,
            "history": deque(maxlen=SPEED_SMOOTH_WINDOW),
            "plate_text": None, "plate_conf": 0.0, "plate_crop": None,
            "first_frame": frame_idx, "events": [],
        })

        area = (x1 - x0) * (y1 - y0)
        if area > st["best_area"]:
            st["best_area"] = area
            st["best_crop"] = frame[max(0, int(y0)):int(y1), max(0, int(x0)):int(x1)].copy()

        st["history"].append((frame_idx, (x0 + x1) / 2, (y0 + y1) / 2))

    for det in detections:
        if det["cls_id"] != pipeline.PLATE_CLASS_ID or det["track_id"] is None:
            continue
        tid = det["track_id"]
        x0, y0, x1, y1 = det["box"]
        ix0, iy0, ix1, iy1 = int(x0), int(y0), int(x1), int(y1)
        crop = frame[max(0, iy0):iy1, max(0, ix0):ix1]

        pst = plate_state.setdefault(tid, {"readings": [], "best_area": 0.0, "best_crop": None, "confirmed": None})
        if crop.size:
            area = (ix1 - ix0) * (iy1 - iy0)
            if area > pst["best_area"]:
                pst["best_area"] = area
                pst["best_crop"] = indian_plate.enhance(crop)  # cleaned, readable plate photo for the report
            # a confirmed plate needs no more OCR (it's the most expensive step: ~0.1-0.5 s per plate)
            text = "" if pst["confirmed"] else read_plate_crop(OCR_READER, crop)
            if text:
                pst["readings"].append(text)
                vote, count = Counter(pst["readings"]).most_common(1)[0]
                if count >= PLATE_MIN_VOTES:
                    # the same plate split over two tracks can be confirmed twice with a 1-2 character misread
                    # (AP39KV4444 / AP39KY4444): reuse the plate already confirmed in this video instead
                    same = [p for p in seen_plates if indian_plate.edit_distance(p, vote) <= 2]
                    pst["confirmed"] = same[0] if same else vote
                    if plate_counts is not None:      # same plate seen again -> the existing record's count goes up
                        plate_counts[pst["confirmed"]] = plate_counts.get(pst["confirmed"], 0) + 1

        label = pst["confirmed"] or "reading..."
        plate_color = pipeline.COLORS[pipeline.PLATE_CLASS_ID]
        cv2.rectangle(annotated, (ix0, iy0), (ix1, iy1), plate_color, 2)
        pipeline.draw_label(annotated, ix0, iy0, label, plate_color)
        live_boxes.append({"cls": "license_plate", "label": label, "box": [x0, y0, x1, y1], "track_id": tid,
                            "color": list(plate_color[::-1])})

        if pst["confirmed"]:
            frame_plates.append(pst["confirmed"])
            if pst["confirmed"] not in seen_plates:
                seen_plates.append(pst["confirmed"])
            vehicle = nearest_vehicle_track(det["box"], vehicle_dets)
            if vehicle is not None and vehicle["track_id"] in track_state:
                vst = track_state[vehicle["track_id"]]
                if vst["plate_text"] is None:
                    vst["plate_text"] = pst["confirmed"]
                    vst["plate_conf"] = 1.0
                    vst["plate_crop"] = pst["best_crop"]

    for ev in new_events:
        if ev["track_id"] in track_state:
            track_state[ev["track_id"]]["events"].append(ev["label"])
    engine.draw_alerts(annotated, frame_idx)
    return annotated, counts, frame_plates, new_events, live_boxes


def save_event_snapshots(out_dir, annotated, new_events):
    """One JPEG per new event: the annotated frame it fired on (the alert
    banner + object outline are already drawn), capped in width to save disk."""
    if not new_events:
        return
    snap_dir = out_dir / "event_snapshots"
    snap_dir.mkdir(exist_ok=True)
    h, w = annotated.shape[:2]
    img = annotated if w <= SNAPSHOT_MAX_WIDTH else cv2.resize(
        annotated, (SNAPSHOT_MAX_WIDTH, int(h * SNAPSHOT_MAX_WIDTH / w)))
    for ev in new_events:
        rel = f"event_snapshots/event_{ev['id']:05d}.jpg"
        cv2.imwrite(str(out_dir / rel), img, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        ev["snapshot"] = rel


def compact_events(events):
    return [{k: ev[k] for k in ("id", "type", "label", "severity", "time_s", "track_id", "object_class")}
            for ev in events[-RECENT_EVENTS_IN_STATUS:]]


def transcode_to_h264(video_path):
    """cv2.VideoWriter's mp4v fourcc writes MPEG-4 Part 2, which no
    mainstream browser's <video> element can decode -- it downloads fine (no
    decoding needed) but silently fails to play in the Library/result pages.
    Re-encode to H.264 in place so playback actually works."""
    video_path = Path(video_path)
    tmp_path = video_path.with_name("annotated_h264.mp4")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(video_path), "-c:v", "libx264", "-pix_fmt", "yuv420p",
             "-preset", "veryfast", "-movflags", "+faststart", "-an", str(tmp_path)],
            check=True, capture_output=True, timeout=600,
        )
        tmp_path.replace(video_path)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        tmp_path.unlink(missing_ok=True)  # keep the original mp4v file if transcoding fails


def write_vehicle_report(out_dir, track_state, fps, *, job_id, original_filename, uploaded_at, plate_counts=None,
                          thorough, latitude, longitude, meters_per_pixel, speed_limit, base_url,
                          events, event_rules, scene_name):
    """One row per tracked vehicle, plus an Events sheet with one row per
    event. Speed, speed limit and lat/long are only ever shown when actually
    supplied at upload/session-start -- otherwise marked honestly as not
    provided/not calibrated rather than showing a made-up number (this is a
    static camera, not a GPS-tracked vehicle, so one lat/long applies to every
    row). Shared by VideoJob and LiveCamera."""
    photos_dir = out_dir / "vehicle_photos"
    plates_dir = out_dir / "plate_photos"
    photos_dir.mkdir(exist_ok=True)
    plates_dir.mkdir(exist_ok=True)

    def media_url(relpath):
        base = base_url.rstrip("/") if base_url else ""
        return f"{base}/media/{job_id}/{relpath}"

    try:
        upload_dt = datetime.fromisoformat(uploaded_at)
    except ValueError:
        upload_dt = datetime.now()

    THUMB_PX = 120
    rows_for_json = []

    wb = Workbook()
    ws = wb.active
    ws.title = "Vehicles"
    headers = ["ID", "Timestamp (IST)", "Vehicle Type", "Vehicle Number Plate", "Plate Confidence",
               "Vehicle Image", "Speed (km/h)", "Speed Limit (km/h)", "Over Speed",
               "Latitude", "Longitude", "Video Clip Path", "Vehicle Image Path", "Plate Image Path", "Events",
               "Times Seen", "Last Seen (IST)"]
    ws.append(headers)
    widths = [7, 19, 12, 18, 15, 16, 13, 15, 11, 12, 12, 34, 34, 34, 30, 11, 19]
    plate_counts = plate_counts or {}
    plate_row = {}   # plate -> (excel row, index in rows_for_json): a repeat of a plate updates that record
    for col_letter, width in zip([get_column_letter(i) for i in range(1, len(headers) + 1)], widths):
        ws.column_dimensions[col_letter].width = width

    row = 2
    for tid in sorted(track_state, key=lambda t: track_state[t]["first_frame"]):
        st = track_state[tid]
        timestamp = upload_dt + timedelta(seconds=st["first_frame"] / fps)
        ts_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")
        plate = st["plate_text"]
        if plate and plate in plate_row:                  # same plate again -> update the existing record
            r0, j0 = plate_row[plate]
            seen = max(plate_counts.get(plate, 0), rows_for_json[j0]["times_seen"] + 1)
            ws.cell(row=r0, column=16, value=seen); ws.cell(row=r0, column=17, value=ts_str)
            rows_for_json[j0]["times_seen"] = seen; rows_for_json[j0]["last_seen"] = ts_str
            for e in st["events"]:
                if e not in rows_for_json[j0]["events"]:
                    rows_for_json[j0]["events"].append(e)
            ws.cell(row=r0, column=15, value="; ".join(rows_for_json[j0]["events"]) or "none")
            continue

        speed = estimate_speed_kmh(st["history"], fps, meters_per_pixel) if meters_per_pixel else None
        speed_val = round(speed, 1) if speed is not None else ("not calibrated" if not meters_per_pixel else "n/a")

        if speed is not None and speed_limit:
            over_speed = "Yes" if speed > speed_limit else "No"
        else:
            over_speed = "n/a"

        vehicle_rel = plate_rel = None
        if st["best_crop"] is not None and st["best_crop"].size:
            fpath = photos_dir / f"track_{tid}.jpg"
            cv2.imwrite(str(fpath), st["best_crop"])
            vehicle_rel = f"vehicle_photos/track_{tid}.jpg"
        if st["plate_crop"] is not None and st["plate_crop"].size:
            fpath = plates_dir / f"track_{tid}.jpg"
            cv2.imwrite(str(fpath), st["plate_crop"])
            plate_rel = f"plate_photos/track_{tid}.jpg"

        values = [
            tid, ts_str, st["class"], st["plate_text"] or "not read",
            f"{st['plate_conf'] * 100:.0f}%" if st["plate_text"] else "n/a",
            None,  # embedded image goes in this column instead of a value
            speed_val, speed_limit or "not provided", over_speed,
            latitude or "not provided", longitude or "not provided",
        ]
        for col, val in enumerate(values, start=1):
            ws.cell(row=row, column=col, value=val)

        if vehicle_rel:
            img = XLImage(str(out_dir / vehicle_rel))
            ch, cw = st["best_crop"].shape[:2]
            img.width, img.height = THUMB_PX, int(THUMB_PX * ch / cw)
            ws.add_image(img, f"F{row}")

        video_url = media_url("annotated.mp4")
        vehicle_url = media_url(vehicle_rel) if vehicle_rel else ""
        plate_url = media_url(plate_rel) if plate_rel else ""

        c = ws.cell(row=row, column=12, value=video_url)
        c.hyperlink = video_url
        if vehicle_url:
            c = ws.cell(row=row, column=13, value=vehicle_url)
            c.hyperlink = vehicle_url
        else:
            ws.cell(row=row, column=13, value="n/a")
        if plate_url:
            c = ws.cell(row=row, column=14, value=plate_url)
            c.hyperlink = plate_url
        else:
            ws.cell(row=row, column=14, value="n/a")
        ws.cell(row=row, column=15, value="; ".join(st["events"]) or "none")
        times_seen = max(plate_counts.get(plate, 1), 1) if plate else 1
        ws.cell(row=row, column=16, value=times_seen); ws.cell(row=row, column=17, value=ts_str)

        ws.row_dimensions[row].height = THUMB_PX * 0.8

        rows_for_json.append({
            "id": tid, "timestamp": ts_str, "vehicle_type": st["class"],
            "plate_number": st["plate_text"] or "not read",
            "plate_confidence": round(st["plate_conf"] * 100, 1) if st["plate_text"] else None,
            "vehicle_image_url": vehicle_url, "plate_image_url": plate_url,
            "speed_kmh": speed_val, "speed_limit_kmh": speed_limit or None, "over_speed": over_speed,
            "latitude": latitude or None, "longitude": longitude or None,
            "video_url": video_url, "events": list(st["events"]),
            "times_seen": times_seen, "last_seen": ts_str,
        })
        if plate:
            plate_row[plate] = (row, len(rows_for_json) - 1)
        row += 1

    ev_ws = wb.create_sheet("Events")
    ev_headers = ["Event ID", "Timestamp (IST)", "Video Time (s)", "Event", "Severity", "Object", "Track ID",
                  "Vehicle Number Plate", "Details", "Snapshot", "Video Clip"]
    ev_ws.append(ev_headers)
    for col_letter, width in zip([get_column_letter(i) for i in range(1, len(ev_headers) + 1)],
                                 [9, 19, 13, 36, 10, 14, 9, 20, 32, 34, 34]):
        ev_ws.column_dimensions[col_letter].width = width

    events_for_json = []
    for ev in events:
        ts_str = (upload_dt + timedelta(seconds=ev["time_s"])).strftime("%Y-%m-%d %H:%M:%S")
        st = track_state.get(ev["track_id"]) if ev["track_id"] is not None else None
        plate = (st["plate_text"] or "not read") if st is not None else "n/a"
        details = ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in ev["details"].items())
        snapshot_url = media_url(ev["snapshot"]) if ev.get("snapshot") else ""
        clip_url = f"{media_url('annotated.mp4')}#t={max(0.0, ev['time_s'] - 2):.1f}"
        ev_ws.append([ev["id"], ts_str, ev["time_s"], ev["label"], ev["severity"], ev["object_class"] or "",
                      ev["track_id"] if ev["track_id"] is not None else "", plate, details,
                      snapshot_url or "n/a", clip_url])
        if snapshot_url:
            ev_ws.cell(row=ev_ws.max_row, column=10).hyperlink = snapshot_url
        ev_ws.cell(row=ev_ws.max_row, column=11).hyperlink = clip_url
        events_for_json.append({**ev, "timestamp": ts_str, "plate_number": plate,
                                "snapshot_url": snapshot_url, "clip_url": clip_url})

    notes = wb.create_sheet("Notes")
    notes["A1"] = "Source"
    notes["B1"] = original_filename
    notes["A2"] = "Processed"
    notes["B2"] = uploaded_at
    notes["A3"] = "Scan mode"
    notes["B3"] = "Thorough (every frame)" if thorough else "Fast (sampled)"
    notes["A5"] = "Timestamp basis"
    notes["B5"] = (
        "Session/upload start time + video-relative offset (frame / fps). For an uploaded file this is an "
        "approximation -- the file itself carries no true recording-start time, so upload time is the "
        "closest available anchor. For a live-camera session this is accurate to real time."
    )
    notes["A6"] = "Speed calibration"
    notes["B6"] = (
        f"meters-per-pixel = {meters_per_pixel} (as entered at start)"
        if meters_per_pixel else
        "Not provided -- speed is not calibrated and is marked 'not calibrated' rather than shown."
    )
    notes["A7"] = "Speed limit"
    notes["B7"] = f"{speed_limit} km/h (as entered at start)" if speed_limit else "Not provided -- 'Over Speed' is marked n/a."
    notes["A8"] = "Camera location"
    notes["B8"] = (
        f"lat={latitude or 'not provided'}, long={longitude or 'not provided'} "
        "-- a fixed camera position entered at start, the same for every row (this is not per-vehicle GPS)."
    )
    notes["A9"] = "Vehicle ID caveat"
    notes["B9"] = (
        "The tracker can occasionally assign a new ID to the same physical vehicle after a brief "
        "occlusion (a known ByteTrack limitation) -- treat the row count as an upper bound on distinct "
        "vehicles, not an exact one."
    )
    notes["A10"] = "Road map"
    notes["B10"] = scene_name or "None selected -- zone and lane based event rules were off."
    notes["A11"] = "Event rules"
    notes["B11"] = "\n".join(
        f"{EVENT_TYPES[etype]['label']}: " + ("on" if rule["enabled"] else f"off -- {rule['reason']}")
        for etype, rule in event_rules.items())
    notes["B11"].alignment = Alignment(wrap_text=True, vertical="top")
    notes.column_dimensions["A"].width = 18
    notes.column_dimensions["B"].width = 80

    wb.save(out_dir / "report.xlsx")
    (out_dir / "vehicles.json").write_text(json.dumps(rows_for_json, indent=2))
    (out_dir / "events.json").write_text(json.dumps(events_for_json, indent=2))
    return len(track_state)


class VideoJob:
    """Processes one uploaded video in a background thread: streams the
    annotated frames out as JPEGs (for the MJPEG endpoint) while writing the
    same frames to annotated.mp4, and accumulates unique plate reads and events."""

    def __init__(self, job_id, source_path, original_filename, thorough=False,
                 latitude="", longitude="", meters_per_pixel=None, speed_limit=None, base_url="", scene_id=None):
        self.id = job_id
        self.source_path = source_path
        self.original_filename = original_filename
        self.thorough = thorough
        self.latitude = latitude
        self.longitude = longitude
        self.meters_per_pixel = meters_per_pixel
        self.speed_limit = speed_limit
        self.base_url = base_url.rstrip("/")
        self.scene = load_scene(scene_id)
        self.scene_id = scene_id if self.scene is not None else None
        self.scene_name = self.scene.name if self.scene is not None else None
        self.uploaded_at = datetime.now().isoformat(timespec="seconds")
        self.out_dir = RESULT_DIR / job_id
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.status = "processing"
        self.error = None
        self.frame_bytes = None
        self.frame_idx = 0
        self.total_frames = 0
        self.plates = []
        self.plate_counts = {}
        self.num_vehicles = 0
        self.vehicle_types = Counter()  # vehicle class -> unique tracked vehicles (a car seen for 200 frames = 1)
        self.people_ids = set()         # unique tracked people (counted separately, never as vehicles)
        self.events = []
        self.event_rules = None
        self.started_at = None
        self.detection_counts = Counter()  # class name -> running total across every frame so far
        self.lock = threading.Lock()

    def start(self):
        self._write_meta()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _write_meta(self):
        with self.lock:
            elapsed = (time.time() - self.started_at) if self.started_at else 0
            proc_fps = round(self.frame_idx / elapsed, 2) if elapsed > 0.5 else None
            meta = {
                "job_id": self.id,
                "original_filename": self.original_filename,
                "uploaded_at": self.uploaded_at,
                "thorough": self.thorough,
                "status": self.status,
                "error": self.error,
                "frame_idx": self.frame_idx,
                "total_frames": self.total_frames,
                "plates": list(self.plates), "plate_counts": dict(self.plate_counts),
                "num_vehicles": self.num_vehicles,
                "vehicle_types": dict(self.vehicle_types),
                "num_people": len(self.people_ids),
                "latitude": self.latitude,
                "longitude": self.longitude,
                "meters_per_pixel": self.meters_per_pixel,
                "speed_limit": self.speed_limit,
                "processing_fps": proc_fps,
                "scene_id": self.scene_id,
                "scene_name": self.scene_name,
                "event_counts": dict(Counter(ev["type"] for ev in self.events)),
                "event_rules": self.event_rules,
                "model_name": MODEL_NAME,
                "model_description": MODEL_DESCRIPTION,
            }
        (self.out_dir / "meta.json").write_text(json.dumps(meta, indent=2))


    def _write_thumbnail(self):
        video_path = self.out_dir / "annotated.mp4"
        cap = cv2.VideoCapture(str(video_path))
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
        cap.set(cv2.CAP_PROP_POS_FRAMES, min(total - 1, total // 3))
        ok, frame = cap.read()
        cap.release()
        if ok:
            cv2.imwrite(str(self.out_dir / "thumb.jpg"), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])

    def _run(self):
        cap = cv2.VideoCapture(str(self.source_path))
        if not cap.isOpened():
            self.status, self.error = "error", "could not open uploaded video"
            self._write_meta()
            return

        self.started_at = time.time()
        self.total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        writer = cv2.VideoWriter(str(self.out_dir / "annotated.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
        engine = EventEngine(fps, self.scene, available_classes=set(MODEL.names.values()))
        self.event_rules = engine.caps

        track_state = {}  # track_id -> {class, best_area, best_crop, history, plate_text, plate_conf, plate_crop, first_frame, events}
        plate_state = {}  # plate track_id -> {readings, best_area, best_crop, confirmed}
        seen_plates = []
        plate_counts = self.plate_counts   # plate -> times seen in this video (updated in place)
        frame_log = []
        frame_idx = 0
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break

                annotated, counts, frame_plates, new_events, live_boxes = process_tracked_frame(
                    frame, frame_idx, track_state, plate_state, self.thorough, w, h, seen_plates, engine,
                    MODEL, MODEL_LOCK, plate_counts)
                save_event_snapshots(self.out_dir, annotated, new_events)

                writer.write(annotated)
                ok2, jpg = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 80])

                frame_idx += 1
                with self.lock:
                    if ok2:
                        self.frame_bytes = jpg.tobytes()
                    self.frame_idx = frame_idx
                    self.plates = list(seen_plates)
                    self.num_vehicles = len(track_state)
                    self.vehicle_types = Counter(st["class"] for st in track_state.values())
                    self.people_ids.update(b["track_id"] for b in live_boxes if b["cls"] == "person" and b["track_id"] is not None)
                    self.events.extend(new_events)
                    for k, v in counts.items():
                        if v:
                            self.detection_counts[k] += v

                frame_log.append({
                    "frame": frame_idx,
                    "person": counts["person"],
                    "vehicle": counts["vehicle"],
                    "pothole": counts["pothole"],
                    "plates": frame_plates,
                    "events": [ev["type"] for ev in new_events],
                })
        except Exception as exc:  # keep the job's error visible in the UI rather than dying silently
            self.status, self.error = "error", str(exc)
        finally:
            cap.release()
            writer.release()
            (self.out_dir / "detections.json").write_text(json.dumps(frame_log, indent=2))
            (self.out_dir / "plates_found.txt").write_text(
                "".join(f"{p}\t{plate_counts.get(p, 1)}\n" for p in seen_plates)   # plate <tab> times seen
            )
            if self.status != "error":
                self.status = "finalizing"
                self._write_meta()
                self.num_vehicles = write_vehicle_report(
                    self.out_dir, track_state, fps, job_id=self.id, original_filename=self.original_filename,
                    uploaded_at=self.uploaded_at, thorough=self.thorough, latitude=self.latitude,
                    longitude=self.longitude, meters_per_pixel=self.meters_per_pixel, plate_counts=plate_counts,
                    speed_limit=self.speed_limit, base_url=self.base_url,
                    events=list(self.events), event_rules=self.event_rules, scene_name=self.scene_name)
                transcode_to_h264(self.out_dir / "annotated.mp4")
                self.status = "done"
                self._write_thumbnail()
            self._write_meta()

    def snapshot(self):
        with self.lock:
            elapsed = (time.time() - self.started_at) if self.started_at else 0
            proc_fps = round(self.frame_idx / elapsed, 2) if elapsed > 0.5 else None
            return {
                "status": self.status,
                "error": self.error,
                "frame_idx": self.frame_idx,
                "total_frames": self.total_frames,
                "plates": list(self.plates), "plate_counts": dict(self.plate_counts),
                "num_vehicles": self.num_vehicles,
                "vehicle_types": dict(self.vehicle_types),
                "num_people": len(self.people_ids),
                "processing_fps": proc_fps,
                "ms_per_frame": round(1000 / proc_fps, 1) if proc_fps else None,
                "eta_secs": round((self.total_frames - self.frame_idx) / proc_fps) if proc_fps and self.total_frames else None,
                "events": compact_events(self.events),
                "num_events": len(self.events),
                "detection_counts": dict(self.detection_counts),
            }

    def get_jpeg(self):
        with self.lock:
            return self.frame_bytes


class LiveCamera:
    """Singleton: one browser-supplied camera stream, started/stopped from the /live page.
    Unlike the old version, the server never opens a camera device itself (cv2.VideoCapture on
    the server machine only ever sees a camera physically attached to the server -- once this
    app is hosted on the cloud there IS no such camera, only whatever the visitor's browser can
    see). Instead the browser captures its own webcam via getUserMedia, shows it locally in a
    <video> element (so the preview itself has zero network latency), and streams JPEG frames to
    /live_ws for detection. The server never sends video back -- only each frame's detections as
    small JSON, which the browser draws on a <canvas> overlaid on its own local video. This is
    also why an uploaded video used to make the live feed stutter: both shared one MODEL_LOCK;
    now the live path has its own LIVE_MODEL/LIVE_MODEL_LOCK (see their definitions) and its own
    frame source, so the two no longer contend for anything.

    Runs the exact same tracked-detection + event rules + plate-OCR + speed + Excel-report
    pipeline as an uploaded VideoJob, recording the session to annotated.mp4 as frames arrive and
    finalizing (report, transcode, thumbnail) when the browser stops streaming -- so a finished
    live session shows up in the Library exactly like an uploaded video."""

    def __init__(self):
        self.running = False
        self.streaming = False  # True once begin_stream() has set up the writer/engine for this session
        self.status = "idle"  # idle | processing | finalizing | done | error
        self.error = None
        self.plates = []
        self.plate_counts = {}
        self.num_vehicles = 0
        self.vehicle_types = Counter()
        self.people_ids = set()
        self.detection_counts = Counter()
        self.frame_idx = 0
        self.job_id = None
        self.started_at = None
        self.scene = None
        self.scene_id = None
        self.scene_name = None
        self.events = []
        self.event_rules = None
        self.lock = threading.Lock()

    def start(self, thorough, latitude, longitude, meters_per_pixel, speed_limit, base_url, scene_id=None):
        with self.lock:
            if self.running:
                return True, None, self.job_id

            self.job_id = uuid.uuid4().hex[:12]
            self.out_dir = RESULT_DIR / self.job_id
            self.out_dir.mkdir(parents=True, exist_ok=True)
            self.thorough = thorough
            self.latitude = latitude
            self.longitude = longitude
            self.meters_per_pixel = meters_per_pixel
            self.speed_limit = speed_limit
            self.base_url = base_url
            self.scene = load_scene(scene_id)
            self.scene_id = scene_id if self.scene is not None else None
            self.scene_name = self.scene.name if self.scene is not None else None
            self.uploaded_at = datetime.now().isoformat(timespec="seconds")
            self.original_filename = f"Live camera session {self.uploaded_at.replace('T', ' ')}"

            self.running = True
            self.streaming = False
            self.status = "processing"
            self.error = None
            self.plates = []
            self.plate_counts = {}
            self.num_vehicles = 0
            self.vehicle_types = Counter()
            self.people_ids = set()
            self.frame_idx = 0
            self.events = []
            self.event_rules = None
        self._write_meta()
        return True, None, self.job_id

    def stop(self):
        with self.lock:
            self.running = False

    def begin_stream(self, width, height, fps):
        """Called once per session, when /live_ws gets the browser's init message (frame size +
        intended send rate) -- everything a VideoWriter/EventEngine needs that a local
        cv2.VideoCapture used to report for us."""
        self.cam_w, self.cam_h, self.cam_fps = width, height, fps or 15.0
        self.writer = cv2.VideoWriter(str(self.out_dir / "annotated.mp4"), cv2.VideoWriter_fourcc(*"mp4v"),
                                       self.cam_fps, (self.cam_w, self.cam_h))
        self.engine = EventEngine(self.cam_fps, self.scene, available_classes=set(LIVE_MODEL.names.values()))
        with self.lock:
            self.event_rules = self.engine.caps
        self.track_state = {}
        self.plate_state = {}
        self.seen_plates = []
        self.frame_log = []
        self.started_at = time.time()
        self.streaming = True

    def handle_frame(self, jpg_bytes):
        """Decode one browser-sent JPEG, run it through the shared detection pipeline, record it
        into annotated.mp4, and return the frame's boxes as JSON-ready dicts for the browser to
        draw on its overlay canvas."""
        frame = cv2.imdecode(np.frombuffer(jpg_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            return []
        if frame.shape[1] != self.cam_w or frame.shape[0] != self.cam_h:
            frame = cv2.resize(frame, (self.cam_w, self.cam_h))

        annotated, counts, frame_plates, new_events, live_boxes = process_tracked_frame(
            frame, self.frame_idx, self.track_state, self.plate_state, self.thorough, self.cam_w, self.cam_h,
            self.seen_plates, self.engine, LIVE_MODEL, LIVE_MODEL_LOCK, self.plate_counts)
        save_event_snapshots(self.out_dir, annotated, new_events)
        self.writer.write(annotated)

        self.frame_idx += 1
        with self.lock:
            self.plates = list(self.seen_plates)
            self.num_vehicles = len(self.track_state)
            self.vehicle_types = Counter(st["class"] for st in self.track_state.values())
            self.people_ids.update(b["track_id"] for b in live_boxes if b["cls"] == "person" and b["track_id"] is not None)
            self.events.extend(new_events)
            for k, v in counts.items():
                if v:
                    self.detection_counts[k] += v

        self.frame_log.append({
            "frame": self.frame_idx, "person": counts["person"], "vehicle": counts["vehicle"],
            "pothole": counts["pothole"], "plates": frame_plates,
            "events": [ev["type"] for ev in new_events],
        })
        if self.frame_idx % 15 == 0:
            self._write_meta()
        return live_boxes

    def finalize(self):
        """Mirror of the tail of the old capture-loop's `finally:` block: report, transcode,
        thumbnail. Called once /live_ws's loop ends (browser closed the socket, or /live/stop
        flipped self.running off), whether or not any frame ever actually arrived."""
        with self.lock:
            self.running = False
        if not self.streaming:
            with self.lock:
                self.status = "done"
            self._write_meta()
            return
        self.writer.release()
        (self.out_dir / "detections.json").write_text(json.dumps(self.frame_log, indent=2))
        (self.out_dir / "plates_found.txt").write_text(
            "".join(f"{p}\t{self.plate_counts.get(p, 1)}\n" for p in self.seen_plates))
        try:
            with self.lock:
                self.status = "finalizing"
            self._write_meta()
            num_vehicles = write_vehicle_report(
                self.out_dir, self.track_state, self.cam_fps, job_id=self.job_id,
                original_filename=self.original_filename, uploaded_at=self.uploaded_at,
                thorough=self.thorough, latitude=self.latitude, longitude=self.longitude,
                meters_per_pixel=self.meters_per_pixel, speed_limit=self.speed_limit, base_url=self.base_url,
                events=list(self.events), event_rules=self.event_rules, scene_name=self.scene_name,
                plate_counts=self.plate_counts)
            transcode_to_h264(self.out_dir / "annotated.mp4")
            video_path = self.out_dir / "annotated.mp4"
            cap2 = cv2.VideoCapture(str(video_path))
            total2 = int(cap2.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
            cap2.set(cv2.CAP_PROP_POS_FRAMES, min(total2 - 1, total2 // 2))
            ok3, thumb_frame = cap2.read()
            cap2.release()
            if ok3:
                cv2.imwrite(str(self.out_dir / "thumb.jpg"), thumb_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            with self.lock:
                self.status = "done"
                self.num_vehicles = num_vehicles
        except Exception as exc:
            with self.lock:
                self.status, self.error = "error", str(exc)
        self.streaming = False
        self._write_meta()

    def _write_meta(self):
        with self.lock:
            elapsed = (time.time() - self.started_at) if self.started_at else 0
            proc_fps = round(self.frame_idx / elapsed, 2) if elapsed > 0.5 else None
            meta = {
                "job_id": self.job_id,
                "original_filename": self.original_filename,
                "uploaded_at": self.uploaded_at,
                "thorough": self.thorough,
                "status": self.status,
                "error": self.error,
                "frame_idx": self.frame_idx,
                "total_frames": 0,
                "plates": list(self.plates), "plate_counts": dict(self.plate_counts),
                "num_vehicles": self.num_vehicles,
                "latitude": self.latitude,
                "longitude": self.longitude,
                "meters_per_pixel": self.meters_per_pixel,
                "speed_limit": self.speed_limit,
                "processing_fps": proc_fps,
                "live_session": True,
                "scene_id": self.scene_id,
                "scene_name": self.scene_name,
                "event_counts": dict(Counter(ev["type"] for ev in self.events)),
                "event_rules": self.event_rules,
                "model_name": MODEL_NAME,
                "model_description": MODEL_DESCRIPTION,
            }
        (self.out_dir / "meta.json").write_text(json.dumps(meta, indent=2))

    def snapshot(self):
        with self.lock:
            elapsed = (time.time() - self.started_at) if self.started_at else 0
            proc_fps = round(self.frame_idx / elapsed, 2) if elapsed > 0.5 else None
            return {
                "running": self.running, "status": self.status, "error": self.error,
                "plates": list(self.plates), "plate_counts": dict(self.plate_counts), "num_vehicles": self.num_vehicles,
                "vehicle_types": dict(self.vehicle_types), "num_people": len(self.people_ids),
                "frame_idx": self.frame_idx, "job_id": self.job_id, "processing_fps": proc_fps,
                "ms_per_frame": round(1000 / proc_fps, 1) if proc_fps else None,
                "events": compact_events(self.events), "num_events": len(self.events),
                "scene_name": self.scene_name,
                "detection_counts": dict(self.detection_counts),
            }


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024 * 1024  # 2GB uploads
app.config["TEMPLATES_AUTO_RELOAD"] = True
sock = Sock(app)

JOBS = {}
JOBS_LOCK = threading.Lock()
LIVE = LiveCamera()
DEVICE_LABEL = "cpu"
MODEL_NAME = ""
MODEL_DESCRIPTION = ""
MODEL_PATH = ""
MODEL_CLASSES = []
MODEL_ARCH = ""
MODEL_SUMMARY = ""

# depth_multiple, width_multiple -> the letter Ultralytics' own yolov8{n,s,m,l,x}.yaml configs use
YOLOV8_SCALES = {(0.33, 0.25): "n", (0.33, 0.50): "s", (0.67, 0.75): "m", (1.00, 1.00): "l", (1.00, 1.25): "x"}
YOLOV8_SCALE_NAMES = {"n": "nano", "s": "small", "m": "medium", "l": "large", "x": "extra-large"}


def describe_model(model_path, model):
    """Name + description for the loaded detector, derived from its path and the classes
    baked into the checkpoint itself -- so this stays correct automatically when --model
    points at a different run, instead of a hand-maintained table going stale."""
    p = Path(model_path)
    name = p.parent.parent.name if p.parent.name == "weights" else p.stem
    class_names = [model.names[i] for i in sorted(model.names)]
    description = f"{len(class_names)} classes: {', '.join(class_names)}"

    n_params = sum(t.numel() for t in model.parameters())
    yaml = getattr(model, "yaml", {}) or {}
    scale = YOLOV8_SCALES.get((yaml.get("depth_multiple"), yaml.get("width_multiple")))
    arch = f"YOLOv8{scale}" if scale else "YOLOv8"
    scale_name = f" ({YOLOV8_SCALE_NAMES[scale]})" if scale else ""
    summary = (f"{arch}{scale_name} object detection model ({n_params / 1e6:.1f}M parameters), run through "
               f"Ultralytics {ultralytics.__version__} on {'GPU' if torch.cuda.is_available() else 'CPU'}. "
               f"Fine-tuned on our own NH5 Highway dataset to detect {len(class_names)} classes of Indian "
               f"road traffic and hazards: {', '.join(class_names)}.")
    return name, description, class_names, arch, summary


@app.context_processor
def inject_globals():
    return {"device": DEVICE_LABEL, "event_types": EVENT_TYPES,
            "model_name": MODEL_NAME, "model_description": MODEL_DESCRIPTION,
            "model_path": MODEL_PATH, "model_classes": MODEL_CLASSES,
            "model_arch": MODEL_ARCH, "model_summary": MODEL_SUMMARY}


def _float_field(name):
    raw = request.form.get(name, "").strip()
    try:
        return float(raw) if raw else None
    except ValueError:
        return None


@app.route("/")
def index():
    return render_template("index.html", scenes=list_scenes())


@app.route("/model")
def model_info():
    return render_template("model.html")


@app.route("/upload", methods=["POST"])
def upload():
    f = request.files.get("video")
    if not f or f.filename == "":
        return redirect(url_for("index"))
    ext = Path(f.filename).suffix.lower()
    if ext not in ALLOWED_EXT | IMAGE_EXT:
        return f"unsupported file type {ext!r} (allowed: {sorted(ALLOWED_EXT | IMAGE_EXT)})", 400
    scene_id = request.form.get("scene_id", "").strip() or None
    if scene_id and _scene_dir(scene_id) is None:
        return "road map not found", 400

    job_id = uuid.uuid4().hex[:12]
    dest = UPLOAD_DIR / f"{job_id}{ext}"
    f.save(dest)

    job = VideoJob(job_id, dest, original_filename=f.filename, thorough=request.form.get("thorough") == "on",
                   latitude=request.form.get("latitude", "").strip(),
                   longitude=request.form.get("longitude", "").strip(),
                   meters_per_pixel=_float_field("meters_per_pixel"), speed_limit=_float_field("speed_limit"),
                   base_url=request.host_url, scene_id=scene_id)
    with JOBS_LOCK:
        JOBS[job_id] = job
    job.start()
    return redirect(url_for("result", job_id=job_id))


@app.route("/result/<job_id>")
def result(job_id):
    job = JOBS.get(job_id)
    if job is None:
        return "job not found", 404
    return render_template("result.html", job_id=job_id, thorough=job.thorough, scene_name=job.scene_name)


@app.route("/stream/<job_id>")
def stream(job_id):
    job = JOBS.get(job_id)
    if job is None:
        return "job not found", 404

    def gen():
        while True:
            jpg = job.get_jpeg()
            if jpg is not None:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
            time.sleep(0.03 if job.status == "processing" else 1.0)

    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/status/<job_id>")
def status(job_id):
    job = JOBS.get(job_id)
    if job is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(job.snapshot())


SERVABLE_FILES = ("annotated.mp4", "plates_found.txt", "detections.json", "thumb.jpg", "report.xlsx", "events.json")


def _job_dir(job_id):
    """Resolve a job's result folder straight from disk -- works for jobs
    still in memory (JOBS) and ones from a previous server run (Library)."""
    d = RESULT_DIR / job_id
    return d if d.is_dir() else None


@app.route("/download/<job_id>/<fname>")
def download(job_id, fname):
    d = _job_dir(job_id)
    if d is None or fname not in SERVABLE_FILES:
        return "not found", 404
    return send_from_directory(d, fname, as_attachment=True)


MEDIA_SUBDIRS = ("vehicle_photos", "plate_photos", "event_snapshots")


@app.route("/media/<job_id>/<path:fname>")
def media(job_id, fname):
    """Top-level files (annotated.mp4, thumb.jpg, report.xlsx, ...) plus
    per-vehicle/plate crops and event snapshots under MEDIA_SUBDIRS -- served
    inline (for <video>/<img> tags and the report's hyperlinks), unlike
    /download which forces a save-as. Resolves and checks the real path
    stays inside the job's own folder so `fname` can't escape it."""
    d = _job_dir(job_id)
    if d is None:
        return "not found", 404

    top = fname.split("/")[0]
    if fname not in SERVABLE_FILES and top not in MEDIA_SUBDIRS:
        return "not found", 404

    target = (d / fname).resolve()
    if d.resolve() not in target.parents:
        return "not found", 404
    if not target.is_file():
        return "not found", 404

    return send_from_directory(target.parent, target.name, as_attachment=False)


@app.route("/library")
def library():
    jobs = []
    for d in sorted(RESULT_DIR.iterdir(), reverse=True):
        meta_path = d / "meta.json"
        if not meta_path.is_file():
            continue
        try:
            meta = json.loads(meta_path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        meta["has_thumb"] = (d / "thumb.jpg").is_file()
        meta["has_video"] = (d / "annotated.mp4").is_file()
        meta["has_report"] = (d / "report.xlsx").is_file()
        jobs.append(meta)
    jobs.sort(key=lambda m: m.get("uploaded_at") or "", reverse=True)
    return render_template("library.html", jobs=jobs)


@app.route("/library/<job_id>")
def library_detail(job_id):
    d = _job_dir(job_id)
    if d is None or not (d / "meta.json").is_file():
        return "not found", 404
    meta = json.loads((d / "meta.json").read_text())
    meta["has_thumb"] = (d / "thumb.jpg").is_file()
    meta["has_video"] = (d / "annotated.mp4").is_file()
    meta["has_report"] = (d / "report.xlsx").is_file()
    return render_template("library_detail.html", job_id=job_id, meta=meta)


@app.route("/library/<job_id>/report")
def report_view(job_id):
    """The same data as report.xlsx, viewable in the browser -- no download
    needed. vehicles.json / events.json are written alongside report.xlsx by
    write_vehicle_report (events.json is absent for jobs from before event rules existed)."""
    d = _job_dir(job_id)
    if d is None or not (d / "vehicles.json").is_file():
        return "not found", 404
    meta = json.loads((d / "meta.json").read_text()) if (d / "meta.json").is_file() else {}
    vehicles = json.loads((d / "vehicles.json").read_text())
    events = json.loads((d / "events.json").read_text()) if (d / "events.json").is_file() else []
    return render_template("report_view.html", job_id=job_id, meta=meta, vehicles=vehicles, events=events)


@app.route("/library/<job_id>/delete", methods=["POST"])
def library_delete(job_id):
    d = _job_dir(job_id)
    if d is None:
        return "not found", 404

    # only block while a worker thread is actually running this job; a job left as
    # processing/finalizing on disk by a crash or server restart is orphaned and deletable
    job = JOBS.get(job_id)
    thread = getattr(job, "thread", None)
    if thread is not None and thread.is_alive():
        return "can't delete a video that's still processing", 409
    if LIVE.job_id == job_id and LIVE.running:
        return "can't delete a live session that's still running", 409

    with JOBS_LOCK:
        JOBS.pop(job_id, None)
    shutil.rmtree(d, ignore_errors=True)

    src = next(UPLOAD_DIR.glob(f"{job_id}.*"), None)  # original uploaded file, if it still exists
    if src:
        src.unlink(missing_ok=True)

    return redirect(url_for("library"))


@app.route("/scenes")
def scenes():
    return render_template("scenes.html", scenes=list_scenes(), error=request.args.get("error"))


@app.route("/scenes/new", methods=["POST"])
def scene_new():
    f = request.files.get("source")
    if not f or f.filename == "":
        return redirect(url_for("scenes", error="Choose an image or video from the camera."))
    ext = Path(f.filename).suffix.lower()
    if ext not in ALLOWED_EXT | IMAGE_EXT:
        return redirect(url_for("scenes", error=f"Unsupported file type {ext!r}."))

    scene_id = uuid.uuid4().hex[:12]
    d = SCENE_DIR / scene_id
    d.mkdir(parents=True)
    src = d / f"source{ext}"
    f.save(src)
    frame = _grab_frame(src)
    src.unlink(missing_ok=True)
    if frame is None:
        shutil.rmtree(d, ignore_errors=True)
        return redirect(url_for("scenes", error="Couldn't read a frame from that file."))

    cv2.imwrite(str(d / "frame.jpg"), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
    now = datetime.now().isoformat(timespec="seconds")
    data = {
        "name": request.form.get("name", "").strip()[:80] or "Untitled road map",
        "zones": [], "lanes": [],
        "frame_size": [frame.shape[1], frame.shape[0]],
        "created_at": now, "updated_at": now,
    }
    (d / "scene.json").write_text(json.dumps(data, indent=2))
    return redirect(url_for("scene_editor", scene_id=scene_id))


@app.route("/scenes/<scene_id>")
def scene_editor(scene_id):
    d = _scene_dir(scene_id)
    data = _read_scene_data(d) if d is not None else None
    if data is None:
        return "not found", 404
    editor_cfg = {
        "scene": data,
        "frameUrl": url_for("scene_image", scene_id=scene_id, kind="frame"),
        "saveUrl": url_for("scene_save", scene_id=scene_id),
    }
    return render_template("scene_editor.html", scene=data, editor_cfg=editor_cfg)


@app.route("/scenes/<scene_id>/<any(frame, preview):kind>.jpg")
def scene_image(scene_id, kind):
    d = _scene_dir(scene_id)
    if d is None or not (d / f"{kind}.jpg").is_file():
        return "not found", 404
    return send_from_directory(d, f"{kind}.jpg", max_age=0)


@app.route("/scenes/<scene_id>/save", methods=["POST"])
def scene_save(scene_id):
    d = _scene_dir(scene_id)
    data = _read_scene_data(d) if d is not None else None
    if data is None:
        return jsonify({"error": "road map not found"}), 404
    try:
        cleaned = clean_scene_data(request.get_json(silent=True))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    data.pop("id", None)
    data.update(cleaned)
    data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    (d / "scene.json").write_text(json.dumps(data, indent=2))
    _render_scene_preview(d, data)
    return jsonify({"ok": True})


@app.route("/scenes/<scene_id>/delete", methods=["POST"])
def scene_delete(scene_id):
    d = _scene_dir(scene_id)
    if d is None:
        return "not found", 404
    shutil.rmtree(d, ignore_errors=True)
    return redirect(url_for("scenes"))


@app.route("/live")
def live():
    return render_template("live.html", scenes=list_scenes(), **LIVE.snapshot())


@app.route("/live/start", methods=["POST"])
def live_start():
    """Sets up the session (job id, scene, report fields) and returns immediately -- the actual
    camera comes from the browser next, over /live_ws, once its getUserMedia + WebSocket are up."""
    scene_id = request.form.get("scene_id", "").strip() or None
    ok, error, job_id = LIVE.start(
        request.form.get("thorough") == "on", request.form.get("latitude", "").strip(),
        request.form.get("longitude", "").strip(), _float_field("meters_per_pixel"),
        _float_field("speed_limit"), request.host_url, scene_id=scene_id)
    return jsonify({"ok": ok, "error": error, "job_id": job_id})


@app.route("/live/stop", methods=["POST"])
def live_stop():
    LIVE.stop()
    return jsonify({"ok": True})


@sock.route("/live_ws")
def live_ws(ws):
    """One browser session's whole life: first message is JSON {width, height, fps} from the
    <video> track's own settings, every message after that is one JPEG frame (binary). Each
    frame gets a JSON reply of that frame's boxes for the browser to draw. Ends -- and finalizes
    the report/recording -- the moment the browser closes the socket (stop button, tab close,
    lost connection) or /live/stop flips LIVE.running off between frames."""
    if not LIVE.running:
        return
    try:
        try:
            init = ws.receive(timeout=10)
        except ConnectionClosed:
            return
        if init is None:
            return
        cfg = json.loads(init)
        LIVE.begin_stream(int(cfg["width"]), int(cfg["height"]), float(cfg.get("fps") or 15))

        while LIVE.running:
            try:
                data = ws.receive(timeout=30)
            except ConnectionClosed:
                break
            if data is None or isinstance(data, str):
                break
            boxes = LIVE.handle_frame(data)
            try:
                ws.send(json.dumps(boxes))
            except ConnectionClosed:
                break
    finally:
        LIVE.finalize()


@app.route("/live_status")
def live_status():
    return jsonify(LIVE.snapshot())


def main():
    global MODEL, LIVE_MODEL, OCR_READER, DEVICE_LABEL, MODEL_NAME, MODEL_DESCRIPTION, MODEL_PATH, \
        MODEL_CLASSES, MODEL_ARCH, MODEL_SUMMARY

    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=str(BASE_DIR / "models" / "nh5_v8_final_ep100.pt"))
    ap.add_argument("--ocr-engine", choices=["easyocr", "paddleocr"], default="paddleocr")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=5000)
    args = ap.parse_args()

    use_gpu = torch.cuda.is_available()
    DEVICE_LABEL = "cuda" if use_gpu else "cpu"
    print(f"device: {DEVICE_LABEL}")
    print(f"loading model ({args.model}) + {args.ocr_engine} reader...")
    MODEL = pipeline.load_model(args.model)
    LIVE_MODEL = pipeline.load_model(args.model)  # own copy so uploads can't starve the live feed's GPU turn
    MODEL_PATH = args.model
    MODEL_NAME, MODEL_DESCRIPTION, MODEL_CLASSES, MODEL_ARCH, MODEL_SUMMARY = describe_model(args.model, MODEL)
    print(f"model: {MODEL_NAME} -- {MODEL_DESCRIPTION}")
    OCR_READER = LockedOCRReader(pipeline.load_ocr_reader(use_gpu=use_gpu, engine=args.ocr_engine))
    print("ready.")

    # debug/reloader off: it would spawn a second process that reloads the
    # model + OCR reader again and opens a second handle on the camera.
    app.run(host=args.host, port=args.port, threaded=True, debug=False)


if __name__ == "__main__":
    main()
