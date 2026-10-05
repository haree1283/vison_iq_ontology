#!/bin/bash
# One-shot: wait for the in-progress epoch to finish and be saved, then stop, set patience=100, resume.
RUN="/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway/runs/detect/runs/detect/runs/nh5_v8/v8n_960_100ep"; W="$RUN/weights/last.pt"
start=$(tail -1 "$RUN/results.csv" | cut -d, -f1 | tr -d ' ')
until [ "$(tail -1 "$RUN/results.csv" | cut -d, -f1 | tr -d ' ')" != "$start" ]; do sleep 5; done
sleep 20   # let last.pt/best.pt finish writing
systemctl --user stop nh5-train-watchdog.timer
systemctl --user stop nh5-train-resume; sleep 5
cp "$W" "$W.before_patience"
/usr/bin/python3 "$(dirname "$0")/set_patience.py" "$W" 100 && sed -i 's/^patience: .*/patience: 100/' "$RUN/args.yaml"
systemctl --user start nh5-train-resume
systemctl --user start nh5-train-watchdog.timer
echo "done: resumed after epoch $(tail -1 "$RUN/results.csv" | cut -d, -f1)"
