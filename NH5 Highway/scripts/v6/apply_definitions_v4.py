"""Make v4 labels match the class definitions (only touches datasets/processed_v2_plus_v6_v4; backups in runs/):
 1. fire_accident = fire/smoke after an accident: move D-Fire (dfire_*) fire images with NO vehicle/person to a side folder.
 2. road_construction = repair / blocked-road work zone: merge all class-9 boxes in an image into ONE padded union box.
 3. accident_scene = the collision: boxes covering >=60% of the frame shrink to the padded union of labeled vehicles/persons."""
import os, glob, json, shutil, collections
R = "datasets/processed_v2_plus_v6_v4"; SIDE = "datasets/v6/public_fire_smoke/_out_no_vehicle_dfire"
VEH = {"0", "1", "2", "3", "4", "5"}
def union(rows, pad):
    x1 = min(float(p[1]) - float(p[3]) / 2 for p in rows); x2 = max(float(p[1]) + float(p[3]) / 2 for p in rows)
    y1 = min(float(p[2]) - float(p[4]) / 2 for p in rows); y2 = max(float(p[2]) + float(p[4]) / 2 for p in rows)
    pw, ph = (x2 - x1) * pad, (y2 - y1) * pad
    x1, y1, x2, y2 = max(0, x1 - pw), max(0, y1 - ph), min(1, x2 + pw), min(1, y2 + ph)
    return (x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1
fmt = lambda c, b: f"{c} {b[0]:.6f} {b[1]:.6f} {b[2]:.6f} {b[3]:.6f}"
moved = []; rc_bk = {}; acc_bk = {}; n = collections.Counter()
for sp in ("train", "val", "test"):
    os.makedirs(f"{SIDE}/images/{sp}", exist_ok=True); os.makedirs(f"{SIDE}/labels/{sp}", exist_ok=True)
    for f in glob.glob(f"{R}/labels/{sp}/*.txt"):
        b = os.path.basename(f); stem = b[:-4]
        lines = [l for l in open(f).read().splitlines() if l.strip()]; rows = [l.split() for l in lines]
        cls = [r[0] for r in rows]
        # 1. fire scope
        if stem.startswith("dfire_") and "12" in cls and not (set(cls) & VEH):
            for e in (".jpg", ".png", ".jpeg"):
                if os.path.exists(f"{R}/images/{sp}/{stem}{e}"):
                    shutil.move(f"{R}/images/{sp}/{stem}{e}", f"{SIDE}/images/{sp}/{stem}{e}"); break
            shutil.move(f, f"{SIDE}/labels/{sp}/{b}"); moved.append(f"{sp}/{stem}"); n["fire images moved out (no vehicle/person)"] += 1; continue
        new = None
        # 2. road work zone
        rc = [r for r in rows if r[0] == "9"]
        if len(rc) >= 2:
            rc_bk[f"{sp}/{b}"] = lines
            rest = [l for l, r in zip(lines, rows) if r[0] != "9"]
            lines = rest + [fmt(9, union(rc, 0.02))]; rows = [l.split() for l in lines]; new = lines; n["road_construction images merged to 1 zone box"] += 1
        # 3. accident tighten
        vehs = [r for r in rows if r[0] in VEH]
        big = [i for i, r in enumerate(rows) if r[0] == "10" and float(r[3]) * float(r[4]) >= 0.6]
        if big and vehs:
            acc_bk.setdefault(f"{sp}/{b}", [l for l in open(f).read().splitlines() if l.strip()])
            u = union(vehs, 0.05)
            for i in big:  # guard: only when the labeled vehicles cover >=30% of the original box (auto-labeler misses wrecks)
                if u[2] * u[3] / (float(rows[i][3]) * float(rows[i][4])) >= 0.30: lines[i] = fmt(10, u); new = lines; n["accident boxes tightened to vehicles/persons"] += 1
        if new is not None: open(f, "w").write("\n".join(new) + "\n")
json.dump(moved, open("runs/dfire_moved_out_list.json", "w")); json.dump(rc_bk, open("runs/rc_zone_backup.json", "w")); json.dump(acc_bk, open("runs/accident_tighten_backup.json", "w"))
for k, v in n.items(): print(f"{v:6d}  {k}")
