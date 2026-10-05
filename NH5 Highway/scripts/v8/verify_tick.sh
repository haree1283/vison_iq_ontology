#!/bin/bash
# Run every 15 min by nh5-verify.timer. Cheap health checks on results.csv each tick; launches the milestone
# video tests (epochs 40/60/80) and the final verification (after epoch 100) as separate low-priority units.
cd "/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway"
RUN=runs/detect/runs/detect/runs/nh5_v8/v8n_960_100ep; V=runs/verify; mkdir -p $V
A=$V/alerts.log
alert() { grep -qxF "$1" $A 2>/dev/null || echo "$(date '+%F %T') $1" >> $A; }
E=$(tail -1 $RUN/results.csv | cut -d, -f1 | tr -d ' ')
echo "$(date "+%F %T") epoch $E train_rss=$(ps -o rss= -p $(pgrep -of "yolo detect train") 2>/dev/null | awk "{print int(\$1/1048576)}")G avail=$(awk "/MemAvailable/{print int(\$2/1048576)}" /proc/meminfo)G disk_free=$(df -BG --output=avail / | tail -1 | tr -d " ")" >> $V/mem.log
# health: NaN losses, mAP50 dropping >3 points below the best so far, no new epoch for 45 min
tail -1 $RUN/results.csv | grep -qi nan && alert "NaN in results.csv at epoch $E"
read CUR BEST < <(awk -F, 'NR>1{m=$8+0; if(m>b)b=m; c=m} END{print c, b}' $RUN/results.csv)
awk -v c=$CUR -v b=$BEST 'BEGIN{exit !(b-c>0.03)}' && alert "mAP50 drop at epoch $E: $CUR vs best $BEST"
AGE=$(( $(date +%s) - $(stat -c %Y $RUN/results.csv) ))
[ "$E" -lt 100 ] && [ $AGE -gt 2700 ] && alert "no new epoch for $((AGE/60)) min (last epoch $E)"
# one verification job at a time, and only with enough free RAM (keeps training safe from OOM)
systemctl --user is-active --quiet nh5-verify-job && exit 0
AVAIL=$(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo)
if [ "$E" -ge 100 ] && ! pgrep -f "yolo detect train" >/dev/null; then
  [ -f $V/done_final ] || [ -f $V/started_final ] && exit 0
  touch $V/started_final
  systemd-run --user --unit=nh5-verify-job --collect -p MemoryMax=16G "$PWD/scripts/v8/final_verify.sh"   # training is done: no guard needed
  exit 0
fi
# milestone snapshots only (a file copy): video tests during training raised memory pressure at epoch end
# (19:12 test: 27%), so every snapshot is video-tested after epoch 100 by final_verify.sh with the GPU free
for M in 30 40 50 60 70 80 90; do
  [ "$E" -ge $M ] && [ ! -f $V/ep${M}_best.pt ] && cp $RUN/weights/best.pt $V/ep${M}_best.pt \
    && echo "$(date '+%F %T') snapshot ep$M best.pt saved" >> $V/verify.log
done
