#!/bin/bash
# Steps 2+3 of the INT8 conversion: calibrate/quantize (3 methods), validate all on the test split, benchmark.
cd "/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway/runs/onnx"
DATA="/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway/datasets/processed_v2_plus_v6_v8/data_train.yaml"
for M in minmax entropy percentile; do echo "== quantize $M"; python3 quantize_int8.py $M 600 2>&1 | grep -E "calibration images|saved|Error|rror"; done
val() {  # $1 model  $2 name  $3 device
  echo "== val $2"
  /home/nikhil/.local/bin/yolo val model="$1" data="$DATA" split=test imgsz=960 batch=1 device=$3 plots=False \
       project="$PWD/val" name="$2" exist_ok=True 2>&1 | sed 's/\x1b\[[0-9;]*[A-Za-z]//g' | tr '\r' '\n' |
       grep -E "^\s+(all|person|bicycle|car|motorcycle|bus|truck|pothole|license_plate|auto|road_construction|accident_scene|fire_accident)\s+[0-9]+\s+[0-9]+|Speed|Error|rror" | sed "s/^/[$2] /"
}
val nh5_v8.pt pt 0
val nh5_v8_fp32.onnx fp32_onnx cpu
for M in minmax entropy percentile; do val nh5_v8_int8_$M.onnx int8_$M cpu; done
python3 bench.py nh5_v8_fp32.onnx nh5_v8_int8_minmax.onnx nh5_v8_int8_entropy.onnx nh5_v8_int8_percentile.onnx
echo ALLDONE
