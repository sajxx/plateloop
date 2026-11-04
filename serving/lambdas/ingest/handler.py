"""POST /predict: store the image, call the endpoint, record the result, return the boxes.

Idempotency: send an `Idempotency-Key` header (letters, digits, - and _, 8-128 chars). The key becomes the request id,
so sending the same key again returns the stored result instead of running detection, saving or labelling a second time.
Nothing is saved when the detector is unavailable, so a retry starts clean.
"""
import base64
import datetime as dt
import json
import os
import re
import uuid

import boto3
from botocore.exceptions import ClientError

s3 = boto3.client("s3")
smr = boto3.client("sagemaker-runtime")
ddb = boto3.resource("dynamodb")
sqs = boto3.client("sqs")

BUCKET = os.environ["BUCKET"]
ENDPOINT = os.environ["ENDPOINT_NAME"]
REQUESTS = ddb.Table(os.environ["REQUESTS_TABLE"])
QUEUE_URL = os.environ.get("LABEL_QUEUE_URL", "")
TTL_DAYS = int(os.environ.get("TTL_DAYS", "30"))
KEY_RE = re.compile(r"^[A-Za-z0-9_\-]{8,128}$")
STALE_SECONDS = 90          # a claim older than this belongs to an attempt that died


def respond(code, body):
    return {"statusCode": code, "headers": {"content-type": "application/json"}, "body": json.dumps(body)}


def emf(pred):
    """Embedded metric format: CloudWatch turns this log line into custom metrics."""
    s = pred["stats"]
    print(json.dumps({
        "_aws": {"Timestamp": int(dt.datetime.now().timestamp() * 1000),
                 "CloudWatchMetrics": [{"Namespace": "PlateLoop", "Dimensions": [[]],
                                        "Metrics": [{"Name": n, "Unit": "None"} for n in
                                                    ("TopConfidence", "NoPlate", "Detections", "Brightness", "BlurScore")]}]},
        "TopConfidence": pred["top_confidence"], "NoPlate": 0 if pred["detections"] else 1,
        "Detections": len(pred["detections"]), "Brightness": s["brightness"], "BlurScore": s["blur_score"]}))


def stored_result(row):
    return {"image_id": row["image_id"], "model_version": row.get("model_version"), "width": int(row["width"]),
            "height": int(row["height"]), "detections": json.loads(row.get("detections", "[]")),
            "top_confidence": float(row.get("top_confidence", 0)), "label_status": row.get("label_status"),
            "stats": {"brightness": float(row.get("brightness", 0)), "blur_score": float(row.get("blur_score", 0)),
                      "box_area": float(row.get("box_area", 0))}}


def claim(image_id, now):
    """Reserve the id. Returns None when we own it, or a response to return straight away."""
    item = {"image_id": image_id, "ts": now.isoformat(), "label_status": "processing",
            "ttl": int(now.timestamp()) + TTL_DAYS * 86400}
    try:
        REQUESTS.put_item(Item=item, ConditionExpression="attribute_not_exists(image_id)")
        return None
    except ClientError as e:
        if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
    old = REQUESTS.get_item(Key={"image_id": image_id}).get("Item") or {}
    if old.get("label_status") != "processing":
        return respond(200, {**stored_result(old), "duplicate": True})
    age = (now - dt.datetime.fromisoformat(old["ts"])).total_seconds()
    if age < STALE_SECONDS:
        return respond(202, {"image_id": image_id, "status": "processing", "duplicate": True})
    try:                                                      # the earlier attempt died: take its place
        REQUESTS.put_item(Item=item, ConditionExpression="#t = :old", ExpressionAttributeNames={"#t": "ts"},
                          ExpressionAttributeValues={":old": old["ts"]})
        return None
    except ClientError:
        return respond(202, {"image_id": image_id, "status": "processing", "duplicate": True})


def handler(event, _ctx):
    body = base64.b64decode(event["body"]) if event.get("isBase64Encoded") else (event.get("body") or "").encode()
    if not body:
        return respond(400, {"error": "empty body: send the image bytes"})
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    ctype = headers.get("content-type", "image/jpeg")
    if ctype not in ("image/jpeg", "image/png"):
        return respond(415, {"error": "content-type must be image/jpeg or image/png"})
    key = headers.get("idempotency-key")
    if key is not None and not KEY_RE.match(key):
        return respond(400, {"error": "Idempotency-Key must be 8-128 letters, digits, - or _"})
    image_id = key or uuid.uuid4().hex
    now = dt.datetime.now(dt.timezone.utc)

    early = claim(image_id, now)
    if early:
        return early
    try:
        try:
            out = smr.invoke_endpoint(EndpointName=ENDPOINT, ContentType=ctype, Body=body)
        except ClientError as e:
            if e.response["Error"]["Code"] in ("ValidationError", "ServiceUnavailable", "ModelError"):
                REQUESTS.delete_item(Key={"image_id": image_id})          # nothing saved, so a retry starts clean
                return respond(503, {"error": "detector is offline; start it from the control panel or scripts/up.py",
                                     "image_id": image_id})
            raise
        pred = json.loads(out["Body"].read())
        s3_key = f"raw/{now:%Y/%m/%d}/{image_id}.{'png' if ctype.endswith('png') else 'jpg'}"
        s3.put_object(Bucket=BUCKET, Key=s3_key, Body=body, ContentType=ctype)
        REQUESTS.put_item(Item={
            "image_id": image_id, "ts": now.isoformat(), "s3_key": s3_key, "model_version": pred["model_version"],
            "width": pred["width"], "height": pred["height"], "n_detections": len(pred["detections"]),
            "top_confidence": str(pred["top_confidence"]), "brightness": str(pred["stats"]["brightness"]),
            "blur_score": str(pred["stats"]["blur_score"]), "box_area": str(pred["stats"]["box_area"]),
            "detections": json.dumps(pred["detections"]), "label_status": "pending",
            "ttl": int(now.timestamp()) + TTL_DAYS * 86400})
    except Exception:
        REQUESTS.delete_item(Key={"image_id": image_id})
        raise
    emf(pred)
    if QUEUE_URL:
        sqs.send_message(QueueUrl=QUEUE_URL, MessageBody=json.dumps({"image_id": image_id, "s3_key": s3_key}))
    return respond(200, {"image_id": image_id, "model_version": pred["model_version"],
                         "width": pred["width"], "height": pred["height"], "detections": pred["detections"],
                         "top_confidence": pred["top_confidence"], "stats": pred["stats"], "duplicate": False})
