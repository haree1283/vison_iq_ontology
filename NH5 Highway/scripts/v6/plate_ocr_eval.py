"""Detect license plates with YOLO (+ByteTrack), read them with PaddleOCR, report accuracy-proxy stats. Test-only: never writes into datasets/."""
import os, sys, json, re, time, collections
import cv2, numpy as np
from ultralytics import YOLO
from paddleocr import PaddleOCR

MODEL = "runs/detect/runs/v3_13class_100ep_ft2/weights/best.pt"
OUT = "runs/plate_ocr_eval"
VIDS = sys.argv[1:]
MAXF = 900; OCR_EVERY = 3
os.makedirs(OUT, exist_ok=True)
det = YOLO(MODEL)
ocr = PaddleOCR(use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False, lang="en", enable_mkldnn=False)
PLATE = re.compile(r"^[A-Z]{2}\d{1,2}[A-Z]{1,3}\d{4}$")  # Indian format e.g. AP39UB1234
clean = lambda s: re.sub(r"[^A-Z0-9]", "", s.upper())

def read(crop):
    h, w = crop.shape[:2]
    s = max(1.0, 96 / max(h, 1))
    if s > 1: crop = cv2.resize(crop, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)
    try:
        res = ocr.predict(crop)
    except Exception as e:
        return "", 0.0
    txts, scs = [], []
    for r in res:
        txts += list(r.get("rec_texts", [])); scs += list(r.get("rec_scores", []))
    if not txts: return "", 0.0
    return "".join(txts), float(np.mean(scs))

allsum = {}
for path in VIDS:
    name = os.path.splitext(os.path.basename(path))[0]
    tracks = collections.defaultdict(list); nplate_frames = 0; n = 0; sizes = []; writer = None; t0 = time.time()
    for r in det.track(path, stream=True, persist=True, tracker="bytetrack.yaml", imgsz=960, conf=0.30, classes=[7], verbose=False):
        n += 1
        if n > MAXF: break
        img = r.orig_img.copy(); H, W = img.shape[:2]
        if len(r.boxes): nplate_frames += 1
        for b in r.boxes:
            tid = int(b.id) if b.id is not None else -1
            x1, y1, x2, y2 = [int(v) for v in b.xyxy[0].tolist()]
            x1, y1 = max(0, x1 - 3), max(0, y1 - 3); x2, y2 = min(W, x2 + 3), min(H, y2 + 3)
            cw, ch = x2 - x1, y2 - y1; sizes.append((cw, ch))
            label = ""
            if tid >= 0 and n % OCR_EVERY == 0 and cw >= 20 and ch >= 8:
                txt, sc = read(img[y1:y2, x1:x2])
                tracks[tid].append((n, clean(txt), sc, cw, ch))
            if tid in tracks and tracks[tid]:
                label = tracks[tid][-1][1]
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 255), 2)
            cv2.putText(img, f"#{tid} {label}", (x1, max(14, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        if writer is None:
            writer = cv2.VideoWriter(f"{OUT}/{name}.mp4", cv2.VideoWriter_fourcc(*"mp4v"), 30, (W, H))
        writer.write(img)
    if writer: writer.release()
    reads = [(t, x) for t, L in tracks.items() for x in L if x[1]]
    valid = [(t, x) for t, x in reads if PLATE.match(x[1])]
    stab = []
    for t, L in tracks.items():
        txts = [x[1] for x in L if x[1]]
        if len(txts) >= 3:
            top = collections.Counter(txts).most_common(1)[0][1]; stab.append(top / len(txts))
    best = {}
    for t, x in reads:
        if PLATE.match(x[1]): best.setdefault(t, collections.Counter())[x[1]] += 1
    s = dict(frames=n - 1 if n > MAXF else n, frames_with_plate=nplate_frames, plate_tracks=len(tracks),
             median_plate_px=(int(np.median([w for w, h in sizes])), int(np.median([h for w, h in sizes]))) if sizes else None,
             ocr_reads=len(reads), mean_ocr_conf=round(float(np.mean([x[2] for _, x in reads])), 3) if reads else None,
             format_valid_reads=len(valid), format_valid_pct=round(100 * len(valid) / max(1, len(reads)), 1),
             tracks_with_valid_plate=len(best), mean_text_consistency_per_track=round(float(np.mean(stab)), 3) if stab else None,
             sample_valid={str(t): c.most_common(2) for t, c in list(best.items())[:6]},
             sample_raw=[x[1] for _, x in reads[:8]], secs=round(time.time() - t0))
    allsum[name] = s; print(name, json.dumps(s), flush=True)
    json.dump(allsum, open(f"{OUT}/summary_{int(time.time())}.json", "w"), indent=1)
