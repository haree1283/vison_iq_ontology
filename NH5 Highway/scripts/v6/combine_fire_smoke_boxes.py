"""Combine separate fire + smoke boxes (all class 12 = fire_accident) into ONE box per image: the padded union of every
fire/smoke box, matching the scene-level fire_accident convention (fire and its smoke are one event).
Only touches labels whose filename starts with the given prefixes and that have >=2 class-12 boxes. Idempotent.
Usage: combine_fire_smoke_boxes.py dfire_ [jimei_ firesafety_ ...]   (saves originals for revert in runs/fire_box_combine_backup.json)"""
import sys, glob, json, os
ROOT = "datasets/processed_v2_plus_v6_v4"; PAD = 0.03
prefixes = tuple(sys.argv[1:]); assert prefixes, "give at least one filename prefix"
BK = "runs/fire_box_combine_backup.json"
backup = json.load(open(BK)) if os.path.exists(BK) else {}
changed = 0; before = after = 0
for sp in ("train", "val", "test"):
    for f in glob.glob(f"{ROOT}/labels/{sp}/*.txt"):
        b = os.path.basename(f)
        if not b.startswith(prefixes): continue
        lines = [l for l in open(f).read().splitlines() if l.strip()]
        fire = [l.split() for l in lines if l.split()[0] == "12"]
        if len(fire) < 2: continue
        rest = [l for l in lines if l.split()[0] != "12"]
        x1 = min(float(p[1]) - float(p[3]) / 2 for p in fire); x2 = max(float(p[1]) + float(p[3]) / 2 for p in fire)
        y1 = min(float(p[2]) - float(p[4]) / 2 for p in fire); y2 = max(float(p[2]) + float(p[4]) / 2 for p in fire)
        pw, ph = (x2 - x1) * PAD, (y2 - y1) * PAD
        x1, y1, x2, y2 = max(0, x1 - pw), max(0, y1 - ph), min(1, x2 + pw), min(1, y2 + ph)
        backup.setdefault(f"{sp}/{b}", lines)
        open(f, "w").write("\n".join(rest + [f"12 {(x1+x2)/2:.6f} {(y1+y2)/2:.6f} {x2-x1:.6f} {y2-y1:.6f}"]) + "\n")
        changed += 1; before += len(fire); after += 1
json.dump(backup, open(BK, "w"))
print(f"combined {changed} images: {before} separate fire/smoke boxes -> {after} boxes (backup: {BK})")
