#!/bin/bash
# Resume of final_verify.sh after the unquoted-path bug: test the epoch snapshots, rebuild the report, mark final done.
cd "/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway"; V=runs/verify
for M in 30 40 50 60 70 80 90; do
  [ -f "$V/ep${M}_best.pt" ] && scripts/v8/milestone_verify.sh "v8_ep$M" "$PWD/$V/ep${M}_best.pt" 960
done
python3 scripts/v8/verify_report.py > /dev/null 2>&1
echo "$(date '+%F %T') FINAL COMPLETE -> runs/verify/report.md, runs/verify/final_val.log" >> $V/verify.log
touch $V/done_final
