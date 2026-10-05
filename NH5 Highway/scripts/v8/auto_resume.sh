#!/bin/bash
# Run at boot by nh5-train-resume.service: resume the v8 run if it is unfinished.
cd "/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway"
RUN="$PWD/runs/detect/runs/detect/runs/nh5_v8/v8n_960_100ep"
W="$RUN/weights/last.pt"; B="$RUN/weights/auto_backup"; CHK="$PWD/scripts/v8/ckpt_ok.py"

if pgrep -f "yolo detect train" >/dev/null; then echo "training already running, nothing to do"; exit 0; fi

# wait up to 5 min for the GPU driver after boot
for i in $(seq 60); do nvidia-smi >/dev/null 2>&1 && break; sleep 5; done

/usr/bin/python3 "$CHK" "$W"; rc=$?
if [ $rc -eq 2 ]; then echo "run finished, nothing to resume"; exit 0; fi
if [ $rc -ne 0 ]; then
  GOOD=$(ls -t "$B"/last_ep*.pt 2>/dev/null | head -1)
  [ -z "$GOOD" ] && { echo "last.pt corrupt and no backup"; exit 1; }
  echo "last.pt corrupt, restoring $GOOD"
  cp "$W" "$W.corrupt.$(date +%s)" 2>/dev/null; cp "$GOOD" "$W"
fi
exec /home/nikhil/.local/bin/yolo detect train resume model="$W"
