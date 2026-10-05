#!/bin/bash
# Full, independent backup of the v8 model + dataset + everything around it (real copies, not links).
set -u
SRC="/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway"
B="$HOME/Backups/NH5_v8_final_2026-09-28"
cd "$SRC"
mkdir -p "$B"/{models/snapshots,dataset,training_run,verification,onnx,video_tests,web_compare,code}
echo "$(date '+%F %T') start"

# models
cp -a models/nh5_v8_final_ep100.pt models/nh5_v8_ep60_overhead_plates.pt "$B/models/"
cp -a runs/onnx/nh5_v8_int8.onnx runs/onnx/nh5_v8_fp32.onnx "$B/models/"
cp -a runs/verify/ep{30,40,50,60,70,80,90}_best.pt "$B/models/snapshots/"

# training run (results.csv, args.yaml, weights incl. last.pt, plots)
rsync -a runs/detect/runs/detect/runs/nh5_v8/v8n_960_100ep "$B/training_run/"

# reports / conversion / website comparison
rsync -a --exclude '*.pt' runs/verify/ "$B/verification/"
rsync -a runs/onnx/ "$B/onnx/"
rsync -a runs/web_compare/ "$B/web_compare/"

# video tests: full v8 results; only summaries + plate text for the other models (their videos are 15 GB)
rsync -a runs/video_tests/v8_ep100 "$B/video_tests/"
rsync -a --copy-links runs/video_tests/v8_final_by_video "$B/video_tests/" 2>/dev/null || rsync -a runs/video_tests/v8_final_by_video "$B/video_tests/"
for d in base_v5 base_v6 v8_ep30 v8_ep40 v8_ep50 v8_ep60 v8_ep70 v8_ep80 v8_ep90; do
  rsync -a --include '*/' --include 'summary.json' --include '*.txt' --exclude '*' "runs/video_tests/$d" "$B/video_tests/"
done

# code as it is today
rsync -a app.py event_engine.py templates static "$B/code/"
rsync -a --exclude '__pycache__' scripts "$B/code/"

# dataset (largest part, last) + copies of the yaml/list pointing at the backup location
rsync -a datasets/processed_v2_plus_v6_v8 "$B/dataset/"
D="$B/dataset/processed_v2_plus_v6_v8"
sed "s#$SRC/datasets/processed_v2_plus_v6_v8#$D#g" "$D/data_train.yaml" > "$D/data_train_BACKUP_PATHS.yaml"
sed "s#$SRC/datasets/processed_v2_plus_v6_v8#$D#g" "$D/train_balanced.txt" > "$D/train_balanced_BACKUP_PATHS.txt"
sed -i "s#train_balanced.txt#train_balanced_BACKUP_PATHS.txt#" "$D/data_train_BACKUP_PATHS.yaml"

# integrity: checksums of the models, counts of the dataset
( cd "$B/models" && sha256sum *.pt *.onnx snapshots/*.pt > SHA256SUMS )
for s in train val test; do
  echo "$s images: $(ls "$D/images/$s" 2>/dev/null | wc -l)  src: $(ls "datasets/processed_v2_plus_v6_v8/images/$s" 2>/dev/null | wc -l)"
done > "$B/dataset/COUNTS.txt"
du -sh "$B" > "$B/SIZE.txt"
echo "$(date '+%F %T') BACKUP_DONE"
