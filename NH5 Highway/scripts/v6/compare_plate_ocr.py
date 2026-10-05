#!/usr/bin/env python3
"""Detect + track license plates with the 100-epoch model, find each plate's single best
(largest) crop the same way log_plates.py does, then run PaddleOCR and TrOCR SEPARATELY (not
combined/voted against each other) on that same crop so their raw outputs can be compared
side by side. No source/intermediate videos are kept -- only the annotated video, the plate
crops, and a CSV with both engines' readings.

Usage:
  python scripts/v6/compare_plate_ocr.py --weights <best.pt> --video <path> [--video <path2> ...] \
      --out-dir <dir>
"""
import argparse
import csv
import subprocess
from pathlib import Path

import cv2
from ultralytics import YOLO


def slow_down(video: Path, factor: float, out_dir: Path) -> Path:
    out = out_dir / f"{video.stem}_slow{factor:g}x.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video), "-vf", f"setpts={factor}*PTS", "-an", str(out)],
        check=True, capture_output=True,
    )
    return out


def paddle_read(ocr, crop_path):
    result = ocr.predict(str(crop_path))
    for res in result:
        texts = res.get("rec_texts") or []
        scores = res.get("rec_scores") or []
        if texts:
            text = "".join(texts).upper().replace(" ", "")
            conf = sum(scores) / len(scores)
            return text, conf
    return "", 0.0


def trocr_read(processor, model, device, crop):
    import torch
    rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
    pixel_values = processor(images=rgb, return_tensors="pt").pixel_values.to(device)
    with torch.no_grad():
        out = model.generate(pixel_values, output_scores=True, return_dict_in_generate=True)
    text = processor.batch_decode(out.sequences, skip_special_tokens=True)[0]
    text = text.upper().replace(" ", "")
    scores = torch.stack(out.scores, dim=1).softmax(-1).max(-1).values
    conf = scores.mean().item() if scores.numel() else 0.0
    return text, conf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", required=True)
    ap.add_argument("--video", action="append", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--conf", type=float, default=0.35)
    ap.add_argument("--slow", type=float, default=2.0)
    args = ap.parse_args()

    import torch
    from paddleocr import PaddleOCR
    from transformers import RobertaTokenizer, ViTImageProcessor, TrOCRProcessor, VisionEncoderDecoderModel

    model = YOLO(args.weights)
    plate_id = next(i for i, n in model.names.items() if n == "license_plate")

    paddle_ocr = PaddleOCR(use_textline_orientation=False, lang="en",
                            use_doc_orientation_classify=False, use_doc_unwarping=False,
                            enable_mkldnn=False)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    tok = RobertaTokenizer.from_pretrained("microsoft/trocr-base-printed")
    img_proc = ViTImageProcessor.from_pretrained("microsoft/trocr-base-printed")
    trocr_processor = TrOCRProcessor(image_processor=img_proc, tokenizer=tok)
    trocr_model = VisionEncoderDecoderModel.from_pretrained("microsoft/trocr-base-printed").to(device).eval()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for video in args.video:
        video = Path(video)
        video_out = out_dir / video.stem
        (video_out / "plates").mkdir(parents=True, exist_ok=True)

        slowed = slow_down(video, args.slow, video_out)
        print(f"[{video.name}] slowed {args.slow}x -> {slowed.name}")

        best_area, best_crop = {}, {}
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
            if boxes is not None:
                for box in boxes:
                    cls_id = int(box.cls[0])
                    xyxy = tuple(map(int, box.xyxy[0].tolist()))
                    tid = int(box.id[0]) if box.id is not None else -1
                    bconf = float(box.conf[0])
                    color = (0, 255, 255) if cls_id == plate_id else (0, 200, 0)
                    cv2.rectangle(drawn, xyxy[:2], xyxy[2:], color, 2)
                    cv2.putText(drawn, f"{model.names[cls_id]} {bconf:.2f}", (xyxy[0], max(0, xyxy[1] - 8)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                    if cls_id == plate_id:
                        x0, y0, x1, y1 = xyxy
                        crop = frame[max(0, y0):y1, max(0, x0):x1]
                        area = (x1 - x0) * (y1 - y0)
                        if area > best_area.get(tid, 0) and crop.size:
                            best_area[tid] = area
                            best_crop[tid] = crop.copy()
            writer.write(drawn)
        writer.release()
        slowed.unlink(missing_ok=True)

        rows = []
        for tid, crop in best_crop.items():
            crop_path = video_out / "plates" / f"track{tid}.jpg"
            cv2.imwrite(str(crop_path), crop)
            paddle_text, paddle_conf = paddle_read(paddle_ocr, crop_path)
            trocr_text, trocr_conf = trocr_read(trocr_processor, trocr_model, device, crop)
            rows.append({
                "track_id": tid, "plate_image": str(crop_path.relative_to(out_dir)),
                "paddleocr_text": paddle_text, "paddleocr_conf": f"{paddle_conf:.3f}",
                "trocr_text": trocr_text, "trocr_conf": f"{trocr_conf:.3f}",
            })

        csv_path = video_out / "ocr_comparison.csv"
        with open(csv_path, "w", newline="") as f:
            writer_csv = csv.DictWriter(f, fieldnames=[
                "track_id", "plate_image", "paddleocr_text", "paddleocr_conf", "trocr_text", "trocr_conf"])
            writer_csv.writeheader()
            writer_csv.writerows(rows)

        (video_out / "paddleocr_plates.txt").write_text(
            "\n".join(r["paddleocr_text"] for r in rows if r["paddleocr_text"]) + "\n" if rows else "")
        (video_out / "trocr_plates.txt").write_text(
            "\n".join(r["trocr_text"] for r in rows if r["trocr_text"]) + "\n" if rows else "")

        print(f"[{video.name}] {len(rows)} plates compared -> {csv_path}")


if __name__ == "__main__":
    main()
