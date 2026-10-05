"""Build train_balanced.txt for datasets/processed_v2_plus_v6_v8 (run from that folder).
car and person appear in most images, so they are not used to up-weight an image: every other class is
repeated toward TARGET images per epoch (max CAP repeats), images holding only car/person are kept with
probability P_CP, empty background images with P_BG. Labels are never changed."""
import os, random, collections
TARGET, CAP, P_CP, P_BG = 18000, 5, 0.15, 0.5
N = ['person','bicycle','car','motorcycle','bus','truck','pothole','license_plate','auto','road_construction','accident_scene','fire_accident']
rnd = random.Random(0); D = os.getcwd(); L = []
for f in sorted(os.listdir('images/train')):
    rows = [int(l.split()[0]) for l in open(f'labels/train/{os.path.splitext(f)[0]}.txt') if l.strip()]
    L.append((f, set(rows), collections.Counter(rows)))
img = collections.Counter(c for _, cls, _ in L for c in cls)
rc = {c: min(CAP, max(0.0, TARGET / img[c])) for c in range(12)}
lines, seen, boxes = [], collections.Counter(), collections.Counter()
for f, cls, cnt in L:
    o = cls - {0, 2}
    r = P_BG if not cls else P_CP if not o else max(rc[c] for c in o)
    n = int(r) + (rnd.random() < r - int(r))
    lines += [f'{D}/images/train/{f}'] * n
    for c in cls: seen[c] += n
    for c, k in cnt.items(): boxes[c] += k * n
open('train_balanced.txt', 'w').write('\n'.join(lines) + '\n')
print(f'train_balanced.txt: {len(lines)} images per epoch')
print(f"{'class':18s} {'train imgs':>10s} {'imgs/epoch':>10s} {'boxes/epoch':>11s}")
for c in range(12): print(f'{N[c]:18s} {img[c]:10d} {seen[c]:10d} {boxes[c]:11d}')
