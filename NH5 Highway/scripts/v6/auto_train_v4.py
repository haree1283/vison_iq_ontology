"""Wait for the yolov8n-1280 pilot to finish, choose 960 vs 1280 from the pilot result, then launch the v4 yolov8n fine-tune detached."""
import csv, glob, subprocess, time, os, sys
os.chdir("/home/harikrishna/Desktop/NH5_Highway_project_2026-09-29/NH5 Highway")
LOG = "runs/auto_train_v4_decision.txt"
def log(s):
    open(LOG, "a").write(time.strftime("%H:%M:%S ") + s + "\n"); print(s, flush=True)
def last(name):
    f = glob.glob(f"runs/**/pilots/{name}/results.csv", recursive=True)
    if not f: return None
    rows = [{k.strip(): v for k, v in r.items()} for r in csv.DictReader(open(f[0]))]
    return rows
while True:  # pilot finished = 3 epochs logged and its process gone
    r = last("n1280")
    running = subprocess.run(["pgrep", "-f", "yolo detect train.*name=n1280"], capture_output=True).stdout.strip()
    if r and len(r) >= 3 and not running: break
    time.sleep(30)
m960 = float(last("n960")[-1]["metrics/mAP50(B)"]); m1280 = float(last("n1280")[-1]["metrics/mAP50(B)"])
use1280 = m1280 >= m960 - 0.005          # small-object classes are the bottleneck; accept a tiny loss on the average
imgsz, epochs = (1280, 40) if use1280 else (960, 50)
log(f"pilot mAP50 after 3 epochs: n960={m960:.3f} n1280={m1280:.3f} -> choosing imgsz={imgsz}, epochs={epochs}")
cmd = ["yolo", "detect", "train", "model=runs/detect/runs/v3_13class_100ep_ft2/weights/best.pt",
       "data=datasets/processed_v2_plus_v6_v4/data.yaml", f"epochs={epochs}", "patience=20", "batch=16", f"imgsz={imgsz}",
       "device=0", "workers=16", "optimizer=SGD", "lr0=0.002", "lrf=0.01", "warmup_epochs=0", "cos_lr=true", "close_mosaic=8",
       "project=runs", "name=v4_n_final", "exist_ok=False"]
log("launching: " + " ".join(cmd))
out = open("runs/v4_n_final.log", "w")
p = subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
log(f"training started, pid {p.pid}")
