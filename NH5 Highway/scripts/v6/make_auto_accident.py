"""Synthetic 'auto-rickshaw involved in accident' images: real auto crops (from the training data) blended next to crashed vehicles in real accident scenes.
Files are prefixed synacc_ so they can be removed. Output goes to v8 train only. No vedios/ data."""
import os, glob, random, json, collections
import numpy as np, cv2
random.seed(11); np.random.seed(11)
V6 = "datasets/processed_v2_plus_v6_v6"; D = "datasets/processed_v2_plus_v6_v8"; N_TARGET = 1500
def imgpath(root, sp, stem): return next((f"{root}/images/{sp}/{stem}{e}" for e in (".jpg", ".png", ".jpeg") if os.path.exists(f"{root}/images/{sp}/{stem}{e}")), None)
def rows_of(f): return [l.split() for l in open(f) if l.strip()]
def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0, min(a[3], b[3]) - max(a[1], b[1])); i = ix * iy
    return i / ((a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - i + 1e-9)
xyxy = lambda r: [float(r[1]) - float(r[3]) / 2, float(r[2]) - float(r[4]) / 2, float(r[1]) + float(r[3]) / 2, float(r[2]) + float(r[4]) / 2]
# ---- auto crop bank (clean, well-sized autos from the training set)
files = glob.glob(f"{V6}/labels/train/*.txt"); random.shuffle(files); bank = []
for f in files[:14000]:
    rows = rows_of(f); au = [r for r in rows if r[0] == "8"]
    if not au or len(bank) >= 2600: continue
    stem = os.path.basename(f)[:-4]
    for r in au:
        b = xyxy(r); w, h = float(r[3]), float(r[4])
        if not (0.05 <= w * h <= 0.45 and 0.6 <= w / h <= 1.9): continue
        if any(o is not r and iou(b, xyxy(o)) > 0.03 for o in rows): continue
        bank.append((stem, b)); break
print("auto crops in bank:", len(bank), flush=True)
# ---- accident scenes with a sizeable crashed vehicle
scenes = []
for f in glob.glob(f"{V6}/labels/train/*.txt"):
    rows = rows_of(f)
    if not any(r[0] == "10" for r in rows): continue
    veh = [r for r in rows if r[0] in ("2", "3", "4", "5") and float(r[4]) >= 0.14 and float(r[3]) >= 0.08]
    if veh: scenes.append((os.path.basename(f)[:-4], f, veh))
random.shuffle(scenes); print("candidate accident scenes:", len(scenes), flush=True)
made = collections.Counter(); k = 0
for stem, lf, veh in scenes:
    if made["ok"] >= N_TARGET: break
    ip = imgpath(V6, "train", stem); scene = cv2.imread(ip) if ip else None
    if scene is None or min(scene.shape[:2]) < 400: continue
    H, W = scene.shape[:2]; rows = rows_of(lf); anchor = random.choice(veh); ab = xyxy(anchor)
    cs, cb = random.choice(bank); cp = imgpath(V6, "train", cs); cimg = cv2.imread(cp) if cp else None
    if cimg is None: continue
    ch_, cw_ = cimg.shape[:2]; crop = cimg[int(cb[1]*ch_):int(cb[3]*ch_), int(cb[0]*cw_):int(cb[2]*cw_)]
    if crop.shape[0] < 40 or crop.shape[1] < 40: continue
    ah = (ab[3] - ab[1]) * H; th = int(np.clip(ah * random.uniform(0.75, 1.15), 40, H * 0.6)); tw = int(crop.shape[1] * th / crop.shape[0])
    if tw > W * 0.6: continue
    crop = cv2.resize(crop, (tw, th), interpolation=cv2.INTER_AREA)
    if random.random() < 0.5: crop = crop[:, ::-1].copy()
    # match brightness of the scene region around the anchor
    reg = scene[int(ab[1]*H):int(ab[3]*H), int(ab[0]*W):int(ab[2]*W)]
    if reg.size:
        crop = np.clip(crop.astype(np.float32) * (reg.mean() + 5) / (crop.mean() + 5) * 0.5 + crop.astype(np.float32) * 0.5, 0, 255).astype(np.uint8)
    side = random.choice([-1, 1]); ax1, ax2 = ab[0] * W, ab[2] * W
    x1 = int(ax1 - tw * random.uniform(0.75, 0.95)) if side < 0 else int(ax2 - tw * random.uniform(0.05, 0.25))
    y2 = int(ab[3] * H + random.uniform(-0.06, 0.08) * ah); y1 = y2 - th
    if x1 < 0 or y1 < 0 or x1 + tw > W or y2 > H: continue
    mask = np.zeros((th, tw), np.uint8); m = max(3, int(min(tw, th) * 0.08)); mask[m:-m, m:-m] = 255
    center = (x1 + tw // 2, y1 + th // 2)
    try: out = cv2.seamlessClone(crop, scene, mask, center, cv2.NORMAL_CLONE)
    except Exception: continue
    nb = [x1 / W, y1 / H, (x1 + tw) / W, y2 / H]; auto = f"8 {(nb[0]+nb[2])/2:.6f} {(nb[1]+nb[3])/2:.6f} {nb[2]-nb[0]:.6f} {nb[3]-nb[1]:.6f}"
    lines = []
    for r in rows:
        if r[0] == "10":  # grow the accident box to include the pasted auto
            b = xyxy(r); u = [min(b[0], nb[0]), min(b[1], nb[1]), max(b[2], nb[2]), max(b[3], nb[3])]
            lines.append(f"10 {(u[0]+u[2])/2:.6f} {(u[1]+u[3])/2:.6f} {u[2]-u[0]:.6f} {u[3]-u[1]:.6f}")
        else: lines.append(" ".join(r))
    lines.append(auto); name = f"synacc_{k:05d}"; k += 1
    cv2.imwrite(f"{D}/images/train/{name}.jpg", out, [cv2.IMWRITE_JPEG_QUALITY, 92]); open(f"{D}/labels/train/{name}.txt", "w").write("\n".join(lines) + "\n"); made["ok"] += 1
    if made["ok"] % 300 == 0: print("made", made["ok"], flush=True)
print("DONE synthetic auto-accident images:", made["ok"])
