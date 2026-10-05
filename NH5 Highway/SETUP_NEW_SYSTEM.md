# NH5 Highway AI - setting up the project on a new system

This zip contains the complete NH5 Highway project **except the datasets**:
the website (with its Library of processed videos), the v8 models (PyTorch + ONNX FP32/INT8),
all scripts, the board inference file, the reports, and the PaddleOCR model files.

## Folder layout (after unzipping)

```
NH5 Highway/
├── app.py, event_engine.py, templates/, static/   website (Flask)
├── webapp_data/          website Library: uploads, results, road maps (keep!)
├── models/               nh5_v8_final_ep100.pt (website model), nh5_v8_ep60_overhead_plates.pt, archive/nh5_v6_best.pt
├── runs/onnx/            nh5_v8_int8.onnx (board), nh5_v8_fp32.onnx, conversion scripts + logs
├── runs/detect/...       v8 training run (results.csv, weights)
├── runs/verify/          verification report
├── board/                nh5_v8_inference.py (single-file inference: detections + number plates)
├── scripts/              data / training / test scripts (v6, v8, v9 folders)
├── reports/              project reports (PDF) + generator scripts
├── ocr_models/           PaddleOCR model files (copy to ~/.paddlex/official_models/)
├── requirements_full.txt exact package versions from the original machine
└── SETUP_NEW_SYSTEM.md   this file
```

Not included: `datasets/` (training data and the test videos). Training scripts need the dataset;
the website, the models and the board file work without it.

## Prompt to give Claude Code on the new system

Open a terminal in the unzipped `NH5 Highway` folder, start Claude Code there, and paste:

---

I have copied the NH5 Highway AI project to this machine (unzipped in the current folder). It is a Flask website
(app.py) that runs a YOLOv8 model (models/nh5_v8_final_ep100.pt, 12 classes: person, bicycle, car, motorcycle, bus,
truck, pothole, license_plate, auto, road_construction, accident_scene, fire_accident) with ByteTrack tracking,
accident/fire/road-work alerts (event_engine.py) and Indian number-plate reading with PaddleOCR
(scripts/v8/indian_plate.py). Please set it up and verify it works. Read SETUP_NEW_SYSTEM.md first.

1. Check the system: OS, Python version (3.10+ needed), free disk and RAM, and whether an NVIDIA GPU + driver
   is present (nvidia-smi).
2. Create a Python virtual environment in this folder (.venv) and install the packages from
   requirements_full.txt. If there is an NVIDIA GPU, install the torch/torchvision build that matches this
   machine's CUDA from pytorch.org instead of the pinned CPU/GPU default; if there is no GPU, use CPU builds.
   Keep ultralytics==8.4.53 and paddleocr==3.7.0 exactly.
3. Copy the PaddleOCR models: create ~/.paddlex/official_models/ and copy everything from ./ocr_models/ into it,
   so plate reading works without downloading.
4. Verify: import torch, ultralytics, paddleocr, onnxruntime, cv2; print whether CUDA is available; load
   models/nh5_v8_final_ep100.pt with ultralytics and print its 12 class names; load runs/onnx/nh5_v8_int8.onnx
   with onnxruntime and print its input/output shapes (1x3x960x960 -> 1x16x18900).
5. Fix machine-specific paths: several files under scripts/ (and runs/onnx/*.sh, reports/*.py) contain the old
   absolute path "/home/nikhil/Downloads/NH5 Highway". Replace it with this folder's absolute path in those
   files only. Do not change app.py, event_engine.py, templates/ or static/ (they already use relative paths).
   Show me the list of files you changed.
6. Start the website: `python3 app.py` (defaults: v8 model, PaddleOCR, port 5000). Check that /, /library,
   /live and /model return HTTP 200, that /model shows nh5_v8_final_ep100, and that the Library lists the
   existing entries from webapp_data/. Then stop it.
7. Test processing end to end without touching the Library: run
   `python3 board/nh5_v8_inference.py --model runs/onnx/nh5_v8_int8.onnx --out /tmp/nh5_check --max-frames 300 <video>`
   using one of the uploaded videos in webapp_data/uploads/ (pick a .mp4). Report the fps it prints and whether
   it produced an annotated video and a plates_unique.txt.
8. Give me a short summary: what was installed, GPU or CPU, anything that failed and how you fixed it, and the
   command to start the website.

Rules: do not delete or modify anything in webapp_data/ (the website Library), do not retrain or replace any
model file, and do not change the website's model. The datasets are not part of this copy.

---

## Starting the website later

```bash
cd "NH5 Highway"
source .venv/bin/activate
python3 app.py            # v8 model, PaddleOCR, port 5000 -> http://127.0.0.1:5000
```
