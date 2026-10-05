#!/bin/bash
# After epoch 100: per-class val of best.pt, then full video tests of final v8 + v6/v5 baselines, then report.
cd "/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway"
RUN=runs/detect/runs/detect/runs/nh5_v8/v8n_960_100ep; V=runs/verify
cp $RUN/weights/best.pt $V/final_best.pt; cp $RUN/weights/last.pt $V/final_last.pt
echo "$(date '+%F %T') FINAL: val best.pt" >> $V/verify.log
/home/nikhil/.local/bin/yolo detect val model=$V/final_best.pt data=datasets/processed_v2_plus_v6_v8/data_train.yaml imgsz=960 batch=16 device=0 \
     workers=4 plots=True project="$PWD/$V" name=final_val exist_ok=True > $V/final_val.log 2>&1
scripts/v8/milestone_verify.sh v8_ep100 $V/final_best.pt 960
scripts/v8/milestone_verify.sh base_v6 models/archive/nh5_v6_best.pt 640
for M in 30 40 50 60 70 80 90; do [ -f $V/ep${M}_best.pt ] && scripts/v8/milestone_verify.sh v8_ep$M "$PWD/$V/ep${M}_best.pt" 960; done
python3 scripts/v8/verify_report.py > /dev/null 2>&1
echo "$(date '+%F %T') FINAL COMPLETE -> runs/verify/report.md, runs/verify/final_val.log" >> $V/verify.log
touch $V/done_final
