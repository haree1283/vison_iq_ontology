#!/bin/bash
# Rebuild the website Library after the accidental deletion: re-upload each surviving original video with the
# model it originally used (v5 before 2026-09-22, v6 after) plus v8, one upload at a time, via the normal /upload.
# Temporary servers on spare ports write into the same webapp_data/ -> entries appear in the Library.
cd "/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway"
VD=datasets/v6/vedios
V5="$HOME/Backups/NH5_v8_final_2026-09-28/models/older_baselines/nh5_v5_best.pt"   # v5 only lives in the backup
V6=models/archive/nh5_v6_best.pt
V8=models/nh5_v8_final_ep100.pt

AQ="$VD/AQNmKG0HFQMCpLhf6Dq_8Sznte446sZFbqoNjLeHVEKpnIv-m2VveyZXRttmJ6gJIORoUmn-CBEYMKOL7MlxAQtWviW98z6GYJlY1XNwkw.mp4"
LP="$VD/License Plate Detection Test - Dev Drone Bhowmik (1080p, h264).mp4"
VID="$VD/VID20260824132342.mp4"; WA="$VD/WhatsApp Video 2026-09-21 at 12.26.27.mp4"
MT="$VD/MicrosoftTeams-video.mp4"; MT1="$VD/MicrosoftTeams-video (1).mp4"; MT2="$VD/MicrosoftTeams-video (2).mp4"
REF="$VD/reference_vedio.mp4"; VP="$VD/videoplayback (4).mp4"; CR="$VD/Create_a_highly_realistic_s.mp4"
CCTV="$VD/real_accident_cctv_test.mp4"
I1="$VD/images/images.jpeg"; I2="$VD/images/images (2).jpeg"; I4="$VD/images/images (4).jpeg"

LIST_V5=("$AQ" "$LP" "$VID" "$WA" "$MT" "$MT1" "$MT2" "$REF" "$I1" "$I2" "$I4")
LIST_V6=("$MT1" "$VP" "$AQ" "$CR" "$LP" "$VID" "$WA" "$CCTV")
LIST_V8=("$AQ" "$LP" "$MT" "$MT1" "$MT2" "$REF" "$CR" "$I1" "$I2" "$I4")   # VID/WA/CCTV/VP already have v8 entries

run_model() {  # $1 label  $2 weights  $3 port  $4.. files
  local label=$1 w=$2 port=$3; shift 3
  python3 app.py --model "$w" --ocr-engine paddleocr --port $port > "webapp_data/rebuild_$label.log" 2>&1 &
  local pid=$!
  for i in $(seq 90); do curl -s -o /dev/null --max-time 2 http://127.0.0.1:$port/ && break; sleep 2; done
  for f in "$@"; do
    [ -f "$f" ] || { echo "MISSING $label $f"; continue; }
    loc=$(curl -s -o /dev/null -w '%{redirect_url}' -F "video=@$f" -F thorough=on http://127.0.0.1:$port/upload)
    job=${loc##*/}
    while :; do
      st=$(curl -s http://127.0.0.1:$port/status/$job | python3 -c "import sys,json;print(json.load(sys.stdin).get('status'))" 2>/dev/null)
      [ "$st" = done ] || [ "$st" = error ] && break; sleep 5
    done
    echo "DONE $label job=$job status=$st $(basename "$f")"
  done
  kill $pid; wait $pid 2>/dev/null
}

run_model v5 "$V5" 5095 "${LIST_V5[@]}"
run_model v6 "$V6" 5096 "${LIST_V6[@]}"
run_model v8 "$V8" 5094 "${LIST_V8[@]}"
echo REBUILD_DONE
