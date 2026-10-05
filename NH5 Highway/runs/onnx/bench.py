"""Speed: ONNX Runtime CPU latency, batch 1, 960x960 (4 threads ~ a phone/SoC CPU budget, and all 32 threads)."""
import sys, time, glob, numpy as np, onnxruntime as ort
for path in sys.argv[1:]:
    for th in (4, 32):
        so = ort.SessionOptions(); so.intra_op_num_threads = th
        s = ort.InferenceSession(path, so, providers=["CPUExecutionProvider"])
        x = np.random.rand(1, 3, 960, 960).astype(np.float32)
        for _ in range(5): s.run(None, {"images": x})
        t = []
        for _ in range(30):
            a = time.perf_counter(); s.run(None, {"images": x}); t.append(time.perf_counter() - a)
        ms = 1000 * float(np.median(t))
        print(f"BENCH {path.split('/')[-1]:32s} threads={th:2d}  {ms:7.1f} ms  {1000/ms:6.1f} FPS", flush=True)
