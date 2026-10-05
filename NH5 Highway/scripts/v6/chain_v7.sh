#!/bin/bash
# waits for the 960px 8-epoch trial to finish, then starts the v7 80-epoch run as a protected service
cd "/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway"
LOG=runs/chain_v7_decision.txt
while systemctl --user is-active --quiet nh5-v6-train.service; do sleep 30; done
W=runs/detect/runs/v6_n960_8ep_b/weights/best.pt
if [ ! -f "$W" ]; then echo "$(date +%H:%M) trial weights missing, NOT starting v7 run" >> $LOG; exit 1; fi
echo "$(date +%H:%M) trial finished, starting v7 80-epoch run from $W" >> $LOG
systemd-run --user --unit=nh5-v7-train --collect -p ManagedOOMPreference=omit -p OOMScoreAdjust=-300 \
  --working-directory="/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway" \
  -p StandardOutput=append:/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5\ Highway/runs/v7_n960_80ep.log -p StandardError=append:/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5\ Highway/runs/v7_n960_80ep.log \
  /home/nikhil/.local/bin/yolo detect train model=$W data=datasets/processed_v2_plus_v6_v7/data.yaml epochs=80 patience=25 batch=16 imgsz=960 device=0 workers=8 \
  optimizer=SGD lr0=0.002 lrf=0.01 warmup_epochs=0 cos_lr=true close_mosaic=10 hsv_v=0.6 project=runs name=v7_n960_80ep >> $LOG 2>&1
echo "$(date +%H:%M) v7 run launched" >> $LOG
