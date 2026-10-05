#!/usr/bin/env bash
# Extracts all raw dataset zips into datasets/raw/<name>/
set -euo pipefail
cd "$(dirname "$0")/../datasets/raw"

extract() {
  local zip="$1" outdir="$2"
  if [ -f "$zip" ]; then
    echo "Extracting $zip -> $outdir"
    mkdir -p "$outdir"
    unzip -q -o "$zip" -d "$outdir"
  else
    echo "MISSING: $zip"
  fi
}

extract coco_val2017_images.zip coco
extract coco_annotations_trainval2017.zip coco
extract pothole_ivcnz.zip pothole
extract license_plate_mendeley.zip license_plate

echo "=== Extracted tree (top levels) ==="
find . -maxdepth 3 -type d | sort
