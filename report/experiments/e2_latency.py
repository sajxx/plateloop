"""E2: CPU latency and size of the three model formats; ONNX Runtime stability."""
import json, time, numpy as np, cv2, os, sys, onnxruntime as ort
sys.path.insert(0, os.path.dirname(__file__))
from common import *
g = json.load(open(f"{ROOT}/golden/annotations.json"))
imgs = [cv2.imread(f"{ROOT}/golden/images/{i['file_name']}") for i in g["images"]]
res = {}
det = Detector(threads=2)
for im in imgs[:10]: det(im)  # warm-up
pre, inf = [], []
for im in imgs:
    t0 = time.perf_counter(); x = det.prep(im); t1 = time.perf_counter()
    det.c({"image": x, "scale_factor": np.array([[416 / im.shape[0], 416 / im.shape[1]]], np.float32)}); t2 = time.perf_counter()
    pre.append((t1 - t0) * 1000); inf.append((t2 - t1) * 1000)
q = lambda a: dict(median=float(np.median(a)), p95=float(np.percentile(a, 95)), mean=float(np.mean(a)))
res["openvino_2threads"] = dict(preprocess_ms=q(pre), inference_ms=q(inf), total_ms=q(np.array(pre) + np.array(inf)), n=len(imgs))
so = ort.SessionOptions(); so.intra_op_num_threads = 2; so.inter_op_num_threads = 1
s = ort.InferenceSession(f"{ROOT}/models/v1/onnx/plate_detector.onnx", so, providers=["CPUExecutionProvider"])
t_ok, fails = [], 0
for im in imgs:
    x = det.prep(im); sf = np.array([[416 / im.shape[0], 416 / im.shape[1]]], np.float32)
    t0 = time.perf_counter()
    try: s.run(None, {"image": x, "scale_factor": sf}); t_ok.append((time.perf_counter() - t0) * 1000)
    except Exception: fails += 1
res["onnxruntime_2threads"] = dict(inference_ms=q(t_ok), failures=fails, n=len(imgs))
sz = lambda p: os.path.getsize(f"{ROOT}/models/v1/{p}")
res["sizes_mb"] = dict(checkpoint=sz("checkpoint/model_final.pdparams") / 1e6, onnx=sz("onnx/plate_detector.onnx") / 1e6,
    openvino=(sz("openvino/plate_detector_ov.bin") + sz("openvino/plate_detector_ov.xml")) / 1e6)
print(json.dumps(res, indent=1)); json.dump(res, open(f"{ROOT}/report/experiments/e2_results.json", "w"), indent=1)
