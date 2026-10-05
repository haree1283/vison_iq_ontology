#!/bin/bash
# Standard video test: EVERY test of the vedios footage runs all three parts. Test-only; outputs never go into datasets/.
# Usage: scripts/v6/test_videos.sh <model.pt> <run_name> [video files... | default: all mp4 in datasets/v6/vedios, minus duplicates]
set -u
cd "/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway"
MODEL="$1"; NAME="$2"; shift 2
OUT="runs/video_tests/$NAME"; mkdir -p "$OUT"
if [ "$#" -gt 0 ]; then VIDS=("$@"); else
  mapfile -t VIDS < <(ls datasets/v6/vedios/*.mp4 | grep -v "h264) 1" | grep -v "/annotated.mp4"); fi
echo "== 1/3 detection inference: tracking + per-class conf + temporal accident/fire alerts =="
for v in "${VIDS[@]}"; do
  python3 scripts/v6/video_infer.py --imgsz "${IMGSZ:-960}" --model "$MODEL" --source "$v" --out "$OUT/annotated/$(basename "${v%.mp4}")" 2>&1 | grep -E "^[^ /].*\{'frames'"
done
echo "== 2/3 plate crops saved + PaddleOCR on the saved crops =="
IMGSZ="${IMGSZ:-960}" MODEL="$MODEL" PLATES_ROOT="$OUT/plates" python3 scripts/v6/plates_pipeline.py "${VIDS[@]}" 2>&1 | grep -E "^\[stage"
echo "== 3/3 refined plate reading (best crops, format-aware correction, track voting) =="
PLATES_ROOT="$OUT/plates" python3 scripts/v6/plates_refine.py 2>&1 | grep -E "unique_plates="
echo "results in $OUT (annotated/, plates/<video>/crops, plates_ocr.txt, plates_final.txt, all_plates_final.txt)"
