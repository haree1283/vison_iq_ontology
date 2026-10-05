#!/usr/bin/env bash
# Extra accident image sets for categories/06_road_accidents (20k accident target, 2026-09-15).
# Public Kaggle downloads, no account needed. Licenses are weak or missing (see datasets/v6/SOURCES.md) --
# none of this is cleared for commercial use. Resumable; a folder holding .done is skipped; stops while
# less than 40 GB of disk is free (UVH-26 still needs room).
#
# Usage (capped, detached):
#   systemd-run --user --unit=nh5-dl-accidents --collect -p MemoryMax=1G -p CPUWeight=20 -p IOWeight=10 \
#     -p Nice=19 bash "/home/indraja/NH5 Highway/scripts/v6/download_accident_sources.sh"
set -u
RAW="$(cd "$(dirname "$0")/../.." && pwd)/datasets/v6/raw"
cd "$RAW"
mkdir -p kaggle _logs
exec >> _logs/download_accident_sources.log 2>&1
log() { echo "[$(date '+%F %T')] $*"; }

kaggle() {  # kaggle <owner/slug>
  local ref=$1 name=${1##*/}
  local dir="kaggle/$name" zip="kaggle/$name.zip" free_gb
  if [ -f "$dir/.done" ]; then log "skip $ref (done)"; return; fi
  free_gb=$(df --output=avail -BG . | tail -1 | tr -dc 0-9)
  if [ "$free_gb" -lt 40 ]; then log "STOP: only ${free_gb} GB free"; exit 1; fi
  log "kaggle $ref"
  for try in 1 2 3 4 5; do
    curl -sL --fail -C - --retry 5 --retry-delay 10 -o "$zip" "https://www.kaggle.com/api/v1/datasets/download/$ref" && break
    log "  retry $try"
    sleep 30
  done
  if unzip -tq "$zip" > /dev/null 2>&1 && mkdir -p "$dir" && unzip -q -o "$zip" -d "$dir"; then
    rm -f "$zip"
    touch "$dir/.done"
    log "  ok $ref ($(du -sh "$dir" | cut -f1))"
  else
    log "  FAILED $ref (zip kept for resume)"
  fi
}

# smallest first
kaggle ckay16/accident-detection-from-cctv-footage                     # 262 MB  CCTV / YouTube frames, image-level
kaggle cubeai/traffic-accident-detection-for-yolov8                    # 274 MB  YOLOv8 boxes
kaggle suryaprabhakaran2005/road-accidents-from-cctv-footages-dataset  # 703 MB  CCTV frames, image-level severity (MIT)
kaggle amedeograndi/accidents-detection-dataset                        # 781 MB  YOLOv8 boxes, moderate / severe
kaggle sarfaraznatha/road-anomaly-dataset                              # 1.4 GB  surveillance anomalies incl. accidents (MIT)
kaggle nardengerges/accident-no-accident-detection                     # 2.0 GB  YOLOv8, ~18k accident frames
kaggle orvile/road-anomaly-detection                                   # 2.1 GB  Pakistan CCTV / mobile, YOLO (CC BY 4.0)
kaggle pampanadeepakbabu/road-accident-anamoly-dataset                 # 2.3 GB  YOLO
log "all accident sources processed"
