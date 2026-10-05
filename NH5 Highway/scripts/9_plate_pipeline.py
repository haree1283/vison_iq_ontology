#!/usr/bin/env python3
"""Two-stage highway detection pipeline.

Stage 1 (full frame): the trained YOLOv8 model finds person / bicycle / car /
motorcycle / bus / truck / pothole directly. (license_plate is intentionally
not read from this pass -- see below.)

Stage 2 (plates, OCR-first): our license_plate class was only ever trained
on clean, close-up ANPR photos, so it doesn't recognize a plate inside a
crop pulled from real highway/dashcam footage -- a genuine domain gap, not
a threshold-tuning problem (verified: zero signal even at conf=0.05 on a
real highway crop). Rather than trust that detector here, for every vehicle
box from stage 1 we crop it out (with padding), upscale it, and run
EasyOCR's own text-region finder directly on the crop -- it's a
general-purpose scene-text model, not narrowly trained on ANPR photos, so it
generalizes better to arbitrary footage. Each text region it finds is
scored against plate-shaped heuristics (alphanumeric pattern, aspect ratio)
and the best candidate is kept as the plate.

Usage:
  python 9_plate_pipeline.py --model runs/nh5_highway/weights/best.pt --source image.jpg
  python 9_plate_pipeline.py --model best.pt --source video.mp4 --out annotated.mp4
  python 9_plate_pipeline.py --model best.pt --source frames_dir/ --out out_dir/
"""
import argparse
import json
import re
from pathlib import Path

import cv2
import numpy as np

# NOTE: "auto" (class 8) is only meaningful once a model trained with the
# 9-class schema (datasets/processed_v2, see 5_unify_and_split.py) is deployed
# here -- the current nh5_v2_best.pt only knows classes 0-7.
NAMES = ["person", "bicycle", "car", "motorcycle", "bus", "truck", "pothole", "license_plate", "auto"]
VEHICLE_CLASS_IDS = {2, 3, 4, 5, 8}  # car, motorcycle, bus, truck, auto
PLATE_CLASS_ID = 7

COLORS = {
    0: (48, 59, 255), 1: (0, 149, 255), 2: (0, 204, 255), 3: (100, 217, 76),
    4: (250, 200, 90), 5: (255, 122, 0), 6: (214, 86, 88), 7: (85, 45, 255),
    8: (180, 105, 255),
    9: (160, 0, 160), 10: (0, 0, 255), 11: (0, 100, 255),  # road_construction purple, accident red, fire orange
}

CROP_PAD_FRAC = 0.20     # padding added around each vehicle box before scanning for text
PLATE_SEARCH_TOP_FRAC = 0.45  # skip the top 45% of the vehicle box -- plates are never up near the roofline
CROP_MIN_SIDE = 480      # upscale the crop so its shorter side is at least this many px
STAGE1_CONF = 0.25

# plate-candidate filtering: keep OCR text regions shaped like a plate
PLATE_TEXT_LEN_RANGE = (6, 11)     # matches PLATE_PATTERN's min/max length (AA00A0000)
PLATE_ASPECT_RANGE = (1.3, 7.0)    # width/height of the text region's bounding box
PLATE_MIN_OCR_CONF = 0.25


def load_model(weights_path):
    from ultralytics import YOLO
    return YOLO(weights_path)


class PaddleOCRReader:
    """Wraps PaddleOCR behind the same `.readtext(image) -> [(bbox_poly, text,
    conf), ...]` interface easyocr.Reader exposes, so it drops into
    find_plate_candidate / _merge_text_fragments unchanged.

    enable_mkldnn=False works around a NotImplementedError
    ("ConvertPirAttribute2RuntimeAttribute") thrown by this paddlepaddle
    build's oneDNN executor on every model tried (PP-OCRv4 and PP-OCRv6,
    mobile and medium) -- reproduced independently of image content, so it's
    an environment/engine issue, not something request-specific to work
    around per-call.
    """

    def __init__(self, use_gpu=False):
        import os
        os.environ.setdefault("FLAGS_use_mkldnn", "0")
        from paddleocr import PaddleOCR
        self._ocr = PaddleOCR(
            lang="en",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            enable_mkldnn=False,
        )

    def readtext(self, image_bgr):
        out = []
        for res in self._ocr.predict(image_bgr):
            polys = res.get("rec_polys") or []
            texts = res.get("rec_texts") or []
            scores = res.get("rec_scores") or []
            for poly, text, score in zip(polys, texts, scores):
                out.append((poly.tolist(), text, float(score)))
        return out


def load_ocr_reader(use_gpu=False, engine="easyocr"):
    if engine == "paddleocr":
        return PaddleOCRReader(use_gpu=use_gpu)
    import easyocr
    return easyocr.Reader(["en"], gpu=use_gpu)


def clamp_box(x0, y0, x1, y1, w, h):
    return max(0, int(x0)), max(0, int(y0)), min(w, int(x1)), min(h, int(y1))


# Indian standard plate format: 2 letters (state) + 2 digits (RTO code) +
# 1-3 letters (series) + 1-4 digits (number), e.g. "MH12AB1234". Spaces are
# allowed in the source regex but never appear here since `clean` above has
# already stripped all non-alphanumeric characters first.
PLATE_PATTERN = re.compile(r"^[A-Z]{2}\d{2}[A-Z]{1,3}\d{1,4}$")

# OCR frequently swaps visually similar characters (a font/resolution issue,
# not a logic bug -- e.g. EasyOCR read a real "MH12AB1234" plate as
# "MH1ZAB1234", confusing 2/Z). match_plate_pattern below tries the strict
# regex first, and only falls back to correcting characters against what the
# Indian plate format expects at each position (2 letters, 2 digits, 1-3
# letters, 1-4 digits) if that fails.
LETTER_LOOKALIKE_TO_DIGIT = {"O": "0", "I": "1", "L": "1", "Z": "2", "S": "5", "B": "8", "G": "6", "Q": "0"}
DIGIT_LOOKALIKE_TO_LETTER = {"0": "O", "1": "I", "2": "Z", "5": "S", "8": "B", "6": "G"}


MAX_LOOKALIKE_CORRECTIONS = 1  # see match_plate_pattern


def match_plate_pattern(clean):
    """Return the text corrected to the Indian plate format (2 letters, 2
    digits, 1-3 letters, 1-4 digits), or None if no split of `clean` into
    those four groups fits -- allowing at most MAX_LOOKALIKE_CORRECTIONS
    look-alike character substitutions (e.g. one 2/Z mixup).

    Capped deliberately: with no cap, a long enough run of unrelated text
    can have EVERY character reinterpreted as some look-alike and still
    "fit" the 4-group shape, producing a plate number that was never
    actually on any plate (reproduced: fused OCR fragments spelling
    "YQ149211 22" got corrected all the way to "BI49ZYO1122"). A genuine
    single-character OCR slip needs at most one or two corrections, not
    four or five, so capping at 1 rejects that class of false positive
    while still fixing the real case this was built for.
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
            fixed = []
            ok = True
            corrections = 0
            for start, end, kind in groups:
                for ch in clean[start:end]:
                    if kind == "digit":
                        if ch.isdigit():
                            fixed.append(ch)
                        elif ch in LETTER_LOOKALIKE_TO_DIGIT:
                            fixed.append(LETTER_LOOKALIKE_TO_DIGIT[ch])
                            corrections += 1
                        else:
                            ok = False
                            break
                    else:
                        if ch.isalpha():
                            fixed.append(ch)
                        elif ch in DIGIT_LOOKALIKE_TO_LETTER:
                            fixed.append(DIGIT_LOOKALIKE_TO_LETTER[ch])
                            corrections += 1
                        else:
                            ok = False
                            break
                    if corrections > MAX_LOOKALIKE_CORRECTIONS:
                        ok = False
                        break
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
    code and the number as separate boxes). Greedily merge fragments that
    sit on the same line and close together, so the combined text can be
    matched against the plate pattern as a whole."""
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
                cl["x0"] = min(cl["x0"], it["x0"])
                cl["x1"] = max(cl["x1"], it["x1"])
                cl["y0"] = min(cl["y0"], it["y0"])
                cl["y1"] = max(cl["y1"], it["y1"])
                cl["parts"].append(it)
                placed = True
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


def find_plate_candidate(reader, crop_bgr):
    """Scan a vehicle crop for OCR text regions shaped like a plate.

    Returns (x0, y0, x1, y1, text, ocr_conf) for the best candidate, or None.
    Coordinates are in the (possibly upscaled) crop's own pixel space.
    """
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


def process_frame(model, ocr_reader, frame_bgr):
    h, w = frame_bgr.shape[:2]
    annotated = frame_bgr.copy()
    detections = {"person": [], "bicycle": [], "vehicle": [], "pothole": [], "plate": []}

    result = model.predict(frame_bgr, conf=STAGE1_CONF, verbose=False)[0]
    if result.boxes is None:
        return annotated, detections

    for box in result.boxes:
        cls = int(box.cls[0])
        conf = float(box.conf[0])
        x0, y0, x1, y1 = box.xyxy[0].tolist()
        name = NAMES[cls]
        color = COLORS[cls]

        if cls == PLATE_CLASS_ID:
            continue  # rely on stage 2 for plates; a full-frame plate box is usually too coarse

        cv2.rectangle(annotated, (int(x0), int(y0)), (int(x1), int(y1)), color, 2)
        draw_label(annotated, int(x0), int(y0), f"{name} {conf:.2f}", color)

        if cls == 0:
            detections["person"].append([x0, y0, x1, y1, conf])
        elif cls == 1:
            detections["bicycle"].append([x0, y0, x1, y1, conf])
        elif cls == 6:
            detections["pothole"].append([x0, y0, x1, y1, conf])
        elif cls in VEHICLE_CLASS_IDS:
            detections["vehicle"].append({"class": name, "box": [x0, y0, x1, y1], "conf": conf})

            # --- stage 2: crop this vehicle, re-detect the plate at higher effective res ---
            # No top padding, and the search starts from PLATE_SEARCH_TOP_FRAC down into
            # the box: plates are always in a vehicle's lower half (bumper/grille height),
            # never near the roofline -- padding the top let background objects above the
            # vehicle (e.g. storefront/bank signage) leak into the OCR crop and occasionally
            # get misread as a plate-shaped string (reproduced: Telugu bank signage above a
            # car parked at the frame edge got read as "JR23O5" and passed every filter,
            # since the misread text was coincidentally shaped like a real plate).
            bw, bh = x1 - x0, y1 - y0
            px0, py0, px1, py1 = clamp_box(
                x0 - bw * CROP_PAD_FRAC, y0 + bh * PLATE_SEARCH_TOP_FRAC,
                x1 + bw * CROP_PAD_FRAC, y1 + bh * CROP_PAD_FRAC, w, h,
            )
            veh_crop = frame_bgr[py0:py1, px0:px1]
            if veh_crop.size == 0:
                continue

            candidate, resized_crop, scale = find_plate_candidate(ocr_reader, veh_crop)
            if candidate is None:
                continue

            qx0, qy0, qx1, qy1, text, ocr_conf = candidate
            # map from resized-crop space -> original-crop space -> full-frame space
            fx0, fy0 = px0 + qx0 / scale, py0 + qy0 / scale
            fx1, fy1 = px0 + qx1 / scale, py0 + qy1 / scale

            plate_color = COLORS[PLATE_CLASS_ID]
            cv2.rectangle(annotated, (int(fx0), int(fy0)), (int(fx1), int(fy1)), plate_color, 2)
            draw_label(annotated, int(fx0), int(fy0), f"{text} ({ocr_conf:.2f})", plate_color)

            detections["plate"].append({
                "box": [fx0, fy0, fx1, fy1],
                "text": text,
                "ocr_conf": ocr_conf,
                "vehicle_class": name,
            })
            print(f"    plate found: {text}  (ocr_conf={ocr_conf:.2f}, vehicle={name})")

    return annotated, detections


def run_on_image(model, ocr_reader, img_path, out_path):
    frame = cv2.imread(str(img_path))
    annotated, detections = process_frame(model, ocr_reader, frame)
    cv2.imwrite(str(out_path), annotated)
    return detections


def run_on_video(model, ocr_reader, video_path, out_path):
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))

    all_detections = []
    frame_idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        annotated, detections = process_frame(model, ocr_reader, frame)
        writer.write(annotated)
        all_detections.append({"frame": frame_idx, **detections})
        frame_idx += 1
        if frame_idx % 30 == 0:
            print(f"  frame {frame_idx} processed")

    cap.release()
    writer.release()
    return all_detections


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="path to trained .pt weights")
    ap.add_argument("--source", required=True, help="image, video, or directory of images")
    ap.add_argument("--out", default=None, help="output path (file or dir); defaults next to source")
    ap.add_argument("--json", default=None, help="optional path to dump structured detections as JSON")
    ap.add_argument("--ocr-engine", choices=["easyocr", "paddleocr"], default="easyocr")
    args = ap.parse_args()

    import torch
    use_gpu = torch.cuda.is_available()
    print(f"device: {'cuda' if use_gpu else 'cpu'}")

    model = load_model(args.model)
    ocr_reader = load_ocr_reader(use_gpu=use_gpu, engine=args.ocr_engine)

    src = Path(args.source)
    all_results = {}

    if src.is_dir():
        out_dir = Path(args.out) if args.out else src.parent / (src.name + "_annotated")
        out_dir.mkdir(parents=True, exist_ok=True)
        for img_path in sorted(src.glob("*.jpg")) + sorted(src.glob("*.png")):
            out_path = out_dir / img_path.name
            print(f"processing {img_path.name}")
            all_results[img_path.name] = run_on_image(model, ocr_reader, img_path, out_path)
    elif src.suffix.lower() in (".mp4", ".avi", ".mov", ".mkv"):
        out_path = Path(args.out) if args.out else src.with_name(src.stem + "_annotated.mp4")
        print(f"processing video {src} -> {out_path}")
        all_results["frames"] = run_on_video(model, ocr_reader, src, out_path)
    else:
        out_path = Path(args.out) if args.out else src.with_name(src.stem + "_annotated" + src.suffix)
        print(f"processing image {src} -> {out_path}")
        all_results[src.name] = run_on_image(model, ocr_reader, src, out_path)

    if args.json:
        Path(args.json).write_text(json.dumps(all_results, indent=2, default=str))
        print(f"wrote {args.json}")

    print("done")


if __name__ == "__main__":
    main()
