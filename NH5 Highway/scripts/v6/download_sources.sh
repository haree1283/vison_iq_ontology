#!/usr/bin/env bash
# Resumable, login-free download of every v6 source listed in datasets/v6/SOURCES.md.
# Safe to re-run: curl resumes partial files (-C -), Hugging Face skips finished files,
# and a source whose folder already holds a "done" marker is skipped.
#
# Usage (detached, survives closing the terminal):
#   setsid nohup bash scripts/v6/download_sources.sh > datasets/v6/raw/_logs/download_all.log 2>&1 &
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
RAW="$ROOT/datasets/v6/raw"
LOGS="$RAW/_logs"
mkdir -p "$RAW/kaggle" "$LOGS"
cd "$RAW"

log() { echo "[$(date '+%F %T')] $*"; }

fetch() {  # fetch <url> <dest file>; retries so a dropped connection resumes instead of failing
  local url=$1 dest=$2 try
  for try in 1 2 3 4 5; do
    curl -sL --fail -C - --retry 5 --retry-delay 10 -o "$dest" "$url" && return 0
    log "  retry $try for $(basename "$dest")"
    sleep 30
  done
  return 1
}

kaggle() {  # kaggle <owner/slug>: public Kaggle download, no account needed
  local ref=$1 name=${1##*/}
  local dir="kaggle/$name" zip="kaggle/$name.zip"
  if [ -f "$dir/.done" ]; then log "skip $ref (done)"; return; fi
  log "kaggle $ref"
  if fetch "https://www.kaggle.com/api/v1/datasets/download/$ref" "$zip" && mkdir -p "$dir" \
     && unzip -q -o "$zip" -d "$dir"; then
    rm -f "$zip"; touch "$dir/.done"; log "  ok $ref ($(du -sh "$dir" | cut -f1))"
  else
    log "  FAILED $ref"
  fi
}

hf() {  # hf <repo id> <folder>
  local repo=$1 dir=$2
  if [ -f "$dir/.done" ]; then log "skip $repo (done)"; return; fi
  log "huggingface $repo"
  if python3 -c "
from huggingface_hub import snapshot_download
snapshot_download('$repo', repo_type='dataset', local_dir='$dir', max_workers=8)"; then
    touch "$dir/.done"; log "  ok $repo ($(du -sh "$dir" | cut -f1))"
  else
    log "  FAILED $repo"
  fi
}

direct() {  # direct <url> <folder> <file name>
  local url=$1 dir=$2 file=$3
  if [ -f "$dir/.done" ]; then log "skip $dir (done)"; return; fi
  mkdir -p "$dir"
  log "download $dir/$file"
  if fetch "$url" "$dir/$file"; then touch "$dir/.done"; log "  ok $dir/$file"; else log "  FAILED $dir/$file"; fi
}

# small / fast sources first, the 90 GB UVH-26 last
kaggle snehilsanyal/construction-site-safety-image-dataset-roboflow
kaggle abtinzandi/obstacle-detection-dataset
kaggle paneraghanshyam/gujarat-vehicle-number-plates-yolo-ready
kaggle deepakat002/indian-vehicle-number-plate-yolo-annotation
kaggle tkm22092/indian-number-plate-images
kaggle lujeenmsendy/raqabah-multi-severity-car-accident-dataset
kaggle jee1oner/dashcam-pov-potholes-and-barricades-for-yolo26n
hf keremberke/license-plate-object-detection hf_keremberke_plates
hf zzd0225/crosswalk-detection-dataset cdset_crosswalk
direct "https://zenodo.org/api/records/13954136/files/number_plate.zip/content" bapatla_plates number_plate.zip
direct "https://ndownloader.figshare.com/files/38030910" rdd2022 RDD2022_released_through_CRDDC2022.zip
hf iisc-aim/UVH-26 uvh26

log "all sources processed"
