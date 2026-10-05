#!/bin/bash
# Runs alongside nh5-verify-job: stops the verification (never training) if RAM gets tight, so the
# memory pressure that makes systemd-oomd kill the training service never builds up.
V="/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway/runs/verify"
while systemctl --user is-active --quiet nh5-verify-job; do
  AVAIL=$(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo)
  PRESS=$(awk '/^some/{split($2,a,"="); print int(a[2])}' /proc/pressure/memory)
  if [ "$AVAIL" -lt 6 ] || [ "$PRESS" -gt 20 ]; then
    systemctl --user stop nh5-verify-job
    echo "$(date '+%F %T') GUARD stopped verification: ${AVAIL}G free, pressure ${PRESS}%" >> "$V/verify.log"
    # let the next tick retry the same milestone later
    for f in "$V"/started_v8_ep*; do [ -f "${f/started_/done_}" ] || rm -f "$f"; done
    rm -f "$V/started_final"
    exit 0
  fi
  sleep 5
done
