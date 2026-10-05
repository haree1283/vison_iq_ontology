"""Merge public D-Fire (fire+smoke) into datasets/processed_v2_plus_v6_v4 as class 12 (fire_accident).
Label convention matches existing fire_accident boxes (scene-level): one box = padded union of all fire+smoke boxes in the image.
Only public dataset images are used; nothing from vedios/."""
import glob, io, os, re, random, hashlib, json, collections
import pyarrow.parquet as pq
from PIL import Image
random.seed(7)
SRC = "datasets/v6/public_fire_smoke/badsaarow__d-fire/data"; DST = "datasets/processed_v2_plus_v6_v4"
MIN_UNION, PAD, MAXSIDE, CAP_POS, N_NEG = 0.004, 0.05, 1280, 10000, 1500
def split_of(fn):
    m = re.match(r"^(AoF)(\d+)", fn)
    key = f"{m.group(1)}{int(m.group(2)) // 60}" if m else fn          # keep AoF sequence chunks together
    h = int(hashlib.md5(key.encode()).hexdigest(), 16) % 1000
    return "val" if h < 25 else "test" if h < 50 else "train"
pos, neg, rows_seen = [], [], 0
for f in sorted(glob.glob(f"{SRC}/*.parquet")):
    pf = pq.ParquetFile(f)
    for rg in range(pf.num_row_groups):
        t = pf.read_row_group(rg).to_pydict()
        for img, lab, fn in zip(t["image"], t["label"], t["filename"]):
            rows_seen += 1
            boxes = [[float(v) for v in l.split()[1:5]] for l in (lab or "").splitlines() if l.strip()]
            m = re.match(r"^AoF(\d+)", fn)
            if m and int(m.group(1)) % 3: continue                        # thin near-identical video frames
            if boxes:
                x1 = min(b[0] - b[2] / 2 for b in boxes); y1 = min(b[1] - b[3] / 2 for b in boxes)
                x2 = max(b[0] + b[2] / 2 for b in boxes); y2 = max(b[1] + b[3] / 2 for b in boxes)
                pw, ph = (x2 - x1) * PAD, (y2 - y1) * PAD
                x1, y1, x2, y2 = max(0, x1 - pw), max(0, y1 - ph), min(1, x2 + pw), min(1, y2 + ph)
                if (x2 - x1) * (y2 - y1) < MIN_UNION: continue
                pos.append((fn, img["bytes"], f"12 {(x1+x2)/2:.6f} {(y1+y2)/2:.6f} {x2-x1:.6f} {y2-y1:.6f}\n"))
            else:
                neg.append((fn, img["bytes"], ""))
random.shuffle(pos); random.shuffle(neg)
pick = pos[:CAP_POS] + neg[:N_NEG]
stats = collections.Counter()
for fn, b, lab in pick:
    sp = split_of(fn); stem = "pubfire_dfire_" + os.path.splitext(fn)[0]
    im = Image.open(io.BytesIO(b)).convert("RGB")
    s = MAXSIDE / max(im.size)
    if s < 1: im = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
    im.save(f"{DST}/images/{sp}/{stem}.jpg", quality=92)
    open(f"{DST}/labels/{sp}/{stem}.txt", "w").write(lab)
    stats[(sp, "fire" if lab else "negative")] += 1
print("rows scanned", rows_seen, "positives available", len(pos), "negatives available", len(neg))
print({f"{k[0]}/{k[1]}": v for k, v in sorted(stats.items())})
json.dump({f"{k[0]}/{k[1]}": v for k, v in stats.items()}, open(f"{DST}/dfire_merge_report.json", "w"), indent=1)
