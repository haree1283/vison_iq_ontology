#!/usr/bin/env python3
"""Split road_construction (class 9) in processed_v2_plus_v6_v3 into two classes: the two
conventions merged into it (see remove_fullframe_road_construction.py for the third, already
removed) draw fundamentally different things -- ~83% are small individual objects (cones,
barrels, equipment, area < 0.05 of the frame) and ~13.5% are wide work-zone boxes spanning most
of the frame (area 0.05-0.9). Forcing one class to mean both is why precision collapsed to 0.125
in the v3_13class run: the model can't converge on one box shape for two different concepts.

class 9 "road_construction" keeps the small-object boxes (majority, and more actionable for a
safety system -- "there's a barrier/cone in the road" localizes something to react to).
class 13 (new) "construction_zone" gets the wide boxes -- "this stretch of road is a work zone."

nc goes from 13 to 14; this is added at the end (13) rather than renumbering, so no other class
id shifts and the existing label files for every other class stay valid as-is."""
import os

V3 = "/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway/datasets/processed_v2_plus_v6_v3"
ROAD_CONSTRUCTION_ID = 9
CONSTRUCTION_ZONE_ID = 13
SPLIT_AREA = 0.05

reassigned = 0
touched_files = 0
for sp in ("train", "val", "test"):
    d = f"{V3}/labels/{sp}"
    for f in os.listdir(d):
        if not f.endswith(".txt"):
            continue
        path = f"{d}/{f}"
        lines = open(path).read().splitlines()
        out, changed = [], False
        for l in lines:
            p = l.split()
            if p and int(p[0]) == ROAD_CONSTRUCTION_ID and float(p[3]) * float(p[4]) >= SPLIT_AREA:
                out.append(" ".join([str(CONSTRUCTION_ZONE_ID)] + p[1:]))
                reassigned += 1
                changed = True
            else:
                out.append(l)
        if changed:
            touched_files += 1
            open(path, "w").write("\n".join(out) + ("\n" if out else ""))

for f in os.listdir(f"{V3}/labels"):
    if f.endswith(".cache"):
        os.remove(f"{V3}/labels/{f}")

print(f"reassigned {reassigned} wide-zone boxes to new class {CONSTRUCTION_ZONE_ID} across {touched_files} files")
