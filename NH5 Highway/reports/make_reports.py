#!/usr/bin/env python3
"""Builds the two NH5 Highway project reports (management + technical) as PDF with ReportLab."""
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

OUT = Path(__file__).resolve().parent
DATE = "28 September 2026"
ss = getSampleStyleSheet()
BLUE = colors.HexColor("#1f3b5c"); LIGHT = colors.HexColor("#e9eef4"); GRID = colors.HexColor("#b7c3d0")
H1 = ParagraphStyle("H1", parent=ss["Heading1"], fontSize=15, textColor=BLUE, spaceBefore=10, spaceAfter=6)
H2 = ParagraphStyle("H2", parent=ss["Heading2"], fontSize=12, textColor=BLUE, spaceBefore=8, spaceAfter=4)
P = ParagraphStyle("P", parent=ss["BodyText"], fontSize=9.5, leading=13, alignment=TA_LEFT, spaceAfter=5)
SMALL = ParagraphStyle("S", parent=P, fontSize=8, leading=10.5)
CELL = ParagraphStyle("C", parent=P, fontSize=8, leading=10, spaceAfter=0)
CELLB = ParagraphStyle("CB", parent=CELL, fontName="Helvetica-Bold", textColor=colors.white)
TITLE = ParagraphStyle("T", parent=ss["Title"], fontSize=22, textColor=BLUE, spaceAfter=4)
SUB = ParagraphStyle("Sub", parent=P, fontSize=11, textColor=colors.HexColor("#555555"))


def para(t, st=P):
    return Paragraph(t, st)


def bullets(items, st=P):
    return [Paragraph("&bull;&nbsp;" + i, ParagraphStyle("b", parent=st, leftIndent=10, firstLineIndent=-8)) for i in items]


def table(rows, widths, header=True, zebra=True):
    data = [[Paragraph(str(c), CELLB if (header and r == 0) else CELL) for c in row] for r, row in enumerate(rows)]
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1 if header else 0)
    style = [("GRID", (0, 0), (-1, -1), 0.4, GRID), ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
             ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), BLUE))
    if zebra:
        for r in range(1 if header else 0, len(rows)):
            if r % 2 == 0:
                style.append(("BACKGROUND", (0, r), (-1, r), LIGHT))
    t.setStyle(TableStyle(style))
    return t


def chart(name, width_mm=165):
    from reportlab.lib.utils import ImageReader
    path = OUT / "charts" / name; iw, ih = ImageReader(str(path)).getSize()
    return Image(str(path), width=width_mm * mm, height=width_mm * mm * ih / iw)


def footer(title):
    def draw(canvas, doc):
        canvas.saveState(); canvas.setFont("Helvetica", 7.5); canvas.setFillColor(colors.grey)
        canvas.drawString(18 * mm, 10 * mm, f"NH5 Highway AI  |  {title}  |  {DATE}")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()
    return draw


def build(path, title, story):
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=16 * mm, title=title, author="NH5 Highway project")
    doc.build(story, onFirstPage=footer(title), onLaterPages=footer(title))
    print("written", path)


# ------------------------------------------------------------------------------------------------ shared data
PER_CLASS = [  # class, pt test, clean test, INT8 test
    ("license_plate", "0.939", "0.946", "0.935"), ("auto", "0.921", "0.921", "0.915"), ("car", "0.916", "0.912", "0.911"),
    ("motorcycle", "0.871", "0.868", "0.864"), ("bus", "0.851", "0.851", "0.850"), ("fire_accident", "0.837", "0.763", "0.804"),
    ("accident_scene", "0.802", "0.777", "0.772"), ("person", "0.801", "0.793", "0.794"), ("truck", "0.792", "0.783", "0.785"),
    ("road_construction", "0.745", "0.741", "0.716"), ("bicycle", "0.740", "0.744", "0.721"), ("pothole", "0.597", "0.559", "0.590"),
]
FILES = [
    ("v8 model (PyTorch)", "models/nh5_v8_final_ep100.pt"),
    ("v8 INT8 ONNX (board)", "runs/onnx/nh5_v8_int8.onnx"),
    ("v8 FP32 ONNX", "runs/onnx/nh5_v8_fp32.onnx"),
    ("Board inference file (detections + plates)", "board/nh5_v8_inference.py"),
    ("Website server", "app.py  (run: python3 app.py, port 5000)"),
    ("Full backup of v8", "~/Backups/NH5_v8_final_2026-09-28/"),
    ("Old v6 model (archive only)", "models/archive/nh5_v6_best.pt"),
]

# ================================================================================================ MANAGEMENT
m = []
RC_NOTE = ("<b>Note - road construction:</b> road-construction data has been added to the dataset and the model detects "
           "work zones, but it still gives false detections (for example permanent roadside bollards and lone signs). "
           "Road construction <b>will be trained separately</b> because of these false detections.")
m += [Spacer(1, 30), para("NH5 Highway AI", TITLE), para("Project report", SUB),
      para(f"{DATE}  &middot;  Model version v8", SUB), Spacer(1, 14)]
m += [para("1. Summary", H1)]
m += [para("The NH5 Highway detection model <b>v8</b> is complete. It detects 12 classes - vehicles (car, motorcycle, "
           "auto, bus, truck, bicycle), people, potholes, number plates, road work, accidents and vehicle fires - and "
           "reads Indian number plates. It exceeds the accuracy target, and the conversion of the model to ONNX "
           "(FP32 and INT8) for the Rubik Pi board is complete.")]
m += [table([["Item", "Result", "Status"],
             ["Accuracy target (mAP50 > 0.75)", "<b>0.805</b> on the leak-free test set (0.818 on the full test set)", "Met"],
             ["Model training", "100 epochs on the cleaned dataset (105k images)", "Completed"],
             ["ONNX conversion", "FP32 ONNX and calibrated INT8 ONNX (3.7 MB, mAP50 0.805)", "Completed"],
             ["Website", "Runs v8 with accident and fire alerts, vehicle counts per type, Indian plates", "Completed"],
             ["Road construction", "Data added, but false detections - to be trained separately", "Planned"]],
            [52, 95, 27])]
m += [para("2. Objective and scope", H1)]
m += bullets(["<b>Goal:</b> automatic monitoring of the NH5 highway from cameras - count and classify traffic, read number "
              "plates, and raise alerts for accidents, vehicle fires, road work and potholes.",
              "<b>Target platform:</b> the Rubik Pi edge board (model converted to INT8 ONNX), and the project website for "
              "uploaded videos and a live camera.",
              "<b>Output of the system:</b> annotated video, alerts with snapshots, vehicle counts per type, number plates, "
              "and an Excel report per video."])
m += [para("3. How the system works", H1)]
m += [table([["Step", "What happens"],
             ["1. Detection", "The v8 model finds all objects of the 12 classes in each video frame."],
             ["2. Tracking", "Each object keeps the same ID across frames, so a vehicle is counted once."],
             ["3. Alerts", "Accident and fire must be seen steadily for about a second before an alert is raised, which "
                           "avoids false alarms from a single frame."],
             ["4. Number plates", "Each plate is cleaned (sharpened, straightened), read, and accepted only if it is a valid "
                                  "Indian plate seen the same way in several frames."],
             ["5. Report", "Annotated video, alert snapshots, counts and plates are recorded for every video."]],
            [34, 140])]
m += [PageBreak()]
m += [para("4. What the model detects", H1)]
m += [table([["Class", "Meaning", "Used for"],
             ["car, motorcycle, auto, bus, truck, bicycle", "Vehicles (rider counted with the vehicle)", "Traffic counts per type"],
             ["person", "Pedestrians", "People count, pedestrian events"],
             ["license_plate", "Number plate of a vehicle", "Indian plate reading"],
             ["pothole", "Hole / broken patch in the road surface", "Road maintenance"],
             ["road_construction", "Road work zone (cones, barriers, workers)", "Work-zone alert"],
             ["accident_scene", "Collision or crashed / overturned vehicle", "Accident alert"],
             ["fire_accident", "Vehicle on fire (flames and smoke)", "Fire alert"]], [52, 70, 52])]
m += [para("5. Accuracy", H1)]
m += [para("mAP50 per class (1.0 = perfect). The leak-free test uses only test images with no near-copy in the training "
           "data, so it is the most honest measure. INT8 is the compressed version converted for the board.")]
m += [chart("accuracy_per_class.png", 150)]
m += [PageBreak()]
m += [table([["Class", "Full test", "Leak-free test", "INT8 (board)"]] + [list(r) for r in PER_CLASS] +
            [["<b>All classes</b>", "<b>0.818</b>", "<b>0.805</b>", "<b>0.805</b>"]], [55, 35, 40, 35])]
m += [para("Strong: number plates, autos, cars, motorcycles, buses (0.85-0.95). Weakest: potholes (0.56-0.60), road "
           "work and bicycles (about 0.72-0.75).", SMALL)]
m += [para("6. Training", H1)]
m += [para("The model was trained for 100 epochs on 88,083 training images at 960 px. Accuracy passed the 0.75 target "
           "within the first 10 epochs and kept improving steadily to 0.813 (validation) at epoch 100.")]
m += [chart("training_progress.png", 150)]
m += [PageBreak()]
m += [para("7. Compared with the previous models", H1)]
m += [chart("model_comparison.png", 150)]
m += [table([["", "v5", "v6", "v8"],
             ["Vehicles detected (14 test videos)", "104,630", "43,023", "<b>133,439</b>"],
             ["Correct number plates read", "10", "31", "<b>31</b>"],
             ["Accident detection", "not possible", "yes, but misses vehicles", "<b>yes</b>"],
             ["Fire detection", "not possible", "not possible", "<b>yes</b>"],
             ["Count stability (lower = better)", "12.1%", "24.0%", "<b>8.3%</b>"]], [60, 30, 45, 40])]
m += [para("8. Results on test videos", H1)]
m += [table([["Scenario", "v8 result"],
             ["Vehicle fires (dashcam and phone videos)", "Fire detected and alert raised"],
             ["Real crashes (CCTV compilation)", "All crashes detected and alerted"],
             ["Busy city traffic, no incidents", "No false accident or fire alerts; Indian plates read correctly"],
             ["Close-up of a normal car", "No accident alert"],
             ["Foreign (non-Indian) number plates", "Correctly ignored"]], [80, 94])]
m += [PageBreak()]
m += [para("9. Work completed", H1)]
m += [table([["Area", "Work done"],
             ["Dataset", "Final dataset of 105k images; missing vehicle labels added; fire and road-work labelling rules applied"],
             ["Training", "YOLOv8n trained for 100 epochs at 960 px; verified on test images and 14 test videos"],
             ["ONNX conversion", "FP32 ONNX export, then calibrated INT8 quantization (3.7 MB) with accuracy validated "
                                 "against the original model"],
             ["Number plates", "Indian-only plate reading with image clean-up and multi-frame confirmation"],
             ["Website", "v8 model, accident and fire alerts, vehicle counts per type, processing speed display, "
                         "plate counts"]], [34, 140])]
m += [para("10. Milestones", H1)]
m += [table([["Date", "Milestone"],
             ["Aug - Sep 2026", "Earlier models (v5, v6) and first website version"],
             ["24 Sep 2026", "Final dataset cleaned (missing vehicle labels added, fire / road-work rules applied)"],
             ["26 Sep 2026", "v8 training completed (100 epochs) and verified"],
             ["28 Sep 2026", "ONNX conversion (FP32 + INT8) completed; website moved to v8 with fire and accident alerts "
                             "and Indian-only plate reading"]], [34, 140])]
m += [para("11. Known limitations", H1)]
m += [table([["Limitation", "Impact", "Planned fix"],
             ["Potholes", "Misses about half", "Label clean-up"],
             ["Accidents on some CCTV clips", "Marked 1-3 s before the impact", "Relabelling"],
             ["Road construction", "False detections (bollards, lone signs)", "Train separately"],
             ["Plates from high/overhead cameras", "Fewer plates read", "More overhead footage"],
             ["Photos of wrecked vehicles", "Not always recognised", "More training data"],
             ["Smoke-only fires (no flames)", "No fire alert", "More training data"]], [62, 55, 57])]
m += [para(RC_NOTE, P)]
m += [para("12. Next steps", H1)]
m += bullets(["<b>Road construction</b>: the data is added, but it gives false detections, so it will be trained separately.",
              "Improve the weaker classes (potholes, accidents on CCTV, aftermath photos) with corrected labels and more data.",
              "Footage from the real NH5 cameras (especially overhead views and night) would help most."])
m += [Spacer(1, 10), para("<b>Note - lane change and wrong-direction detection:</b> these will be checked once the camera is fixed in the position where the model needs to be tested, because both depend on the camera view (the lanes and the allowed direction of travel are set for that fixed position).", P)]
build(OUT / "NH5_v8_Report_Management.pdf", "Management report", m)

# ================================================================================================ TECHNICAL
t = []
t += [Spacer(1, 20), para("NH5 Highway AI", TITLE), para("Technical report - v8 model, conversion, pipeline and website", SUB),
      para(f"{DATE}", SUB), Spacer(1, 10)]
t += [para("Contents: 1 System overview &middot; 2 Dataset &middot; 3 Training &middot; 4 Evaluation &middot; 5 INT8 ONNX "
           "&middot; 6 Plate reading &middot; 7 Website &middot; 8 Known issues", SMALL)]

t += [para("1. System overview", H1)]
t += [table([["Stage", "What it does"],
             ["Detection", "YOLOv8n, 12 classes, 960 px input, ByteTrack tracking"],
             ["Events", "Temporal rules for accident / fire / road-work alerts; zone and lane rules with a road map"],
             ["Plates", "Plate crop -> clarity filter -> PaddleOCR -> Indian-format check -> multi-frame voting"],
             ["Website", "Upload, live camera, Library, Excel report"],
             ["Deployment", "FP32 and INT8 ONNX for the Rubik Pi"]], [30, 144])]
t += [para("Classes (id): 0 person, 1 bicycle, 2 car, 3 motorcycle, 4 bus, 5 truck, 6 pothole, 7 license_plate, 8 auto, "
           "9 road_construction, 10 accident_scene, 11 fire_accident. Rules: riders are part of the vehicle box (person = "
           "pedestrians only); fire and smoke form one fire_accident box; fire_accident only when a vehicle is burning; a "
           "lone cone/sign is not road work.", SMALL)]

t += [para("2. Dataset (v8)", H1)]
t += [para("Built from public and project sources (COCO-style traffic, Indian road datasets, CCPD/plate sets, RDD2022 "
           "potholes (D40 only), road-work sets, accident and fire sets, night scenes). Cleaned in place on 24 Sep: "
           "~170k missing person/vehicle boxes added (78,614 cars), road-work zones rebuilt from object annotations, fire "
           "restricted to vehicle fires, 5,328 noisy images removed. The vedios/ folder is test-only and never used for "
           "training.")]
t += [table([["Class", "Train boxes", "Val boxes", "Test boxes"],
             ["person", "81,869", "12,140", "11,518"], ["bicycle", "14,827", "601", "572"], ["car", "167,200", "14,704", "13,224"],
             ["motorcycle", "48,801", "5,493", "3,225"], ["bus", "23,578", "1,652", "1,552"], ["truck", "38,289", "4,159", "3,491"],
             ["pothole", "27,479", "1,409", "802"], ["license_plate", "17,524", "2,000", "2,062"], ["auto", "33,903", "2,957", "2,286"],
             ["road_construction", "11,414", "1,484", "1,329"], ["accident_scene", "14,038", "971", "942"],
             ["fire_accident", "3,452", "549", "602"],
             ["<b>Images</b>", "<b>88,083</b>", "<b>8,819</b>", "<b>8,040</b>"]], [50, 40, 40, 40])]
t += [para("Balancing: fire images are repeated 5x and pothole / bicycle / road-work images 2x in each epoch "
           "(128,530 samples per epoch from 82,975 unique images).", SMALL)]

t += [para("3. Training", H1)]
t += [table([["Setting", "Value", "Setting", "Value"],
             ["Model", "YOLOv8n (fine-tuned)", "Image size", "960"], ["Epochs", "100", "Batch", "32"],
             ["Optimizer", "auto (SGD), lr0 0.01, lrf 0.01, cosine", "Warm-up", "3 epochs"],
             ["Augmentation", "mosaic 1.0 (off last 10 epochs), hsv_v 0.4", "Patience", "100 (all epochs run)"],
             ["Hardware", "RTX 3090 Ti 24 GB, 62 GB RAM", "Time", "~16.5 min/epoch, finished 26 Sep 15:10"]], [28, 62, 26, 58])]
t += [table([["Epoch", "21", "40", "50", "60", "70", "80", "90", "100"],
             ["mAP50 (val)", "0.780", "0.793", "0.797", "0.802", "0.806", "0.810", "0.811", "0.813"],
             ["mAP50-95", "0.570", "0.584", "0.588", "0.594", "0.598", "0.601", "0.601", "0.602"]],
            [24] + [18.75] * 8)]
t += [chart("training_progress.png", 160)]

t += [para("4. Evaluation", H1)]
t += [para("Per-class mAP50. Full test = 8,040 images. <b>Leak-free test</b> = 6,786 test images with no near-duplicate "
           "(dHash distance <= 4) in train; about 16% of val/test had a near-copy in train, mainly consecutive video frames.")]
t += [table([["Class", "Full test (.pt)", "Leak-free test (.pt)", "Full test (INT8)"]] + [list(r) for r in PER_CLASS] +
            [["<b>all</b>", "<b>0.818 / 0.606</b>", "<b>0.805 / 0.590</b>", "<b>0.805 / 0.589</b>"]], [48, 40, 45, 40])]
t += [para("Values in the last row are mAP50 / mAP50-95.", SMALL)]
t += [chart("accuracy_per_class.png", 150)]
t += [para("Video tests (14 test videos, full pipeline incl. PaddleOCR)", H2)]
t += [table([["Model", "Vehicle boxes", "Valid plates", "Accident alert frames", "Fire alert frames", "Flicker %", "Jitter %"],
             ["v5", "104,630", "10", "0 (no class)", "0 (no class)", "29.8", "12.1"],
             ["v6", "43,023", "31", "1,514", "0 (no class)", "44.4", "24.0"],
             ["v8 final", "133,439", "31", "1,161", "438", "35.8", "8.3"]], [22, 26, 22, 30, 28, 22, 22])]
t += [para("Snapshots (epochs 30-90) were tested the same way; the final model is best on 10 of 11 classes. The epoch-60 "
           "checkpoint reads more plates from overhead cameras and is kept as an alternative. "
           "Weight averaging of checkpoints was tried and rejected (mAP50 0.765-0.775).", SMALL)]

t += [para("5. INT8 ONNX conversion", H1)]
t += bullets(["Step 1: export best.pt to FP32 ONNX (opset 17, 1x3x960x960, no NMS, onnxslim). Verified against PyTorch: "
              "max box diff 0.03 px, score diff 1e-5.",
              "Step 2: static calibration with ONNX Runtime, QDQ format, weights INT8 per-channel symmetric, activations UINT8. "
              "600 calibration images from TRAIN (all 12 classes + night). The 24 Detect-head decode nodes stay FP32 (the "
              "output mixes 0-960 px boxes with 0-1 scores).",
              "Methods compared on the test set (mAP50): Percentile 99.999 = <b>0.805</b> (chosen), Entropy 0.804, MinMax 0.782.",
              "Speed on PC CPU (4 threads): FP32 53 ms, INT8 26 ms per frame. Output 1x16x18900 (cx, cy, w, h + 12 class "
              "scores); NMS is done by the application.",
              "Pitfalls found: Entropy/Percentile calibration must be fed in chunks (~500 MB of activations per 960 image); "
              "ORT 1.23 CalibMaxIntermediateOutputs discards MinMax batches (\"No data is collected\")."], P)

t += [para("6. Number-plate reading", H1)]
t += bullets(["Indian formats only: state code (incl. TG, BH series), 1-2 digit district (1 digit only for DL), 1-3 series "
              "letters, 4 digits; at most 2 look-alike characters corrected (O/0, S/5, B/8 ...); anything else rejected.",
              "Clarity filter per crop: upscale to 128 px, non-local-means denoise, deskew (2-20 deg), CLAHE, unsharp mask.",
              "Two-line (bike/auto) plates: split at the emptiest row and read top line first.",
              "Video test: per video, a plate is confirmed when >= 2 frames agree, mean OCR conf >= 0.85 and best >= 0.93; "
              "readings within 2 characters are merged; rejects logged with the reason.",
              "Website: OCR conf >= 0.85, 5 agreeing reads per track, near-duplicate merge, cheapest-first OCR with early "
              "exit and no OCR after confirmation (1.7-2x faster, same plates).",
              "Result on the 14 test videos: 11 confirmed plates, all correct, 0 false (previously 83 readings incl. UK and "
              "junk)."], P)

t += [para("7. Website", H1)]
t += [table([["Area", "Behaviour / threshold"],
             ["Model", "v8 detection model with PaddleOCR for number plates"],
             ["Fire alert", "fire_accident conf >= 0.45 in 60% of a 1 s window; box must contain >= 1.2% orange/red flame pixels"],
             ["Accident alert", "accident_scene conf >= 0.50 in 60% of a 1 s window; weaker boxes not drawn"],
             ["Cooldown", "30 s between repeated accident / fire / road-work alerts"],
             ["Vehicle counts", "unique tracks per type (car, motorcycle, auto, bus, truck, bicycle); people separate"],
             ["Plate counts", "one record per plate per video, 'Times Seen' + 'Last Seen' in Excel, xN on pages"],
             ["Speed display", "upload progress (MB/s); frames X/Y, fps, ms/frame, time left; live page too"],
             ["Known gaps", "images cannot raise alerts (1 s rule); concurrent uploads share one tracker"]], [30, 144])]

t += [PageBreak()]
t += [para("Results per test video (v8, full video test)", H2)]
t += [table([["Video", "Frames", "Vehicle boxes", "Person boxes", "Accident alert frames", "Fire alert frames",
              "Road-work boxes", "Jitter %"],
             ["AQNm... (short clip)", "866", "1,630", "1", "0", "0", "0", "13.4"],
             ["Create_a_highly_realistic", "240", "2,830", "334", "0", "0", "0", "6.6"],
             ["License Plate Test (UK)", "1,800", "36,947", "1", "0", "0", "0", "3.1"],
             ["MicrosoftTeams (fallen bike)", "287", "218", "967", "18", "0", "0", "6.9"],
             ["MicrosoftTeams (1)", "888", "16,918", "336", "246", "0", "0", "3.4"],
             ["MicrosoftTeams (2)", "545", "8,037", "1,642", "0", "0", "0", "5.2"],
             ["VID20260824132342", "1,844", "11,953", "471", "0", "0", "57", "7.1"],
             ["VID20260824132956", "2,110", "10,074", "3,471", "0", "0", "20", "8.5"],
             ["VID20260824133121", "866", "13,494", "3,012", "0", "0", "0", "4.7"],
             ["WhatsApp 12.25.40 (car fire)", "304", "271", "4", "0", "111", "4", "26.6"],
             ["WhatsApp 12.26.27", "1,916", "6,203", "108", "0", "0", "0", "7.0"],
             ["real_accident_cctv_test", "2,298", "14,453", "1,909", "897", "148", "0", "3.5"],
             ["reference_vedio", "1,949", "9,868", "7,627", "0", "0", "0", "8.2"],
             ["videoplayback (4) (car fire)", "304", "543", "9", "0", "179", "0", "11.5"]],
            [38, 14, 20, 18, 24, 20, 20, 16])]
t += [para("Jitter = average frame-to-frame change of the object count (lower = steadier). The 148 fire alert frames on "
           "the CCTV compilation are the dust cloud of a truck crash; the website now blocks this with the flame-colour "
           "check.", SMALL)]
t += [para("INT8 calibration comparison (test set, 8,040 images)", H2)]
t += [table([["Model", "Precision", "Recall", "mAP50", "mAP50-95", "Size", "CPU ms/frame (4 threads)"],
             [".pt (PyTorch)", "0.785", "0.762", "0.818", "0.606", "6 MB", "-"],
             ["FP32 ONNX", "0.784", "0.760", "0.814", "0.600", "12 MB", "53"],
             ["<b>INT8 Percentile 99.999 (chosen)</b>", "0.761", "0.765", "<b>0.805</b>", "0.589", "3.7 MB", "26"],
             ["INT8 Entropy", "0.765", "0.761", "0.804", "0.586", "3.7 MB", "-"],
             ["INT8 MinMax", "0.783", "0.705", "0.782", "0.567", "3.7 MB", "26"]], [50, 18, 16, 16, 18, 16, 40])]
t += [para("Class drops FP32 -> INT8 (mAP50): fire -2.6, road work -2.3, bicycle -1.6, pothole -1.3, all other classes "
           "< 1 point; license_plate unchanged (0.935).", SMALL)]
t += [PageBreak()]
t += [para("8. Known issues", H1)]
t += [table([["#", "Issue", "Evidence", "Fix"],
             ["1", "Potholes weak", "mAP50 0.56-0.60, recall ~0.45", "label clean-up"],
             ["2", "Accident fires 1-3 s before impact", "CCTV clips; ~1 in 5 accident training frames are pre-impact", "relabel pre-impact frames"],
             ["3", "Accident on close-up normal cars", "0.34-0.68 conf", "website 0.50 rule; more negatives"],
             ["4", "Road construction false detections", "data added; bollards / lone signs detected (0.48 conf)", "train separately"],
             ["5", "Overhead plates", "125 -> 1 plate crops (ep30 -> ep100)", "more data"],
             ["6", "Aftermath photos missed", "0.11 / 0 conf on test photos", "more data"],
             ["7", "Smoke-only fire", "no flames -> no alert", "more data"],
             ["8", "Two-line plates", "bike / auto plates sometimes read with one character different", "more labels"],
             ["9", "Concurrent uploads", "same video 11/16/47 vehicles", "code fix"],
             ["10", "Image uploads cannot alert", "fire 0.89 on a photo, no alert", "code fix"],
             ["11", "INT8 drop", "fire -2.6, road work -2.3 points", "calibration"],
             ["12", "Rubik Pi speed unknown", "PC only", "board test"]], [8, 50, 70, 46])]
t += [para("<b>Note - road construction:</b> road-construction data has been added to the dataset and the model detects work zones, but it still gives false detections (for example permanent roadside bollards and lone signs). Road construction <b>will be trained separately</b> as its own improvement step.", P)]

t += [Spacer(1, 10), para("<b>Note - lane change and wrong-direction detection:</b> these will be checked once the camera is fixed in the position where the model needs to be tested, because both depend on the camera view (the lanes and the allowed direction of travel are set for that fixed position).", P)]
build(OUT / "NH5_v8_Report_Technical.pdf", "Technical report", t)
