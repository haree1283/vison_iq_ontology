#!/bin/bash
# 3-epoch pilots from the same COCO weights on a 30k-image subset, scored on the full v3 val split
cd "/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway"
D=datasets/pilot_v3_subset/data.yaml
S="/media/nikhil/New Volume/Nikhil/yolov8s.pt"
run() { yolo detect train model="$1" data=$D epochs=3 imgsz=$2 batch=$3 device=0 workers=8 warmup_epochs=0.5 close_mosaic=1 plots=False project=runs/pilots name=$4 exist_ok=True > runs/pilots_$4.log 2>&1; }
run yolov8n.pt 960 16 n960
run yolov8n.pt 1280 12 n1280
run "$S" 960 16 s960
run "$S" 1280 8 s1280
echo ALLDONE > runs/pilots_done.flag
