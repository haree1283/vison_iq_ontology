#!/bin/bash
# every 5 min: if the v9 chain is not complete and not running, start it again
cd "/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway"
[ -f runs/v9/CHAIN_COMPLETE ] && exit 0
pgrep -f "yolo detect (train|val)" >/dev/null && exit 0
st=$(systemctl --user is-active nh5-v9-train)
[ "$st" = active ] || [ "$st" = activating ] && exit 0
echo "$(date '+%F %T') watchdog: chain not running ($st) -> starting" >> runs/v9/chain.log
systemctl --user reset-failed nh5-v9-train 2>/dev/null; systemctl --user start nh5-v9-train
