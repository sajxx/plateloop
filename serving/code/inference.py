"""SageMaker handlers for the plate detector (OpenVINO IR, CPU).

Runs inside the AWS scikit-learn container: model_fn / input_fn / predict_fn / output_fn.
Input: raw image bytes (image/jpeg or image/png). Output: JSON with boxes in original pixels.
"""
import json
import os

import cv2
import numpy as np
import openvino as ov

MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)
SIZE = 416
SCORE_THRESHOLD = float(os.environ.get("SCORE_THRESHOLD", "0.4"))
THREADS = int(os.environ.get("INFERENCE_THREADS", "2"))
MODEL_VERSION = os.environ.get("MODEL_VERSION", "unknown")


class Detector:
    def __init__(self, xml_path):
        core = ov.Core()
        compiled = core.compile_model(
            core.read_model(xml_path), "CPU",
            {"INFERENCE_NUM_THREADS": THREADS, "PERFORMANCE_HINT": "LATENCY"},
        )
        self.compiled = compiled
        self.out_boxes, self.out_count = compiled.outputs[0], compiled.outputs[1]

    @staticmethod
    def preprocess(bgr):
        x = cv2.resize(bgr, (SIZE, SIZE), interpolation=cv2.INTER_CUBIC)[:, :, ::-1].astype(np.float32) / 255
        return ((x - MEAN) / STD).transpose(2, 0, 1)[None].astype(np.float32)

    def detect(self, bgr):
        h, w = bgr.shape[:2]
        scale = np.array([[SIZE / h, SIZE / w]], np.float32)
        res = self.compiled({"image": self.preprocess(bgr), "scale_factor": scale})
        n = int(np.array(res[self.out_count])[0])
        return np.array(res[self.out_boxes])[:n]   # class, score, x1, y1, x2, y2


def model_fn(model_dir):
    return Detector(os.path.join(model_dir, "openvino", "plate_detector_ov.xml"))


def input_fn(body, content_type):
    if content_type not in ("image/jpeg", "image/png", "application/x-image", "application/octet-stream"):
        raise ValueError(f"unsupported content type {content_type}")
    img = cv2.imdecode(np.frombuffer(body, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("could not decode image")
    return img


def predict_fn(img, detector):
    h, w = img.shape[:2]
    rows = detector.detect(img)
    rows = rows[rows[:, 1] >= SCORE_THRESHOLD]
    rows = rows[np.argsort(-rows[:, 1])]
    dets = [{"score": round(float(r[1]), 4),
             "box": [round(float(min(max(r[2], 0), w)), 1), round(float(min(max(r[3], 0), h)), 1),
                     round(float(min(max(r[4], 0), w)), 1), round(float(min(max(r[5], 0), h)), 1)]}
            for r in rows]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    area = max((d["box"][2] - d["box"][0]) * (d["box"][3] - d["box"][1]) for d in dets) / (w * h) if dets else 0.0
    return {"model_version": MODEL_VERSION, "width": w, "height": h,
            "detections": dets, "top_confidence": dets[0]["score"] if dets else 0.0,
            "stats": {"brightness": round(float(gray.mean()), 2),
                      "blur_score": round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 2),
                      "box_area": round(float(area), 5)}}


def output_fn(prediction, accept):
    return json.dumps(prediction), "application/json"
