"""Final label clean-up of datasets/processed_v2_plus_v6_v8 (in place; backup in ~/Backups/v8_before_label_fix_2026-09-24).

Rules (user decisions 2026-09-24):
  1. road_construction = one work-zone box rebuilt from the original per-object annotations
     (ROADWork CMU / discovered / AutoNOMOS / StarLine): >=3 channelizers clustered, or worker/work
     vehicle + channelizer, or arrow board. Lone cone / sign / bollard -> no zone.  (staged labels)
  2. jcb_excavator removed (boxes unrecoverable); night_ copies whose original can't be traced
     and that carry a zone are removed.
  3. v6_fire_* images: accident_scene -> fire_accident; fire_accident = one union box per image.
  4. dfire_* (generic fire sets): fire with no vehicle in the image -> fire label dropped (not a vehicle fire).
  5. Riders are not persons: person boxes sitting on a motorcycle / bicycle / auto are dropped.
  6. car labelled where COCO yolov8l is sure it is a bus (conf>=0.8, IoU>=0.6) -> bus.
  7. Unlabelled persons / vehicles found by COCO yolov8l (conf>=0.5) are added; COCO vehicles that our
     model sees as an auto-rickshaw become auto; persons on/in a vehicle are skipped (rule 5);
     hetero bicycles (cycle-rickshaws) are skipped.
Usage: python3 scripts/v6/fix_v8_labels.py <scratch dir with coco_check.jsonl, auto_check.jsonl, rw/staged_labels> <backup dir>
"""
import os, sys, json, shutil, collections

D = "datasets/processed_v2_plus_v6_v8"
SCR, BAK = sys.argv[1], sys.argv[2]
STAGED = f"{SCR}/rw/staged_labels"
RIDEABLE = {"1", "3", "8"}
VEHICLE = {"1", "2", "3", "4", "5", "8"}


def xyxy(r):
    x, y, w, h = map(float, r[1:5]); return (x - w / 2, y - h / 2, x + w / 2, y + h / 2)


def inter(a, b):
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


def area(a):
    return (a[2] - a[0]) * (a[3] - a[1])


def iou(a, b):
    i = inter(a, b); return i / (area(a) + area(b) - i + 1e-9)


def row(c, b):
    return [str(c), f"{(b[0]+b[2])/2:.6f}", f"{(b[1]+b[3])/2:.6f}", f"{b[2]-b[0]:.6f}", f"{b[3]-b[1]:.6f}"]


coco = {}
for l in open(f"{SCR}/coco_check.jsonl"):
    d = json.loads(l); coco[(d["sp"], os.path.splitext(d["f"])[0])] = d
autos = {}
for l in open(f"{SCR}/auto_check.jsonl"):
    d = json.loads(l); autos[(d["sp"], os.path.splitext(d["f"])[0])] = d["auto"]

st = collections.Counter()
os.makedirs(f"{BAK}/removed_images", exist_ok=True)


def remove(sp, stem, why):
    for e in (".jpg", ".png", ".jpeg"):
        p = f"{D}/images/{sp}/{stem}{e}"
        if os.path.exists(p): os.makedirs(f"{BAK}/removed_images/{sp}", exist_ok=True); shutil.move(p, f"{BAK}/removed_images/{sp}/")
    os.remove(f"{D}/labels/{sp}/{stem}.txt"); st[f"removed: {why}"] += 1


for sp in ("train", "val", "test"):
    for f in sorted(os.listdir(f"{D}/labels/{sp}")):
        if not f.endswith(".txt"): continue
        stem = f[:-4]; lp = f"{D}/labels/{sp}/{f}"
        rows = [l.split() for l in open(lp) if l.strip()]
        staged = f"{STAGED}/{sp}/{f}"
        if stem.startswith("jcb_excavator"): remove(sp, stem, "jcb_excavator"); continue
        if stem.startswith("night_") and any(r[0] == "9" for r in rows) and not os.path.exists(staged):
            remove(sp, stem, "night copy with untraceable zone"); continue
        cc = coco.get((sp, stem), {"missing": [], "wrong": []})
        # 6. car -> bus (indices refer to the original row order)
        for k, g, pc, cf in cc["wrong"]:
            if g == 2 and pc == 4 and cf >= 0.8 and rows[k][0] == "2": rows[k][0] = "4"; st["car -> bus"] += 1
        # 1. rebuilt work zones
        if os.path.exists(staged):
            new9 = [l.split() for l in open(staged) if l.strip() and l.split()[0] == "9"]
            old9 = sum(r[0] == "9" for r in rows)
            rows = [r for r in rows if r[0] != "9"] + new9
            st["zone: rebuilt"] += bool(new9); st["zone: lone object, removed"] += bool(old9 and not new9); st["zone: newly added"] += bool(new9 and not old9)
        # 3. fire images labelled as accident
        if stem.startswith("v6_fire_"):
            n = sum(r[0] == "10" for r in rows)
            if n: rows = [["11"] + r[1:] if r[0] == "10" else r for r in rows]; st["fire image: accident -> fire_accident"] += 1
        # 4. generic fire sets: fire without any vehicle is not a vehicle fire
        if stem.startswith("dfire") and any(r[0] == "11" for r in rows):
            veh = any(r[0] in VEHICLE for r in rows) or any(m[0] in (1, 2, 3, 4, 5) for m in cc["missing"])
            if not veh: rows = [r for r in rows if r[0] != "11"]; st["dfire: non-vehicle fire label dropped"] += 1
        # 5. riders are not persons
        rid = [xyxy(r) for r in rows if r[0] in RIDEABLE]
        keep = []
        for r in rows:
            if r[0] == "0" and rid:
                p = xyxy(r); cx = (p[0] + p[2]) / 2
                if any(inter(p, v) >= 0.5 * area(p) and v[0] <= cx <= v[2] for v in rid): st["rider person box dropped"] += 1; continue
            keep.append(r)
        rows = keep
        # 7. add unlabelled persons / vehicles
        ap = [tuple(a) for a in autos.get((sp, stem), [])]
        mv = [(m[0], tuple(m[2:6])) for m in cc["missing"] if m[0] != 0]
        for m in cc["missing"]:
            c, cf, b = m[0], m[1], tuple(m[2:6])
            if c == 0:
                vb = [xyxy(r) for r in rows if r[0] in VEHICLE] + [v for _, v in mv] + ap
                if any(inter(b, v) >= 0.4 * area(b) for v in vb): st["COCO person on/in vehicle skipped"] += 1; continue
                rows.append(row(0, b)); st["added person"] += 1
            else:
                if c == 1 and stem.startswith("hetero"): st["hetero bicycle (rickshaw) skipped"] += 1; continue
                if any(iou(b, xyxy(r)) >= 0.3 for r in rows): continue
                if any(iou(b, a) >= 0.4 for a in ap): rows.append(row(8, b)); st["added auto"] += 1; continue
                rows.append(row(c, b)); st[f"added {['person','bicycle','car','motorcycle','bus','truck'][c]}"] += 1
        # 3b. one combined fire box per image
        fb = [xyxy(r) for r in rows if r[0] == "11"]
        if len(fb) > 1:
            u = (min(b[0] for b in fb), min(b[1] for b in fb), max(b[2] for b in fb), max(b[3] for b in fb))
            rows = [r for r in rows if r[0] != "11"] + [row(11, u)]; st["fire boxes merged into one"] += 1
        open(lp, "w").write("".join(" ".join(r) + "\n" for r in rows))

for k, v in sorted(st.items()): print(f"{v:8d}  {k}")
json.dump(dict(st), open(f"{D}/report_label_fix.json", "w"), indent=1)
