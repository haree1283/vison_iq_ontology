"""Indian number-plate reading with EasyOCR on the plate crops saved by scripts/v6/plates_pipeline.py.

Per plate track: sharpest crops -> 'clear plate' filter (straighten the plate to a flat rectangle, upscale,
denoise, CLAHE contrast, unsharp mask) -> EasyOCR (A-Z0-9 only, one- and two-line plates) on two filter variants ->
strict Indian format with position-aware character fixes -> per-character vote across frames -> accept only if
at least MIN_AGREE different frames agree. Everything that fails a check goes to rejected.txt with the reason.

Usage: python3 scripts/v8/plates_easyocr.py <run_dir>     e.g. runs/video_tests/v8_ep100
OCR_ENGINE=easyocr|paddle|both (default easyocr; both = a plate is accepted only when both engines read it).
Writes <run_dir>/plates/<video>/ocr_<engine>/{plates.txt, rejected.txt, clear/}, <run_dir>/plates/all_plates_ocr_<engine>.txt.
Test-only: reads crops, never touches datasets/."""
import collections, glob, os, re, shutil, sys
import cv2, numpy as np
import easyocr

TOPK = 8                    # sharpest crops per track that get OCR'd
MIN_DET_CONF = 0.30         # YOLO plate confidence stored in the crop file name
MIN_H, MIN_W = 14, 40       # px: smaller crops have too few pixels per character to read reliably
MIN_OCR_CONF = 0.40         # EasyOCR confidence of a read that may vote
MIN_MEAN_CONF = 0.50        # mean confidence of the reads supporting an accepted plate
MIN_AGREE = 2               # different frames whose read matches the final plate (<=1 char apart, 1 exact)

STATES = set("AN AP AR AS BR CH CG DD DL DN GA GJ HP HR JH JK KA KL LA LD MH ML MN MP MZ NL OD OR PB PY RJ SK "
             "TN TR TS UK UP WB".split())
TO_LET = {"0": "O", "1": "I", "5": "S", "8": "B", "2": "Z", "6": "G", "4": "A", "7": "T"}
# digit positions: an open-top '4' in plate fonts is read as 'L'; I/J/| as 1
TO_DIG = {"O": "0", "Q": "0", "D": "0", "U": "0", "I": "1", "J": "1", "L": "4", "S": "5", "B": "8", "Z": "2",
          "G": "6", "A": "4", "T": "7"}
STD = re.compile(r"^([A-Z]{2})(\d{2})([A-Z]{1,3})(\d{4})$")   # TS 07 HX 5831
BH = re.compile(r"^(\d{2})BH(\d{4})([A-Z]{1,2})$")             # 22 BH 1234 AB (Bharat series)
ALLOW = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

ENGINE = os.environ.get("OCR_ENGINE", "easyocr")    # easyocr | paddle | both (both engines must agree)
reader = easyocr.Reader(["en"], gpu=True, verbose=False) if ENGINE in ("easyocr", "both") else None
paddle = None
if ENGINE in ("paddle", "both"):
    from paddleocr import PaddleOCR
    paddle = PaddleOCR(use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False,
                       lang="en", enable_mkldnn=False)


def fix_to_template(t, tmpl):
    """Coerce t to a letter/digit template (L/D/fixed chars); returns (text, substitutions) or None."""
    if len(t) != len(tmpl):
        return None
    out, subs = [], 0
    for ch, k in zip(t, tmpl):
        if k == "L" and ch.isdigit():
            if ch not in TO_LET: return None
            ch, subs = TO_LET[ch], subs + 1
        elif k == "D" and ch.isalpha():
            if ch not in TO_DIG: return None
            ch, subs = TO_DIG[ch], subs + 1
        elif k not in "LD" and ch != k:
            return None
        out.append(ch)
    return "".join(out), subs


def to_indian(raw):
    """Strict Indian plate: valid state code, LL DD L{1-3} DDDD (or BH series); at most 2 corrected chars."""
    t = re.sub(r"[^A-Z0-9]", "", raw.upper())
    if t.startswith("IND"): t = t[3:]            # the "IND" strip on HSRP plates
    best = None
    for cand in {t, t[1:], t[:-1]} if len(t) >= 10 else {t}:   # tolerate one stray edge character
        for tmpl in ["LLDD" + "L" * s + "DDDD" for s in (1, 2, 3)] + ["DDBHDDDD" + "L" * s for s in (1, 2)]:
            r = fix_to_template(cand, tmpl)
            if not r: continue
            txt, subs = r
            ok = (STD.match(txt) and txt[:2] in STATES and txt[2:4] != "00" and txt[-4:] != "0000") or BH.match(txt)
            if ok and subs <= 2 and (best is None or subs < best[1]):
                best = (txt, subs)
    return best


def sharpness(img):
    return cv2.Laplacian(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()


def upscale(img, h=128):
    s = max(1.0, h / img.shape[0])
    return cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC) if s > 1 else img.copy()


def rectify(img):
    """Find the plate's bright rectangle and warp it flat (fixes tilt/perspective); returns img if none found."""
    g = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    bw = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    cs = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]
    if not cs: return img
    c = max(cs, key=cv2.contourArea)
    H, W = img.shape[:2]
    if cv2.contourArea(c) < 0.30 * H * W: return img
    (cx, cy), (rw, rh), ang = cv2.minAreaRect(c)
    if rw < rh: rw, rh, ang = rh, rw, ang - 90
    if rh < 10 or not 1.0 <= rw / rh <= 6.5: return img
    # grow the box 8% wide / 14% tall so edge characters are never cut, then warp it flat
    box = cv2.boxPoints(((cx, cy), (rw * 1.08, rh * 1.14), ang)).astype(np.float32)
    s = box.sum(1); d = np.diff(box, axis=1).ravel()
    src = np.array([box[s.argmin()], box[d.argmin()], box[s.argmax()], box[d.argmax()]], np.float32)  # tl tr br bl
    W2, H2 = int(rw * 1.08), int(rh * 1.14)
    dst = np.array([[0, 0], [W2, 0], [W2, H2], [0, H2]], np.float32)
    return cv2.warpPerspective(img, cv2.getPerspectiveTransform(src, dst), (W2, H2), flags=cv2.INTER_CUBIC,
                               borderMode=cv2.BORDER_REPLICATE)


def enhance(img):
    """The 'clear plate' filter: straighten, upscale to ~128 px tall, denoise, CLAHE contrast, unsharp mask."""
    a = upscale(rectify(upscale(img)))
    a = cv2.fastNlMeansDenoisingColored(a, None, 5, 5, 7, 21)
    lab = cv2.cvtColor(a, cv2.COLOR_BGR2LAB)
    lab[:, :, 0] = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(4, 8)).apply(lab[:, :, 0])
    a = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    return cv2.addWeighted(a, 1.7, cv2.GaussianBlur(a, (0, 0), 1.5), -0.7, 0)


def gray_variant(clear):
    g = cv2.cvtColor(clear, cv2.COLOR_BGR2GRAY)
    return cv2.cvtColor(cv2.createCLAHE(2.0, (8, 8)).apply(g), cv2.COLOR_GRAY2BGR)


def ocr_paddle(img):
    try: res = paddle.predict(img)
    except Exception: return "", 0.0
    t, c = [], []
    for r in res: t += list(r.get("rec_texts", [])); c += list(r.get("rec_scores", []))
    return ("".join(t), float(np.mean(c))) if t else ("", 0.0)


def ocr(img):
    """EasyOCR; boxes that overlap vertically are one line (left-to-right), otherwise two lines top-to-bottom."""
    res = [r for r in reader.readtext(img, allowlist=ALLOW, detail=1, paragraph=False, width_ths=0.9,
                                      text_threshold=0.5) if r[1].strip()]
    if not res: return "", 0.0
    boxes = [(min(p[0] for p in r[0]), min(p[1] for p in r[0]), max(p[1] for p in r[0]), r) for r in res]
    boxes.sort(key=lambda b: (b[1] + b[2]) / 2)
    lines, cur = [], [boxes[0]]
    for b in boxes[1:]:
        top, bot = max(x[1] for x in cur), min(x[2] for x in cur)
        ov = min(bot, b[2]) - max(top, b[1])
        if ov > 0.3 * min(b[2] - b[1], bot - top + 1e-9): cur.append(b)
        else: lines.append(cur); cur = [b]
    lines.append(cur)
    rows = [b[3] for ln in lines for b in sorted(ln, key=lambda x: x[0])]
    text = "".join(r[1] for r in rows)
    return text, float(np.average([r[2] for r in rows], weights=[len(r[1]) for r in rows]))


def near(a, b):
    return len(a) == len(b) and sum(x != y for x, y in zip(a, b)) <= 1


def main(RUN):
    summary = []
    for vdir in sorted(glob.glob(f"{RUN}/plates/*/")):
        name = os.path.basename(vdir.rstrip("/"))
        out = f"{vdir}ocr_{ENGINE}"; shutil.rmtree(out, ignore_errors=True); os.makedirs(f"{out}/clear")
        tracks = collections.defaultdict(list)
        for f in glob.glob(f"{vdir}raw/crops/*.png"):
            m = re.match(r"id(\d+)_f(\d+)_c([\d.]+)\.png", os.path.basename(f))
            if m: tracks[m.group(1)].append((f, int(m.group(2)), float(m.group(3))))
        accepted, rejected = [], []
        for tid, items in sorted(tracks.items()):
            good = []
            for f, fr, dc in items:
                img = cv2.imread(f)
                if dc >= MIN_DET_CONF and img.shape[0] >= MIN_H and img.shape[1] >= MIN_W:
                    good.append((sharpness(img), f, fr, img))
            if not good:
                rejected.append((tid, "", "crops too small or low detection confidence")); continue
            reads = []                                       # (indian_text, conf, frame, crop_file, clear_img)
            raw_best = ("", 0.0)
            for sh, f, fr, img in sorted(good, key=lambda g: -g[0])[:TOPK]:
                clear = enhance(img)
                for v in (clear, gray_variant(clear)):
                    for eng, fn in (("easyocr", ocr), ("paddle", ocr_paddle)):
                        if (eng == "easyocr" and reader is None) or (eng == "paddle" and paddle is None): continue
                        txt, cf = fn(v)
                        if cf > raw_best[1]: raw_best = (txt, cf)
                        ind = to_indian(txt)
                        if ind and cf >= MIN_OCR_CONF: reads.append((ind[0], cf, fr, f, clear, eng))
            if not reads:
                rejected.append((tid, raw_best[0], "no read matches an Indian plate format with enough confidence"))
                continue
            # per-character weighted vote among reads of the most common length
            L = collections.Counter(len(r[0]) for r in reads).most_common(1)[0][0]
            cols = [collections.Counter() for _ in range(L)]
            for t, cf, *_ in reads:
                if len(t) == L:
                    for i, ch in enumerate(t): cols[i][ch] += cf
            voted = "".join(c.most_common(1)[0][0] for c in cols)
            plate = voted if to_indian(voted) and to_indian(voted)[1] == 0 else \
                collections.Counter(r[0] for r in reads).most_common(1)[0][0]
            support = [r for r in reads if near(r[0], plate)]
            frames = {r[2] for r in support}
            exact = [r for r in support if r[0] == plate]
            mean_conf = float(np.mean([r[1] for r in support]))
            engines_ok = ENGINE != "both" or {r[5] for r in exact} == {"easyocr", "paddle"}
            if len(frames) >= MIN_AGREE and exact and mean_conf >= MIN_MEAN_CONF and engines_ok:
                top = max(exact, key=lambda r: r[1])
                accepted.append(dict(plate=plate, conf=mean_conf, agree=len(frames), frames=len(good), top=top))
            else:
                why = (f"only {len(frames)} frame(s) agree" if len(frames) < MIN_AGREE else
                       "EasyOCR and PaddleOCR disagree" if not engines_ok else
                       f"mean confidence {mean_conf:.2f} too low" if mean_conf < MIN_MEAN_CONF else "no exact read")
                rejected.append((tid, plate, why))
        # one entry per physical plate: tracks whose texts differ by at most one character are the same plate
        final = []
        for a in sorted(accepted, key=lambda a: (-a["agree"], -a["conf"])):
            dup = next((k for k in final if near(k["plate"], a["plate"])), None)
            if dup: dup["tracks"] += 1; dup["agree"] += a["agree"]
            else: a["tracks"] = 1; final.append(a)
        with open(f"{out}/plates.txt", "w") as fh:
            fh.write("# plate\tmean_ocr_conf\tframes_agreeing\ttracks\tclear_image\toriginal_crop\n")
            for a in final:
                cimg, oimg = f"clear/{a['plate']}.png", f"clear/{a['plate']}_original.png"
                cv2.imwrite(f"{out}/{cimg}", a["top"][4]); shutil.copy(a["top"][3], f"{out}/{oimg}")
                fh.write(f"{a['plate']}\t{a['conf']:.2f}\t{a['agree']}\t{a['tracks']}\t{cimg}\t{oimg}\n")
                summary.append(f"{name}\t{a['plate']}\t{a['conf']:.2f}\t{a['agree']}\t{name}/ocr_{ENGINE}/{cimg}")
        with open(f"{out}/rejected.txt", "w") as fh:
            fh.write("# track\tbest_text_read\treason_rejected\n")
            for r in rejected: fh.write("\t".join(r) + "\n")
        print(f"{name[:45]:45s} tracks={len(tracks):3d} accepted={len(final):3d} rejected={len(rejected):3d}  "
              f"{' '.join(a['plate'] for a in final)}", flush=True)
    with open(f"{RUN}/plates/all_plates_ocr_{ENGINE}.txt", "w") as fh:
        fh.write("# video\tplate\tmean_ocr_conf\tframes_agreeing\tclear_image\n" + "\n".join(summary) + "\n")


if __name__ == "__main__":
    main(sys.argv[1].rstrip("/"))
