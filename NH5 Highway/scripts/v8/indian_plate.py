"""Indian number plates only: crop clean-up filter, PaddleOCR reading, strict Indian-format validation.

Shared by scripts/v6/plates_refine.py (video tests) and app.py (website). A reading is only ever returned in a
real Indian format -- anything else (foreign plates, stickers, shop signs, OCR noise) is rejected, never guessed.
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
