"""How much accuracy does INT8 (what the Rubik Pi 3 NPU runs) cost? Export -> ONNX -> static QDQ INT8 quantization -> compare mAP on a val subset.
Calibration images come from the v6 TRAIN split only (never from vedios/). Usage: int8_check.py <onnx> <imgsz> <tag>"""
import sys, os, glob, random, numpy as np, cv2, subprocess
import onnxruntime as ort
from onnxruntime.quantization import quantize_static, CalibrationDataReader, QuantFormat, QuantType, CalibrationMethod
onnx_path, SZ, tag = sys.argv[1], int(sys.argv[2]), sys.argv[3]
R = "datasets/processed_v2_plus_v6_v6"; OUT = f"runs/deploy_test/{tag}"; os.makedirs(OUT, exist_ok=True)
random.seed(9)
tr = sorted(glob.glob(f"{R}/images/train/*.*")); cal = random.sample(tr, 300)
va = sorted(glob.glob(f"{R}/images/val/*.*")); sub = random.sample(va, 1500)
open(f"{OUT}/val_subset.txt", "w").write("\n".join(os.path.abspath(p) for p in sub) + "\n")
open(f"{OUT}/data.yaml", "w").write(f"path: {os.path.abspath(R)}\ntrain: images/train\nval: {os.path.abspath(OUT)}/val_subset.txt\nnc: 13\nnames: ['person','bicycle','car','motorcycle','bus','truck','pothole','license_plate','auto','road_construction','accident_scene','traffic_cone','fire_accident']\n")
def letterbox(im, s):
    h, w = im.shape[:2]; r = min(s / h, s / w); nh, nw = round(h * r), round(w * r)
    im = cv2.resize(im, (nw, nh), interpolation=cv2.INTER_LINEAR); top, left = (s - nh) // 2, (s - nw) // 2
    out = np.full((s, s, 3), 114, np.uint8); out[top:top + nh, left:left + nw] = im; return out
class Reader(CalibrationDataReader):
    def __init__(self, files, name): self.it = iter(files); self.name = name
    def get_next(self):
        p = next(self.it, None)
        if p is None: return None
        im = letterbox(cv2.imread(p), SZ)[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0
        return {self.name: im}
inp = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"]).get_inputs()[0].name
q = f"{OUT}/model_int8.onnx"
quantize_static(onnx_path, q, Reader(cal, inp), quant_format=QuantFormat.QDQ, activation_type=QuantType.QUInt8, weight_type=QuantType.QInt8,
                per_channel=True, calibrate_method=CalibrationMethod.MinMax, extra_options={"ActivationSymmetric": False, "WeightSymmetric": True})
print("quantized ->", q, os.path.getsize(q) / 1e6, "MB", flush=True)
for name, path in (("FP32", onnx_path), ("INT8", q)):
    r = subprocess.run(["yolo", "val", f"model={path}", f"data={OUT}/data.yaml", f"imgsz={SZ}", "batch=1", "device=cpu", "plots=False", f"project={OUT}", f"name=val_{name}", "exist_ok=True"], capture_output=True, text=True)
    lines = [l for l in (r.stdout + r.stderr).replace("\r", "\n").splitlines() if l.strip().split(" ")[0] in ("all", "person", "car", "pothole", "license_plate", "road_construction", "accident_scene", "traffic_cone", "fire_accident", "motorcycle", "truck")]
    print(f"== {name} =="); [print(l[:110]) for l in lines[-11:]]
