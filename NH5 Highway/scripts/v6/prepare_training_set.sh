#!/usr/bin/env bash
# From "downloads running" to "dataset ready" on this machine (CPU). Builds data only -- never trains.
#  1. accident sets: convert, pre-label vehicles (records the vehicle type under each crash box);
#     includes every Roboflow export zip dropped in "datasets/car accidents/"
#  2. pre-label people/vehicles the small sources don't annotate (nh5_v5)
#  3. after the RDD2022 download: convert India potholes, pre-label them
#  4. after the UVH-26 download (retried if Hugging Face drops it): convert train+val, pre-label persons
#  5. balanced detector set -> datasets/v6/training/detector_yolo, packed as detector_yolo.tar
#  6. scene candidates (SigLIP-base on CPU; scores cached, so re-runs only score new crops) and categories/
# Re-runnable: a step whose marker exists in datasets/v6/.prepare/ is skipped. Logs to
# datasets/v6/raw/_logs/prepare_training_set.log.
#
# Launch as a capped systemd user unit -- the machine (15 GB RAM, ~8 GB taken by VS Code + Chrome) froze
# several times when this ran unbounded; with the cap the kernel stops this job instead of hanging the
# desktop, and the unit doesn't die with the terminal:
#   systemd-run --user --unit=nh5-prepare --collect -p MemoryMax=4G -p MemorySwapMax=256M \
#     -p CPUWeight=20 -p IOWeight=10 -p Nice=19 bash "/home/indraja/NH5 Highway/scripts/v6/prepare_training_set.sh"
#   systemctl --user status nh5-prepare        # progress: tail -f the log above
# Don't edit this file while the unit runs (bash reads it as it goes) -- write a copy and mv it over.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
exec >> datasets/v6/raw/_logs/prepare_training_set.log 2>&1
export OMP_NUM_THREADS=6 MKL_NUM_THREADS=6 OPENBLAS_NUM_THREADS=6
DL_LOG=datasets/v6/raw/_logs/download_all.log
MARK=datasets/v6/.prepare
TRAINING=datasets/v6/training
SORT_ARGS=${SORT_ARGS:-}   # e.g. SORT_ARGS="--max-images 3000" to cap SigLIP time per source on CPU
SIGLIP_CPU=models/zero_shot/siglip-base-patch16-224
ROBOFLOW_ACCIDENTS="accidents_hackcimat accidents_ai_challenge accidents_collision"
KAGGLE_ACCIDENTS="accidents_cubeai accidents_amedeograndi accidents_nardengerges accidents_pampana"
INBOX_ID=$(ls "datasets/car accidents" 2>/dev/null | md5sum | cut -c1-8)   # changes whenever a zip is added
mkdir -p "$MARK"
log() { echo "[$(date '+%F %T')] $*"; }

step() {  # step <name> <command...>: run once, marker only on success
  local name=$1; shift
  if [ -f "$MARK/$name" ]; then log "skip $name (done)"; return 0; fi
  log "start $name"
  if "$@"; then touch "$MARK/$name"; log "done $name"; else log "FAILED $name"; return 1; fi
}

# batch 1 by default: on CPU at 1280 px one batch of 4 needs >6 GB of feature maps; later args override
prelabel() { python3 scripts/v6/prelabel_missing.py --device cpu --batch 1 "$@"; }
prelabel_640() { prelabel "$@" --imgsz 640 --batch 4; }   # 640x640 accident exports: ~2.5 GB at batch 4

prelabel_inbox() {  # every accidents_rf_* source the inbox registered (none is fine)
  local names
  names=$(cd datasets/v6/sources && ls -d accidents_rf_* 2>/dev/null)
  [ -z "$names" ] && return 0
  # shellcheck disable=SC2086
  prelabel_640 $names
}

# shellcheck disable=SC2086
step convert_accidents python3 scripts/v6/convert_yolo_sources.py $ROBOFLOW_ACCIDENTS \
  && step prelabel_accidents prelabel_640 $ROBOFLOW_ACCIDENTS
step convert_accidents_cctv python3 scripts/v6/convert_hf_cctv_accidents.py \
  && step prelabel_accidents_cctv prelabel_640 accidents_cctv
# shellcheck disable=SC2086
step convert_accidents_kaggle python3 scripts/v6/convert_yolo_sources.py $KAGGLE_ACCIDENTS \
  && step prelabel_accidents_kaggle prelabel_640 $KAGGLE_ACCIDENTS
step "convert_inbox_$INBOX_ID" python3 scripts/v6/convert_yolo_sources.py inbox \
  && step "prelabel_inbox_$INBOX_ID" prelabel_inbox
step prelabel_small prelabel open_images cdset gujarat_plates gate_plates video_plates dashcam
python3 scripts/v6/build_categories.py > /dev/null

log "waiting for RDD2022 download"
until grep -qaE "(ok|FAILED) rdd2022/" "$DL_LOG"; do sleep 60; done
if grep -qa "ok rdd2022/" "$DL_LOG"; then
  step convert_rdd2022 python3 scripts/v6/convert_rdd2022.py && step prelabel_rdd2022 prelabel rdd2022_india
else
  log "RDD2022 download FAILED -- potholes stay at the dashcam images only"
fi

log "waiting for UVH-26 download"
until grep -qa "all sources processed" "$DL_LOG"; do sleep 300; done
for try in 1 2 3; do  # Hugging Face snapshot resumes where it stopped
  n=$(find datasets/v6/raw/uvh26 -name '*.png' | wc -l)
  [ "$n" -ge 26646 ] && break
  log "UVH-26 has $n/26646 images -- retry $try"
  python3 -c "from huggingface_hub import snapshot_download
snapshot_download('iisc-aim/UVH-26', repo_type='dataset', local_dir='datasets/v6/raw/uvh26', max_workers=4)"
done
step convert_uvh26 python3 scripts/v6/convert_uvh26.py --workers 2 && step prelabel_uvh26 prelabel uvh26

log "balanced detector set"
python3 scripts/v6/balance_v6_dataset.py || { log "balance FAILED"; exit 1; }
log "packing $TRAINING/detector_yolo.tar"
tar -C "$TRAINING" -cf "$TRAINING/detector_yolo.tar.part" detector_yolo \
  && mv "$TRAINING/detector_yolo.tar.part" "$TRAINING/detector_yolo.tar" \
  && log "DATASET READY: $(du -h "$TRAINING/detector_yolo.tar" | cut -f1) $TRAINING/detector_yolo.tar"
python3 scripts/v6/build_categories.py > /dev/null

log "scene candidates (SigLIP) $SORT_ARGS"
# shellcheck disable=SC2086
python3 scripts/v6/sort_scene_categories.py accidents potholes construction persons parked --device cpu \
  --model "$SIGLIP_CPU" $SORT_ARGS || log "sort_scene_categories FAILED"
python3 scripts/v6/build_categories.py && log "categories/ rebuilt -- see datasets/v6/categories/README.md"
