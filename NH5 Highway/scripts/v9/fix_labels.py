#!/usr/bin/env python3
"""v9 label fixes on the TRAIN split of datasets/processed_v9 (val/test labels stay exactly as in v8, so v8 and v9
are compared on the same ground truth). Uses the v8 prediction cache from cache_predictions.py.

  python3 scripts/v9/fix_labels.py            # dry run: counts + review sheets, writes nothing
  python3 scripts/v9/fix_labels.py --apply    # write the fixed labels (backup of every changed file first)

Fixes (each rule is conservative; every one produces a review sheet: green = kept/added label, red = removed):
  A leakage   train images that are near-duplicates (dHash <= 4 bits) of a val/test image -> moved out of train
  B roadwork  pubrw/roadwork label with NO v8 road_construction prediction near it and area < 2% of the image
              (lone sign / far pole, against the class definition) -> label removed, image kept as a negative
  C1 pothole  confident v8 pothole (>= 0.60) with no labelled pothole overlapping it, in pothole-source images -> added
  C2 pothole  one label box covering >= 2 confident predicted potholes (each >= 80% inside, each <= 50% of the box)
              -> replaced by the individual pothole boxes (one box per pothole, the consistent style)
  C3 pothole  rdd2022 label smaller than 0.2% of the image that v8 does not see at all -> removed (faint/far patch)
  D  fire     no fire label, v8 fire >= 0.60 with a vehicle >= 50% inside it and >= 1.2% flame-coloured pixels -> added
  E  accident no accident label, v8 accident >= 0.75 with >= 2 vehicles/people inside it -> added
"""
import collections, json, os, random, re, shutil, sys
from pathlib import Path
import cv2, numpy as np

ROOT = Path("/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway")
D = ROOT / "datasets/processed_v9"
AUD = ROOT / "runs/v9_audit"
SHEETS = AUD / "fix_sheets"; SHEETS.mkdir(parents=True, exist_ok=True)
APPLY = "--apply" in sys.argv
VEH = {2, 3, 4, 5, 8}; PERSON = 0
POT_SRC = {"pothole", "pubpot", "potholewf", "rdd2022", "roaddmg", "hydpot"}
RW_SRC = {"pubrw", "roadwork"}
# fire / accident additions only for images hand-checked on the numbered review sheets (auto rules were too loose:
# building/forest fires with a fire engine nearby, normal traffic queues); C2 cluster splitting disabled after review
WHITE = json.load(open(AUD / "manual_whitelist.json")) if (AUD / "manual_whitelist.json").exists() else {}
USE_C2 = False


def src(name):
    return re.split(r"[_\-]", Path(name).stem)[0]


def load_cache(split):
    return {j["img"]: j for j in map(json.loads, (AUD / f"cache_{split}.jsonl").open())}


def read_labels(split, img):
    p = D / "labels" / split / (Path(img).stem + ".txt")
    return [[int(l.split()[0])] + [float(v) for v in l.split()[1:5]] for l in p.read_text().split("\n") if l.strip()] if p.exists() else []


def to_xyxy(l, w, h):
    c, x, y, bw, bh = l
    return ((x - bw / 2) * w, (y - bh / 2) * h, (x + bw / 2) * w, (y + bh / 2) * h)


def to_yolo(c, b, w, h):
    x0, y0, x1, y1 = max(0, b[0]), max(0, b[1]), min(w, b[2]), min(h, b[3])
    return [c, (x0 + x1) / 2 / w, (y0 + y1) / 2 / h, (x1 - x0) / w, (y1 - y0) / h]


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0, min(a[3], b[3]) - max(a[1], b[1])); i = ix * iy
    return i / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i + 1e-9)


def inside(a, b):  # fraction of box a inside box b
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    return ix * iy / ((a[2] - a[0]) * (a[3] - a[1]) + 1e-9)


def area(b):
    return max(0, b[2] - b[0]) * max(0, b[3] - b[1])


def flame_fraction(img, b):
    """share of bright ORANGE/YELLOW flame pixels in box b (pure red excluded: red fire engines / cars are not fire)"""
    x0, y0, x1, y1 = (int(v) for v in b); roi = img[max(0, y0):y1, max(0, x0):x1]
    if roi.size == 0:
        return 0.0
    h, s, v = cv2.split(cv2.cvtColor(roi, cv2.COLOR_BGR2HSV))
    return float(((h >= 6) & (h <= 35) & (s >= 100) & (v >= 180)).mean())


# ---------------------------------------------------------------- A: train/val/test near-duplicates (leakage)
def popcount64(x):
    x = x - ((x >> np.uint64(1)) & np.uint64(0x5555555555555555))
    x = (x & np.uint64(0x3333333333333333)) + ((x >> np.uint64(2)) & np.uint64(0x3333333333333333))
    x = (x + (x >> np.uint64(4))) & np.uint64(0x0F0F0F0F0F0F0F0F)
    return (x * np.uint64(0x0101010101010101)) >> np.uint64(56)


print("loading prediction cache ...", flush=True)
CT = load_cache("train"); CV = load_cache("val"); CE = load_cache("test")
tr_names = list(CT); tr_h = np.array([CT[n]["hash"] for n in tr_names], dtype=np.uint64)
leak = set()
for cache in (CV, CE):
    for j in cache.values():
        d = popcount64(tr_h ^ np.uint64(j["hash"]))
        for i in np.nonzero(d <= 4)[0]:
            leak.add(tr_names[i])
print(f"A leakage: {len(leak)} train images near-identical to a val/test image", flush=True)

# ---------------------------------------------------------------- B-E per train image
changes = collections.defaultdict(list)     # rule -> [(img, before_labels, after_labels)]
new_labels = {}
for name, j in CT.items():
    if name in leak:
        continue
    w, h, s = j["w"], j["h"], src(name)
    labels = read_labels("train", name); orig = [list(l) for l in labels]
    P = [(p[0], p[1], tuple(p[2:])) for p in j["preds"]]
    img = None
    # B road work
    if s in RW_SRC:
        keep = []
        for l in labels:
            if l[0] == 9:
                b = to_xyxy(l, w, h)
                near = any(c == 9 and iou(b, pb) >= 0.1 for c, _, pb in P)
                if not near and l[3] * l[4] < 0.02:
                    changes["B_roadwork_removed"].append(name); continue
            keep.append(l)
        labels = keep
    # C pothole
    if s in POT_SRC or any(l[0] == 6 for l in labels):
        pot_preds = [(cf, pb) for c, cf, pb in P if c == 6]
        out = []
        for l in labels:
            if l[0] != 6:
                out.append(l); continue
            b = to_xyxy(l, w, h)
            parts = [pb for cf, pb in pot_preds if cf >= 0.40 and inside(pb, b) >= 0.8 and area(pb) <= 0.5 * area(b)]
            if USE_C2 and len(parts) >= 2:                                         # C2 split cluster box
                out += [to_yolo(6, pb, w, h) for pb in parts]; changes["C2_pothole_cluster_split"].append(name); continue
            if s == "rdd2022" and l[3] * l[4] < 0.002 and not any(iou(b, pb) >= 0.1 for _, pb in pot_preds):
                changes["C3_pothole_faint_removed"].append(name); continue          # C3 faint far patch
            out.append(l)
        labels = out
        if s in POT_SRC:                                                           # C1 missing potholes
            gt = [to_xyxy(l, w, h) for l in labels if l[0] == 6]
            for cf, pb in pot_preds:
                if cf >= 0.60 and not any(iou(pb, g) >= 0.1 or inside(pb, g) >= 0.5 for g in gt):
                    labels.append(to_yolo(6, pb, w, h)); gt.append(pb); changes["C1_pothole_added"].append(name)
    # D fire (vehicle in fire, visible flames)
    if not any(l[0] == 11 for l in labels) and (not WHITE or name in WHITE.get("D_fire_added", [])):
        for c, cf, pb in P:
            if c != 11 or cf < 0.60:
                continue
            vehs = [vb for cc, ccf, vb in P if cc in VEH and ccf >= 0.4 and inside(vb, pb) >= 0.5]
            if not vehs:
                continue
            img = img if img is not None else cv2.imread(str(D / "images/train" / name))
            # the VEHICLE itself must be burning: >= 10% of the vehicle box is orange/yellow flame
            if img is not None and any(flame_fraction(img, vb) >= 0.10 for vb in vehs):
                labels.append(to_yolo(11, pb, w, h)); changes["D_fire_added"].append(name); break
    # E accident
    if not any(l[0] == 10 for l in labels) and (not WHITE or name in WHITE.get("E_accident_added", [])):
        for c, cf, pb in P:
            if c == 10 and cf >= 0.75:
                inv = [1 for cc, ccf, vb in P if (cc in VEH or cc == PERSON) and ccf >= 0.4 and inside(vb, pb) >= 0.5]
                if len(inv) >= 2:
                    labels.append(to_yolo(10, pb, w, h)); changes["E_accident_added"].append(name); break
    if labels != orig:
        new_labels[name] = (orig, labels)

# ---------------------------------------------------------------- report + review sheets
report = {"A_leakage_train_images_moved_out": len(leak)}
for k, v in sorted(changes.items()):
    report[k] = {"boxes": len(v), "images": len(set(v)),
                 "by_source": collections.Counter(src(n) for n in set(v)).most_common(6)}
report["train_label_files_changed"] = len(new_labels)
print(json.dumps(report, indent=1), flush=True)
json.dump(report, open(AUD / ("fix_report_applied.json" if APPLY else "fix_report_dryrun.json"), "w"), indent=1)

COL = {6: "pothole", 9: "road_construction", 10: "accident_scene", 11: "fire_accident"}
for rule, names in changes.items():
    random.seed(1); pick = random.sample(sorted(set(names)), min(24, len(set(names)))); tiles = []
    for n in pick:
        im = cv2.imread(str(D / "images/train" / n)); w, h = CT[n]["w"], CT[n]["h"]
        before, after = new_labels[n]; t = max(2, w // 250)
        bset = {tuple(round(v, 4) for v in l) for l in before}; aset = {tuple(round(v, 4) for v in l) for l in after}
        for l in after:
            if l[0] in COL:
                b = to_xyxy(l, w, h); cv2.rectangle(im, (int(b[0]), int(b[1])), (int(b[2]), int(b[3])),
                                                    (0, 220, 0) if tuple(round(v, 4) for v in l) in bset else (0, 255, 255), t)
        for l in before:
            if l[0] in COL and tuple(round(v, 4) for v in l) not in aset:
                b = to_xyxy(l, w, h); cv2.rectangle(im, (int(b[0]), int(b[1])), (int(b[2]), int(b[3])), (0, 0, 255), t)
        tl = cv2.resize(im, (320, 240)); cv2.putText(tl, src(n)[:14], (4, 18), 0, 0.55, (255, 255, 0), 2); tiles.append(tl)
    while len(tiles) % 6:
        tiles.append(np.zeros((240, 320, 3), np.uint8))
    if tiles:
        cv2.imwrite(str(SHEETS / f"{rule}.jpg"), cv2.vconcat([cv2.hconcat(tiles[i:i + 6]) for i in range(0, len(tiles), 6)]))
print(f"review sheets: {SHEETS}  (green = unchanged label, yellow = added, red = removed)", flush=True)

# ---------------------------------------------------------------- apply
if APPLY:
    bk = ROOT / "runs/v9_audit/labels_before_fix/train"; bk.mkdir(parents=True, exist_ok=True)
    for n, (before, after) in new_labels.items():
        lp = D / "labels/train" / (Path(n).stem + ".txt")
        if lp.exists():
            shutil.copy2(lp, bk / lp.name)
        lp.write_text("".join(f"{int(l[0])} {l[1]:.6f} {l[2]:.6f} {l[3]:.6f} {l[4]:.6f}\n" for l in after))
    ex = D / "_excluded_leakage"; (ex / "images").mkdir(parents=True, exist_ok=True); (ex / "labels").mkdir(parents=True, exist_ok=True)
    for n in leak:
        shutil.move(str(D / "images/train" / n), str(ex / "images" / n))
        lp = D / "labels/train" / (Path(n).stem + ".txt")
        if lp.exists():
            shutil.move(str(lp), str(ex / "labels" / lp.name))
    for c in (D / "labels").glob("*.cache"):
        c.unlink()
    print(f"APPLIED: {len(new_labels)} label files rewritten (backup in {bk}), {len(leak)} leaked images moved to {ex}")
