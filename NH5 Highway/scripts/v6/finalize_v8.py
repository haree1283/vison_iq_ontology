"""Final v8 QA + packaging: label sanity (fix/drop bad lines), orphan cleanup, train/val/test leakage check, class counts, weak-class repeat list."""
import os, re, glob, json, collections, hashlib
D = os.path.abspath("datasets/processed_v2_plus_v6_v8"); NAMES = ['person','bicycle','car','motorcycle','bus','truck','pothole','license_plate','auto','road_construction','accident_scene','fire_accident']
REP = {6: 2, 1: 2, 11: 2}   # extra passes for the weak classes (pothole, bicycle, fire_accident)
stats = collections.Counter(); files = {}
for sp in ("train", "val", "test"):
    imgs = {os.path.splitext(f)[0]: f for f in os.listdir(f"{D}/images/{sp}")}; labs = {f[:-4] for f in os.listdir(f"{D}/labels/{sp}")}
    for s in labs - set(imgs): os.remove(f"{D}/labels/{sp}/{s}.txt"); stats["orphan labels removed"] += 1
    for s in set(imgs) - labs: os.remove(f"{D}/images/{sp}/{imgs[s]}"); stats["orphan images removed"] += 1
    files[sp] = {s: imgs[s] for s in imgs if s in labs}
cnt = {sp: (collections.Counter(), collections.Counter()) for sp in files}; dups = collections.Counter(); bad_files = 0
for sp, d in files.items():
    for s in d:
        p = f"{D}/labels/{sp}/{s}.txt"; out = []; changed = False
        for l in open(p):
            q = l.split()
            if not q: continue
            try:
                c = int(q[0]); x, y, w, h = map(float, q[1:5]); ok = 0 <= c <= 11 and 0 <= x <= 1 and 0 <= y <= 1 and 0 < w <= 1.0001 and 0 < h <= 1.0001 and len(q) == 5
            except Exception: ok = False
            if not ok: changed = True; stats["bad label lines dropped"] += 1; continue
            key = " ".join(q)
            if key in out: changed = True; stats["duplicate boxes dropped"] += 1; continue
            out.append(key)
        if changed: open(p, "w").write("\n".join(out) + ("\n" if out else ""))
        for c in {int(k.split()[0]) for k in out}: cnt[sp][0][c] += 1
        for k in out: cnt[sp][1][int(k.split()[0])] += 1
def base(s): return re.sub(r"(_(pothaug\d*|balpot\d*|aug\d*|bal[a-z]*\d*))+$", "", re.sub(r"\.rf\.[0-9a-f]{20,}", "", s))
tb = {base(s) for s in files["train"]}; leak = {sp: sum(1 for s in files[sp] if base(s) in tb) for sp in ("val", "test")}
print("LEAKAGE (val/test images whose original also appears in train):", leak, "of", {sp: len(files[sp]) for sp in ("val", "test")})
print(f"\n{'class':18s} | {'train imgs':>10s} {'boxes':>7s} | {'val imgs':>8s} {'boxes':>6s} | {'test imgs':>9s} {'boxes':>6s}")
for k in range(12): print(f"{NAMES[k]:18s} | {cnt['train'][0][k]:10d} {cnt['train'][1][k]:7d} | {cnt['val'][0][k]:8d} {cnt['val'][1][k]:6d} | {cnt['test'][0][k]:9d} {cnt['test'][1][k]:6d}")
print({sp: len(files[sp]) for sp in files}, dict(stats))
# training list with repeats for the weak classes
lines = []; per = collections.Counter()
for s, f in files["train"].items():
    cls = {int(l.split()[0]) for l in open(f"{D}/labels/train/{s}.txt") if l.strip()}
    rf = max([REP.get(c, 1) for c in cls] or [1]); lines += [f"{D}/images/train/{f}"] * rf
    for c in cls: per[c] += rf
open(f"{D}/train_balanced.txt", "w").write("\n".join(lines) + "\n")
open(f"{D}/data_train.yaml", "w").write(f"path: {D}\ntrain: {D}/train_balanced.txt\nval: {D}/images/val\ntest: {D}/images/test\nnc: 12\nnames: {NAMES}\n")
print(f"\ntrain list length {len(lines)} (unique {len(files['train'])}); images per class after repeats:", {NAMES[k]: per[k] for k in range(12)})
print("imbalance most/least: %.1fx" % (max(per[k] for k in range(12)) / max(1, min(per[k] for k in range(12)))))
json.dump({"leak": leak}, open(f"{D}/qa_report.json", "w"))
