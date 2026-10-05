#!/bin/bash
# Re-run of the MinMax branch after the ORT batching bug (runs once the main job has finished).
cd "/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway/runs/onnx"
DATA="/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway/datasets/processed_v2_plus_v6_v8/data_train.yaml"
while systemctl --user is-active --quiet nh5-onnx; do sleep 20; done
echo "== quantize minmax (rerun)"; python3 quantize_int8.py minmax 600 2>&1 | grep -E "calibration images|saved|Error|rror"
echo "== val int8_minmax"
/home/nikhil/.local/bin/yolo val model=nh5_v8_int8_minmax.onnx data="$DATA" split=test imgsz=960 batch=1 device=cpu plots=False \
     project="$PWD/val" name=int8_minmax exist_ok=True 2>&1 | sed 's/\x1b\[[0-9;]*[A-Za-z]//g' | tr '\r' '\n' |
     grep -E "^\s+(all|person|bicycle|car|motorcycle|bus|truck|pothole|license_plate|auto|road_construction|accident_scene|fire_accident)\s+[0-9]+\s+[0-9]+|Speed|Error|rror" | sed "s/^/[int8_minmax] /"
python3 bench.py nh5_v8_int8_minmax.onnx
echo MINMAXDONE
