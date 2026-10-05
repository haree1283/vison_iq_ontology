"""Audit v8: (1) drop train images whose original also appears in val/test, (2) cross-source near-duplicates (dHash) among fire and road_construction images -> keep one,
(3) degenerate zone/fire boxes per source. Removed train files are moved to datasets/v6/_audit_removed_v8 (reversible)."""
import os, re, glob, shutil, collections, json
import numpy as np, cv2
from multiprocessing import Pool
D = "datasets/processed_v2_plus_v6_v8"; SIDE = "datasets/v6/_audit_removed_v8"; st = collections.Counter(); removed = set()
def clean(s): return re.sub(r"(_(pothaug\d*|balpot\d*|aug\d*|bal[a-z]*\d*))+$", "", re.sub(r"\.rf\.[0-9a-f]{20,}", "", s))
def move(s):
    if s in removed: return
    removed.add(s)
    for sp in ("images", "labels"): os.makedirs(f"{SIDE}/{sp}/train", exist_ok=True)
    for e in (".jpg", ".png", ".jpeg"):
        p = f"{D}/images/train/{s}{e}"
        if os.path.exists(p): shutil.move(p, f"{SIDE}/images/train/{s}{e}")
    if os.path.exists(f"{D}/labels/train/{s}.txt"): shutil.move(f"{D}/labels/train/{s}.txt", f"{SIDE}/labels/train/{s}.txt")
tr = [f[:-4] for f in os.listdir(f"{D}/labels/train")]
vt = {clean(f[:-4]) for sp in ("val", "test") for f in os.listdir(f"{D}/labels/{sp}")}
for s in tr:
    if clean(s) in vt: move(s); st["train images removed: original also in val/test"] += 1
def dh(p):
    im = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
    if im is None: return None
    s = cv2.resize(im, (9, 8), interpolation=cv2.INTER_AREA); return int("".join("1" if x else "0" for x in (s[:, 1:] > s[:, :-1]).flatten()), 2)
def group(s):
    if s.startswith("night_") or s.startswith("synacc_"): return None
    lab = f"{D}/labels/train/{s}.txt"
    cls = {l.split()[0] for l in open(lab) if l.strip()} if os.path.exists(lab) else set()
    return "fire" if "11" in cls else "rc" if "9" in cls else None
for gname in ("fire", "rc"):
    items = [s for s in tr if s not in removed and group(s) == gname]
    paths = []
    for s in items: paths.append(next((f"{D}/images/train/{s}{e}" for e in (".jpg", ".png", ".jpeg") if os.path.exists(f"{D}/images/train/{s}{e}")), None))
    with Pool(8) as pool: hs = pool.map(dh, paths, chunksize=64)
    buckets = collections.defaultdict(list)
    for s, h in zip(items, hs):
        if h is None: continue
        buckets[h >> 48].append((s, h))               # coarse bucket on the top 16 bits, then exact Hamming <= 4 inside
        buckets[(h >> 32) & 0xFFFF]
    seen = []; 
    for key, lst in buckets.items():
        keep = []
        for s, h in lst:
            if s in removed: continue
            dup = next((k for k, hk in keep if bin(h ^ hk).count("1") <= 4), None)
            if dup is not None:
                move(s); st[f"{gname}: cross-source near-duplicates removed"] += 1
            else: keep.append((s, h))
print(dict(st), flush=True)
# degenerate boxes per source (class 9 zone, class 11 fire)
bad = collections.Counter(); srcs = collections.defaultdict(list)
for f in glob.glob(f"{D}/labels/train/*.txt"):
    s = os.path.basename(f)[:-4]
    for l in open(f):
        q = l.split()
        if q and q[0] in ("9", "11"):
            a = float(q[3]) * float(q[4]); k = ("pubrw_" + s.split("_")[1]) if s.startswith("pubrw") else ("pubfire" if s.startswith("pubfire") else "existing")
            srcs[(q[0], k)].append(a)
for (c, k), a in sorted(srcs.items()):
    a = np.array(a); print(f"class {c:>2s} {k:16s} n={len(a):6d} area median {np.median(a):.3f} p10 {np.percentile(a,10):.4f} p90 {np.percentile(a,90):.2f}  tiny(<0.3%): {100*np.mean(a<0.003):4.1f}%  huge(>90%): {100*np.mean(a>0.9):4.1f}%")
json.dump(dict(st), open(f"{D}/audit_report.json", "w"))
