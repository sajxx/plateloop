"""Smoke-test the labeller on N golden images using fixture rows; python scripts/test_labeller.py [N] [--keep]."""
import json
import pathlib
import sys
import time
import uuid
from decimal import Decimal

import boto3
import cv2

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "serving" / "code"))
import inference as inf
from _common import CFG, REGION, ROOT

n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 6
s3, ddb, sqs = boto3.client("s3"), boto3.resource("dynamodb"), boto3.client("sqs")
bucket = CFG["aws"]["bucket"]
req, state = ddb.Table(f"{CFG['project']}-requests"), ddb.Table(f"{CFG['project']}-state")
queue = sqs.get_queue_url(QueueName=f"{CFG['project']}-label-queue")["QueueUrl"]
ann = json.load(open(ROOT / "golden" / "annotations.json"))
gt = {}
for a in ann["annotations"]:
    x, y, w, h = a["bbox"]; gt.setdefault(a["image_id"], []).append([x, y, x + w, y + h])
images = ann["images"][:n]

det = inf.model_fn(str(ROOT / "models" / "v1"))
ids = {}
for im in images:
    path = ROOT / "golden" / "images" / im["file_name"]
    body = path.read_bytes()
    pred = inf.predict_fn(inf.input_fn(body, "image/jpeg"), det)
    iid = "test-" + uuid.uuid4().hex[:12]
    key = f"raw/test/{iid}.jpg"
    s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType="image/jpeg")
    req.put_item(Item={"image_id": iid, "s3_key": key, "width": pred["width"], "height": pred["height"],
                       "detections": json.dumps(pred["detections"]), "label_status": "pending"})
    sqs.send_message(QueueUrl=queue, MessageBody=json.dumps({"image_id": iid, "s3_key": key}))
    ids[iid] = im["id"]

print("sent", len(ids), "waiting...")
t0 = time.time()
while time.time() - t0 < 180:
    rows = {i: req.get_item(Key={"image_id": i})["Item"]["label_status"] for i in ids}
    if all(v != "pending" for v in rows.values()):
        break
    time.sleep(5)

def iou(a, b):
    iw = max(0, min(a[2], b[2]) - max(a[0], b[0])); ih = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    i = iw * ih; u = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - i
    return i / u if u else 0

for iid, gid in ids.items():
    st = req.get_item(Key={"image_id": iid})["Item"]["label_status"]
    pre = "quarantine" if st == "quarantined" else "labels/auto"
    try:
        rec = json.loads(s3.get_object(Bucket=bucket, Key=f"{pre}/{iid}.json")["Body"].read())
    except Exception:
        print(iid, st, "(no record)"); continue
    best = [round(max([iou(nb, g) for g in gt.get(gid, [])] or [0]), 2) for nb in rec["nova"]]
    print(f"{iid} {st:20s} live={len(rec['live'])} nova={len(rec['nova'])} gt={len(gt.get(gid, []))} nova-vs-gt IoU={best}")

if "--keep" not in sys.argv:
    for iid in ids:
        req.delete_item(Key={"image_id": iid})
        for k in (f"raw/test/{iid}.jpg", f"labels/auto/{iid}.json", f"quarantine/{iid}.json"):
            s3.delete_object(Bucket=bucket, Key=k)
    for k in ("new_labels", "labels_accepted", "labels_nova_only", "labels_quarantined"):
        state.delete_item(Key={"key": k})
    print("fixtures removed")
