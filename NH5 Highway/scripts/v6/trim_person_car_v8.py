"""Trim person/car dominance in v8 train: drop (move aside, reversible) images that hold person/car boxes but none of the weak/rare classes."""
import os, glob, random, shutil, collections, json
random.seed(17); D = "datasets/processed_v2_plus_v6_v8"; SIDE = "datasets/v6/_dropped_person_car_v8"
PROTECT = {1, 4, 6, 8, 9, 10, 11}; PT = 45000; CT = 45000   # also protect bus and auto (auto accidents need them)
info = {}
for f in glob.glob(f"{D}/labels/train/*.txt"):
    c = collections.Counter(int(l.split()[0]) for l in open(f) if l.strip()); info[os.path.basename(f)[:-4]] = c
tot = collections.Counter()
for c in info.values(): tot.update(c)
p, c_ = tot[0], tot[2]; print("before: person", p, "car", c_)
pool = [s for s, c in info.items() if (c[0] or c[2]) and not (set(c) & PROTECT)]; random.shuffle(pool)
drop = []; dropped = set()
def take(s):
    global p, c_
    if s in dropped: return
    dropped.add(s); drop.append(s); p -= info[s][0]; c_ -= info[s][2]
for s in pool:                                   # 1) car-only images
    if info[s][0] == 0 and info[s][2] > 0 and c_ > CT: take(s)
mixed = sorted([s for s in pool if s not in dropped and info[s][0] > 0 and info[s][2] > 0], key=lambda s: -info[s][2])
for s in mixed:                                  # 2) mixed images, car-heavy first (they lower both)
    if p <= PT: break
    take(s)
for s in pool:                                   # 3) person-only images if still above target
    if p <= PT: break
    if info[s][2] == 0 and info[s][0] > 0: take(s)
print("after : person", p, "car", c_, "| images dropped:", len(drop))
for sp in ("images", "labels"): os.makedirs(f"{SIDE}/{sp}/train", exist_ok=True)
for s in drop:
    for e in (".jpg", ".png", ".jpeg"):
        if os.path.exists(f"{D}/images/train/{s}{e}"): shutil.move(f"{D}/images/train/{s}{e}", f"{SIDE}/images/train/{s}{e}")
    shutil.move(f"{D}/labels/train/{s}.txt", f"{SIDE}/labels/train/{s}.txt")
json.dump(drop, open("runs/dropped_person_car_v8.json", "w"))
