"""Merge a YOLO-format public fire/smoke dataset into processed_v2_plus_v6_v4 as class 12 (fire_accident).
Usage: add_yolo_fire_to_v4.py <dataset_root> <prefix> <added.json>   (polygon labels -> bounding boxes; images hardlinked)"""
import sys, os, glob, json, hashlib
root, prefix, out = sys.argv[1:4]
DST = "/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway/datasets/processed_v2_plus_v6_v4"
def split_of(n):
    h = int(hashlib.md5(n.encode()).hexdigest(), 16) % 100
    return 'val' if h < 4 else 'test' if h < 8 else 'train'
added = []; skipped = 0
for lf in glob.glob(f"{root}/**/labels/*.txt", recursive=True):
    base = os.path.basename(lf)[:-4]
    imgdir = os.path.dirname(os.path.dirname(lf)) + "/images"
    img = next((f"{imgdir}/{base}{e}" for e in ('.jpg', '.jpeg', '.png') if os.path.exists(f"{imgdir}/{base}{e}")), None)
    if not img: skipped += 1; continue
    lines = []
    for l in open(lf):
        p = l.split()
        if len(p) == 5:
            lines.append("12 " + " ".join(p[1:5]) + "\n")
        elif len(p) >= 7 and len(p) % 2 == 1:
            xs = [float(v) for v in p[1::2]]; ys = [float(v) for v in p[2::2]]
            x1, x2, y1, y2 = min(xs), max(xs), min(ys), max(ys)
            lines.append(f"12 {(x1+x2)/2:.6f} {(y1+y2)/2:.6f} {x2-x1:.6f} {y2-y1:.6f}\n")
    if not lines: skipped += 1; continue
    name = f"{prefix}{base}"[:180]; sp = split_of(name); ext = os.path.splitext(img)[1]
    d = f"{DST}/images/{sp}/{name}{ext}"
    if not os.path.exists(d): os.link(img, d)
    open(f"{DST}/labels/{sp}/{name}.txt", "w").writelines(lines)
    added.append(f"{sp}/{name}{ext}")
json.dump(added, open(out, "w"))
print("added", len(added), "skipped", skipped)
