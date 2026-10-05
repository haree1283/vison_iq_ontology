#!/usr/bin/env python3
"""Standalone script: run a trained YOLO .pt file on a real video and produce
  1. an annotated video -- detection boxes drawn live (each vehicle labeled
     with a persistent track ID and estimated speed), plus a sidebar listing
     every unique license plate read so far
  2. a folder of cropped plate images, one per unique plate text recognized
  3. a speed summary (JSON) of every tracked vehicle's estimated top speed

Self-contained -- no imports from other project scripts, so it can be
copied and run on its own.

--- Method ---
Stage 1 (every frame): the YOLO model detects + tracks person / bicycle /
car / motorcycle / bus / truck / pothole (tracking via ultralytics' built-in
ByteTrack, model.track(persist=True) -- assigns each vehicle a consistent ID
across frames, which speed estimation needs to know "this box is the same
vehicle as 5 frames ago").

Speed: pixel displacement of a tracked vehicle's center over time, converted
to km/h via --meters-per-pixel.
IMPORTANT -- this is a PLACEHOLDER calibration, not a real measurement:
--meters-per-pixel is one constant applied uniformly across the whole frame.
In a real (non-overhead) camera view this is wrong by construction -- a
vehicle near the camera covers many pixels per real meter, one far away
covers few, so one constant can't be correct in both places at once. Treat
the speed numbers as illustrative of the mechanism, not trustworthy, until
calibrated against the real installed camera (e.g. by measuring a known
real-world distance -- a lane width, a pole spacing -- visible in the actual
footage, or by using two fixed reference lines a known distance apart and
timing crossings between them, the way real non-radar speed cameras do it).

Stage 2 (plates): the model's own license_plate class was only ever trained
on clean, close-up ANPR photos, so it doesn't reliably fire on a plate
inside a crop pulled from real highway/dashcam footage (verified: near-zero
signal on real highway crops even at very low confidence thresholds --
a genuine domain gap, not a threshold-tuning problem). So instead: for every
vehicle box from stage 1, crop it out (with padding), upscale it, and run
EasyOCR -- a general-purpose scene-text reader, not narrowly trained on ANPR
photos -- directly on the crop. Each text region EasyOCR finds is checked
against the Indian plate format (2 letters, 2 digits, 1-3 letters, 1-4
digits), allowing at most one look-alike character correction (e.g. one
2/Z mix-up) so a single OCR slip doesn't cost a match -- but capped at one
correction specifically so it can't force arbitrary text into looking like
a plate that was never really there.

Usage:
  python test_pt_on_video.py --model nh5_v2_best.pt --source my_video.mp4 --out-dir results/
  python test_pt_on_video.py --model nh5_v2_best.pt --source my_video.mp4 --out-dir results/ --max-frames 200
"""
import argparse
import json
import re
from collections import defaultdict, deque
from pathlib import Path

import cv2

# --- class schema -----------------------------------------------------------
NAMES = ["person", "bicycle", "car", "motorcycle", "bus", "truck", "pothole", "license_plate", "auto"]
VEHICLE_CLASS_IDS = {2, 3, 4, 5, 8}  # car, motorcycle, bus, truck, auto
PLATE_CLASS_ID = 7

COLORS = {
    0: (48, 59, 255), 1: (0, 149, 255), 2: (0, 204, 255), 3: (100, 217, 76),
    4: (250, 200, 90), 5: (255, 122, 0), 6: (214, 86, 88), 7: (85, 45, 255),
    8: (180, 105, 255),
}

CROP_PAD_FRAC = 0.20     # padding added around each vehicle box before scanning for text
CROP_MIN_SIDE = 480      # upscale the crop so its shorter side is at least this many px
STAGE1_CONF = 0.25
PLATE_SEARCH_TOP_FRAC = 0.45  # skip the top 45% of the vehicle box -- plates are never up near the roofline

PLATE_TEXT_LEN_RANGE = (6, 11)     # matches PLATE_PATTERN's min/max length (AA00A0000)
PLATE_ASPECT_RANGE = (1.3, 7.0)    # width/height of the text region's bounding box
PLATE_MIN_OCR_CONF = 0.25

# Indian standard plate format: 2 letters (state) + 2 digits (RTO code) +
# 1-3 letters (series) + 1-4 digits (number), e.g. "MH12AB1234".
PLATE_PATTERN = re.compile(r"^[A-Z]{2}\d{2}[A-Z]{1,3}\d{1,4}$")

# OCR frequently swaps visually similar characters (a font/resolution issue,
# not a logic bug -- e.g. a real "MH12AB1234" plate got read as "MH1ZAB1234",
# confusing 2/Z). match_plate_pattern tries the strict regex first, and only
# falls back to correcting characters against what the plate format expects
# at each position if that fails.
LETTER_LOOKALIKE_TO_DIGIT = {"O": "0", "I": "1", "L": "1", "Z": "2", "S": "5", "B": "8", "G": "6", "Q": "0"}
DIGIT_LOOKALIKE_TO_LETTER = {"0": "O", "1": "I", "2": "Z", "5": "S", "8": "B", "6": "G"}
MAX_LOOKALIKE_CORRECTIONS = 1  # see match_plate_pattern


def match_plate_pattern(clean):
    """Return `clean` corrected to the Indian plate format (2 letters, 2
    digits, 1-3 letters, 1-4 digits), or None if no split fits -- allowing at
    most MAX_LOOKALIKE_CORRECTIONS look-alike substitutions.

    Capped deliberately: with no cap, a long enough run of unrelated text can
    have EVERY character reinterpreted as some look-alike and still "fit" the
    4-group shape, producing a plate number that was never actually on any
    plate. A genuine single-character OCR slip needs at most one correction,
    not four or five, so capping at 1 rejects that class of false positive.
    """
    if PLATE_PATTERN.match(clean):
        return clean
    n = len(clean)
    for series_len in (1, 2, 3):
        for number_len in (1, 2, 3, 4):
            if 2 + 2 + series_len + number_len != n:
                continue
            groups = [(0, 2, "letter"), (2, 4, "digit"),
                      (4, 4 + series_len, "letter"), (4 + series_len, n, "digit")]
            fixed, ok, corrections = [], True, 0
            for start, end, kind in groups:
                for ch in clean[start:end]:
                    if kind == "digit":
                        if ch.isdigit():
                            fixed.append(ch)
                        elif ch in LETTER_LOOKALIKE_TO_DIGIT:
                            fixed.append(LETTER_LOOKALIKE_TO_DIGIT[ch]); corrections += 1
                        else:
                            ok = False; break
                    else:
                        if ch.isalpha():
                            fixed.append(ch)
                        elif ch in DIGIT_LOOKALIKE_TO_LETTER:
                            fixed.append(DIGIT_LOOKALIKE_TO_LETTER[ch]); corrections += 1
                        else:
                            ok = False; break
                    if corrections > MAX_LOOKALIKE_CORRECTIONS:
                        ok = False; break
                if not ok:
                    break
            if ok:
                return "".join(fixed)
    return None


# how close two OCR text fragments must be to count as pieces of one plate
MERGE_Y_OVERLAP_RATIO = 0.3   # fraction of the shorter fragment's height that must overlap vertically
MERGE_X_GAP_FACTOR = 1.0      # max horizontal gap, as a multiple of average fragment height


def _merge_text_fragments(results):
    """EasyOCR often splits one plate into several text regions (e.g. a state
    code and the number as separate boxes). Greedily merge fragments that sit
    on the same line and close together, so the combined text can be matched
    against the plate pattern as a whole."""
    items = []
    for bbox_poly, text, conf in results:
        xs = [p[0] for p in bbox_poly]
        ys = [p[1] for p in bbox_poly]
        items.append({"x0": min(xs), "x1": max(xs), "y0": min(ys), "y1": max(ys), "text": text, "conf": conf})
    items.sort(key=lambda it: it["x0"])

    clusters = []
    for it in items:
        placed = False
        for cl in clusters:
            overlap = min(cl["y1"], it["y1"]) - max(cl["y0"], it["y0"])
            min_h = min(cl["y1"] - cl["y0"], it["y1"] - it["y0"])
            if min_h <= 0:
                continue
            avg_h = ((cl["y1"] - cl["y0"]) + (it["y1"] - it["y0"])) / 2
            x_gap = it["x0"] - cl["x1"]
            if (overlap / min_h) > MERGE_Y_OVERLAP_RATIO and x_gap < avg_h * MERGE_X_GAP_FACTOR:
                cl["x0"] = min(cl["x0"], it["x0"]); cl["x1"] = max(cl["x1"], it["x1"])
                cl["y0"] = min(cl["y0"], it["y0"]); cl["y1"] = max(cl["y1"], it["y1"])
                cl["parts"].append(it); placed = True
                break
        if not placed:
            clusters.append({"x0": it["x0"], "x1": it["x1"], "y0": it["y0"], "y1": it["y1"], "parts": [it]})

    merged = []
    for cl in clusters:
        parts = sorted(cl["parts"], key=lambda p: p["x0"])
        text = "".join(p["text"] for p in parts)
        total_len = sum(len(p["text"]) for p in parts) or 1
        conf = sum(p["conf"] * len(p["text"]) for p in parts) / total_len
        merged.append((cl["x0"], cl["y0"], cl["x1"], cl["y1"], text, conf))
    return merged


def clamp_box(x0, y0, x1, y1, w, h):
    return max(0, int(x0)), max(0, int(y0)), min(w, int(x1)), min(h, int(y1))


def find_plate_candidate(reader, crop_bgr):
    """Scan a vehicle crop for OCR text regions shaped like a plate.
    Returns ((x0, y0, x1, y1, text, ocr_conf), resized_crop, scale) or
    (None, crop_bgr, scale). Box coords are in the (possibly upscaled)
    crop's own pixel space."""
    h, w = crop_bgr.shape[:2]
    scale = max(1.0, CROP_MIN_SIDE / min(h, w))
    if scale > 1.0:
        crop_bgr = cv2.resize(crop_bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)

    raw = reader.readtext(crop_bgr)
    candidates = []
    for x0, y0, x1, y1, text, conf in _merge_text_fragments(raw):
        clean = re.sub(r"[^A-Z0-9]", "", text.upper())
        if not (PLATE_TEXT_LEN_RANGE[0] <= len(clean) <= PLATE_TEXT_LEN_RANGE[1]):
            continue
        clean = match_plate_pattern(clean)
        if clean is None:
            continue
        if conf < PLATE_MIN_OCR_CONF:
            continue
        bw, bh = x1 - x0, y1 - y0
        if bh <= 0:
            continue
        aspect = bw / bh
        if not (PLATE_ASPECT_RANGE[0] <= aspect <= PLATE_ASPECT_RANGE[1]):
            continue
        candidates.append((conf, x0, y0, x1, y1, clean))

    if not candidates:
        return None, crop_bgr, scale
    candidates.sort(key=lambda c: -c[0])
    conf, x0, y0, x1, y1, clean = candidates[0]
    return (x0, y0, x1, y1, clean, conf), crop_bgr, scale


def draw_label(img, x0, y0, text, color):
    font = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), _ = cv2.getTextSize(text, font, 0.5, 1)
    y0 = max(th + 6, y0)
    cv2.rectangle(img, (x0, y0 - th - 6), (x0 + tw + 6, y0), color, -1)
    cv2.putText(img, text, (x0 + 3, y0 - 4), font, 0.5, (255, 255, 255), 1, cv2.LINE_AA)


SPEED_SMOOTH_WINDOW = 8  # track points kept per vehicle, for the median-of-steps speed calc below


def estimate_speed_kmh(history, fps, meters_per_pixel):
    """Median of per-step speeds across the track's recent history, not a
    single start-to-end displacement. A tracker can occasionally reassign a
    track ID to a different nearby vehicle for one frame (an "ID switch"),
    which shows up as one large position jump; a start-to-end calculation
    lets that single bad step corrupt the whole estimate, but the median
    across several steps shrinks it to one outlier among many and ignores
    it. Needs >= 3 points to compute a meaningful median."""
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


def process_frame(model, ocr_reader, frame_bgr, frame_idx, fps, meters_per_pixel, track_history, track_class):
    """Run stage 1 (tracked detection) + stage 2 (plate OCR) + speed
    estimation on one frame. Returns (annotated_frame, detections_dict)."""
    h, w = frame_bgr.shape[:2]
    annotated = frame_bgr.copy()
    detections = {"person": [], "bicycle": [], "vehicle": [], "pothole": [], "plate": []}

    result = model.track(frame_bgr, conf=STAGE1_CONF, persist=True, verbose=False, tracker="bytetrack.yaml")[0]
    if result.boxes is None:
        return annotated, detections

    box_ids = result.boxes.id
    for i, box in enumerate(result.boxes):
        cls = int(box.cls[0])
        conf = float(box.conf[0])
        x0, y0, x1, y1 = box.xyxy[0].tolist()
        name = NAMES[cls]
        color = COLORS[cls]
        track_id = int(box_ids[i]) if box_ids is not None else None

        if cls == PLATE_CLASS_ID:
            continue  # rely on stage 2 for plates; a full-frame plate box is usually too coarse

        label = f"{name} {conf:.2f}"
        speed_kmh = None
        if track_id is not None and cls in VEHICLE_CLASS_IDS:
            track_class[track_id] = cls
            hist = track_history[track_id]
            hist.append((frame_idx, (x0 + x1) / 2, (y0 + y1) / 2))
            if meters_per_pixel is not None:
                speed_kmh = estimate_speed_kmh(hist, fps, meters_per_pixel)
                label = f"#{track_id} {name}" + (f" ~{speed_kmh:.0f}km/h" if speed_kmh is not None else "")
            else:
                label = f"#{track_id} {name}"

        cv2.rectangle(annotated, (int(x0), int(y0)), (int(x1), int(y1)), color, 2)
        draw_label(annotated, int(x0), int(y0), label, color)

        if cls == 0:
            detections["person"].append([x0, y0, x1, y1, conf])
        elif cls == 1:
            detections["bicycle"].append([x0, y0, x1, y1, conf])
        elif cls == 6:
            detections["pothole"].append([x0, y0, x1, y1, conf])
        elif cls in VEHICLE_CLASS_IDS:
            detections["vehicle"].append({"class": name, "box": [x0, y0, x1, y1], "conf": conf,
                                           "track_id": track_id, "speed_kmh": speed_kmh})

            # stage 2: crop this vehicle, re-detect the plate at higher effective res.
            # No top padding -- plates sit near bumper height, never near the roofline,
            # and padding the top let background objects above the vehicle (e.g. a
            # storefront sign) leak into the OCR crop and occasionally get misread as a
            # plate-shaped string.
            bw, bh = x1 - x0, y1 - y0
            px0, py0, px1, py1 = clamp_box(
                x0 - bw * CROP_PAD_FRAC, y0 + bh * PLATE_SEARCH_TOP_FRAC,
                x1 + bw * CROP_PAD_FRAC, y1 + bh * CROP_PAD_FRAC, w, h,
            )
            veh_crop = frame_bgr[py0:py1, px0:px1]
            if veh_crop.size == 0:
                continue

            candidate, _resized_crop, scale = find_plate_candidate(ocr_reader, veh_crop)
            if candidate is None:
                continue

            qx0, qy0, qx1, qy1, text, ocr_conf = candidate
            fx0, fy0 = px0 + qx0 / scale, py0 + qy0 / scale
            fx1, fy1 = px0 + qx1 / scale, py0 + qy1 / scale

            plate_color = COLORS[PLATE_CLASS_ID]
            cv2.rectangle(annotated, (int(fx0), int(fy0)), (int(fx1), int(fy1)), plate_color, 2)
            draw_label(annotated, int(fx0), int(fy0), f"{text} ({ocr_conf:.2f})", plate_color)

            detections["plate"].append({
                "box": [fx0, fy0, fx1, fy1], "text": text, "ocr_conf": ocr_conf, "vehicle_class": name,
            })
            print(f"    plate found: {text}  (ocr_conf={ocr_conf:.2f}, vehicle={name})")

    return annotated, detections


# --- sidebar (shows every unique plate found so far, live) ------------------
SIDEBAR_WIDTH = 320
SIDEBAR_BG = (32, 32, 32)


def add_plate_sidebar(frame, plate_list, current_frame_plates):
    """Return a wider frame with a dark panel on the right listing every
    unique plate read so far, newest at top. Plates read in the CURRENT
    frame are highlighted green so it's clear what's being detected right
    now vs. what was found earlier."""
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


class _NullOCR:
    """Stand-in reader for frames we skip OCR on (see --ocr-stride) -- returns
    no text so find_plate_candidate exits immediately without doing any real
    (slow) OCR work."""
    def readtext(self, *_args, **_kwargs):
        return []


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, help="path to the trained .pt weights to test")
    ap.add_argument("--source", required=True, help="input video path")
    ap.add_argument("--out-dir", required=True, help="folder to save annotated.mp4 and number_plates/ into")
    ap.add_argument("--conf", type=float, default=0.25, help="YOLO detection confidence threshold")
    ap.add_argument("--ocr-stride", type=int, default=3,
                     help="run plate OCR every N frames per vehicle (OCR is the slow part on CPU)")
    ap.add_argument("--meters-per-pixel", type=float, default=None,
                     help="PLACEHOLDER speed calibration constant -- see module docstring. If omitted, "
                          "speed is not estimated (tracking + plates still run).")
    ap.add_argument("--max-frames", type=int, default=None, help="stop after this many frames (for quick tests)")
    args = ap.parse_args()

    global STAGE1_CONF
    STAGE1_CONF = args.conf

    import torch
    from ultralytics import YOLO
    import easyocr

    use_gpu = torch.cuda.is_available()
    print(f"device: {'cuda' if use_gpu else 'cpu'}")

    out_dir = Path(args.out_dir)
    plates_dir = out_dir / "number_plates"
    out_dir.mkdir(parents=True, exist_ok=True)
    plates_dir.mkdir(parents=True, exist_ok=True)
    video_out_path = out_dir / "annotated.mp4"

    if args.meters_per_pixel is not None:
        print(f"WARNING: --meters-per-pixel={args.meters_per_pixel} is a placeholder, not a real calibration "
              f"(see script docstring). Treat speeds as illustrative only.")

    print("loading model + OCR reader...")
    model = YOLO(args.model)
    ocr_reader = easyocr.Reader(["en"], gpu=use_gpu)
    null_ocr = _NullOCR()
    track_history = defaultdict(lambda: deque(maxlen=SPEED_SMOOTH_WINDOW))
    track_class = {}

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
    max_speed_seen = {}  # track_id -> (kmh, frame_idx)
    frame_log = []
    frame_idx = 0

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if args.max_frames is not None and frame_idx >= args.max_frames:
            break

        reader = ocr_reader if frame_idx % args.ocr_stride == 0 else null_ocr
        annotated, detections = process_frame(
            model, reader, frame, frame_idx, fps, args.meters_per_pixel, track_history, track_class,
        )

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

        for v in detections["vehicle"]:
            if v["track_id"] is not None and v["speed_kmh"] is not None:
                tid = v["track_id"]
                prev = max_speed_seen.get(tid, (0.0, 0))
                if v["speed_kmh"] > prev[0]:
                    max_speed_seen[tid] = (v["speed_kmh"], frame_idx)

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

    (out_dir / "detections.json").write_text(json.dumps(frame_log, indent=2))
    (out_dir / "plates_found.txt").write_text(
        "\n".join(sorted(seen_plate_texts)) + ("\n" if seen_plate_texts else "")
    )

    print(f"done. {frame_idx} frames -> {video_out_path}")
    print(f"{len(seen_plate_texts)} unique plates -> {plates_dir}")
    print(f"log: {out_dir / 'detections.json'}")

    if args.meters_per_pixel is not None:
        speed_summary = {
            str(tid): {"class": NAMES[track_class[tid]], "max_speed_kmh": round(v[0], 1), "frame": v[1]}
            for tid, v in max_speed_seen.items() if tid in track_class
        }
        (out_dir / "speed_summary.json").write_text(json.dumps(speed_summary, indent=2))
        print(f"{len(speed_summary)} tracked vehicles -> {out_dir / 'speed_summary.json'}")
        print("REMINDER: speeds use a placeholder meters-per-pixel constant -- calibrate against the real "
              "camera before trusting these numbers.")


if __name__ == "__main__":
    main()
