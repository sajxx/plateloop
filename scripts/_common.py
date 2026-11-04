import pathlib

import boto3
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config.yaml").read_text())
REGION = CFG["aws"]["region"]
P = CFG["project"]
ENDPOINT = f"{P}-endpoint"
SM = boto3.client("sagemaker", region_name=REGION)
# AWS-owned scikit-learn container (Python 3.10); the handler installs OpenVINO from code/requirements.txt
IMAGE = f"783357654285.dkr.ecr.{REGION}.amazonaws.com/sagemaker-scikit-learn:1.4-2-cpu-py3"
