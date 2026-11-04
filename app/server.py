"""Local control panel for the license-plate MLOps system on AWS.

    .venv/bin/python app/server.py            ->  http://127.0.0.1:8000

Everything the CLI scripts do is exposed here: endpoint start/stop, detection, label review,
retraining, model approval, monitoring and logs. Runs only on localhost with the repo's own AWS profile.
"""
import datetime as dt
import io
import json
import mimetypes
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request
from decimal import Decimal

ROOT = pathlib.Path(__file__).resolve().parent.parent
os.environ["AWS_CONFIG_FILE"] = str(ROOT / ".aws" / "config")
os.environ["AWS_SHARED_CREDENTIALS_FILE"] = str(ROOT / ".aws" / "credentials")
os.environ.setdefault("AWS_PROFILE", "mlops")
os.environ.setdefault("AWS_REGION", "ap-southeast-2")
os.environ.setdefault("AWS_DEFAULT_REGION", "ap-southeast-2")

import boto3  # noqa: E402
import uvicorn  # noqa: E402
import yaml  # noqa: E402
from PIL import Image  # noqa: E402
from botocore.exceptions import ClientError  # noqa: E402
from fastapi import FastAPI, File, HTTPException, Request, UploadFile  # noqa: E402
from fastapi.encoders import jsonable_encoder  # noqa: E402
from fastapi.responses import JSONResponse, Response  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

CFG = yaml.safe_load((ROOT / "config.yaml").read_text())
P = CFG["project"]
REGION = CFG["aws"]["region"]
BUCKET = CFG["aws"]["bucket"]
ENDPOINT = f"{P}-endpoint"
GROUP = CFG["release"]["model_group"]
MACHINE_ARN = None
PORT = int(os.environ.get("PORT", "8000"))
SK_IMAGE = f"783357654285.dkr.ecr.{REGION}.amazonaws.com/sagemaker-scikit-learn:1.4-2-cpu-py3"

sess = boto3.Session(profile_name=os.environ["AWS_PROFILE"], region_name=REGION)
sts, cfn, sm = sess.client("sts"), sess.client("cloudformation"), sess.client("sagemaker")
s3, sqs, cw, logs = sess.client("s3"), sess.client("sqs"), sess.client("cloudwatch"), sess.client("logs")
sfn, cb, lam = sess.client("stepfunctions"), sess.client("codebuild"), sess.client("lambda")
smr = sess.client("sagemaker-runtime")
budgets = sess.client("budgets", region_name="us-east-1")
ddb = sess.resource("dynamodb")
REQUESTS, STATE = ddb.Table(f"{P}-requests"), ddb.Table(f"{P}-state")

app = FastAPI(title=f"{P} control panel", docs_url=None, redoc_url=None)


# ------------------------------------------------------------------ safety
@app.middleware("http")
async def guard(request: Request, call_next):
    host = request.headers.get("host", "")
    if host not in (f"127.0.0.1:{PORT}", f"localhost:{PORT}"):
        return JSONResponse({"error": "bad host"}, status_code=403)
    if request.method not in ("GET", "HEAD") and request.headers.get("x-plateloop") != "1":
        return JSONResponse({"error": "missing header"}, status_code=403)
    return await call_next(request)


def ok(data, status=200):
    return JSONResponse(jsonable_encoder(data, custom_encoder={Decimal: float}), status_code=status)


def aws_error(e: Exception):
    if isinstance(e, ClientError):
        return HTTPException(502, f"{e.response['Error']['Code']}: {e.response['Error']['Message']}")
    return HTTPException(500, str(e))


def safe(fn, default=None):
    try:
        return fn()
    except Exception as e:  # one broken section must not blank a whole page
        return default if default is not None else {"error": str(e)[:200]}


def state_get(key):
    return STATE.get_item(Key={"key": key}).get("Item")


def counters():
    items = {i["key"]: i for i in STATE.scan()["Items"]}
    return {k: int(v.get("n", 0)) for k, v in items.items() if "n" in v}


def current_version():
    item = state_get("current_model_version")
    return item["value"] if item else CFG["model"]["current_version"]


def api_url():
    global _API
    if "_API" not in globals():
        out = cfn.describe_stacks(StackName=f"{P}-serve")["Stacks"][0]["Outputs"]
        _API = next(o["OutputValue"] for o in out if o["OutputKey"] == "ApiUrl")
    return _API


def machine_arn():
    global MACHINE_ARN
    if not MACHINE_ARN:
        out = cfn.describe_stacks(StackName=f"{P}-pipeline")["Stacks"][0]["Outputs"]
        MACHINE_ARN = next(o["OutputValue"] for o in out if o["OutputKey"] == "StateMachineArn")
    return MACHINE_ARN


# ------------------------------------------------------------------ overview
def idle_setting():
    item = state_get("idle_shutdown_minutes")
    return int(item["value"]) if item else CFG["serving"]["idle_shutdown_minutes"]


def last_invocation():
    now = dt.datetime.now(dt.timezone.utc)
    r = cw.get_metric_statistics(Namespace="AWS/SageMaker", MetricName="Invocations", StartTime=now - dt.timedelta(hours=3),
                                 EndTime=now, Period=60, Statistics=["Sum"],
                                 Dimensions=[{"Name": "EndpointName", "Value": ENDPOINT}, {"Name": "VariantName", "Value": "AllTraffic"}])
    pts = [p["Timestamp"] for p in r["Datapoints"] if p["Sum"] > 0]
    return max(pts) if pts else None


def endpoint_info():
    try:
        e = sm.describe_endpoint(EndpointName=ENDPOINT)
    except ClientError:
        return {"status": "Off", "idle_minutes": idle_setting()}
    cfg_name = e.get("EndpointConfigName", "")
    info = {"status": e["EndpointStatus"], "created": e["CreationTime"], "updated": e["LastModifiedTime"],
            "config": cfg_name, "failure": e.get("FailureReason"), "idle_minutes": idle_setting(),
            "version": cfg_name.replace(f"{P}-config-", "") if cfg_name else None}
    if e["EndpointStatus"] == "InService":
        last = safe(last_invocation, None)
        info["last_activity"] = last if last and last >= e["CreationTime"] else None      # ignore a previous endpoint's traffic
    return info


@app.get("/api/endpoint")
def endpoint_status():
    return ok(endpoint_info())


@app.post("/api/endpoint/idle")
async def endpoint_idle(request: Request):
    minutes = (await request.json()).get("minutes")
    if minutes not in (0, 15, 30, 60, 120, 240):
        raise HTTPException(400, "choose 0 (never), 15, 30, 60, 120 or 240 minutes")
    STATE.put_item(Item={"key": "idle_shutdown_minutes", "value": minutes})
    return ok({"idle_minutes": minutes})


def queue_depth(name):
    url = sqs.get_queue_url(QueueName=name)["QueueUrl"]
    a = sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["ApproximateNumberOfMessages",
                                                               "ApproximateNumberOfMessagesNotVisible"])["Attributes"]
    return int(a["ApproximateNumberOfMessages"]) + int(a["ApproximateNumberOfMessagesNotVisible"])


def budget_info():
    b = budgets.describe_budget(AccountId=ACCOUNT, BudgetName=f"{P}-monthly-budget")["Budget"]
    spend = b.get("CalculatedSpend", {})
    return {"limit": float(b["BudgetLimit"]["Amount"]),
            "actual": float(spend.get("ActualSpend", {}).get("Amount", 0)),
            "forecast": float(spend.get("ForecastedSpend", {}).get("Amount", 0))}


ACCOUNT = sts.get_caller_identity()["Account"]


@app.get("/api/overview")
def overview():
    stacks = safe(lambda: [{"name": s["StackName"], "status": s["StackStatus"],
                            "updated": s.get("LastUpdatedTime") or s["CreationTime"]}
                           for s in cfn.describe_stacks()["Stacks"] if s["StackName"].startswith(P)], [])
    alarms = safe(lambda: [{"name": a["AlarmName"], "state": a["StateValue"]}
                           for a in cw.describe_alarms(AlarmNamePrefix=f"{P}-")["MetricAlarms"]], [])
    lock = safe(lambda: state_get("retrain_lock") or {}, {})
    return ok({
        "account": ACCOUNT, "region": REGION, "bucket": BUCKET, "api_url": safe(api_url, ""),
        "endpoint": endpoint_info(), "model_version": current_version(), "stacks": stacks, "alarms": alarms,
        "counters": safe(counters, {}),
        "requests_total": safe(lambda: REQUESTS.scan(Select="COUNT")["Count"], 0),
        "queues": {"labeling": safe(lambda: queue_depth(f"{P}-label-queue"), 0),
                   "failed": safe(lambda: queue_depth(f"{P}-label-dlq"), 0)},
        "quarantine": safe(lambda: s3.list_objects_v2(Bucket=BUCKET, Prefix="quarantine/").get("KeyCount", 0), 0),
        "budget": safe(budget_info, {}), "retrain": lock,
        "thresholds": {"new_label_count": CFG["retrain_triggers"]["new_label_count"],
                       "score": CFG["model"]["score_threshold"]}})


# ------------------------------------------------------------------ endpoint
@app.post("/api/endpoint/start")
def endpoint_start():
    version = current_version()
    model, cfg_name = f"{P}-model-{version}", f"{P}-config-{version}"
    role = f"arn:aws:iam::{ACCOUNT}:role/{P}-sagemaker-role"
    try:
        try:
            sm.describe_model(ModelName=model)
        except ClientError:
            sm.create_model(
                ModelName=model, ExecutionRoleArn=role,
                PrimaryContainer={"Image": SK_IMAGE, "ModelDataUrl": f"s3://{BUCKET}/models/{version}/model.tar.gz",
                                  "Environment": {"SAGEMAKER_PROGRAM": "inference.py",
                                                  "SAGEMAKER_SUBMIT_DIRECTORY": "/opt/ml/model/code",
                                                  "SAGEMAKER_REGION": REGION, "MODEL_VERSION": version,
                                                  "SCORE_THRESHOLD": str(CFG["model"]["score_threshold"])}})
        try:
            sm.describe_endpoint_config(EndpointConfigName=cfg_name)
        except ClientError:
            sm.create_endpoint_config(EndpointConfigName=cfg_name, ProductionVariants=[{
                "VariantName": "AllTraffic", "ModelName": model, "InitialInstanceCount": 1,
                "InstanceType": CFG["serving"]["instance_type"]}])
        try:
            sm.describe_endpoint(EndpointName=ENDPOINT)
            return ok({"started": False, "why": "endpoint already exists"})
        except ClientError:
            sm.create_endpoint(EndpointName=ENDPOINT, EndpointConfigName=cfg_name)
        return ok({"started": True, "version": version})
    except Exception as e:
        raise aws_error(e)


@app.post("/api/endpoint/stop")
def endpoint_stop():
    try:
        sm.delete_endpoint(EndpointName=ENDPOINT)
        return ok({"stopping": True})
    except Exception as e:
        raise aws_error(e)


# ------------------------------------------------------------------ detect
@app.post("/api/detect")
async def detect(request: Request, file: UploadFile = File(...), store: bool = True):
    """store=true goes through the public API (saved, monitored, auto-labelled); store=false asks the model directly."""
    body = await file.read()
    ctype = "image/png" if file.content_type == "image/png" else "image/jpeg"
    t = time.perf_counter()
    if store:
        hdrs = {"content-type": ctype}
        if request.headers.get("x-idempotency-key"):
            hdrs["Idempotency-Key"] = request.headers["x-idempotency-key"]
        req = urllib.request.Request(api_url() + "/predict", data=body, method="POST", headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data, status = json.loads(r.read()), r.status
        except urllib.error.HTTPError as e:
            data, status = json.loads(e.read() or b"{}"), e.code
    else:
        try:
            out = smr.invoke_endpoint(EndpointName=ENDPOINT, ContentType=ctype, Body=body)
            data, status = json.loads(out["Body"].read()), 200
        except ClientError as e:
            if e.response["Error"]["Code"] not in ("ValidationError", "ServiceUnavailable", "ModelError"):
                raise aws_error(e)
            data, status = {"error": "detector is offline"}, 503
    data["latency_ms"] = round((time.perf_counter() - t) * 1000)
    data["http_status"], data["stored"] = status, store
    return ok(data)


GALLERY_PAGE = 48


def _coco(path, key_prefix, kind):
    d = json.load(open(path)) if isinstance(path, (str, pathlib.Path)) else path
    by = {}
    for a in d["annotations"]:
        x, y, w, h = a["bbox"]
        by.setdefault(a["image_id"], []).append([x, y, x + w, y + h])
    return [{"id": str(i["id"]), "name": i["file_name"], "key": key_prefix + i["file_name"], "width": i["width"], "height": i["height"],
             "boxes": [{"box": b, "kind": kind} for b in by.get(i["id"], [])], "status": None} for i in d["images"]]


def _list_keys(prefix, suffix=""):
    keys, token = [], None
    while True:
        r = s3.list_objects_v2(Bucket=BUCKET, Prefix=prefix, **({"ContinuationToken": token} if token else {}))
        keys += [(o["Key"], o["LastModified"]) for o in r.get("Contents", []) if o["Key"].endswith(suffix) and not o["Key"].endswith("/")]
        token = r.get("NextContinuationToken")
        if not token:
            return sorted(keys, key=lambda k: k[1], reverse=True)


@app.get("/api/gallery")
def gallery(collection: str, page: int = 1, q: str = "", run: str = ""):
    q = q.lower().strip()
    runs, chosen = [], run
    if collection == "golden":
        items = _coco(ROOT / "golden" / "annotations.json", "golden/images/", "truth")
    elif collection == "train":
        items = _coco(ROOT / "data" / "original" / "train_2k.json", "datasets/original/images/", "truth")
    elif collection == "labels":
        keys = [k for k, _ in _list_keys("labels/auto/", ".json") if q in k.lower()]
        total = len(keys)
        keys = keys[(page - 1) * GALLERY_PAGE: page * GALLERY_PAGE]
        items = []
        for k in keys:
            r = json.loads(s3.get_object(Bucket=BUCKET, Key=k)["Body"].read())
            items.append({"id": r["image_id"], "name": r["image_id"], "key": r["s3_key"], "width": r["width"], "height": r["height"],
                          "boxes": [{"box": b, "kind": "truth"} for b in r["boxes"]], "status": r["status"]})
        return ok({"items": items, "total": total, "page": page, "pages": max(1, -(-total // GALLERY_PAGE)), "runs": []})
    elif collection == "raw":
        keys = [k for k, _ in _list_keys("raw/") if q in k.lower() and k.lower().endswith((".jpg", ".png"))]
        total = len(keys)
        rows = {r["s3_key"]: r for r in REQUESTS.scan()["Items"]}
        items = []
        for k in keys[(page - 1) * GALLERY_PAGE: page * GALLERY_PAGE]:
            r = rows.get(k, {})
            items.append({"id": r.get("image_id", k), "name": k.split("/")[-1], "key": k, "width": int(r["width"]) if "width" in r else None,
                          "height": int(r["height"]) if "height" in r else None,
                          "boxes": [{"box": d["box"], "kind": "detection", "score": d["score"]} for d in json.loads(r.get("detections", "[]"))],
                          "status": r.get("label_status")})
        return ok({"items": items, "total": total, "page": page, "pages": max(1, -(-total // GALLERY_PAGE)), "runs": []})
    elif collection == "run":
        runs = [p["Prefix"].split("/")[1] for p in s3.list_objects_v2(Bucket=BUCKET, Prefix="runs/", Delimiter="/").get("CommonPrefixes", [])]
        runs = sorted([r for r in runs if s3_json(f"runs/{r}/train.json")], reverse=True)
        chosen = run if run in runs else (runs[0] if runs else "")
        items = _coco(s3_json(f"runs/{chosen}/train.json"), f"runs/{chosen}/images/", "truth") if chosen else []
    else:
        raise HTTPException(400, "unknown collection")
    if q:
        items = [i for i in items if q in i["name"].lower()]
    total = len(items)
    return ok({"items": items[(page - 1) * GALLERY_PAGE: page * GALLERY_PAGE], "total": total, "page": page,
               "pages": max(1, -(-total // GALLERY_PAGE)), "runs": runs, "run": chosen})


@app.get("/api/golden")
def golden():
    ann = json.load(open(ROOT / "golden" / "annotations.json"))
    gt = {}
    for a in ann["annotations"]:
        x, y, w, h = a["bbox"]
        gt.setdefault(a["image_id"], []).append([x, y, x + w, y + h])
    return ok({"items": [{"file": i["file_name"], "width": i["width"], "height": i["height"],
                          "gt": gt.get(i["id"], [])} for i in ann["images"]]})


# ------------------------------------------------------------------ requests + images
SAFE_ID = re.compile(r"^[A-Za-z0-9_\-]+$")
KEY_OK = re.compile(r"^(raw/[\w/.\-]+|golden/images/[\w.\-]+|datasets/original/images/[\w.\-]+|runs/[\w\-]+/images/[\w.\-]+)$")
_thumbs: dict = {}


@app.get("/api/image")
def image(key: str, w: int = 0):
    """Serve an image from the bucket; w=N returns a JPEG thumbnail at most N pixels wide."""
    if not KEY_OK.match(key) or ".." in key:
        raise HTTPException(400, "bad key")
    w = max(0, min(w, 2000))
    if w and (key, w) in _thumbs:
        return Response(_thumbs[(key, w)], media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})
    try:
        data = s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
    except ClientError:
        raise HTTPException(404, "not found")
    if w:
        img = Image.open(io.BytesIO(data)).convert("RGB")
        if img.width > w:
            img = img.resize((w, round(img.height * w / img.width)), Image.LANCZOS)
        buf = io.BytesIO(); img.save(buf, "JPEG", quality=82); data = buf.getvalue()
        if len(_thumbs) > 600:
            _thumbs.clear()
        _thumbs[(key, w)] = data
        return Response(data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})
    return Response(data, media_type=mimetypes.guess_type(key)[0] or "image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


@app.get("/api/request/{image_id}")
def request_status(image_id: str):
    if not SAFE_ID.match(image_id):
        raise HTTPException(400, "bad id")
    item = REQUESTS.get_item(Key={"image_id": image_id}).get("Item")
    if not item:
        raise HTTPException(404, "unknown request")
    item["detections"] = json.loads(item.get("detections", "[]"))
    return ok(item)


@app.get("/api/requests")
def requests_list(limit: int = 60):
    items = REQUESTS.scan()["Items"]
    items = sorted(items, key=lambda i: i.get("ts", ""), reverse=True)[:limit]
    for i in items:
        i["detections"] = json.loads(i.get("detections", "[]"))
    return ok({"items": items, "total": len(items)})


# ------------------------------------------------------------------ label review


@app.get("/api/review")
def review_list(limit: int = 40):
    keys = [o["Key"] for o in s3.list_objects_v2(Bucket=BUCKET, Prefix="quarantine/", MaxKeys=limit).get("Contents", [])
            if o["Key"].endswith(".json")]
    return ok({"items": [json.loads(s3.get_object(Bucket=BUCKET, Key=k)["Body"].read()) for k in keys]})


@app.post("/api/review/{image_id}")
async def review_resolve(image_id: str, request: Request):
    if not SAFE_ID.match(image_id):
        raise HTTPException(400, "bad id")
    action = (await request.json()).get("action")
    qkey = f"quarantine/{image_id}.json"
    try:
        rec = json.loads(s3.get_object(Bucket=BUCKET, Key=qkey)["Body"].read())
    except ClientError:
        raise HTTPException(404, "not in quarantine")
    boxes = {"live": rec["live"], "nova": rec["nova"], "none": []}.get(action)
    if action == "discard":
        status = "discarded"
    elif boxes is None:
        raise HTTPException(400, "unknown action")
    else:
        status = "no_plate" if action == "none" else "accepted_reviewed"
        rec.update(status=status, boxes=boxes)
        s3.put_object(Bucket=BUCKET, Key=f"labels/auto/{image_id}.json", Body=json.dumps(rec),
                      ContentType="application/json")
    s3.delete_object(Bucket=BUCKET, Key=qkey)
    REQUESTS.update_item(Key={"image_id": image_id}, UpdateExpression="SET label_status = :s",
                         ExpressionAttributeValues={":s": status})
    if status != "discarded":
        fresh = STATE.update_item(Key={"key": "new_labels"}, UpdateExpression="ADD n :d",
                                  ExpressionAttributeValues={":d": 1}, ReturnValues="UPDATED_NEW")["Attributes"]["n"]
        STATE.update_item(Key={"key": "labels_accepted"}, UpdateExpression="ADD n :d",
                          ExpressionAttributeValues={":d": 1})
        if int(fresh) >= CFG["retrain_triggers"]["new_label_count"]:
            lam.invoke(FunctionName=f"{P}-retrain-trigger", InvocationType="Event",
                       Payload=json.dumps({"reason": "labels"}).encode())
    return ok({"status": status})


# ------------------------------------------------------------------ retraining
STAGES = ["Prepare", "Train", "Evaluate", "ReleaseRule", "Better?", "Register"]
FINISH = {"FinishRegistered": "registered", "FinishNotBetter": "not_better", "FinishFailed": "failed"}


def run_progress(arn, status):
    events = sfn.get_execution_history(executionArn=arn, maxResults=200)["events"]
    stage = {s: "waiting" for s in STAGES}
    entered = None
    outcome = None
    for e in events:
        t = e["type"]
        if t.endswith("StateEntered"):
            name = e["stateEnteredEventDetails"]["name"]
            entered = name
            if name in stage:
                stage[name] = "running"
            if name in FINISH:
                outcome = FINISH[name]
        elif t.endswith("StateExited"):
            name = e["stateExitedEventDetails"]["name"]
            if name in stage:
                stage[name] = "done"
    if status == "FAILED":
        for s in STAGES:
            if stage[s] == "running":
                stage[s] = "failed"
    if outcome == "not_better":
        stage["Register"] = "skipped"
    return {"stages": [{"name": s, "state": stage[s]} for s in STAGES], "outcome": outcome, "current": entered}


def build_summary(b):
    env = {v["name"]: v["value"] for v in b.get("environment", {}).get("environmentVariables", [])}
    return {"id": b["id"], "status": b["buildStatus"], "phase": b.get("currentPhase"), "stage": env.get("STAGE"),
            "run_id": env.get("RUN_ID"), "start": b.get("startTime"), "end": b.get("endTime"),
            "log_stream": b.get("logs", {}).get("streamName")}


def s3_json(key):
    try:
        return json.loads(s3.get_object(Bucket=BUCKET, Key=key)["Body"].read())
    except ClientError:
        return None


@app.get("/api/retrain")
def retrain(run: str | None = None):
    execs = sfn.list_executions(stateMachineArn=machine_arn(), maxResults=10)["executions"]
    runs = [{"run_id": e["name"], "status": e["status"], "start": e["startDate"], "stop": e.get("stopDate")}
            for e in execs]
    sel = next((e for e in execs if e["name"] == run), execs[0] if execs else None)
    detail = None
    if sel:
        detail = {"run_id": sel["name"], "status": sel["status"], "start": sel["startDate"],
              "stop": sel.get("stopDate"), **run_progress(sel["executionArn"], sel["status"]),
              "metrics": s3_json(f"runs/{sel['name']}/metrics.json"),
              "dataset": s3_json(f"runs/{sel['name']}/dataset.json")}
        ex = sfn.describe_execution(executionArn=sel["executionArn"])
        detail["reason"] = json.loads(ex["input"]).get("reason")
    ids = cb.list_builds_for_project(projectName=f"{P}-retrain")["ids"][:6]
    builds = [build_summary(b) for b in cb.batch_get_builds(ids=ids)["builds"]] if ids else []
    return ok({"lock": state_get("retrain_lock") or {}, "runs": runs, "detail": detail, "builds": builds,
               "new_labels": counters().get("new_labels", 0),
               "label_threshold": CFG["retrain_triggers"]["new_label_count"]})


@app.post("/api/retrain/start")
def retrain_start():
    try:
        out = lam.invoke(FunctionName=f"{P}-retrain-trigger", Payload=json.dumps({"reason": "manual"}).encode())
        return ok(json.loads(out["Payload"].read()))
    except Exception as e:
        raise aws_error(e)


@app.post("/api/retrain/stop")
async def retrain_stop(request: Request):
    run = (await request.json()).get("run_id")
    if not run or not SAFE_ID.match(run):
        raise HTTPException(400, "bad run id")
    arn = machine_arn().replace(":stateMachine:", ":execution:") + ":" + run
    try:
        sfn.stop_execution(executionArn=arn, cause="stopped from the control panel")
        ids = cb.list_builds_for_project(projectName=f"{P}-retrain")["ids"][:3]
        for b in cb.batch_get_builds(ids=ids)["builds"]:
            if b["buildStatus"] == "IN_PROGRESS":
                cb.stop_build(id=b["id"])
        STATE.update_item(Key={"key": "retrain_lock"}, UpdateExpression="SET #s = :i REMOVE started_at",
                          ExpressionAttributeNames={"#s": "status"}, ExpressionAttributeValues={":i": "idle"})
        return ok({"stopped": True})
    except Exception as e:
        raise aws_error(e)


@app.get("/api/build-log")
def build_log(stream: str, lines: int = 40):
    if not re.match(r"^[\w\-:]+$", stream):
        raise HTTPException(400, "bad stream")
    try:
        ev = logs.get_log_events(logGroupName=f"/aws/codebuild/{P}-retrain", logStreamName=stream,
                                 limit=lines, startFromHead=False)["events"]
    except ClientError:
        return ok({"lines": []})
    return ok({"lines": [e["message"].rstrip() for e in ev]})


# ------------------------------------------------------------------ models
@app.get("/api/models")
def models():
    pk = safe(lambda: sm.list_model_packages(ModelPackageGroupName=GROUP, SortBy="CreationTime",
                                             SortOrder="Descending", MaxResults=20)["ModelPackageSummaryList"], [])
    items = []
    for s in pk:
        d = sm.describe_model_package(ModelPackageName=s["ModelPackageArn"])
        m = d.get("CustomerMetadataProperties", {})
        items.append({"arn": s["ModelPackageArn"], "status": d["ModelApprovalStatus"], "created": d["CreationTime"],
                      "version": m.get("version"), "run_id": m.get("run_id"), "base": m.get("base_version"),
                      "ap50_live": m.get("ap50_live"), "ap50_candidate": m.get("ap50_candidate"),
                      "description": d.get("ModelPackageDescription")})
    e1 = json.load(open(ROOT / "report" / "experiments" / "e1_results.json"))
    return ok({"current": current_version(), "packages": items, "endpoint": endpoint_info(),
               "baseline": {"version": CFG["model"]["current_version"], "ap50_golden": 0.761,
                            "ap50_val": e1["full_val"]["AP50"]}})


@app.post("/api/models/approval")
async def model_approval(request: Request):
    b = await request.json()
    if b.get("status") not in ("Approved", "Rejected") or not str(b.get("arn", "")).startswith("arn:aws:sagemaker:"):
        raise HTTPException(400, "bad request")
    try:
        sm.update_model_package(ModelPackageArn=b["arn"], ModelApprovalStatus=b["status"])
        return ok({"status": b["status"]})
    except Exception as e:
        raise aws_error(e)


# ------------------------------------------------------------------ monitoring
@app.get("/api/monitoring")
def monitoring(hours: int = 24):
    hours = max(1, min(hours, 168))
    period = 300 if hours <= 6 else 900 if hours <= 24 else 3600
    end = dt.datetime.now(dt.timezone.utc)
    dims = [{"Name": "EndpointName", "Value": ENDPOINT}, {"Name": "VariantName", "Value": "AllTraffic"}]

    def q(i, ns, name, stat, d=None):
        return {"Id": i, "MetricStat": {"Metric": {"Namespace": ns, "MetricName": name, "Dimensions": d or []},
                                        "Period": period, "Stat": stat}, "ReturnData": True}

    queries = [q("conf", "PlateLoop", "TopConfidence", "Average"), q("n", "PlateLoop", "TopConfidence", "SampleCount"),
               q("miss", "PlateLoop", "NoPlate", "Average"), q("det", "PlateLoop", "Detections", "Average"),
               q("bright", "PlateLoop", "Brightness", "Average"), q("blur", "PlateLoop", "BlurScore", "Average"),
               q("inv", "AWS/SageMaker", "Invocations", "Sum", dims),
               q("lat", "AWS/SageMaker", "ModelLatency", "Average", dims),
               q("p95", "AWS/SageMaker", "ModelLatency", "p95", dims)]
    res = cw.get_metric_data(MetricDataQueries=queries, StartTime=end - dt.timedelta(hours=hours), EndTime=end,
                             ScanBy="TimestampAscending")["MetricDataResults"]
    series = {r["Id"]: [{"t": t, "v": v} for t, v in zip(r["Timestamps"], r["Values"])] for r in res}
    alarms = [{"name": a["AlarmName"], "state": a["StateValue"], "reason": a.get("StateReason", ""),
               "description": a.get("AlarmDescription", "")}
              for a in cw.describe_alarms(AlarmNamePrefix=f"{P}-")["MetricAlarms"]]
    return ok({"series": series, "alarms": alarms, "period": period,
               "limits": CFG["monitoring"]})


# ------------------------------------------------------------------ logs / evaluation / config
LOG_GROUPS = {"ingest": f"/aws/lambda/{P}-ingest", "labeller": f"/aws/lambda/{P}-labeller",
              "trigger": f"/aws/lambda/{P}-retrain-trigger", "steps": f"/aws/lambda/{P}-steps",
              "deploy": f"/aws/lambda/{P}-deploy", "idle shutdown": f"/aws/lambda/{P}-idle-shutdown",
              "training (CodeBuild)": f"/aws/codebuild/{P}-retrain",
              "endpoint": f"/aws/sagemaker/Endpoints/{ENDPOINT}"}


@app.get("/api/logs")
def get_logs(source: str, minutes: int = 60):
    group = LOG_GROUPS.get(source)
    if not group:
        raise HTTPException(400, "unknown source")
    start = int((time.time() - minutes * 60) * 1000)
    try:
        ev = logs.filter_log_events(logGroupName=group, startTime=start, limit=200)["events"]
    except ClientError:
        return ok({"lines": [], "note": "no log group yet"})
    return ok({"lines": [{"t": e["timestamp"], "m": e["message"].rstrip()[:600]} for e in ev
                         if not e["message"].startswith(("START ", "END ", "REPORT "))]})


@app.get("/api/log-sources")
def log_sources():
    return ok(list(LOG_GROUPS))


@app.get("/api/evaluation")
def evaluation():
    d = ROOT / "report" / "experiments"
    out = {n: json.load(open(d / f"{n}.json")) for n in ("e1_results", "e2_results", "e3_results", "dataset_stats")}
    return ok(out)


@app.get("/api/config")
def config():
    return ok({"project": CFG["project"], "region": REGION, "bucket": BUCKET, "model": CFG["model"],
               "serving": CFG["serving"], "training": CFG["training"], "labeling": CFG["labeling"],
               "release": CFG["release"], "retrain_triggers": CFG["retrain_triggers"],
               "monitoring": CFG["monitoring"]})


app.mount("/", StaticFiles(directory=str(pathlib.Path(__file__).parent / "static"), html=True), name="static")

if __name__ == "__main__":
    print(f"Control panel: http://127.0.0.1:{PORT}")
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
