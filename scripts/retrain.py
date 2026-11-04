"""Start a retraining run by hand: python scripts/retrain.py"""
import json

import boto3
from _common import P, REGION

out = boto3.client("lambda", region_name=REGION).invoke(
    FunctionName=f"{P}-retrain-trigger", Payload=json.dumps({"reason": "manual"}).encode())
print(json.loads(out["Payload"].read()))
