"""E3: how the drift signals and the accuracy move as the input images degrade (golden set, 150 images)."""
import json, numpy as np, cv2, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from common import *
THR = 0.4
g = json.load(open(f"{ROOT}/golden/annotations.json"))
imgs = [(i, cv2.imread(f"{ROOT}/golden/images/{i['file_name']}")) for i in g["images"]]
det = Detector(threads=4)
gtp = f"{ROOT}/golden/annotations.json"
ids = [i["id"] for i, _ in imgs]
conds = {"brightness": [("1.0", lambda x: x), ("0.7", lambda x: darken(x, .7)), ("0.5", lambda x: darken(x, .5)), ("0.35", lambda x: darken(x, .35)), ("0.25", lambda x: darken(x, .25)), ("0.15", lambda x: darken(x, .15)), ("0.10", lambda x: darken(x, .10))],
         "blur": [(str(s), (lambda s: lambda x: blur(x, s))(s)) for s in [0, 1, 2, 3, 4, 6]],
         "noise": [(str(s), (lambda s: lambda x: noise(x, s, seed=1))(s)) for s in [0, 10, 20, 35, 50, 70]]}
out = {}
for fam, levels in conds.items():
    out[fam] = []
    for lab, fn in levels:
        d_all, tops, nodet, br, bl = [], [], 0, [], []
        for im, img in imgs:
            x = fn(img); d = det(x); d_all += to_coco_dets(im["id"], d)
            keep = d[d[:, 1] >= THR]; tops.append(float(d[:, 1].max()) if len(d) else 0.0)
            nodet += int(len(keep) == 0); br.append(brightness(x)); bl.append(blur_score(x))
        m = coco_eval(gtp, d_all, ids)
        row = dict(level=lab, ap50=m["AP50"], ap=m["AP"], mean_top_conf=float(np.mean(tops)), no_det_rate=nodet / len(imgs),
                   mean_brightness=float(np.mean(br)), mean_blur=float(np.mean(bl)))
        out[fam].append(row); print(fam, row, flush=True)
json.dump(out, open(f"{ROOT}/report/experiments/e3_results.json", "w"), indent=1)
