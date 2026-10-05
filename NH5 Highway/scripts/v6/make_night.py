"""Low-light (night) simulation of real, non-augmented training images: gamma+gain darkening, headlight bloom, sensor noise. Labels copied.
Prefix night_ ; train only; a small share (about 2.5%) to cover the missing night data. No vedios/ data."""
import os, glob, random, re, collections
import numpy as np, cv2
from multiprocessing import Pool
random.seed(5); D = "datasets/processed_v2_plus_v6_v8"
AUG = re.compile(r"aug|_bal|balpot|balacc|balfire|synacc|night_", re.I)
QUOTA = {"10": 800, "11": 400, "7": 300, "9": 300, "2": 700, "0": 300, "5": 200, "8": 200, "3": 200, "6": 200}   # class -> images
def night(args):
    src, name, seed = args; rng = np.random.RandomState(seed); im = cv2.imread(src)
    if im is None: return 0
    H, W = im.shape[:2]
    if max(H, W) > 1280: s = 1280 / max(H, W); im = cv2.resize(im, (int(W * s), int(H * s)), interpolation=cv2.INTER_AREA)
    f = im.astype(np.float32) / 255.0
    lum = f.mean(axis=2); bright = np.clip((lum - 0.75) * 4, 0, 1)[..., None] * f
    bloom = cv2.GaussianBlur(bright, (0, 0), sigmaX=max(6, im.shape[1] / 90)) * rng.uniform(0.8, 1.6)
    g = rng.uniform(1.9, 3.0); gain = rng.uniform(0.35, 0.7); out = (f ** g) * gain
    tint = np.array([rng.uniform(1.0, 1.25), rng.uniform(0.95, 1.05), rng.uniform(0.8, 0.95)], np.float32)   # BGR: cool/blue-ish night
    out = out * tint + bloom * 0.6
    out += rng.normal(0, rng.uniform(0.012, 0.035), out.shape).astype(np.float32)
    out = np.clip(out, 0, 1); cv2.imwrite(f"{D}/images/train/{name}.jpg", (out * 255).astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 90])
    src_lab = f"{D}/labels/train/{os.path.basename(src)[:os.path.basename(src).rfind('.')]}.txt"
    open(f"{D}/labels/train/{name}.txt", "w").write(open(src_lab).read()); return 1
if __name__ == "__main__":
    by = collections.defaultdict(list)
    for lf in glob.glob(f"{D}/labels/train/*.txt"):
        stem = os.path.basename(lf)[:-4]
        if AUG.search(stem): continue
        cls = {l.split()[0] for l in open(lf) if l.strip()}
        for c in QUOTA:
            if c in cls: by[c].append(stem)
    chosen = {}
    for c, q in QUOTA.items():
        random.shuffle(by[c])
        for s in by[c]:
            if len(chosen) >= 10 ** 9: break
            if s not in chosen and sum(1 for v in chosen.values() if v == c) < q: chosen[s] = c
    jobs = []
    for i, s in enumerate(chosen):
        p = next((f"{D}/images/train/{s}{e}" for e in (".jpg", ".png", ".jpeg") if os.path.exists(f"{D}/images/train/{s}{e}")), None)
        if p: jobs.append((p, f"night_{i:05d}", i))
    print("night images to make:", len(jobs), flush=True)
    with Pool(8) as pool: n = sum(pool.imap_unordered(night, jobs, chunksize=16))
    print("DONE night images:", n)
