"""Registry approval -> blue/green endpoint update with alarm rollback (or just record the version if the endpoint is off)."""
import os

import boto3

sm = boto3.client("sagemaker")
s3 = boto3.client("s3")
ddb = boto3.resource("dynamodb")
STATE = ddb.Table(os.environ["STATE_TABLE"])
BUCKET, ROLE, IMAGE = os.environ["BUCKET"], os.environ["SAGEMAKER_ROLE_ARN"], os.environ["IMAGE"]
ENDPOINT, REGION = os.environ["ENDPOINT_NAME"], os.environ["AWS_REGION"]
PROJECT = os.environ["PROJECT"]
ALARMS = os.environ["ROLLBACK_ALARMS"].split(",")
SCORE = os.environ.get("SCORE_THRESHOLD", "0.4")
INSTANCE = os.environ["INSTANCE_TYPE"]


def handler(event, _ctx):
    d = event["detail"]
    if d.get("ModelApprovalStatus") != "Approved":
        return {"action": "ignored"}
    pkg = sm.describe_model_package(ModelPackageName=d["ModelPackageArn"])
    version = pkg["CustomerMetadataProperties"]["version"]
    src = pkg["InferenceSpecification"]["Containers"][0]["ModelDataUrl"].replace(f"s3://{BUCKET}/", "")
    dest = f"models/{version}/model.tar.gz"
    s3.copy_object(Bucket=BUCKET, CopySource={"Bucket": BUCKET, "Key": src}, Key=dest)

    model, cfg = f"{PROJECT}-model-{version}", f"{PROJECT}-config-{version}"
    sm.create_model(ModelName=model, ExecutionRoleArn=ROLE, PrimaryContainer={
        "Image": IMAGE, "ModelDataUrl": f"s3://{BUCKET}/{dest}",
        "Environment": {"SAGEMAKER_PROGRAM": "inference.py", "SAGEMAKER_SUBMIT_DIRECTORY": "/opt/ml/model/code",
                        "SAGEMAKER_REGION": REGION, "MODEL_VERSION": version, "SCORE_THRESHOLD": SCORE}})
    sm.create_endpoint_config(EndpointConfigName=cfg, ProductionVariants=[{
        "VariantName": "AllTraffic", "ModelName": model, "InitialInstanceCount": 1, "InstanceType": INSTANCE}])
    try:
        status = sm.describe_endpoint(EndpointName=ENDPOINT)["EndpointStatus"]
    except sm.exceptions.ClientError:
        status = None
    if status == "InService":
        sm.update_endpoint(EndpointName=ENDPOINT, EndpointConfigName=cfg, DeploymentConfig={
            "BlueGreenUpdatePolicy": {
                "TrafficRoutingConfiguration": {"Type": "ALL_AT_ONCE", "WaitIntervalInSeconds": 300},
                "TerminationWaitInSeconds": 120, "MaximumExecutionTimeoutInSeconds": 1800},
            "AutoRollbackConfiguration": {"Alarms": [{"AlarmName": a} for a in ALARMS]}})
        action = "blue_green_update_started"
    else:
        action = "recorded_endpoint_off"
    STATE.put_item(Item={"key": "current_model_version", "value": version})
    return {"action": action, "version": version}
