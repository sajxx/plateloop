"""SQS -> label an ingested image by comparing the live detector with Nova 2 Lite.

Rules (config.yaml labeling.*):
  live box and Nova box overlap (IoU >= accept_iou)         -> accept (label = the live box)
  Nova-only box that looks like a plate, within the cap      -> accept
  live-only, disagreeing, or Nova-only over the cap          -> quarantine
  neither finds a plate                                      -> accept as "no plate"
"""
import json
import os
import re
from decimal import Decimal

import boto3

s3 = boto3.client("s3")
brt = boto3.client("bedrock-runtime")
lam = boto3.client("lambda")
ddb = boto3.resource("dynamodb")

BUCKET = os.environ["BUCKET"]
REQUESTS = ddb.Table(os.environ["REQUESTS_TABLE"])
STATE = ddb.Table(os.environ["STATE_TABLE"])
MODEL = os.environ["BEDROCK_MODEL"]
ACCEPT_IOU = float(os.environ.get("ACCEPT_IOU", "0.5"))
TRIGGER = os.environ.get("TRIGGER_FUNCTION", "")
NEW_LABELS = int(os.environ.get("NEW_LABEL_COUNT", "200"))
MAX_NOVA_ONLY = float(os.environ.get("MAX_NOVA_ONLY_FRACTION", "0.3"))

PROMPT = ("Find every vehicle license plate in this image. Reply with JSON only, in this form: "
          '{"plates":[{"box":[x1,y1,x2,y2]}]}. Coordinates are integers from 0 to 1000, relative to the image '
          "width and height, with (0,0) at the top left. Use {\"plates\":[]} if no plate is visible.")


def iou(a, b):
    iw = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    ih = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = iw * ih
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def ask_nova(body, fmt, w, h):
    resp = brt.converse(
        modelId=MODEL,
        messages=[{"role": "user", "content": [{"image": {"format": fmt, "source": {"bytes": body}}},
                                               {"text": PROMPT}]}],
        inferenceConfig={"maxTokens": 400, "temperature": 0})
    text = resp["output"]["message"]["content"][0]["text"]
    m = re.search(r"\{.*\}", text, re.S)
    boxes = []
    for p in (json.loads(m.group(0)).get("plates", []) if m else []):
        x1, y1, x2, y2 = [float(v) for v in p["box"]]
        boxes.append([x1 * w / 1000, y1 * h / 1000, x2 * w / 1000, y2 * h / 1000])
    return boxes, resp.get("usage", {})


def plausible(box, w, h):
    bw, bh = box[2] - box[0], box[3] - box[1]
    if bw <= 0 or bh <= 0:
        return False
    return 0.0005 <= bw * bh / (w * h) <= 0.5 and 1.2 <= bw / bh <= 6.0


def bump(key, n=1):
    r = STATE.update_item(Key={"key": key}, UpdateExpression="ADD n :d", ExpressionAttributeValues={":d": n},
                          ReturnValues="UPDATED_NEW")
    return int(r["Attributes"]["n"])


def count(key):
    return int(STATE.get_item(Key={"key": key}).get("Item", {}).get("n", 0))


def decide(live, nova, w, h):
    matched, nova_left = [], list(nova)
    for lb in live:
        best = max(nova_left, key=lambda nb: iou(lb, nb), default=None)
        if best is not None and iou(lb, best) >= ACCEPT_IOU:
            matched.append(lb); nova_left.remove(best)
    if not live and not nova:
        return "no_plate", []
    if matched and len(matched) == len(live) and not nova_left:
        return "accepted", matched
    if not live and nova and all(plausible(b, w, h) for b in nova):
        total, only = count("labels_accepted"), count("labels_nova_only")
        if (only + 1) / (total + 1) <= MAX_NOVA_ONLY:
            return "accepted_nova_only", nova
    return "quarantined", []


def handler(event, _ctx):
    for rec in event["Records"]:
        msg = json.loads(rec["body"])
        image_id, key = msg["image_id"], msg["s3_key"]
        row = REQUESTS.get_item(Key={"image_id": image_id}).get("Item")
        if not row:
            continue
        w, h = int(row["width"]), int(row["height"])
        live = [d["box"] for d in json.loads(row["detections"])]
        body = s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
        nova, usage = ask_nova(body, "png" if key.endswith("png") else "jpeg", w, h)

        status, boxes = decide(live, nova, w, h)
        record = {"image_id": image_id, "s3_key": key, "width": w, "height": h, "status": status,
                  "boxes": boxes, "live": live, "nova": nova}
        prefix = "quarantine" if status == "quarantined" else "labels/auto"
        s3.put_object(Bucket=BUCKET, Key=f"{prefix}/{image_id}.json", Body=json.dumps(record),
                      ContentType="application/json")
        REQUESTS.update_item(Key={"image_id": image_id}, UpdateExpression="SET label_status = :s",
                             ExpressionAttributeValues={":s": status})
        if status != "quarantined":
            fresh = bump("new_labels"); bump("labels_accepted")
            if TRIGGER and fresh >= NEW_LABELS:
                lam.invoke(FunctionName=TRIGGER, InvocationType="Event", Payload=json.dumps({"reason": "labels"}).encode())
            if status == "accepted_nova_only":
                bump("labels_nova_only")
        else:
            bump("labels_quarantined")
        bump("nova_input_tokens", int(usage.get("inputTokens", 0)))
        bump("nova_output_tokens", int(usage.get("outputTokens", 0)))
    return {"ok": True}
