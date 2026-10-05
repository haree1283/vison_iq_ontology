#!/usr/bin/env python3
"""Validate + clean processed_v2_plus_v6_v3: (1) image<->label pairing (delete orphan labels; images without a label
file get an empty one = background), (2) unreadable/tiny images removed with their labels, (3) label lines: 5 fields,
class 0..nc-1 (nc read live from data.yaml), coords clamped to [0,1], w/h>0, exact duplicate lines removed, invalid
lines dropped, (4) identical image bytes appearing in more than one split -> kept in train only, (5) stale .cache
files removed. Prints a summary."""
import cv2, hashlib, os, collections, yaml
V = "/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway/datasets/processed_v2_plus_v6_v3"
NC = yaml.safe_load(open(f"{V}/data.yaml"))["nc"]  # read from data.yaml, not hardcoded -- a stale
                                                     # copy of this number here once silently deleted
                                                     # a newly-added class's boxes as "invalid" (2026-09-23)
st = collections.Counter(); seen = {}
for sp in ("train", "val", "test"):
    imgs = {f.rsplit(".", 1)[0]: f for f in os.listdir(f"{V}/images/{sp}")}
    labs = {f[:-4] for f in os.listdir(f"{V}/labels/{sp}") if f.endswith(".txt")}
    for n in labs - imgs.keys(): os.remove(f"{V}/labels/{sp}/{n}.txt"); st["orphan labels removed"] += 1
    for n in imgs.keys() - labs: open(f"{V}/labels/{sp}/{n}.txt", "w").close(); st["missing labels -> empty"] += 1
    for n, f in imgs.items():
        ip, lp = f"{V}/images/{sp}/{f}", f"{V}/labels/{sp}/{n}.txt"
        im = cv2.imread(ip)
        if im is None or min(im.shape[:2]) < 32:
            os.remove(ip); os.path.exists(lp) and os.remove(lp); st["bad/tiny images removed"] += 1; continue
        h = hashlib.md5(open(ip, "rb").read()).hexdigest()
        if h in seen and seen[h] != sp:   # same image already in an earlier split (train > val > test): keep that one
            os.remove(ip); os.remove(lp); st[f"cross-split duplicate removed from {sp}"] += 1; continue
        seen.setdefault(h, sp)
        out, ch = [], False
        for l in open(lp).read().splitlines():
            p = l.split()
            if not p: continue
            try: c = int(p[0]); x, y, w, hh = map(float, p[1:5])
            except Exception: ch = True; st["invalid label lines dropped"] += 1; continue
            if len(p) != 5 or not 0 <= c < NC or w <= 0 or hh <= 0: ch = True; st["invalid label lines dropped"] += 1; continue
            x0, y0, x1, y1 = max(0, x-w/2), max(0, y-hh/2), min(1, x+w/2), min(1, y+hh/2)
            if x1-x0 <= 1e-4 or y1-y0 <= 1e-4: ch = True; st["degenerate boxes dropped"] += 1; continue
            nl = f"{c} {(x0+x1)/2:.6f} {(y0+y1)/2:.6f} {x1-x0:.6f} {y1-y0:.6f}"
            if nl != l: ch = True; st["boxes clamped/normalised"] += (abs(x0 - (x-w/2)) > 1e-6 or x1 != x+w/2 or y0 != y-hh/2 or y1 != y+hh/2)
            if nl in out: ch = True; st["duplicate lines removed"] += 1; continue
            out.append(nl)
        if ch: 
            os.unlink(lp); open(lp, "w").write("\n".join(out) + ("\n" if out else ""))
for f in os.listdir(f"{V}/labels"):
    if f.endswith(".cache"): os.remove(f"{V}/labels/{f}"); st["cache removed"] += 1
tot = {sp: len(os.listdir(f"{V}/images/{sp}")) for sp in ("train", "val", "test")}
print(dict(st)); print("images", tot, sum(tot.values()))
