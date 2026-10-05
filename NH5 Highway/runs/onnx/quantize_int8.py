"""Step 2: FP32 ONNX -> INT8 ONNX with static calibration (ONNX Runtime, QDQ format).
Usage: python3 quantize_int8.py <minmax|entropy|percentile> [n_calib_images]

- Calibration images: calib_images.txt (600 train images, every class represented; never vedios/, never val/test).
- Preprocessing identical to Ultralytics inference: letterbox 960 (pad 114), BGR->RGB, /255, NCHW float32.
- Weights: INT8 symmetric per-channel. Activations: UINT8 asymmetric (QNN/HTP-friendly QDQ layout).
- The Detect-head decode tail (DFL softmax, box decode, sigmoid, final concat) stays FP32: the output tensor mixes
  box pixels (0-960) with class scores (0-1), and one 8-bit scale for both would destroy the scores.
"""
import os, sys, time
import cv2, numpy as np, onnx
from onnxruntime.quantization import (CalibrationDataReader, CalibrationMethod, QuantFormat, QuantType,
                                      quantize_static)
from onnxruntime.quantization.shape_inference import quant_pre_process
from onnxruntime.quantization import calibrate as _cal

# Entropy/Percentile calibration keeps every image's activations in RAM before building histograms (~60 MB per
# 960x960 image here -> ~36 GB for 600). Feed the calibrator in chunks instead: its HistogramCollector merges the
# histograms across calls, so the result covers all images while memory stays at one chunk.
CHUNK = 8
_orig_collect = _cal.HistogramCalibrater.collect_data


class _ListReader(CalibrationDataReader):
    def __init__(self, items):
        self.items = iter(items)

    def get_next(self):
        return next(self.items, None)


def _chunked_collect(self, data_reader):
    while True:
        chunk = []
        for _ in range(CHUNK):
            x = data_reader.get_next()
            if not x:
                break
            chunk.append(x)
        if not chunk:
            return
        _orig_collect(self, _ListReader(chunk))
        if len(chunk) < CHUNK:
            return


_cal.HistogramCalibrater.collect_data = _chunked_collect

HERE = os.path.dirname(os.path.abspath(__file__))
FP32 = f"{HERE}/nh5_v8_fp32.onnx"
PRE = f"{HERE}/nh5_v8_fp32_prep.onnx"
METHOD = sys.argv[1] if len(sys.argv) > 1 else "entropy"
N = int(sys.argv[2]) if len(sys.argv) > 2 else 600
OUT = f"{HERE}/nh5_v8_int8_{METHOD}.onnx"


def letterbox(img, size=960):
    h, w = img.shape[:2]; r = min(size / h, size / w)
    nh, nw = round(h * r), round(w * r)
    img = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    top, left = (size - nh) // 2, (size - nw) // 2
    out = np.full((size, size, 3), 114, np.uint8); out[top:top + nh, left:left + nw] = img
    return out


def preprocess(path):
    x = letterbox(cv2.imread(path))[:, :, ::-1].transpose(2, 0, 1)
    return np.ascontiguousarray(x, dtype=np.float32)[None] / 255.0


class Reader(CalibrationDataReader):
    def __init__(self, paths):
        self.paths = iter(paths); self.n = 0

    def get_next(self):
        p = next(self.paths, None)
        if p is None:
            return None
        self.n += 1
        if self.n % 100 == 0:
            print(f"  calibrated {self.n} images", flush=True)
        return {"images": preprocess(p)}


def decode_tail(model):
    """Names of the Detect-head post-processing nodes that must stay FP32: everything in /model.22/ that is NOT part
    of the box (cv2.*) or class (cv3.*) conv branches -- i.e. reshapes/concats, DFL, box decode, sigmoid, output."""
    return [n.name for n in model.graph.node
            if n.name.startswith("/model.22/") and not n.name.startswith(("/model.22/cv2", "/model.22/cv3"))]


if __name__ == "__main__":
    if not os.path.exists(PRE):
        quant_pre_process(FP32, PRE, skip_symbolic_shape=True)
    model = onnx.load(PRE)
    exclude = decode_tail(model)
    paths = [l.strip() for l in open(f"{HERE}/calib_images.txt") if l.strip()][:N]
    method = {"minmax": CalibrationMethod.MinMax, "entropy": CalibrationMethod.Entropy,
              "percentile": CalibrationMethod.Percentile}[METHOD]
    # (no CalibMaxIntermediateOutputs: in ORT 1.23 it discards each batch instead of merging it -> "No data is
    # collected". MinMax doesn't need it: it only keeps per-tensor min/max values, a few MB per image.)
    extra = {"ActivationSymmetric": False, "WeightSymmetric": True, "CalibTensorRangeSymmetric": False}
    if METHOD == "percentile":
        extra["CalibPercentile"] = 99.999
    if METHOD == "entropy":
        extra["CalibNumBins"] = 2048
    print(f"{METHOD}: {len(paths)} calibration images, {len(exclude)} decode nodes kept FP32", flush=True)
    t = time.time()
    quantize_static(PRE, OUT, Reader(paths), quant_format=QuantFormat.QDQ, per_channel=True,
                    activation_type=QuantType.QUInt8, weight_type=QuantType.QInt8, calibrate_method=method,
                    nodes_to_exclude=exclude, extra_options=extra)
    print(f"saved {OUT} ({os.path.getsize(OUT) / 1e6:.1f} MB) in {time.time() - t:.0f}s", flush=True)
