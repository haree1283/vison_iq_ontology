#!/usr/bin/env bash
# Car Crash Dataset (CCD, github.com/Cogito2012/CarCrashDataset, MIT): Crash-1500.zip (793 MB, 1,500
# dashcam crash clips of 50 frames) + Crash-1500.txt (per-frame accident labels) from the authors'
# public Google Drive folder -- no account needed, but Drive answers "Quota exceeded" when the file
# was downloaded too often that day. This retries every 2 hours and only marks the download done
# once the file is a real zip of the full size.
#
# Usage (capped, detached):
#   systemd-run --user --unit=nh5-dl-ccd --collect -p MemoryMax=1G -p CPUWeight=20 -p IOWeight=10 -p Nice=19 \
#     bash "/home/indraja/NH5 Highway/scripts/v6/download_ccd.sh"
set -u
DIR="$(cd "$(dirname "$0")/../.." && pwd)/datasets/v6/raw/ccd"
mkdir -p "$DIR"
cd "$DIR"
exec >> ../_logs/ccd.log 2>&1
URL="https://drive.usercontent.google.com/download?export=download&confirm=t&id="
ZIP_ID=1fmcwGhr8JT9YfLUrlcvuCZ3ychi2eyFP
TXT_ID=13OgrD0-8cKG0X00MlA6JXr0G_JJmHYXg
ZIP_BYTES=793091291
log() { echo "[$(date '+%F %T')] $*"; }

[ -f .done ] && { log "already done"; exit 0; }
[ -s Crash-1500.txt ] || curl -sL --fail "$URL$TXT_ID" -o Crash-1500.txt

for try in $(seq 1 24); do
  # probe with a normal (un-ranged) request, reading only its first bytes: while the quota is exceeded
  # Drive still answers ranged requests but sends a small HTML page for a plain download
  if [ "$(curl -sL "$URL$ZIP_ID" 2>/dev/null | head -c 2)" = "PK" ]; then
    log "try $try: file available, downloading"
    # a partial that isn't a zip is a saved quota page -- resuming onto it would corrupt the file
    [ -f Crash-1500.zip.part ] && [ "$(head -c 2 Crash-1500.zip.part)" != "PK" ] && rm -f Crash-1500.zip.part
    curl -sL --fail -C - --retry 5 --retry-delay 30 -o Crash-1500.zip.part "$URL$ZIP_ID"
    size=$(stat -c %s Crash-1500.zip.part 2>/dev/null || echo 0)
    if [ "$size" -eq "$ZIP_BYTES" ] && [ "$(head -c 2 Crash-1500.zip.part)" = "PK" ]; then
      mv Crash-1500.zip.part Crash-1500.zip && touch .done && log "ok Crash-1500.zip ($size bytes)"
      exit 0
    fi
    log "try $try: got $size of $ZIP_BYTES bytes -- resuming next round"
  else
    log "try $try: Drive quota exceeded -- next try in 2 h"
  fi
  sleep 7200
done
log "FAILED: still unavailable after 24 tries"
exit 1
