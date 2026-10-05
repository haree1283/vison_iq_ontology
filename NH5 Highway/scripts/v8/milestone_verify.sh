#!/bin/bash
# Full video test (detection+tracking+stability, plate crops + PaddleOCR, refined plates) of a v8 checkpoint snapshot.
# Usage: milestone_verify.sh <tag> <model.pt> [imgsz]   -> runs/video_tests/<tag>, then rebuilds runs/verify/report.md
cd "/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway"
TAG="$1"; MODEL="$2"; V=runs/verify
echo "$(date '+%F %T') START $TAG ($MODEL)" >> $V/verify.log
IMGSZ="${3:-960}" scripts/v6/test_videos.sh "$MODEL" "$TAG" > "$V/$TAG.log" 2>&1
rc=$?
python3 scripts/v8/verify_report.py >> "$V/$TAG.log" 2>&1
echo "$(date '+%F %T') DONE $TAG rc=$rc" >> $V/verify.log
touch "$V/done_$TAG"
