"""E1: detector accuracy (full val and leak-free holdout), precision/recall by score threshold."""
import json, time, numpy as np, cv2, sys
sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *

tr, va, t2 = load_split()
clean = clean_holdout(va, tr)
t2stems = {stem(i["file_name"]) for i in t2["images"]}
clean2k = [i for i in va["images"] if stem(i["file_name"]) not in t2stems]
det = Detector(threads=8)
gt = gt_boxes(f"{DATA}/val.json")
res = {}; dets_all = {}; t0 = time.time()
for k, im in enumerate(va["images"]):
    img = cv2.imread(f"{DATA}/images/{im['file_name']}")
    dets_all[im["id"]] = det(img)
    if k % 500 == 0: print(k, round(time.time() - t0), "s", flush=True)
# sanity check of coordinate convention: mean best IoU of top box vs GT on first 200 images
b = []
for im in va["images"][:200]:
    d = dets_all[im["id"]]
    if len(d) and im["id"] in gt: b.append(max(iou(d[0][2:6], g) for g in gt[im["id"]]))
print("mean IoU of top-1 box with a GT box (first 200):", round(float(np.mean(b)), 3))

def score(images):
    ids = [i["id"] for i in images]
    d = []
    for i in ids: d += to_coco_dets(i, dets_all[i])
    return coco_eval(f"{DATA}/val.json", d, ids)

res["full_val"] = dict(n=len(va["images"]), **score(va["images"]))
res["clean_holdout"] = dict(n=len(clean), **score(clean))
res["clean_vs_2k_subset"] = dict(n=len(clean2k), **score(clean2k))
leaky = [i for i in va["images"] if i not in clean]
res["leaky_val"] = dict(n=len(leaky), **score(leaky))
print(json.dumps(res, indent=1))
# precision / recall by threshold on clean holdout
pi = [(dets_all[i["id"]], gt.get(i["id"], [])) for i in clean]
thr = [0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
res["pr_curve"] = [dict(thr=t, **dict(zip(("p", "r", "f1"), prf(pi, t)))) for t in thr]
for r in res["pr_curve"]: print(r)
json.dump(res, open(f"{ROOT}/report/experiments/e1_results.json", "w"), indent=1)
json.dump({"clean_ids": [i["id"] for i in clean]}, open(f"{ROOT}/report/experiments/clean_holdout_ids.json", "w"))
