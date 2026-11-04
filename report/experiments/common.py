"""Shared helpers for the report experiments: data access, degradations, OpenVINO inference, COCO scoring."""
import json, re, os, io, contextlib
import numpy as np, cv2
import openvino as ov
from pycocotools.coco import COCO
from pycocotools.cocoeval import COCOeval

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA = os.path.join(ROOT, "data", "original")
IR = os.path.join(ROOT, "models", "v1", "openvino", "plate_detector_ov.xml")
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)
CAT_ID = 1


def stem(f):
    return re.split(r"_jpg\.rf\.|\.rf\.|\.jpg$", f)[0]


def load_split():
    tr = json.load(open(f"{DATA}/train.json"))
    va = json.load(open(f"{DATA}/val.json"))
    t2 = json.load(open(f"{DATA}/train_2k.json"))
    return tr, va, t2


def clean_holdout(va, tr):
    """Validation images whose source picture never appears in the training split."""
    ts = {stem(i["file_name"]) for i in tr["images"]}
    return [i for i in va["images"] if stem(i["file_name"]) not in ts]


class Detector:
    def __init__(self, xml=IR, threads=8):
        core = ov.Core()
        m = core.read_model(xml)
        self.c = core.compile_model(m, "CPU", {"INFERENCE_NUM_THREADS": threads, "PERFORMANCE_HINT": "LATENCY"})
        self.o_det, self.o_n = self.c.outputs[0], self.c.outputs[1]

    @staticmethod
    def prep(bgr):
        x = cv2.resize(bgr, (416, 416), interpolation=cv2.INTER_CUBIC)[:, :, ::-1].astype(np.float32) / 255
        return ((x - MEAN) / STD).transpose(2, 0, 1)[None].astype(np.float32)

    def __call__(self, bgr):
        h, w = bgr.shape[:2]
        sf = np.array([[416 / h, 416 / w]], np.float32)
        r = self.c({"image": self.prep(bgr), "scale_factor": sf})
        n = int(np.array(r[self.o_n])[0])
        return np.array(r[self.o_det])[:n]  # rows: class, score, x1, y1, x2, y2 (original pixels)


def to_coco_dets(image_id, dets, min_score=0.01):
    out = []
    for c, s, x1, y1, x2, y2 in dets:
        if s >= min_score:
            out.append({"image_id": image_id, "category_id": CAT_ID, "score": float(s),
                        "bbox": [float(x1), float(y1), float(x2 - x1), float(y2 - y1)]})
    return out


def coco_eval(gt_json, dets, img_ids):
    """Return AP50:95, AP50, AP75, AR@100 on the listed images."""
    with contextlib.redirect_stdout(io.StringIO()):
        gt = COCO(gt_json)
        if not dets:
            return dict(AP=0, AP50=0, AP75=0, AR=0)
        dt = gt.loadRes(dets)
        e = COCOeval(gt, dt, "bbox")
        e.params.imgIds = list(img_ids)
        e.evaluate(); e.accumulate(); e.summarize()
    s = e.stats
    return dict(AP=float(s[0]), AP50=float(s[1]), AP75=float(s[2]), AR=float(s[8]))


def iou(a, b):
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1]); ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1); inter = iw * ih
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / u if u > 0 else 0.0


def prf(per_image, thr, iou_thr=0.5):
    """per_image: list of (dets[n,6], gt[[x1,y1,x2,y2],...]). Greedy match by score."""
    tp = fp = fn = 0
    for dets, gts in per_image:
        d = dets[dets[:, 1] >= thr]
        d = d[np.argsort(-d[:, 1])]
        used = set()
        for row in d:
            best, bj = 0, -1
            for j, g in enumerate(gts):
                if j in used: continue
                v = iou(row[2:6], g)
                if v > best: best, bj = v, j
            if best >= iou_thr: tp += 1; used.add(bj)
            else: fp += 1
        fn += len(gts) - len(used)
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


# ---- degradations (used for the drift and retraining experiments) ----
def darken(img, f):
    return np.clip(img.astype(np.float32) * f, 0, 255).astype(np.uint8)

def blur(img, sigma):
    return img if sigma <= 0 else cv2.GaussianBlur(img, (0, 0), sigma)

def noise(img, sigma, seed=0):
    if sigma <= 0: return img
    rng = np.random.default_rng(seed)
    return np.clip(img.astype(np.float32) + rng.normal(0, sigma, img.shape), 0, 255).astype(np.uint8)

def blur_score(img):
    return float(cv2.Laplacian(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())

def brightness(img):
    return float(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).mean())


def gt_boxes(coco_json):
    d = json.load(open(coco_json)); m = {}
    for a in d["annotations"]:
        x, y, w, h = a["bbox"]; m.setdefault(a["image_id"], []).append([x, y, x + w, y + h])
    return m
