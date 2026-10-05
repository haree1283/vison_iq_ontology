#!/bin/bash
# Keep the 3 most recent valid copies of last.pt (one per epoch) in weights/auto_backup/.
RUN="/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway/runs/detect/runs/detect/runs/nh5_v8/v8n_960_100ep"
W="$RUN/weights"; B="$W/auto_backup"; mkdir -p "$B"
[ -f "$W/last.pt" ] || exit 0
# skip if last.pt is mid-write (changed within the last 30 s)
[ $(( $(date +%s) - $(stat -c %Y "$W/last.pt") )) -lt 30 ] && exit 0
EP=$(tail -1 "$RUN/results.csv" | cut -d, -f1 | tr -d ' ')
[ -f "$B/last_ep$EP.pt" ] && exit 0
cp "$W/last.pt" "$B/.tmp.pt" && /usr/bin/python3 "$(dirname "$0")/ckpt_ok.py" "$B/.tmp.pt" >/dev/null \
  && mv "$B/.tmp.pt" "$B/last_ep$EP.pt" || rm -f "$B/.tmp.pt"
ls -t "$B"/last_ep*.pt 2>/dev/null | tail -n +4 | xargs -r rm -f
