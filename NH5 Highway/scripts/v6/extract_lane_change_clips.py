#!/usr/bin/env python3
"""Cut lane-change clips out of a FIXED overhead traffic video into
datasets/v6/categories/07_lane_change/.

The detector (nh5_v5) was trained on side views and misses cars seen from
straight above, so vehicles here come from background subtraction: on a fixed
camera over a freeway every moving blob is a vehicle. Blobs are tracked by
nearest predicted position and fed to event_engine.EventEngine with the
camera's road map, so the lane-change rule is the same one the app runs.

The engine judges lanes at a box's bottom edge; seen from above that edge is a
vehicle's side, not its centre, so each box is passed with its bottom moved to
the blob centroid.

Each event is kept only if the track looks clean: it exists 2 s before and 1 s
after, its centroid really moved sideways by --min-shift of a lane width, and its
blob size didn't jump (two vehicles merging into one blob). For each kept event
it writes <name>.mp4 (road map, target vehicle in red with its trail) and
<name>.jpg (before / during / after), plus lane_change_index.csv.

Wrong-side events on real traffic can only be tracker mistakes -- their count is
printed as a sanity check of the lane directions.

Usage:
  python scripts/v6/extract_lane_change_clips.py VIDEO SCENE.json --preview   # check the lane map first
  python scripts/v6/extract_lane_change_clips.py VIDEO SCENE.json --prefix ngsim_i80_cam4
"""
import argparse
import csv
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from event_engine import EventEngine, Scene  # noqa: E402

OUT = ROOT / "datasets" / "v6" / "categories" / "07_lane_change"
WARMUP_FRAMES = 150         # background model settles before tracks count
MIN_AREA, MAX_AREA = 60, 8000
TRUCK_LENGTH_PX = 45        # blob longer than this is passed as a truck (label only)
PRE_SECS, POST_SECS = 3.0, 2.0


def blobs(mask, scene, w, h):
    n, _, stats, cents = cv2.connectedComponentsWithStats(mask)
    out = []
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        cx, cy = cents[i]
        if MIN_AREA <= area <= MAX_AREA and scene.lane_at((cx, cy)) is not None:
            out.append({"box": (float(x), float(y), float(x + bw), float(y + bh)), "c": (cx, cy), "area": int(area)})
    return out


class Tracker:
    def __init__(self, max_dist=25.0, max_missed=5):
        self.tracks, self.next_id = {}, 1
        self.max_dist, self.max_missed = max_dist, max_missed

    def update(self, dets):
        preds = {tid: (t["c"][0] + t["v"][0], t["c"][1] + t["v"][1]) for tid, t in self.tracks.items()}
        pairs = sorted((np.hypot(d["c"][0] - p[0], d["c"][1] - p[1]), tid, i)
                       for tid, p in preds.items() for i, d in enumerate(dets))
        used_t, used_d = set(), set()
        for dist, tid, i in pairs:
            if dist > self.max_dist or tid in used_t or i in used_d:
                continue
            t, d = self.tracks[tid], dets[i]
            t["v"] = (0.6 * t["v"][0] + 0.4 * (d["c"][0] - t["c"][0]), 0.6 * t["v"][1] + 0.4 * (d["c"][1] - t["c"][1]))
            t.update(c=d["c"], missed=0)
            d["id"] = tid
            used_t.add(tid)
            used_d.add(i)
        for tid in list(self.tracks):
            if tid not in used_t:
                self.tracks[tid]["missed"] += 1
                if self.tracks[tid]["missed"] > self.max_missed:
                    del self.tracks[tid]
        for i, d in enumerate(dets):
            if i not in used_d:
                d["id"] = self.next_id
                self.tracks[self.next_id] = {"c": d["c"], "v": (0.0, 0.0), "missed": 0}
                self.next_id += 1
        return dets


def lane_width_at(scene, x, y):
    """Vertical size of the lane polygon under (x, y), in pixels."""
    name = scene.lane_at((x, y))
    poly = next(p for n, p, _ in scene._lane_px if n == name)
    ys = [yy for yy in range(int(poly[:, 1].min()), int(poly[:, 1].max()) + 1)
          if cv2.pointPolygonTest(poly, (float(x), float(yy)), False) >= 0]
    return max(1, len(ys))


def clean(event, hist, fps, scene, min_shift):
    track = hist[event["track_id"]]
    f = event["frame"]
    before = [track[k] for k in track if f - 2.5 * fps <= k <= f - 1.5 * fps]
    after = [track[k] for k in track if f + 0.3 * fps <= k <= f + 1.3 * fps]
    if len(before) < 0.6 * fps or len(after) < 0.6 * fps:
        return None
    window = [track[k] for k in track if f - 2.5 * fps <= k <= f + 1.3 * fps]
    areas = [b["area"] for b in window]
    if max(areas) > 2.2 * min(areas):
        return None
    cy0 = float(np.median([b["c"][1] for b in before]))
    cy1 = float(np.median([b["c"][1] for b in after]))
    cx0 = float(np.median([b["c"][0] for b in before]))
    cx1 = float(np.median([b["c"][0] for b in after]))
    lane_px = lane_width_at(scene, cx0, cy0)
    # remove the road's own tilt between the two x positions before measuring the sideways move
    tilt = next((vec[1] / vec[0] for n, _, vec in scene._lane_px if n == event["details"]["from_lane"]), 0.0)
    shift = abs((cy1 - cy0) - tilt * (cx1 - cx0))
    return shift / lane_px if shift >= min_shift * lane_px else None


def render(video, scene, event, hist, all_boxes, fps, out_stem):
    cap = cv2.VideoCapture(str(video))
    f0, f1 = int(event["frame"] - PRE_SECS * fps), int(event["frame"] + POST_SECS * fps)
    cap.set(cv2.CAP_PROP_POS_FRAMES, f0)
    w, h = int(cap.get(3)), int(cap.get(4))
    scale = 2
    tmp = out_stem.with_suffix(".tmp.mp4")
    writer = cv2.VideoWriter(str(tmp), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w * scale, h * scale))
    track = hist[event["track_id"]]
    stills = {}
    label = f"LANE CHANGE  {event['details']['from_lane']} -> {event['details']['to_lane']}"
    for f in range(f0, f1 + 1):
        ok, frame = cap.read()
        if not ok:
            break
        img = cv2.resize(frame, (w * scale, h * scale), interpolation=cv2.INTER_CUBIC)
        scene.draw(img)
        for b in all_boxes.get(f, []):
            x0, y0, x1, y1 = (int(v * scale) for v in b)
            cv2.rectangle(img, (x0, y0), (x1, y1), (170, 170, 170), 1)
        trail = [track[k]["c"] for k in sorted(track) if f0 <= k <= f]
        for a, b in zip(trail, trail[1:]):
            cv2.line(img, (int(a[0] * scale), int(a[1] * scale)), (int(b[0] * scale), int(b[1] * scale)), (0, 0, 255), 2)
        if f in track:
            x0, y0, x1, y1 = (int(v * scale) for v in track[f]["box"])
            cv2.rectangle(img, (x0 - 3, y0 - 3), (x1 + 3, y1 + 3), (0, 0, 255), 3)
        color = (0, 0, 255) if f >= event["frame"] - 1.0 * fps else (60, 60, 60)
        cv2.rectangle(img, (10, 10), (30 + 17 * len(label), 52), color, -1)
        cv2.putText(img, label, (20, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)
        writer.write(img)
        for name, at in (("before", f0 + int(1.0 * fps)), ("during", event["frame"]), ("after", f1)):
            if f == at:
                stills[name] = img.copy()
    writer.release()
    if shutil.which("ffmpeg"):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(tmp), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-movflags", "+faststart", str(out_stem.with_suffix(".mp4"))], check=True)
        tmp.unlink()
    else:
        tmp.rename(out_stem.with_suffix(".mp4"))
    if len(stills) == 3:
        strip = np.hstack([cv2.resize(stills[k], (w, h)) for k in ("before", "during", "after")])
        cv2.imwrite(str(out_stem.with_suffix(".jpg")), strip, [int(cv2.IMWRITE_JPEG_QUALITY), 88])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("scene", type=Path)
    ap.add_argument("--prefix", default=None, help="file name prefix, default: video name")
    ap.add_argument("--preview", action="store_true", help="only write <scene>.preview.jpg with the lane map drawn")
    ap.add_argument("--max-frames", type=int, default=None)
    ap.add_argument("--min-shift", type=float, default=0.6, help="sideways move, in lane widths")
    ap.add_argument("--max-clips", type=int, default=200)
    args = ap.parse_args()

    scene = Scene.load(args.scene)
    cap = cv2.VideoCapture(str(args.video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 10.0
    w, h = int(cap.get(3)), int(cap.get(4))
    scene.fit(w, h)

    if args.preview:
        cap.set(cv2.CAP_PROP_POS_FRAMES, 3000)
        _, frame = cap.read()
        img = cv2.resize(frame, (w * 2, h * 2))
        scene.draw(img)
        cv2.imwrite(str(args.scene.with_suffix(".preview.jpg")), img)
        print("wrote", args.scene.with_suffix(".preview.jpg"))
        return

    mog = cv2.createBackgroundSubtractorMOG2(history=300, varThreshold=25, detectShadows=True)
    k_open = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    k_close = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 5))
    engine = EventEngine(fps, scene, available_classes={"car", "truck"})
    tracker = Tracker()
    hist = defaultdict(dict)        # track id -> frame -> blob
    all_boxes = defaultdict(list)   # frame -> boxes, for drawing context

    f = 0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    while True:
        ok, frame = cap.read()
        if not ok or (args.max_frames and f >= args.max_frames):
            break
        mask = mog.apply(frame)
        mask = np.where(mask == 255, 255, 0).astype(np.uint8)  # 127 = shadow
        mask = cv2.morphologyEx(cv2.morphologyEx(mask, cv2.MORPH_OPEN, k_open), cv2.MORPH_CLOSE, k_close)
        if f >= WARMUP_FRAMES:
            dets = tracker.update(blobs(mask, scene, w, h))
            engine_dets = []
            for d in dets:
                x0, y0, x1, y1 = d["box"]
                cy = d["c"][1]
                hist[d["id"]][f] = d
                all_boxes[f].append(d["box"])
                engine_dets.append({"cls": "truck" if x1 - x0 > TRUCK_LENGTH_PX else "car", "conf": 1.0,
                                    "box": (x0, cy - (y1 - y0), x1, cy), "track_id": d["id"]})
            engine.update(f, w, h, engine_dets)
        f += 1
        if f % 1000 == 0:
            print(f"  {f}/{total} frames, {engine.summary()}")

    counts = engine.summary()
    changes = [e for e in engine.events if e["type"] == "lane_change"]
    print(f"engine events: {counts} (wrong_side on real traffic = tracker mistakes)")

    kept = []
    for ev in changes:
        shift = clean(ev, hist, fps, scene, args.min_shift)
        if shift is not None:
            kept.append((shift, ev))
    kept.sort(key=lambda se: se[1]["frame"])
    print(f"lane changes: {len(changes)} raw, {len(kept)} kept after track checks")

    OUT.mkdir(parents=True, exist_ok=True)
    prefix = args.prefix or args.video.stem
    rows = []
    for shift, ev in kept[:args.max_clips]:
        stem = OUT / f"{prefix}_t{ev['time_s']:07.1f}s_id{ev['track_id']}"
        render(args.video, scene, ev, hist, all_boxes, fps, stem)
        rows.append({"clip": stem.with_suffix(".mp4").name, "video": args.video.name, "time_s": ev["time_s"],
                     "track_id": ev["track_id"], "vehicle": ev["object_class"], "from_lane": ev["details"]["from_lane"],
                     "to_lane": ev["details"]["to_lane"], "sideways_shift_lane_widths": round(shift, 2)})
    index = OUT / "lane_change_index.csv"
    old = [r for r in csv.DictReader(open(index))] if index.is_file() else []
    old = [r for r in old if r["video"] != args.video.name]
    with open(index, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]) if rows else ["clip"])
        writer.writeheader()
        writer.writerows(old + rows)
    print(f"wrote {len(rows)} clips to {OUT}")


if __name__ == "__main__":
    main()
