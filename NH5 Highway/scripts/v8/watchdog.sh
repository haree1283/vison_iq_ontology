#!/bin/bash
# Run every 5 min by nh5-train-watchdog.timer: if the v8 run is unfinished and nothing is training, resume it.
RUN="/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway/runs/detect/runs/detect/runs/nh5_v8/v8n_960_100ep"
LAST=$(tail -1 "$RUN/results.csv" | cut -d, -f1 | tr -d ' ')
[ "${LAST:-0}" -ge 100 ] && exit 0
pgrep -f "yolo detect train" >/dev/null && exit 0
state=$(systemctl --user is-active nh5-train-resume)
[ "$state" = "activating" ] && exit 0
echo "$(date '+%F %T') training not running (last epoch $LAST, service $state) -> resuming"
systemctl --user reset-failed nh5-train-resume 2>/dev/null
systemctl --user start nh5-train-resume
