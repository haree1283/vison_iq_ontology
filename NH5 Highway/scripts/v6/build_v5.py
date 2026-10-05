"""Build datasets/processed_v2_plus_v6_v5 from v4 without touching v4 (images hardlinked, labels copied):
 - train: keep each original + at most 2 augmented copies (was up to 11 copies per original)
 - val: add ~10% of RDD2022 pothole originals (all their copies removed from train) so pothole validation matches its training data
 - test unchanged."""
import os, re, glob, random, shutil, collections, json
random.seed(5)
S = "datasets/processed_v2_plus_v6_v4"; D = "datasets/processed_v2_plus_v6_v5"; MAX_AUG = 2
AUG = re.compile(r'(_(?:pothaug\d*|balpot\d*|aug\d*|bal[a-z]*\d*))+$', re.I)
clean = lambda b: re.sub(r'\.rf\.[0-9a-f]{20,}', '', b)
base = lambda b: AUG.sub('', clean(b)); isaug = lambda b: bool(AUG.search(clean(b)))
for sp in ("train", "val", "test"):
    os.makedirs(f"{D}/images/{sp}", exist_ok=True); os.makedirs(f"{D}/labels/{sp}", exist_ok=True)
def img_of(sp, stem):
    for e in (".jpg", ".png", ".jpeg"):
        if os.path.exists(f"{S}/images/{sp}/{stem}{e}"): return e
def put(sp_src, sp_dst, stem):
    e = img_of(sp_src, stem)
    if e is None: return False
    os.link(f"{S}/images/{sp_src}/{stem}{e}", f"{D}/images/{sp_dst}/{stem}{e}")
    shutil.copy2(f"{S}/labels/{sp_src}/{stem}.txt", f"{D}/labels/{sp_dst}/{stem}.txt"); return True
groups = collections.defaultdict(list)
for f in glob.glob(f"{S}/labels/train/*.txt"):
    b = os.path.basename(f)[:-4]; groups[base(b)].append(b)
# RDD2022 originals with at least one pothole box -> validation
def has_pothole(stem):
    return any(l.split() and l.split()[0] == "6" for l in open(f"{S}/labels/train/{stem}.txt"))
rdd = [g for g, v in groups.items() if g.startswith("rdd") and any(not isaug(x) and has_pothole(x) for x in v)]
random.shuffle(rdd); to_val = set(rdd[:int(len(rdd) * 0.10)])
n = collections.Counter()
for g, stems in groups.items():
    orig = [s for s in stems if not isaug(s)]; aug = [s for s in stems if isaug(s)]
    if g in to_val:
        for s in orig[:1]: n["rdd originals moved to val"] += put("train", "val", s)
        continue
    random.shuffle(aug); keep = orig + aug[:MAX_AUG]
    n["train files dropped (extra augmented copies)"] += len(stems) - len(keep)
    for s in keep: n["train files kept"] += put("train", "train", s)
for sp in ("val", "test"):
    for f in glob.glob(f"{S}/labels/{sp}/*.txt"):
        put(sp, sp, os.path.basename(f)[:-4]); n[f"{sp} files copied"] += 1
open(f"{D}/data.yaml", "w").write(open(f"{S}/data.yaml").read().replace("processed_v2_plus_v6_v4", "processed_v2_plus_v6_v5"))
json.dump(dict(n), open(f"{D}/build_report.json", "w"), indent=1)
for k, v in n.items(): print(f"{v:7d}  {k}")
