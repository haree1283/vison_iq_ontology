import json, os, shutil

ROOT = "/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway/datasets/processed_v2_plus_v6_v3"
os.chdir(ROOT)

with open('/tmp/roadwork_split_moves.json') as f:
    moves = json.load(f)

manifest = []
errors = []
done = 0
for basename, old_split, new_split in moves:
    old_label = f'labels/{old_split}/{basename}.txt'
    new_label = f'labels/{new_split}/{basename}.txt'
    # find image with matching extension
    img_ext = None
    for ext in ('.jpg', '.png', '.jpeg'):
        if os.path.exists(f'images/{old_split}/{basename}{ext}'):
            img_ext = ext
            break
    if img_ext is None:
        errors.append(f"MISSING IMAGE: {basename} in {old_split}")
        continue
    old_img = f'images/{old_split}/{basename}{img_ext}'
    new_img = f'images/{new_split}/{basename}{img_ext}'
    if not os.path.exists(old_label):
        errors.append(f"MISSING LABEL: {old_label}")
        continue
    if os.path.exists(new_label) or os.path.exists(new_img):
        errors.append(f"COLLISION at destination: {basename} -> {new_split}")
        continue
    shutil.move(old_label, new_label)
    shutil.move(old_img, new_img)
    manifest.append({"basename": basename, "from": old_split, "to": new_split, "img_ext": img_ext})
    done += 1

with open('/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway/runs/roadwork_split_fix_manifest.json', 'w') as f:
    json.dump(manifest, f, indent=1)

print(f"Moved: {done}")
print(f"Errors: {len(errors)}")
for e in errors[:20]:
    print(" ", e)
