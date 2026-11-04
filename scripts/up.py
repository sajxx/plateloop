"""Start the detector endpoint: python scripts/up.py [version]  (default: config model.current_version)."""
import sys

import boto3
from _common import CFG, ENDPOINT, IMAGE, P, REGION, SM

def recorded_version():
    item = boto3.resource("dynamodb", region_name=REGION).Table(f"{P}-state").get_item(
        Key={"key": "current_model_version"}).get("Item")
    return item["value"] if item else CFG["model"]["current_version"]


version = sys.argv[1] if len(sys.argv) > 1 else recorded_version()
bucket = CFG["aws"]["bucket"]
account = boto3.client("sts").get_caller_identity()["Account"]
role = f"arn:aws:iam::{account}:role/{P}-sagemaker-role"
model, cfg_name = f"{P}-model-{version}", f"{P}-config-{version}"

try:
    SM.describe_model(ModelName=model)
except SM.exceptions.ClientError:
    SM.create_model(
        ModelName=model, ExecutionRoleArn=role,
        PrimaryContainer={"Image": IMAGE, "ModelDataUrl": f"s3://{bucket}/models/{version}/model.tar.gz",
                          "Environment": {"SAGEMAKER_PROGRAM": "inference.py",
                                          "SAGEMAKER_SUBMIT_DIRECTORY": "/opt/ml/model/code",
                                          "SAGEMAKER_REGION": REGION, "MODEL_VERSION": version,
                                          "SCORE_THRESHOLD": str(CFG["model"]["score_threshold"])}})
try:
    SM.describe_endpoint_config(EndpointConfigName=cfg_name)
except SM.exceptions.ClientError:
    SM.create_endpoint_config(
        EndpointConfigName=cfg_name,
        ProductionVariants=[{"VariantName": "AllTraffic", "ModelName": model, "InitialInstanceCount": 1,
                             "InstanceType": CFG["serving"]["instance_type"]}])
try:
    SM.describe_endpoint(EndpointName=ENDPOINT)
    print("endpoint already exists; use the deploy flow to change versions")
except SM.exceptions.ClientError:
    SM.create_endpoint(EndpointName=ENDPOINT, EndpointConfigName=cfg_name)
    print("creating", ENDPOINT, "(5-10 minutes)")
SM.get_waiter("endpoint_in_service").wait(EndpointName=ENDPOINT, WaiterConfig={"Delay": 20, "MaxAttempts": 60})
print("InService")
