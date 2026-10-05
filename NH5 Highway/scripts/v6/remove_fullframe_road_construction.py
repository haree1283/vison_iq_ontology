#!/usr/bin/env python3
"""Drop the full-frame road_construction (class 9) label lines in processed_v2_plus_v6_v3:
some merged sources (obstacle_detection and others tagged v6_*) carried a whole-image scene
label ("this photo is a construction scene") into the object detector's label files as a literal
"9 0.5 0.5 1.0 1.0" box. Mixed in with the other two road_construction conventions already in this
class (small individual objects ~83% of boxes, wide zone boxes ~13.5%), these full-frame boxes
(~3.4%, area > 0.9) carry zero localization signal and were pulling training toward "the whole
image is a valid box" -- one likely contributor to road_construction's precision collapsing to
0.125 in the v3_13class run. Only the offending LINES are removed, not the images/other boxes in
them, since an image can still have legitimate boxes for other classes."""
import os

V3 = "/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway/datasets/processed_v2_plus_v6_v3"
RC_ID = 9
AREA_THRESHOLD = 0.9

removed_lines = 0
touched_files = 0
for sp in ("train", "val", "test"):
    d = f"{V3}/labels/{sp}"
    for f in os.listdir(d):
        if not f.endswith(".txt"):
            continue
        path = f"{d}/{f}"
        lines = open(path).read().splitlines()
        kept = []
        changed = False
        for l in lines:
            p = l.split()
            if p and int(p[0]) == RC_ID and float(p[3]) * float(p[4]) > AREA_THRESHOLD:
                removed_lines += 1
                changed = True
                continue
            kept.append(l)
        if changed:
            touched_files += 1
            open(path, "w").write("\n".join(kept) + ("\n" if kept else ""))

for f in os.listdir(f"{V3}/labels"):
    if f.endswith(".cache"):
        os.remove(f"{V3}/labels/{f}")

print(f"removed {removed_lines} full-frame road_construction lines across {touched_files} label files")
