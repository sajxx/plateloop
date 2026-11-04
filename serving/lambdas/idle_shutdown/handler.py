"""Every 15 minutes: delete the endpoint if it has been up 30+ minutes with no requests."""
import datetime as dt
import os

import boto3

sm = boto3.client("sagemaker")
cw = boto3.client("cloudwatch")
STATE = boto3.resource("dynamodb").Table(os.environ["STATE_TABLE"])
NAME = os.environ["ENDPOINT_NAME"]
DEFAULT_IDLE = int(os.environ.get("IDLE_MINUTES", "30"))


def idle_minutes():
    """The control panel stores the chosen value; 0 means never switch off automatically."""
    item = STATE.get_item(Key={"key": "idle_shutdown_minutes"}).get("Item")
    return int(item["value"]) if item else DEFAULT_IDLE


def handler(_e, _c):
    IDLE = idle_minutes()
    if IDLE <= 0:
        return {"action": "none", "reason": "auto-shutdown is switched off"}
    try:
        ep = sm.describe_endpoint(EndpointName=NAME)
    except sm.exceptions.ClientError:
        return {"action": "none", "reason": "no endpoint"}
    if ep["EndpointStatus"] != "InService":
        return {"action": "none", "reason": ep["EndpointStatus"]}
    now = dt.datetime.now(dt.timezone.utc)
    if now - ep["CreationTime"] < dt.timedelta(minutes=IDLE):
        return {"action": "none", "reason": "recently created"}
    stats = cw.get_metric_statistics(
        Namespace="AWS/SageMaker", MetricName="Invocations",
        Dimensions=[{"Name": "EndpointName", "Value": NAME}, {"Name": "VariantName", "Value": "AllTraffic"}],
        StartTime=now - dt.timedelta(minutes=IDLE), EndTime=now, Period=IDLE * 60, Statistics=["Sum"])
    calls = sum(p["Sum"] for p in stats["Datapoints"])
    if calls == 0:
        sm.delete_endpoint(EndpointName=NAME)
        return {"action": "deleted", "idle_minutes": IDLE}
    return {"action": "none", "invocations": calls}
