"""Run the handlers on a few golden images (2 CPU threads) and compare with the stored boxes."""
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent / "code"))
import inference as inf

ROOT = pathlib.Path(__file__).resolve().parent.parent
n = int(sys.argv[1]) if len(sys.argv) > 1 else 8
ann = json.load(open(ROOT / "golden" / "annotations.json"))
files = [i["file_name"] for i in ann["images"]][:n]

det = inf.model_fn(str(ROOT / "models" / "v1"))
for f in files:
    body = (ROOT / "golden" / "images" / f).read_bytes()
    t = time.perf_counter()
    out = json.loads(inf.output_fn(inf.predict_fn(inf.input_fn(body, "image/jpeg"), det), "application/json")[0])
    print(f"{f[:40]:40s} {1000*(time.perf_counter()-t):6.1f} ms  boxes={len(out['detections'])} top={out['top_confidence']}")
