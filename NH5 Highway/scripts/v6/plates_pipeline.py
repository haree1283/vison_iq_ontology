"""Stage 1: detect plates (YOLO+ByteTrack) and save crops to runs/plates/<video>/crops/.
Stage 2: run PaddleOCR on the saved crop images and write .txt results. Test-only output; never touches datasets/."""
import os, sys, re, glob, collections, cv2, numpy as np
from ultralytics import YOLO
from paddleocr import PaddleOCR

MODEL = os.environ.get("MODEL", "runs/detect/runs/v3_13class_100ep_ft2/weights/best.pt")
ROOT = os.environ.get("PLATES_ROOT", "runs/plates"); SAVE_EVERY = 3; MAX_PER_TRACK = 60; MAXF = int(os.environ.get("MAXF", 900))
PLATE = re.compile(r"^[A-Z]{2}\d{1,2}[A-Z]{1,3}\d{4}$")
clean = lambda s: re.sub(r"[^A-Z0-9]", "", s.upper())
det = YOLO(MODEL)
ocr = PaddleOCR(use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False, lang="en", enable_mkldnn=False)

def read(img):
    h = img.shape[0]; s = max(1.0, 96 / max(h, 1))
    if s > 1: img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)
    try: res = ocr.predict(img)
    except Exception: return "", 0.0
    t, c = [], []
    for r in res: t += list(r.get("rec_texts", [])); c += list(r.get("rec_scores", []))
    return ("".join(t), float(np.mean(c))) if t else ("", 0.0)

def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0, min(a[3], b[3]) - max(a[1], b[1])); i = ix * iy
    return i / (((a[2] - a[0]) * (a[3] - a[1])) + ((b[2] - b[0]) * (b[3] - b[1])) - i + 1e-9)

all_lines = []
for path in sys.argv[1:]:
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", os.path.splitext(os.path.basename(path))[0])[:60]
    RAW = f"{ROOT}/{name}/raw"; cdir = f"{RAW}/crops"; os.makedirs(cdir, exist_ok=True)
    per_track = collections.Counter(); n = 0; saved = 0; pseudo = {}; next_pid = 9000
    for r in det.track(path, stream=True, persist=True, tracker="bytetrack.yaml", imgsz=int(os.environ.get("IMGSZ", 960)), conf=0.30, classes=[7], verbose=False):
        n += 1
        if n > MAXF: break
        H, W = r.orig_img.shape[:2]
        for b in r.boxes:
            tid = int(b.id) if b.id is not None else -1
            x1, y1, x2, y2 = [int(v) for v in b.xyxy[0].tolist()]
            if tid < 0:  # ByteTrack gave no id (short-lived plate): fall back to a simple IoU association
                cands = [(iou((x1, y1, x2, y2), bx), pid) for pid, (bx, lf) in pseudo.items() if n - lf <= 10]
                best = max(cands, default=(0, None))
                if best[0] > 0.2: tid = best[1]
                else: tid = next_pid; next_pid += 1
                pseudo[tid] = ((x1, y1, x2, y2), n)
            if n % SAVE_EVERY or per_track[tid] >= MAX_PER_TRACK: continue
            x1, y1, x2, y2 = max(0, x1 - 3), max(0, y1 - 3), min(W, x2 + 3), min(H, y2 + 3)
            if x2 - x1 < 20 or y2 - y1 < 8: continue
            cv2.imwrite(f"{cdir}/id{tid:04d}_f{n:05d}_c{float(b.conf):.2f}.png", r.orig_img[y1:y2, x1:x2])
            per_track[tid] += 1; saved += 1
    print(f"[stage1] {name}: {saved} crops, {len(per_track)} tracks", flush=True)
    # stage 2: OCR the saved crop images
    rows = []
    for f in sorted(glob.glob(f"{cdir}/*.png")):
        txt, sc = read(cv2.imread(f)); rows.append((os.path.basename(f), clean(txt), sc))
    with open(f"{RAW}/plates_ocr.txt", "w") as fh:
        fh.write("# crop_file\ttext\tocr_conf\tvalid_indian_format\n")
        for fn, t, sc in rows: fh.write(f"{fn}\t{t}\t{sc:.3f}\t{int(bool(PLATE.match(t)))}\n")
    by = collections.defaultdict(list)
    for fn, t, sc in rows: by[fn.split("_")[0]].append((t, sc))
    with open(f"{RAW}/plates_per_track.txt", "w") as fh:
        fh.write("# track\tconsensus_text\tvotes/reads\tvalid_format\n")
        for tid, L in sorted(by.items()):
            valid = [t for t, s in L if PLATE.match(t)]
            pool = valid or [t for t, s in L if t]
            if pool:
                best, cnt = collections.Counter(pool).most_common(1)[0]
                fh.write(f"{tid}\t{best}\t{cnt}/{len(L)}\t{int(bool(valid))}\n"); all_lines.append(f"{name}\t{tid}\t{best}\t{cnt}/{len(L)}\t{int(bool(valid))}")
            else: fh.write(f"{tid}\t\t0/{len(L)}\t0\n")
    print(f"[stage2] {name}: OCR'd {len(rows)} crops -> {RAW}/plates_ocr.txt", flush=True)
with open(f"{ROOT}/all_plates_summary.txt", "a") as fh:
    fh.write("# video\ttrack\tconsensus_text\tvotes/reads\tvalid_format\n"); fh.write("\n".join(all_lines) + "\n")
