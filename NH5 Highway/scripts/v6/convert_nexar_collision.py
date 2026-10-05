#!/usr/bin/env python3
"""Extract whole-frame accident_scene images from the real nexar-ai/nexar_collision_prediction
dashcam videos (train/positive = real collisions, train/negative = real normal driving) into a
v6 source. These are genuine dashcam recordings from Nexar's own fleet, not a scraped/synthetic
Roboflow re-upload -- there are no object-level boxes (this is a video-classification dataset), so
each frame is stored as a whole-frame "damaged_vehicle" carrier box (same whole-image convention
already used for fire_images/raqabah), which build_unified_yolo.py's road_accidents scene pass
already knows how to use. Negative (no-collision) frames are kept as label-less background images
-- real driving scenes with no accident, useful as hard negatives.

Usage:
  python scripts/v6/convert_nexar_collision.py
"""
import subprocess
from pathlib import Path

from classes import CLASS_IDS

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "datasets" / "v6" / "raw" / "nexar_collision" / "train"
OUT = ROOT / "datasets" / "v6" / "sources" / "nexar_collision" / "train"
CARRIER_ID = CLASS_IDS["damaged_vehicle"]


def extract_frame(video_path, out_path, position_fraction):
    """Grab one frame at the given fraction of the video's duration via ffmpeg."""
    duration = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
        capture_output=True, text=True,
    ).stdout.strip()
    try:
        t = float(duration) * position_fraction
    except ValueError:
        return False
    result = subprocess.run(
        ["ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", str(video_path), "-frames:v", "1", str(out_path)],
        capture_output=True,
    )
    return result.returncode == 0 and out_path.is_file()


def main():
    (OUT / "images").mkdir(parents=True, exist_ok=True)
    (OUT / "labels").mkdir(parents=True, exist_ok=True)

    positive_written = negative_written = 0
    # these are event-triggered dashcam recordings (accelerometer-triggered save), so the actual
    # collision sits at or right before the very end of the clip, not at a fixed fraction of its
    # duration -- a 75%/90% heuristic mostly landed on ordinary mid-drive traffic instead
    for video in sorted((RAW / "positive").glob("*.mp4")):
        duration = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
            capture_output=True, text=True,
        ).stdout.strip()
        try:
            dur = float(duration)
        except ValueError:
            continue
        offsets = [max(0.0, dur - 0.2), max(0.0, dur - 1.0)]
        for j, t in enumerate(offsets):
            stem = f"nexar_{video.stem}_{j}"
            img_path = OUT / "images" / f"{stem}.jpg"
            result = subprocess.run(
                ["ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1", str(img_path)],
                capture_output=True,
            )
            if result.returncode == 0 and img_path.is_file():
                cx, cy, w, h = 0.5, 0.5, 1.0, 1.0
                (OUT / "labels" / f"{stem}.txt").write_text(f"{CARRIER_ID} {cx} {cy} {w} {h}\n")
                positive_written += 1

    for video in sorted((RAW / "negative").glob("*.mp4")):
        stem = f"nexar_{video.stem}"
        img_path = OUT / "images" / f"{stem}.jpg"
        if extract_frame(video, img_path, 0.5):
            (OUT / "labels" / f"{stem}.txt").write_text("")  # background, no accident
            negative_written += 1

    print(f"positive (accident) frames: {positive_written}")
    print(f"negative (background) frames: {negative_written}")


if __name__ == "__main__":
    main()
