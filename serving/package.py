"""Build serving/build/model.tar.gz (OpenVINO IR + code/) and optionally upload it to S3.

    python serving/package.py v1 [--upload]
"""
import pathlib
import subprocess
import sys
import tarfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
version = sys.argv[1] if len(sys.argv) > 1 else "v1"
cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
out = ROOT / "serving" / "build" / f"model-{version}.tar.gz"
out.parent.mkdir(exist_ok=True)

with tarfile.open(out, "w:gz") as tar:
    for f in sorted((ROOT / "models" / version / "openvino").glob("plate_detector_ov.*")):
        tar.add(f, arcname=f"openvino/{f.name}")
    tar.add(ROOT / "models" / version / "MANIFEST.json", arcname="MANIFEST.json")
    for f in (ROOT / "serving" / "code").glob("*"):
        if f.is_file():
            tar.add(f, arcname=f"code/{f.name}")
print(out, out.stat().st_size, "bytes")

if "--upload" in sys.argv:
    dest = f"s3://{cfg['aws']['bucket']}/models/{version}/model.tar.gz"
    subprocess.run(["aws", "s3", "cp", str(out), dest, "--only-show-errors"], check=True)
    print("uploaded", dest)
