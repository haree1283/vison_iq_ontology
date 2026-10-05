"""Add D-Fire (public HF dataset badsaarow/d-fire) to datasets/processed_v2_plus_v6_v4.
fire + smoke boxes -> class 12 (fire_accident). Images with no fire/smoke are kept as background negatives (capped).
Only public data; nothing from vedios/."""
import glob, os, io, json, hashlib, random
import pyarrow.parquet as pq
random.seed(7)
SRC = "/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway/datasets/v6/public_fire_smoke/badsaarow__d-fire/data"
DST = "/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway/datasets/processed_v2_plus_v6_v4"
MAX_NEG = 3000
def split_of(name):
    h = int(hashlib.md5(name.encode()).hexdigest(), 16) % 100
    return 'val' if h < 4 else 'test' if h < 8 else 'train'
pos = neg = 0
added = []
for f in sorted(glob.glob(f"{SRC}/*.parquet")):
    pf = pq.ParquetFile(f)
    for batch in pf.iter_batches(batch_size=200):
        for r in batch.to_pylist():
            name = "dfire_" + r['filename'].rsplit('.', 1)[0]
            lines = []
            for l in (r['label'] or '').splitlines():
                p = l.split()
                if len(p) >= 5:
                    lines.append("12 " + " ".join(p[1:5]) + "\n")
            if not lines:
                if neg >= MAX_NEG or random.random() > 0.35:
                    continue
                neg += 1
            else:
                pos += 1
            sp = split_of(name)
            ext = os.path.splitext(r['filename'])[1].lower() or '.jpg'
            open(f"{DST}/images/{sp}/{name}{ext}", "wb").write(r['image']['bytes'])
            open(f"{DST}/labels/{sp}/{name}.txt", "w").writelines(lines)
            added.append(f"{sp}/{name}{ext}")
    print(f, "pos", pos, "neg", neg, flush=True)
json.dump(added, open(f"{DST}/dfire_added.json", "w"))
print("DONE positives", pos, "negatives", neg, flush=True)
