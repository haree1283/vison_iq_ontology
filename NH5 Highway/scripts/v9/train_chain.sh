#!/bin/bash
# v9 training chain (user-approved 2026-09-28): 8-epoch trial -> v8 vs trial on the leak-free test -> 100-epoch run.
# Both runs fine-tune from the v8 reference model with v8's settings. Idempotent: every stage is skipped when done
# and resumed from last.pt when interrupted, so the service / watchdog can simply re-run this script.
# v8 (models/, datasets/processed_v2_plus_v6_v8, runs/.../nh5_v8) and the website model are never written.
cd "/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway"
YOLO=/home/nikhil/.local/bin/yolo
DATA=datasets/processed_v9/data_train.yaml
CLEAN=datasets/processed_v9/data_clean_test.yaml
V8=models/nh5_v8_final_ep100.pt
P=runs/v9
LOG=$P/chain.log; mkdir -p $P
say() { echo "$(date '+%F %T') $*" | tee -a $LOG; }
COMMON="data=$DATA imgsz=960 batch=32 workers=8 device=0 optimizer=SGD lr0=0.01 lrf=0.01 cos_lr=True warmup_epochs=3 close_mosaic=10 patience=100 plots=True"

epochs_done() { [ -f "$1/results.csv" ] && tail -n +2 "$1/results.csv" | grep -c . || echo 0; }
resumable() { /usr/bin/python3 scripts/v8/ckpt_ok.py "$1" >/dev/null 2>&1; }

run() {  # $1 name  $2 epochs  $3 save_period
  local d=$P/$1 w=$P/$1/weights/last.pt
  if [ "$(epochs_done $d)" -ge "$2" ] && ! resumable "$w"; then say "$1 already complete"; return 0; fi
  if [ -f "$w" ] && resumable "$w"; then
    say "$1 resume from epoch $(epochs_done $d)"; $YOLO detect train resume model="$PWD/$w" >> $P/$1.log 2>&1
  else
    say "$1 start ($2 epochs, from v8)"
    $YOLO detect train model=$V8 $COMMON epochs=$2 save_period=$3 project="$PWD/$P" name=$1 exist_ok=True >> $P/$1.log 2>&1
  fi
  local rc=$?; say "$1 exit code $rc, epochs done $(epochs_done $d)"
  [ "$(epochs_done $d)" -ge "$2" ]
}

compare() {  # v8 vs a v9 model on the leak-free test set -> $P/compare_<tag>.txt
  local out=$P/compare_$1.txt
  [ -s "$out" ] && return 0
  for m in "$V8" "$2"; do
    echo "== $m" >> $out
    $YOLO detect val model="$m" data=$CLEAN imgsz=960 batch=16 device=0 plots=False project="$PWD/$P" name=val_$1 exist_ok=True 2>&1 \
      | sed 's/\x1b\[[0-9;]*[A-Za-z]//g' | grep -E "^\s+(all|person|bicycle|car|motorcycle|bus|truck|pothole|license_plate|auto|road_construction|accident_scene|fire_accident)\s+[0-9]" >> $out
  done
  say "comparison written: $out"
}

run v9_trial8 8 -1 || { say "trial not finished -> stop (will resume)"; exit 1; }
compare trial8 $P/v9_trial8/weights/best.pt
run v9_100ep 100 10 || { say "100-epoch run not finished -> stop (will resume)"; exit 1; }
compare 100ep $P/v9_100ep/weights/best.pt
say "CHAIN COMPLETE"
touch $P/CHAIN_COMPLETE
