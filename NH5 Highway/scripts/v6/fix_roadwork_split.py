import re, glob, os, random, shutil, collections, json

random.seed(42)
ROOT = "/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway/datasets/processed_v2_plus_v6_v3"
os.chdir(ROOT)

SPLITS = ['train', 'val', 'test']
TARGET_RATIO = {'train': 0.915, 'val': 0.044, 'test': 0.041}  # mirrors overall dataset split

def city_and_group(basename):
    # basename has no extension
    m = re.match(r'^roadwork_(?:cmu_roadworkcmu_)?([a-z_]+?)_([0-9a-f]{16,40})_(\d{6})_(\d+)$', basename)
    if m:
        city, h, sub, frame = m.groups()
        return city, f"{city}|{h}|{sub}"   # group = one clip/subclip, all frames stay together
    m = re.match(r'^roadwork_(?:cmu_roadworkcmu_)?([a-z]+?\d*)_(\d+)$', basename)
    if m:
        city, num = m.groups()
        return city, f"{city}|{num}"       # no hash -> treat each numbered file independently
    m = re.match(r'^roadwork_(?:cmu_roadworkcmu_)?(IMG)_(\d+)$', basename)
    if m:
        return 'phone', f"phone|{basename}"
    return 'other', basename

# 1. inventory all roadwork_* label files across all splits
records = []  # (city, group, split, basename)
for split in SPLITS:
    for path in glob.glob(f'labels/{split}/roadwork_*.txt'):
        basename = os.path.basename(path)[:-4]
        city, group = city_and_group(basename)
        records.append((city, group, split, basename))

print(f"Total roadwork_* files: {len(records)}")

# 2. group by city -> set of unique groups
city_groups = collections.defaultdict(set)
group_files = collections.defaultdict(list)
for city, group, split, basename in records:
    city_groups[city].add(group)
    group_files[group].append(basename)

print(f"Cities found: {len(city_groups)}")
for c, gs in sorted(city_groups.items(), key=lambda x: -len(x[1])):
    print(f"  {c:20s} groups={len(gs):5d} files={sum(len(group_files[g]) for g in gs):5d}")

# 3. reassign each city's groups to train/val/test proportionally to file count
new_split_of_group = {}
for city, groups in city_groups.items():
    groups = sorted(groups)
    random.shuffle(groups)
    # order groups by size desc isn't needed; just cumulative-file-count based assignment
    total_files = sum(len(group_files[g]) for g in groups)
    if total_files == 0:
        continue
    cum = 0
    for g in groups:
        cum += len(group_files[g])
        frac = cum / total_files
        if frac <= TARGET_RATIO['train']:
            new_split_of_group[g] = 'train'
        elif frac <= TARGET_RATIO['train'] + TARGET_RATIO['val']:
            new_split_of_group[g] = 'val'
        else:
            new_split_of_group[g] = 'test'
    # ensure at least one group in val and test if city has >=3 groups
    assigned_splits = set(new_split_of_group[g] for g in groups)
    if len(groups) >= 3 and assigned_splits == {'train'}:
        new_split_of_group[groups[-1]] = 'val'
        if len(groups) >= 5:
            new_split_of_group[groups[-2]] = 'test'

# 4. build move list: (basename, old_split, new_split)
moves = []
old_split_of_basename = {}
for city, group, split, basename in records:
    old_split_of_basename[basename] = split
for group, files in group_files.items():
    new_split = new_split_of_group.get(group)
    if new_split is None:
        continue
    for basename in files:
        old_split = old_split_of_basename[basename]
        if old_split != new_split:
            moves.append((basename, old_split, new_split))

print(f"\nPlanned moves: {len(moves)} / {len(records)} files")
mv_by_pair = collections.Counter((m[1], m[2]) for m in moves)
for (o, n), c in mv_by_pair.items():
    print(f"  {o} -> {n}: {c}")

with open('/tmp/roadwork_split_moves.json', 'w') as f:
    json.dump(moves, f)
print("\nSaved move manifest to /tmp/roadwork_split_moves.json (dry run only, no files touched yet)")
