"""Heavy pipeline stages, run inside CodeBuild:  python pipeline/stage.py prepare|train|evaluate

Environment: BUCKET, RUN_ID, BASE_VERSION (the live model), ORIGINAL_MIX (0.7).
"""
import json
import os
import pathlib
import random
import shutil
import subprocess
import sys
import tarfile

import boto3
import cv2
import numpy as np
import openvino as ov
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUCKET, RUN, BASE = os.environ["BUCKET"], os.environ["RUN_ID"], os.environ["BASE_VERSION"]
CFG = yaml.safe_load((ROOT / "config.yaml").read_text())
s3 = boto3.client("s3")
RUN_PREFIX = f"runs/{RUN}"
DATA = ROOT / "data"
PD = ROOT / "training" / "paddledet"
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)


def download(prefix, dest, suffix=None):
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=prefix):
        for o in page.get("Contents", []):
            if o["Key"].endswith("/") or (suffix and not o["Key"].endswith(suffix)):
                continue
            s3.download_file(BUCKET, o["Key"], str(dest / pathlib.Path(o["Key"]).name)); n += 1
    return n


def upload_dir(src, prefix):
    for f in src.rglob("*"):
        if f.is_file():
            s3.upload_file(str(f), BUCKET, f"{prefix}/{f.relative_to(src)}")


# ---------------------------------------------------------------- prepare
def prepare():
    out = DATA / "finetune"
    (out / "images").mkdir(parents=True, exist_ok=True)
    orig = DATA / "original"
    download("datasets/original/images/", orig / "images")
    s3.download_file(BUCKET, "datasets/original/train_2k.json", str(orig / "train_2k.json"))
    base = json.load(open(orig / "train_2k.json"))

    labels = []
    tmp = DATA / "labels"; tmp.mkdir(exist_ok=True)
    download("labels/auto/", tmp, ".json")
    for f in sorted(tmp.glob("*.json")):
        rec = json.load(open(f))
        if rec["status"] in ("accepted", "accepted_nova_only", "accepted_reviewed", "no_plate"):
            labels.append(rec)
    random.seed(42); random.shuffle(labels)
    mix = float(os.environ.get("ORIGINAL_MIX", CFG["training"]["original_data_mix"]))
    n_new = len(labels)
    n_orig = min(len(base["images"]), int(n_new * mix / (1 - mix)))
    n_new = min(n_new, int(n_orig * (1 - mix) / mix)) if n_orig == len(base["images"]) else n_new
    labels = labels[:n_new]

    images, anns = [], []
    boxes_by_img = {}
    for a in base["annotations"]:
        boxes_by_img.setdefault(a["image_id"], []).append(a["bbox"])
    chosen = random.sample(base["images"], n_orig)
    iid = 1
    for im in chosen:
        shutil.copy(orig / "images" / im["file_name"], out / "images" / im["file_name"])
        images.append({"id": iid, "file_name": im["file_name"], "width": im["width"], "height": im["height"]})
        for b in boxes_by_img.get(im["id"], []):
            anns.append({"id": len(anns) + 1, "image_id": iid, "category_id": 1, "bbox": b,
                         "area": b[2] * b[3], "iscrowd": 0})
        iid += 1
    for rec in labels:
        name = f"new_{rec['image_id']}{pathlib.Path(rec['s3_key']).suffix}"
        s3.download_file(BUCKET, rec["s3_key"], str(out / "images" / name))
        images.append({"id": iid, "file_name": name, "width": rec["width"], "height": rec["height"]})
        for x1, y1, x2, y2 in rec["boxes"]:
            anns.append({"id": len(anns) + 1, "image_id": iid, "category_id": 1,
                         "bbox": [x1, y1, x2 - x1, y2 - y1], "area": (x2 - x1) * (y2 - y1), "iscrowd": 0})
        iid += 1
    json.dump({"images": images, "annotations": anns, "categories": [{"id": 1, "name": "license_plate"}]},
              open(out / "train.json", "w"))
    summary = {"original_images": n_orig, "new_images": n_new, "boxes": len(anns), "base_version": BASE}
    print(summary)
    s3.put_object(Bucket=BUCKET, Key=f"{RUN_PREFIX}/dataset.json", Body=json.dumps(summary))
    s3.upload_file(str(out / "train.json"), BUCKET, f"{RUN_PREFIX}/train.json")
    # the train stage runs in a fresh container, so keep the image set in S3 too
    for f in (out / "images").iterdir():
        s3.upload_file(str(f), BUCKET, f"{RUN_PREFIX}/images/{f.name}")


# ---------------------------------------------------------------- train
def run(cmd, cwd):
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def train():
    out = DATA / "finetune"
    download(f"{RUN_PREFIX}/images/", out / "images")
    s3.download_file(BUCKET, f"{RUN_PREFIX}/train.json", str(out / "train.json"))
    ck = ROOT / "models" / BASE / "checkpoint"
    download(f"models/{BASE}/checkpoint/", ck)
    py = sys.executable
    run([py, "tools/train.py", "-c", "configs/picodet/picodet_xs_plate_finetune.yml",
         "-o", "use_gpu=false", f"pretrain_weights={ck}/model_final"], PD)
    found = next((PD / "output").rglob("model_final.pdparams"))     # the save folder differs between versions
    ckpt_dir, weights = found.parent, found.with_suffix("")
    export = ROOT / "export"
    run([py, "tools/export_model.py", "-c", "configs/picodet/picodet_xs_plate_finetune.yml",
         "-o", f"weights={weights}", "use_gpu=false", "--output_dir", str(export)], PD)
    inf = export / "picodet_xs_plate_finetune"
    model = ov.convert_model(str(inf / "model.pdmodel"))
    pkg = ROOT / "package"
    (pkg / "openvino").mkdir(parents=True, exist_ok=True)
    ov.save_model(model, str(pkg / "openvino" / "plate_detector_ov.xml"))
    shutil.copytree(ROOT / "serving" / "code", pkg / "code", dirs_exist_ok=True)
    n_images = len(json.load(open(DATA / "finetune" / "train.json"))["images"])
    (pkg / "MANIFEST.json").write_text(json.dumps({"run_id": RUN, "base_version": BASE, "train_images": n_images}))
    tar = ROOT / "model.tar.gz"
    with tarfile.open(tar, "w:gz") as t:
        for f in sorted(pkg.rglob("*")):
            if f.is_file():
                t.add(f, arcname=str(f.relative_to(pkg)))
    s3.upload_file(str(tar), BUCKET, f"{RUN_PREFIX}/model.tar.gz")
    upload_dir(pkg / "openvino", f"{RUN_PREFIX}/openvino")
    for f in ckpt_dir.glob("model_final.*"):
        s3.upload_file(str(f), BUCKET, f"{RUN_PREFIX}/checkpoint/{f.name}")
    print("uploaded candidate to", f"{RUN_PREFIX}/")


# ---------------------------------------------------------------- evaluate
def load(xml):
    core = ov.Core()
    return core.compile_model(core.read_model(xml), "CPU", {"INFERENCE_NUM_THREADS": os.cpu_count() or 2})


def detect(comp, bgr):
    h, w = bgr.shape[:2]
    x = cv2.resize(bgr, (416, 416), interpolation=cv2.INTER_CUBIC)[:, :, ::-1].astype(np.float32) / 255
    x = ((x - MEAN) / STD).transpose(2, 0, 1)[None].astype(np.float32)
    r = comp({"image": x, "scale_factor": np.array([[416 / h, 416 / w]], np.float32)})
    n = int(np.array(r[comp.outputs[1]])[0])
    return np.array(r[comp.outputs[0]])[:n]


def iou(a, b):
    iw = max(0, min(a[2], b[2]) - max(a[0], b[0])); ih = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    i = iw * ih; u = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - i
    return i / u if u else 0.0


def score(comp, images, gt, gt_json):
    import contextlib, io
    from pycocotools.coco import COCO
    from pycocotools.cocoeval import COCOeval
    dets, per = [], []
    for im in images:
        rows = detect(comp, cv2.imread(str(DATA / "golden" / "images" / im["file_name"])))
        for _, s, x1, y1, x2, y2 in rows:
            if s >= 0.01:
                dets.append({"image_id": im["id"], "category_id": 1, "score": float(s),
                             "bbox": [float(x1), float(y1), float(x2 - x1), float(y2 - y1)]})
        per.append((rows[rows[:, 1] >= CFG["model"]["score_threshold"]], gt.get(im["id"], [])))
    with contextlib.redirect_stdout(io.StringIO()):
        g = COCO(str(gt_json)); e = COCOeval(g, g.loadRes(dets), "bbox") if dets else None
        if e:
            e.params.imgIds = [i["id"] for i in images]; e.evaluate(); e.accumulate(); e.summarize()
    tp = fn = fp = 0
    for rows, gts in per:
        used = set()
        for r in rows[np.argsort(-rows[:, 1])]:
            best, bj = 0, -1
            for j, b in enumerate(gts):
                if j not in used and iou(r[2:6], b) > best:
                    best, bj = iou(r[2:6], b), j
            if best >= 0.5: tp += 1; used.add(bj)
            else: fp += 1
        fn += len(gts) - len(used)
    return {"ap50": float(e.stats[1]) if e else 0.0, "ap": float(e.stats[0]) if e else 0.0,
            "recall": tp / (tp + fn) if tp + fn else 0.0, "precision": tp / (tp + fp) if tp + fp else 0.0}


def evaluate():
    gold = DATA / "golden"
    download("golden/images/", gold / "images")
    s3.download_file(BUCKET, "golden/annotations.json", str(gold / "annotations.json"))
    ann = json.load(open(gold / "annotations.json"))
    gt = {}
    for a in ann["annotations"]:
        x, y, w, h = a["bbox"]; gt.setdefault(a["image_id"], []).append([x, y, x + w, y + h])
    for name, prefix in (("live", f"models/{BASE}/openvino"), ("candidate", f"{RUN_PREFIX}/openvino")):
        download(prefix + "/", ROOT / "eval" / name)
    res = {"base_version": BASE, "golden_images": len(ann["images"])}
    for name in ("live", "candidate"):
        res[name] = score(load(str(ROOT / "eval" / name / "plate_detector_ov.xml")), ann["images"], gt,
                          gold / "annotations.json")
        print(name, res[name], flush=True)
    s3.put_object(Bucket=BUCKET, Key=f"{RUN_PREFIX}/metrics.json", Body=json.dumps(res))


if __name__ == "__main__":
    {"prepare": prepare, "train": train, "evaluate": evaluate}[sys.argv[1]]()
