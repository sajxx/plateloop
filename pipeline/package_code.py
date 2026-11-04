"""Zip the code CodeBuild needs and upload it:  python pipeline/package_code.py"""
import pathlib
import subprocess
import zipfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
bucket = yaml.safe_load((ROOT / "config.yaml").read_text())["aws"]["bucket"]
out = ROOT / "pipeline" / "build" / "pipeline-src.zip"
out.parent.mkdir(exist_ok=True)
skip = {"__pycache__", "output"}
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    z.write(ROOT / "pipeline" / "buildspec.yml", "buildspec.yml")
    z.write(ROOT / "config.yaml", "config.yaml")
    z.write(ROOT / "env" / "pipeline-requirements.txt", "env/pipeline-requirements.txt")
    for base in ("pipeline/stage.py", "serving/code", "training/paddledet"):
        p = ROOT / base
        for f in ([p] if p.is_file() else sorted(p.rglob("*"))):
            if f.is_file() and not (skip & set(f.parts)) and f.suffix != ".pyc":
                z.write(f, f.relative_to(ROOT))
print(out, out.stat().st_size // 1024, "KB")
subprocess.run(["aws", "s3", "cp", str(out), f"s3://{bucket}/code/pipeline-src.zip", "--only-show-errors"], check=True)
