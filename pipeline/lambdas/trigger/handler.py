"""Guard in front of the retraining pipeline. Triggers: weekly schedule, label count, drift alarm, manual."""
import datetime as dt
import json
import os
import uuid

import boto3
from botocore.exceptions import ClientError

ddb = boto3.resource("dynamodb")
sfn = boto3.client("stepfunctions")
STATE = ddb.Table(os.environ["STATE_TABLE"])
MACHINE = os.environ["STATE_MACHINE_ARN"]
MIN_HOURS = int(os.environ.get("MIN_HOURS_BETWEEN_RUNS", "24"))
STALE_HOURS = 4
DRIFT_ALARMS = ("low-confidence", "no-plate-share")


def reason_of(event):
    if "Records" in event:                                    # SNS: only drift alarms count
        msg = json.loads(event["Records"][0]["Sns"]["Message"])
        name = msg.get("AlarmName", "")
        return "drift" if msg.get("NewStateValue") == "ALARM" and any(a in name for a in DRIFT_ALARMS) else None
    return event.get("reason", "manual")


def handler(event, _ctx):
    reason = reason_of(event)
    if reason is None:
        return {"started": False, "why": "not a drift alarm"}
    now = int(dt.datetime.now(dt.timezone.utc).timestamp())
    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    try:
        STATE.update_item(
            Key={"key": "retrain_lock"},
            UpdateExpression="SET #s = :run, started_at = :now, run_id = :rid, reason = :why REMOVE finished_at, outcome",
            ConditionExpression="attribute_not_exists(started_at) OR (#s <> :run AND started_at < :cool) "
                                "OR (#s = :run AND started_at < :stale)",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":run": "running", ":now": now, ":rid": run_id, ":why": reason,
                                       ":cool": now + 1 if reason == "manual" else now - MIN_HOURS * 3600, ":stale": now - STALE_HOURS * 3600})
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return {"started": False, "why": f"another run in progress or less than {MIN_HOURS} h since the last"}
        raise
    item = STATE.get_item(Key={"key": "current_model_version"}).get("Item", {})
    base = item.get("value", os.environ.get("DEFAULT_VERSION", "v1"))
    try:
        sfn.start_execution(stateMachineArn=MACHINE, name=run_id,
                            input=json.dumps({"run_id": run_id, "reason": reason, "base_version": base}))
    except Exception:
        STATE.update_item(Key={"key": "retrain_lock"}, UpdateExpression="SET #s = :i",
                          ExpressionAttributeNames={"#s": "status"}, ExpressionAttributeValues={":i": "idle"})
        raise
    return {"started": True, "run_id": run_id, "reason": reason, "base_version": base}
