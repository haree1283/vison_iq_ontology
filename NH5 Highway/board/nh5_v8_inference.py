#!/usr/bin/env python3
"""NH5 Highway -- full video test for the board (Rubik Pi) or any PC, in ONE file:
detections (vehicles, people, potholes, road work, accident + fire alerts) AND number-plate numbers.

It is the project's standard video test (scripts/v6/test_videos.sh) merged into one file with the logic unchanged:
  Part 1  detections   = scripts/v6/video_infer.py   : NH5 v8 model + ByteTrack; per-class confidence (0.30,
                         accident/fire 0.50); one class per tracked vehicle; accident/fire ALERT only when present
                         in >= 8 of the last 15 frames; annotated video + summary.json (counts, alerts, stability)
  Part 2  plate crops  = scripts/v6/plates_pipeline.py: plates tracked, crop saved every 3rd frame, raw PaddleOCR
  Part 3  plate numbers= scripts/v6/plates_refine.py + scripts/v8/indian_plate.py: 8 sharpest crops per plate ->
                         clarity filter (upscale, denoise, deskew, CLAHE, sharpen), two-line plates read line by
                         line -> INDIAN plates only; CONFIRMED when >= 2 frames agree (mean OCR conf >= 0.85,
                         best >= 0.93); near-identical readings merged; everything else rejected with the reason

Usage (board, INT8 model on CPU):
  python3 nh5_v8_inference.py --model nh5_v8_int8.onnx --out results video1.mp4 [video2.mp4 ...]
Options: --device 0 (NVIDIA GPU)   --max-frames 0 (whole video; default 900 like the project test)
         --plates-only / --detections-only

Output:
  results/annotated/<video>/<video>.mp4    video with all detections, track ids, ACCIDENT / FIRE alert banner
  results/annotated/<video>/summary.json   objects per class, alert frames, stability (flicker / jitter)
  results/plates/<video>/plates_unique.txt confirmed plate numbers (+ unique/<PLATE>.png clean images)
  results/plates/all_plates_unique.txt     all videos together
  speed (fps) printed for each part

Requirements: numpy, opencv-python, ultralytics, onnxruntime (for .onnx), paddleocr + paddlepaddle
"""
import re
import cv2
import numpy as np

# state / UT codes (TG added 2024 for Telangana alongside TS; OD alongside OR; LA for Ladakh)
STATES = set("AN AP AR AS BR CG CH DD DL DN GA GJ HP HR JH JK KA KL LA LD MH ML MN MP MZ NL OD OR PB PY RJ SK "
             "TG TN TR TS UK UP WB".split())
TO_LET = {"0": "O", "1": "I", "2": "Z", "4": "A", "5": "S", "6": "G", "7": "T", "8": "B"}
TO_DIG = {"O": "0", "Q": "0", "D": "0", "U": "0", "I": "1", "L": "1", "J": "1", "Z": "2", "S": "5", "B": "8",
          "G": "6", "A": "4", "T": "7"}
MAX_FIXES = 2  # never "repair" more than 2 characters: more than that means it wasn't a plate
STANDARD = re.compile(r"^([A-Z]{2})(\d{1,2})([A-Z]{1,3})(\d{4})$")  # TS07HA3898, DL3CAB1234
BHARAT = re.compile(r"^(\d{2})BH(\d{4})([A-Z]{1,2})$")               # 22BH1234AA
TEXT = re.compile(r"[^A-Z0-9]")


def _fit(t, tmpl):
    """Force t onto a letter/digit template (L/D/literal); returns (text, fixes) or None."""
    out, fixes = [], 0
    for ch, k in zip(t, tmpl):
        if k == "L" and ch.isdigit():
            ch = TO_LET.get(ch, ch); fixes += 1
        elif k == "D" and ch.isalpha():
            ch = TO_DIG.get(ch, ch); fixes += 1
        elif k not in "LD" and ch != k:
            return None
        out.append(ch)
    return "".join(out), fixes


def _valid(p):
    m = STANDARD.match(p)
    if m:
        state, dist, _, num = m.groups()
        if state not in STATES or num == "0000" or int(dist) == 0:
            return False
        return len(dist) == 2 or state == "DL"  # only Delhi uses a 1-digit district (DL3CAB1234)
    m = BHARAT.match(p)
    return bool(m) and 21 <= int(m.group(1)) <= 40 and m.group(2) != "0000"


def normalize(raw):
    """OCR text -> (indian_plate, fixes) or None. Also tolerates one stray character at either edge (IND strip)."""
    t = TEXT.sub("", raw.upper())
    t = t[3:] if t.startswith("IND") and len(t) > 11 else t
    best = None
    for cand in {t, t[1:], t[:-1]} if len(t) >= 10 else {t}:
        n = len(cand)
        tmpls = []
        for dd in (2, 1):
            sl = n - 2 - dd - 4
            if 1 <= sl <= 3:
                tmpls.append("LL" + "D" * dd + "L" * sl + "DDDD")
        if n in (9, 10):
            tmpls.append("DDBHDDDD" + "L" * (n - 8))
        for tm in tmpls:
            r = _fit(cand, tm)
            if r and r[1] <= MAX_FIXES and _valid(r[0]):
                edge = int(cand != t)
                if best is None or r[1] + edge < best[1]:
                    best = (r[0], r[1] + edge)
    return best


def _deskew(g):
    """Straighten a tilted plate using the angle of its dark text strokes (only corrects 2-20 degrees)."""
    _, bw = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    pts = cv2.findNonZero(bw)
    if pts is None or len(pts) < 50:
        return None
    (_, _), (w, h), ang = cv2.minAreaRect(pts)
    if w < h:
        ang -= 90
    if abs(ang) < 2 or abs(ang) > 20:
        return None
    M = cv2.getRotationMatrix2D((g.shape[1] / 2, g.shape[0] / 2), ang, 1.0)
    return M


def enhance(crop, target_h=128):
    """Clear plate image: upscale -> denoise -> deskew -> contrast (CLAHE) -> sharpen. Returns BGR."""
    h, w = crop.shape[:2]
    s = max(1.0, target_h / max(h, 1))
    img = cv2.resize(crop, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC) if s > 1 else crop.copy()
    img = cv2.fastNlMeansDenoisingColored(img, None, 5, 5, 7, 21)
    M = _deskew(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    if M is not None:
        img = cv2.warpAffine(img, M, (img.shape[1], img.shape[0]), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    lab[:, :, 0] = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 8)).apply(lab[:, :, 0])
    img = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    blur = cv2.GaussianBlur(img, (0, 0), 1.5)
    return cv2.addWeighted(img, 1.7, blur, -0.7, 0)


def sharpness(img):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    return float(cv2.Laplacian(g, cv2.CV_64F).var())


def ocr_lines(ocr, img):
    """PaddleOCR -> (joined text in reading order, mean score). Two-line plates (bikes) read top line first."""
    try:
        res = ocr.predict(img)
    except Exception:
        return "", 0.0
    items = []
    for r in res:
        polys = r.get("rec_polys", r.get("dt_polys", []))
        for i, (t, c) in enumerate(zip(r.get("rec_texts", []), r.get("rec_scores", []))):
            if not t.strip():
                continue
            p = np.asarray(polys[i]) if i < len(polys) else np.zeros((4, 2))
            items.append((float(p[:, 1].mean()), float(p[:, 0].min()), float(p[:, 1].max() - p[:, 1].min()), t, float(c)))
    if not items:
        return "", 0.0
    lh = np.median([it[2] for it in items]) or 1.0
    items.sort(key=lambda it: (round(it[0] / (0.6 * lh)), it[1]))  # same row if centres within ~0.6 line height
    return "".join(it[3] for it in items), float(np.mean([it[4] for it in items]))


def _pad(img, frac=0.08):
    """Margin around the plate so characters touching the crop edge (leading T, last digit) are not lost."""
    p = max(4, int(frac * img.shape[0]))
    return cv2.copyMakeBorder(img, p, p, p, p, cv2.BORDER_REPLICATE)


def _split_rows(img):
    """Two-line plate (bike/auto): split at the emptiest row between the text lines -> (top, bottom) or None."""
    h, w = img.shape[:2]
    if w / max(h, 1) > 2.6:                       # wide = single-line plate
        return None
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    _, bw = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    if bw.mean() > 127:                           # light text on dark plate: invert so text is "ink"
        bw = 255 - bw
    prof = bw[:, int(0.1 * w):int(0.9 * w)].mean(axis=1)
    lo, hi = int(0.35 * h), int(0.65 * h)
    cut = lo + int(np.argmin(prof[lo:hi]))
    return img[:cut], img[cut:]


def _up(img, target_h=128):
    s = max(1.0, target_h / max(img.shape[0], 1))
    return cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC) if s > 1 else img


def read_plate(ocr, crop):
    """One crop -> list of (indian_plate, ocr_score, fixes) from the enhanced and raw images; two-line plates are
    also read line by line (top line first)."""
    out = []
    for img in (enhance(crop), _up(crop)):
        texts = [ocr_lines(ocr, _pad(img))]
        rows = _split_rows(img)
        if rows:
            (t1, s1), (t2, s2) = ocr_lines(ocr, _pad(_up(rows[0], 96))), ocr_lines(ocr, _pad(_up(rows[1], 96)))
            if t1 and t2:
                texts.append((t1 + t2, (s1 + s2) / 2))
        for txt, sc in texts:
            n = normalize(txt) if txt else None
            if n:
                out.append((n[0], sc, n[1]))
    return out


def edit_distance(a, b):
    d = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev, d[0] = d[0], i
        for j, cb in enumerate(b, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (ca != cb))
    return d[-1]


# ================================================================================================================
# pipeline (stage 1-2 = scripts/v6/plates_pipeline.py, stage 3 = scripts/v6/plates_refine.py)
# ================================================================================================================
import argparse, collections, glob, json, os, shutil, sys, time

EVENT = {'accident_scene', 'fire_accident'}
COLORS = {'person': (255, 120, 0), 'bicycle': (255, 0, 200), 'car': (0, 220, 0), 'motorcycle': (255, 0, 255), 'bus': (0, 255, 255), 'truck': (0, 165, 255),
          'pothole': (60, 20, 220), 'license_plate': (255, 255, 255), 'auto': (255, 255, 0), 'road_construction': (160, 0, 160),
          'accident_scene': (0, 0, 255), 'traffic_cone': (0, 215, 255), 'fire_accident': (0, 100, 255)}

GROUP = {'car', 'truck', 'bus', 'auto'}          # visually confusable vehicle types: dedupe boxes + one class per track
INVOLVED = {'car', 'truck', 'bus', 'auto', 'motorcycle', 'bicycle', 'person'}

def iou(p, q):
    ix = max(0, min(p[2], q[2]) - max(p[0], q[0])); iy = max(0, min(p[3], q[3]) - max(p[1], q[1])); i = ix * iy
    return i / ((p[2]-p[0])*(p[3]-p[1]) + (q[2]-q[0])*(q[3]-q[1]) - i + 1e-9)

def inside_frac(v, e):  # fraction of vehicle box v lying inside event box e
    ix = max(0, min(v[2], e[2]) - max(v[0], e[0])); iy = max(0, min(v[3], e[3]) - max(v[1], e[1]))
    return ix * iy / ((v[2]-v[0])*(v[3]-v[1]) + 1e-9)


def detect_video(model, path, out_dir, a):
    """Part 1 (scripts/v6/video_infer.py, unchanged): ByteTrack ids + per-class confidence + temporal voting
    for accident/fire alerts -> out_dir/<video>.mp4 annotated, returns the per-video summary."""
    os.makedirs(out_dir, exist_ok=True); names = model.names; summary = {}
    votes = collections.defaultdict(collections.Counter)   # track id -> weighted class votes (GROUP classes only)
    hist = {e: collections.deque(maxlen=a.window) for e in EVENT}
    alert = {e: False for e in EVENT}; alert_frames = {e: 0 for e in EVENT}; raw_frames = {e: 0 for e in EVENT}
    writer = None; n = 0; cls_tot = collections.Counter(); last_involved = {}; involved_total = collections.Counter()
    track_len = collections.Counter(); per_frame = []   # stability stats: frames each drawn object track lives, objects drawn per frame
    for r in model.track(path, stream=True, persist=True, tracker='bytetrack.yaml', imgsz=a.imgsz, device=a.device, conf=min(a.conf, a.acc_conf), verbose=False):
        img = r.orig_img.copy(); n += 1
        present = {e: 0.0 for e in EVENT}
        keep = []
        for b in r.boxes:
            name = names[int(b.cls)]; c = float(b.conf)
            if c < (a.acc_conf if name in EVENT else a.conf):
                continue
            if name in EVENT:
                present[name] = max(present[name], c)
            keep.append((name, c, b.xyxy[0].tolist(), int(b.id) if b.id is not None else -1))
        # class-agnostic NMS among confusable vehicle types (accident/fire boxes are exempt so they can overlap vehicles)
        keep.sort(key=lambda k: -k[1]); kept = []
        for k in keep:
            if k[0] in GROUP and any(o[0] in GROUP and iou(k[2], o[2]) > 0.6 for o in kept): continue
            kept.append(k)
        keep = kept
        # one class per tracked vehicle: weighted majority over its whole history
        for i, (name, c, bx, tid) in enumerate(keep):
            if name in GROUP and tid >= 0:
                votes[tid][name] += c
                keep[i] = (votes[tid].most_common(1)[0][0], c, bx, tid)
        for e in EVENT:
            hist[e].append(1 if present[e] > 0 else 0); raw_frames[e] += int(present[e] > 0)
            s = sum(hist[e])
            if not alert[e] and s >= a.vote: alert[e] = True
            elif alert[e] and s < a.off: alert[e] = False
            alert_frames[e] += int(alert[e])
        H_, W_ = img.shape[:2]; th = a.thickness or max(3, round(min(H_, W_) / 200)); fs = max(0.6, min(H_, W_) / 800)
        # big event boxes first (behind), then objects on top so scene-level boxes never hide vehicles
        for name, c, (x1, y1, x2, y2), tid in sorted(keep, key=lambda k: k[0] not in EVENT):
            if name in EVENT and not alert[name]:
                continue  # hide flickering event boxes until the temporal vote confirms
            col = COLORS.get(name, (0, 255, 0)); t = th * 2 if name in EVENT else th
            p1, p2 = (int(x1), int(y1)), (int(x2), int(y2))
            cv2.rectangle(img, p1, p2, col, t)
            label = f"{name}{'#'+str(tid) if tid >= 0 else ''} {c:.2f}"
            (tw, tht), bl = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, fs, max(1, th // 2))
            ty = int(y1) if int(y1) - tht - bl - 4 < 0 else int(y1) - tht - bl - 4      # keep tag inside the frame
            cv2.rectangle(img, (int(x1), ty), (int(x1) + tw + 6, ty + tht + bl + 4), col, -1)
            cv2.putText(img, label, (int(x1) + 3, ty + tht + 1), cv2.FONT_HERSHEY_SIMPLEX, fs, (0, 0, 0), max(1, th // 2), cv2.LINE_AA)
            cls_tot[name] += 1
            if name not in EVENT and tid >= 0: track_len[tid] += 1
        per_frame.append(sum(1 for k in keep if k[0] not in EVENT))
        acc_boxes = [k[2] for k in keep if k[0] == 'accident_scene']
        if acc_boxes:  # which vehicles / people sit inside the accident region right now
            inv = collections.Counter(k[0] for k in keep if k[0] in INVOLVED and any(inside_frac(k[2], ab) > 0.5 for ab in acc_boxes))
            if inv: last_involved = dict(inv)
        for k, e in enumerate(sorted(EVENT)):
            if alert[e]:
                txt = f"{e.upper()} ALERT"
                if e == 'accident_scene' and last_involved:
                    txt += ": " + ", ".join(f"{v} {c}" for c, v in last_involved.items())
                    involved_total.update(last_involved)
                cv2.putText(img, txt, (10, 30 + 30 * k), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 3)
        if writer is None:
            h, w = img.shape[:2]
            writer = cv2.VideoWriter(os.path.join(out_dir, os.path.splitext(os.path.basename(path))[0] + '.mp4'), cv2.VideoWriter_fourcc(*'mp4v'), 30, (w, h))
        writer.write(img)
    if writer: writer.release()
    mean_cnt = sum(per_frame) / max(1, len(per_frame))
    stability = {'tracks': len(track_len),
                 'mean_track_len': round(sum(track_len.values()) / max(1, len(track_len)), 1),
                 'short_tracks_pct': round(100 * sum(1 for v in track_len.values() if v <= 5) / max(1, len(track_len)), 1),
                 'count_jitter_pct': round(100 * sum(abs(x - y) for x, y in zip(per_frame, per_frame[1:])) / max(1, len(per_frame) - 1) / max(1e-9, mean_cnt), 1) if mean_cnt else 0.0}
    summary[os.path.basename(path)] = {'frames': n, 'raw_event_frames': raw_frames, 'alert_frames': alert_frames, 'objects_drawn': dict(cls_tot), 'accident_involved_frames': dict(involved_total), 'stability': stability}
    print(os.path.basename(path), summary[os.path.basename(path)], flush=True)
    json.dump(summary, open(os.path.join(out_dir, 'summary.json'), 'w'), indent=1)
    return summary[os.path.basename(path)]

PLATE_CLASS = 7          # license_plate in the NH5 v8 model
SAVE_EVERY = 3           # save a crop of each tracked plate every 3rd frame
MAX_PER_TRACK = 60       # at most 60 crops per plate track
DET_CONF = 0.30          # plate detection confidence
TOPK = 8                 # sharpest crops per track that get OCR'd in the refined reading
MIN_CROPS = 2            # different frames that must agree on the same plate
MIN_MEAN = 0.85          # mean OCR confidence of the agreeing reads
MIN_BEST = 0.93          # at least one agreeing read this confident
MIN_H = 12               # crops shorter than this (px) are too small to read reliably


def _iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0, min(a[3], b[3]) - max(a[1], b[1])); i = ix * iy
    return i / (((a[2] - a[0]) * (a[3] - a[1])) + ((b[2] - b[0]) * (b[3] - b[1])) - i + 1e-9)


def _raw_read(ocr, img):
    """stage 2: plain PaddleOCR of one saved crop (upscaled to 96 px high) -> (text, mean conf)"""
    h = img.shape[0]; s = max(1.0, 96 / max(h, 1))
    if s > 1:
        img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)
    try:
        res = ocr.predict(img)
    except Exception:
        return "", 0.0
    t, c = [], []
    for r in res:
        t += list(r.get("rec_texts", [])); c += list(r.get("rec_scores", []))
    return ("".join(t), float(np.mean(c))) if t else ("", 0.0)


def capture(det, path, root, imgsz, device, maxf):
    """stage 1: detect + track plates, save crops -> root/<video>/raw/crops. Returns (video name, frames, secs)."""
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", os.path.splitext(os.path.basename(path))[0])[:60]
    cdir = f"{root}/{name}/raw/crops"; os.makedirs(cdir, exist_ok=True)
    per_track = collections.Counter(); n = 0; saved = 0; pseudo = {}; next_pid = 9000; t0 = time.perf_counter()
    for r in det.track(path, stream=True, persist=True, tracker="bytetrack.yaml", imgsz=imgsz, conf=DET_CONF,
                       classes=[PLATE_CLASS], device=device, verbose=False):
        n += 1
        if maxf and n > maxf:
            break
        H, W = r.orig_img.shape[:2]
        for b in r.boxes:
            tid = int(b.id) if b.id is not None else -1
            x1, y1, x2, y2 = [int(v) for v in b.xyxy[0].tolist()]
            if tid < 0:  # ByteTrack gave no id (short-lived plate): fall back to a simple IoU association
                cands = [(_iou((x1, y1, x2, y2), bx), pid) for pid, (bx, lf) in pseudo.items() if n - lf <= 10]
                best = max(cands, default=(0, None))
                if best[0] > 0.2:
                    tid = best[1]
                else:
                    tid = next_pid; next_pid += 1
                pseudo[tid] = ((x1, y1, x2, y2), n)
            if n % SAVE_EVERY or per_track[tid] >= MAX_PER_TRACK:
                continue
            x1, y1, x2, y2 = max(0, x1 - 3), max(0, y1 - 3), min(W, x2 + 3), min(H, y2 + 3)
            if x2 - x1 < 20 or y2 - y1 < 8:
                continue
            cv2.imwrite(f"{cdir}/id{tid:04d}_f{n:05d}_c{float(b.conf):.2f}.png", r.orig_img[y1:y2, x1:x2])
            per_track[tid] += 1; saved += 1
    secs = time.perf_counter() - t0
    print(f"[stage1] {name}: {n} frames in {secs:.1f}s ({n / max(secs, 1e-9):.1f} fps), "
          f"{saved} crops, {len(per_track)} plate tracks", flush=True)
    return name, n, secs


def raw_ocr(ocr, vdir):
    """stage 2: PaddleOCR on every saved crop -> raw/plates_ocr.txt"""
    rows = []
    for f in sorted(glob.glob(f"{vdir}/raw/crops/*.png")):
        txt, sc = _raw_read(ocr, cv2.imread(f)); rows.append((os.path.basename(f), TEXT.sub("", txt.upper()), sc))
    with open(f"{vdir}/raw/plates_ocr.txt", "w") as fh:
        fh.write("# crop_file\ttext\tocr_conf\tvalid_indian_format\n")
        for fn, t, sc in rows:
            fh.write(f"{fn}\t{t}\t{sc:.3f}\t{int(normalize(t) is not None)}\n")
    return len(rows)


def refine(ocr, vdir):
    """stage 3: Indian-only confirmed plates -> plates_unique.txt, unique/, raw/plates_rejected.txt"""
    name = os.path.basename(vdir.rstrip("/")); RAW = f"{vdir}/raw"
    tracks = collections.defaultdict(list)
    for f in glob.glob(f"{RAW}/crops/*.png"):
        tracks[os.path.basename(f).split("_")[0]].append(f)
    rejected = []
    votes = collections.defaultdict(dict)                    # plate -> {frame: (score, crop_file)} across the video
    for tid, files in sorted(tracks.items()):
        crops = [(f, cv2.imread(f)) for f in files]
        crops = [(f, c) for f, c in crops if c is not None and c.shape[0] >= MIN_H]
        if not crops:
            rejected.append((tid, "", 0, 0.0, "crops too small")); continue
        crops = sorted(crops, key=lambda fc: sharpness(fc[1]), reverse=True)[:TOPK]
        got = False
        for f, c in crops:
            reads = [(plate, sc * (1.0 - 0.05 * fixes)) for plate, sc, fixes in read_plate(ocr, c)]
            if not reads:
                continue
            plate, sc = max(reads, key=lambda r: r[1])       # one vote per frame: its most confident reading
            frame = os.path.basename(f).split("_")[1]
            if sc > votes[plate].get(frame, (0.0, ""))[0]:
                votes[plate][frame] = (sc, f)
            got = True
        if not got:
            rejected.append((tid, "", 0, 0.0, "no Indian-format reading"))
    confirmed = []
    for plate, fr in votes.items():
        scores = [v[0] for v in fr.values()]
        n, mean, best = len(scores), sum(scores) / len(scores), max(scores)
        if n < MIN_CROPS or mean < MIN_MEAN or best < MIN_BEST:
            why = f"only {n} frame(s) agree" if n < MIN_CROPS else f"low confidence (mean {mean:.2f}, best {best:.2f})"
            rejected.append(("-", plate, n, round(mean, 3), why)); continue
        confirmed.append(dict(text=plate, frames=n, conf=round(mean, 3), crop=max(fr.values())[1], tracks=[plate]))
    # one entry per real plate: readings 1-2 characters apart in the same video are misreads of the same plate
    merged = []
    for c in sorted(confirmed, key=lambda c: (c["frames"], c["conf"]), reverse=True):
        for k in merged:
            if abs(len(k["text"]) - len(c["text"])) <= 1 and edit_distance(k["text"], c["text"]) <= 2:
                k["frames"] += c["frames"]; k["tracks"] += c["tracks"]
                rejected.append((c["tracks"][0], c["text"], c["frames"], c["conf"], f"merged into {k['text']}")); break
        else:
            merged.append(c)
    ud = f"{vdir}/unique"; shutil.rmtree(ud, ignore_errors=True); os.makedirs(ud)
    summary = []
    with open(f"{vdir}/plates_unique.txt", "w") as fh:
        fh.write("# plate_text\tocr_conf\tstatus\tframes_agreeing\tclear_image\toriginal_crop\n")
        for k in merged:
            crop = cv2.imread(k["crop"])
            cv2.imwrite(f"{ud}/{k['text']}.png", enhance(crop))
            cv2.imwrite(f"{ud}/{k['text']}_original.png", crop)
            fh.write(f"{k['text']}\t{k['conf']:.3f}\tVALID\t{k['frames']}\tunique/{k['text']}.png\tunique/{k['text']}_original.png\n")
            summary.append((name, k["text"], k["conf"], "VALID", k["frames"], f"{name}/unique/{k['text']}.png"))
    with open(f"{RAW}/plates_rejected.txt", "w") as fh:
        fh.write("# track\tbest_indian_reading\tframes_agreeing\tmean_conf\treason\n")
        for r in rejected:
            fh.write("\t".join(map(str, r)) + "\n")
    print(f"[stage3] {name[:45]:45s} plate_tracks={len(tracks):3d} confirmed={len(merged):3d} "
          f"rejected={len(rejected):3d}  {', '.join(k['text'] for k in merged)}", flush=True)
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("videos", nargs="+", help="video files")
    ap.add_argument("--model", required=True, help="nh5_v8_int8.onnx (board), nh5_v8_fp32.onnx or nh5_v8_final_ep100.pt")
    ap.add_argument("--out", default="nh5_results", help="output folder (default ./nh5_results)")
    ap.add_argument("--imgsz", type=int, default=960)
    ap.add_argument("--device", default="cpu", help="cpu (board) or 0 for the first NVIDIA GPU")
    ap.add_argument("--max-frames", type=int, default=int(os.environ.get("MAXF", 900)),
                    help="frames per video for the plate part (default 900 = project test; 0 = whole video)")
    ap.add_argument("--conf", type=float, default=0.30, help="default class confidence (detections)")
    ap.add_argument("--acc-conf", type=float, default=0.50, help="accident_scene / fire_accident confidence")
    ap.add_argument("--window", type=int, default=15)
    ap.add_argument("--vote", type=int, default=8, help="frames in window needed to raise an alert")
    ap.add_argument("--off", type=int, default=3, help="alert clears when fewer than this many frames in window")
    ap.add_argument("--thickness", type=int, default=0, help="box line thickness (0 = auto)")
    ap.add_argument("--plates-only", action="store_true")
    ap.add_argument("--detections-only", action="store_true")
    a = ap.parse_args()

    from ultralytics import YOLO
    if not a.plates_only:
        print("== part 1/3 detections: tracking + per-class conf + accident/fire alerts ==", flush=True)
        for v in a.videos:
            model = YOLO(a.model, task="detect")                  # fresh tracker per video
            name = os.path.splitext(os.path.basename(v))[0]; t0 = time.perf_counter()
            s = detect_video(model, v, os.path.join(a.out, "annotated", name), a)
            secs = time.perf_counter() - t0
            print(f"{name}: {s['frames']} frames, {s['frames'] / max(secs, 1e-9):.1f} fps | objects {s['objects_drawn']} "
                  f"| ALERT frames {s['alert_frames']} | stability {s.get('stability')}", flush=True)
    if a.detections_only:
        return
    from paddleocr import PaddleOCR
    det = YOLO(a.model, task="detect")
    ocr = PaddleOCR(use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False,
                    lang="en", enable_mkldnn=False)
    root = os.path.join(a.out, "plates"); os.makedirs(root, exist_ok=True)
    summary = []
    print("== part 2-3/3 number plates: crops + PaddleOCR + refined Indian-plate reading ==", flush=True)
    for v in a.videos:
        t0 = time.perf_counter()
        name, frames, det_secs = capture(det, v, root, a.imgsz, a.device, a.max_frames)
        n = raw_ocr(ocr, f"{root}/{name}")
        print(f"[stage2] {name}: OCR'd {n} crops -> {root}/{name}/raw/plates_ocr.txt", flush=True)
        summary += refine(ocr, f"{root}/{name}")
        total = time.perf_counter() - t0
        print(f"[speed ] {name}: {frames} frames, plate detection+tracking {frames / max(det_secs, 1e-9):.1f} fps, "
              f"whole plate pipeline {total:.1f}s ({frames / max(total, 1e-9):.1f} fps)\n", flush=True)
    with open(f"{root}/all_plates_unique.txt", "w") as fh:
        fh.write("# video\tplate_text\tocr_conf\tstatus\tframes_agreeing\tclear_image\n")
        for r in summary:
            fh.write("\t".join(map(str, r)) + "\n")
    print(f"results: {os.path.abspath(a.out)}  (annotated/ = detections, plates/ = plate numbers)")


if __name__ == "__main__":
    main()
