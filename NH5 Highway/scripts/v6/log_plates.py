#!/usr/bin/env python3
"""Detect license plates, crop each one, and OCR ONLY the crop with PaddleOCR (confirmed more
accurate than TrOCR in a head-to-head comparison on this footage -- TrOCR kept hallucinating
receipt/invoice words like "TOTAL"/"AMOUNT" regardless of the crop's actual content, since it's
tuned for printed documents, not plates).

Each plate is read repeatedly across the frames it's tracked in (target: 5-6 reads) and validated
against the Indian plate layout every time; a reading is only trusted once it's recurred at least
--min-votes times, so a one-off misread never makes it to the output. Confirmed plates get their
single largest/clearest crop saved, and plates.txt lists each unique plate number exactly once
(no duplicates), even if the same plate was tracked as multiple ids or read by multiple vehicles.

Usage:
  python scripts/v6/log_plates.py --weights <best.pt> --video <path> [--video <path2> ...] \
      --out-dir <dir> [--slow 2.0] [--min-votes 5]
"""
import argparse
import csv
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

import cv2
from ultralytics import YOLO

# state code (2 letters) + RTO code (2 digits) + series (1-2 letters) + running number (1-4
# digits, zero-padded to 4 below) -- e.g. "AP" "09" "AB" "7" -> "AP09AB0007"
INDIAN_PLATE_RE = re.compile(r"^([A-Z]{2})([0-9]{2})([A-Z]{1,2})([0-9]{1,4})$")


def normalize_indian_plate(text):
    """Validate an OCR string against the Indian plate layout and zero-pad its running number to
    4 digits; returns None (reject) if it doesn't fit the layout or the padded number is 0000."""
    m = INDIAN_PLATE_RE.match(text)
    if not m:
        return None
    state, rto, series, number = m.groups()
    number = number.zfill(4)
    if number == "0000":
        return None
    return f"{state}{rto}{series}{number}"


def slow_down(video: Path, factor: float, out_dir: Path) -> Path:
    out = out_dir / f"{video.stem}_slow{factor:g}x.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video), "-vf", f"setpts={factor}*PTS", "-an", str(out)],
        check=True, capture_output=True,
    )
    return out


def read_plate(ocr, crop_path):
    """PaddleOCR runs only on the already-cropped plate image, never the full frame."""
    result = ocr.predict(str(crop_path))
    for res in result:
        texts = res.get("rec_texts") or []
        if not texts:
            continue
        raw = "".join(texts).upper().replace(" ", "")
        return normalize_indian_plate(raw) or ""
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", required=True)
    ap.add_argument("--video", action="append", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--conf", type=float, default=0.35)
    ap.add_argument("--slow", type=float, default=2.0, help="playback-speed divisor, e.g. 2.0 = half speed")
    ap.add_argument("--min-votes", type=int, default=5,
                     help="a plate's winning OCR reading must recur at least this many times across "
                          "frames before it's trusted enough to save; anything under this is dropped")
    args = ap.parse_args()

    from paddleocr import PaddleOCR
    model = YOLO(args.weights)
    ocr = PaddleOCR(use_textline_orientation=False, lang="en",
                     use_doc_orientation_classify=False, use_doc_unwarping=False, enable_mkldnn=False)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    plate_id = next(i for i, n in model.names.items() if n == "license_plate")

    for video in args.video:
        video = Path(video)
        video_out = out_dir / video.stem
        (video_out / "plates").mkdir(parents=True, exist_ok=True)
        tmp_crop = video_out / "_tmp_crop.jpg"  # PaddleOCR reads from a file path, not an array

        slowed = slow_down(video, args.slow, video_out)
        print(f"[{video.name}] slowed {args.slow}x -> {slowed.name}")

        readings = defaultdict(list)   # plate track id -> [ocr text, ...] across all frames
        best_area = {}                 # plate track id -> largest plate box area seen so far
        best_crop = {}                 # plate track id -> plate crop at that best frame
        annotated_path = video_out / f"{video.stem}_annotated.mp4"
        cap = cv2.VideoCapture(str(slowed))
        fps = cap.get(cv2.CAP_PROP_FPS) or 25
        w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        writer = cv2.VideoWriter(str(annotated_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))

        for result in model.track(str(slowed), conf=args.conf, persist=True, stream=True, verbose=False):
            frame = result.orig_img
            drawn = frame.copy()
            boxes = result.boxes
            plate_boxes = []
            if boxes is not None:
                for box in boxes:
                    cls_id = int(box.cls[0])
                    xyxy = tuple(map(int, box.xyxy[0].tolist()))
                    tid = int(box.id[0]) if box.id is not None else -1
                    conf = float(box.conf[0])
                    if cls_id == plate_id:
                        plate_boxes.append((xyxy, tid))
                        continue  # plate boxes get their OCR-read text as a label below instead
                    color = (0, 200, 0)
                    cv2.rectangle(drawn, xyxy[:2], xyxy[2:], color, 2)
                    cv2.putText(drawn, f"{model.names[cls_id]} {conf:.2f}", (xyxy[0], max(0, xyxy[1] - 8)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

            for xyxy, tid in plate_boxes:
                x0, y0, x1, y1 = xyxy
                cv2.rectangle(drawn, (x0, y0), (x1, y1), (0, 255, 255), 2)
                plate_crop = frame[max(0, y0):y1, max(0, x0):x1]
                if plate_crop.size:
                    cv2.imwrite(str(tmp_crop), plate_crop)
                    text = read_plate(ocr, tmp_crop)
                    if text:
                        readings[tid].append(text)

                    area = (x1 - x0) * (y1 - y0)
                    if area > best_area.get(tid, 0):
                        best_area[tid] = area
                        best_crop[tid] = plate_crop.copy()

                current_best = Counter(readings[tid]).most_common(1)
                label = current_best[0][0] if current_best else "reading..."
                cv2.putText(drawn, label, (x0, max(0, y0 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

            writer.write(drawn)
        writer.release()
        tmp_crop.unlink(missing_ok=True)

        rows, rejected, seen_plates = [], 0, set()
        for tid, texts in readings.items():
            if tid not in best_crop or not texts:
                continue  # never got a single readable OCR result for this plate track
            vote, count = Counter(texts).most_common(1)[0]
            if count < args.min_votes:
                # the top reading didn't recur enough times across the frames this plate was
                # tracked in -- not corroborated enough to trust, so drop it instead of saving a
                # possibly-wrong guess
                rejected += 1
                continue
            if vote in seen_plates:
                continue  # same plate number already confirmed via another track -- no duplicates
            seen_plates.add(vote)
            plate_path = video_out / "plates" / f"{vote}.jpg"
            cv2.imwrite(str(plate_path), best_crop[tid])
            rows.append({
                "track_id": tid, "plate_number": vote, "votes_for_this_reading": count,
                "total_reads": len(texts), "all_readings": "|".join(texts),
                "plate_image": str(plate_path.relative_to(out_dir)),
            })

        csv_path = video_out / "plates_log.csv"
        with open(csv_path, "w", newline="") as f:
            writer_csv = csv.DictWriter(f, fieldnames=[
                "track_id", "plate_number", "votes_for_this_reading", "total_reads",
                "all_readings", "plate_image"])
            writer_csv.writeheader()
            writer_csv.writerows(rows)

        text_path = video_out / "plates.txt"
        text_path.write_text("\n".join(sorted(seen_plates)) + "\n" if seen_plates else "")

        print(f"[{video.name}] {len(rows)} confirmed unique plates (>= {args.min_votes}x match), "
              f"{rejected} dropped for not being read the same way at least {args.min_votes} times -> {text_path}")
        print(f"[{video.name}] annotated video -> {annotated_path}")

        slowed.unlink(missing_ok=True)  # intermediate only, not part of the wanted output


if __name__ == "__main__":
    main()
