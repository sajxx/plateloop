"""Small pipeline steps: release_rule, register, finish."""
import datetime as dt
import json
import os

import boto3

s3 = boto3.client("s3")
sm = boto3.client("sagemaker")
ddb = boto3.resource("dynamodb")
STATE = ddb.Table(os.environ["STATE_TABLE"])
BUCKET = os.environ["BUCKET"]
GROUP = os.environ["MODEL_GROUP"]
IMAGE = os.environ["IMAGE"]
MIN_GAIN = float(os.environ.get("MIN_AP50_GAIN", "0.01"))


def release_rule(ev):
    m = json.loads(s3.get_object(Bucket=BUCKET, Key=f"runs/{ev['run_id']}/metrics.json")["Body"].read())
    live, cand = m["live"], m["candidate"]
    gain = cand["ap50"] - live["ap50"]
    passed = gain >= MIN_GAIN and cand["recall"] >= live["recall"]
    return {"passed": passed, "ap50_gain": round(gain, 4), "live": live, "candidate": cand}


def register(ev):
    try:
        sm.describe_model_package_group(ModelPackageGroupName=GROUP)
    except sm.exceptions.ClientError:
        sm.create_model_package_group(ModelPackageGroupName=GROUP, ModelPackageGroupDescription="Plate detector versions")
    n = int(STATE.update_item(Key={"key": "model_version_counter"}, UpdateExpression="ADD n :one",
                              ExpressionAttributeValues={":one": 1}, ReturnValues="UPDATED_NEW")["Attributes"]["n"])
    version = f"v{n + 1}"                                     # v1 is the model the system started with
    rule = ev["rule"]
    pkg = sm.create_model_package(
        ModelPackageGroupName=GROUP, ModelApprovalStatus="PendingManualApproval",
        ModelPackageDescription=f"Fine-tuned from {ev['base_version']} ({ev['reason']} run {ev['run_id']})",
        CustomerMetadataProperties={"version": version, "run_id": ev["run_id"], "base_version": ev["base_version"],
                                    "ap50_live": str(round(rule["live"]["ap50"], 4)),
                                    "ap50_candidate": str(round(rule["candidate"]["ap50"], 4))},
        InferenceSpecification={
            "Containers": [{"Image": IMAGE, "ModelDataUrl": f"s3://{BUCKET}/runs/{ev['run_id']}/model.tar.gz"}],
            "SupportedContentTypes": ["image/jpeg", "image/png"], "SupportedResponseMIMETypes": ["application/json"]})
    return {"version": version, "model_package_arn": pkg["ModelPackageArn"]}


def finish(ev):
    now = int(dt.datetime.now(dt.timezone.utc).timestamp())
    outcome = ev["outcome"]                                   # registered | not_better | failed
    # a failed run does not start the cooldown, so it can be retried straight away
    expr = "SET #s = :i, finished_at = :n, outcome = :o" + (" REMOVE started_at" if outcome == "failed" else "")
    STATE.update_item(Key={"key": "retrain_lock"}, UpdateExpression=expr,
                      ExpressionAttributeNames={"#s": "status"},
                      ExpressionAttributeValues={":i": "idle", ":n": now, ":o": outcome})
    if outcome != "failed":                                   # the labels were used, so start counting again
        STATE.put_item(Item={"key": "new_labels", "n": 0})
    STATE.put_item(Item={"key": f"run#{ev['run_id']}", "outcome": outcome, "finished_at": now,
                         "detail": json.dumps(ev.get("detail", {}), default=str)[:3000]})
    return {"outcome": outcome}


def handler(event, _ctx):
    return {"release_rule": release_rule, "register": register, "finish": finish}[event["action"]](event)
