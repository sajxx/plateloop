import sys, os, json, collections, numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from style import *
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.dirname(__file__)
E1 = json.load(open(f"{R}/report/experiments/e1_results.json")); E2 = json.load(open(f"{R}/report/experiments/e2_results.json")); E3 = json.load(open(f"{R}/report/experiments/e3_results.json"))
def save(fig, name): fig.tight_layout(); fig.savefig(f"{OUT}/{name}.png", dpi=200); plt.close(fig)

# ---------- dataset statistics ----------
def stats(path):
    d = json.load(open(path)); im = {i["id"]: i for i in d["images"]}
    per = collections.Counter(a["image_id"] for a in d["annotations"])
    rel = [a["bbox"][2] * a["bbox"][3] / (im[a["image_id"]]["width"] * im[a["image_id"]]["height"]) for a in d["annotations"]]
    asp = [a["bbox"][2] / max(a["bbox"][3], 1e-6) for a in d["annotations"]]
    sizes = collections.Counter((i["width"], i["height"]) for i in d["images"])
    return dict(n_images=len(d["images"]), n_boxes=len(d["annotations"]), per=[per.get(i, 0) for i in im], rel=rel, asp=asp, sizes=sizes)
S = {k: stats(f"{R}/data/original/{k}.json") for k in ["train", "val", "train_2k"]}; S["golden"] = stats(f"{R}/golden/annotations.json")
tab = {k: dict(images=v["n_images"], boxes=v["n_boxes"], boxes_per_image=float(np.mean(v["per"])), median_rel_area=float(np.median(v["rel"])), median_aspect=float(np.median(v["asp"])),
               share_416=v["sizes"].get((416, 416), 0) / v["n_images"], empty=int(sum(1 for x in v["per"] if x == 0))) for k, v in S.items()}
json.dump(tab, open(f"{R}/report/experiments/dataset_stats.json", "w"), indent=1); print(json.dumps(tab, indent=1))

fig, ax = plt.subplots(1, 2, figsize=(9.2, 3.5), gridspec_kw={"width_ratios": [1, 1.15]})
names = ["Training\nset", "Training\nsubset", "Validation\nset", "Held-out\nsources", "Golden\nset"]; vals = [22906, 2000, 2546, 681, 150]
b = ax[0].bar(names, vals, color=[NAVY, BLUE, TEAL, ORANGE, RED], width=0.62)
for r, v in zip(b, vals): ax[0].text(r.get_x() + r.get_width() / 2, v + 350, f"{v:,}", ha="center", fontsize=8)
ax[0].set_ylabel("Images"); ax[0].set_title("Image sets"); ax[0].set_ylim(0, 26500)
rel = np.array(S["train"]["rel"]) * 100
ax[1].hist(rel, bins=np.logspace(-2.5, 2, 45), color=BLUE, edgecolor="white"); ax[1].set_xscale("log")
ax[1].axvline(np.median(rel), color=ORANGE, ls="--", lw=1.5); ax[1].text(np.median(rel) * 1.15, ax[1].get_ylim()[1] * 0.9, f"median {np.median(rel):.2f}%", color=ORANGE, fontsize=8)
ax[1].set_xlabel("Plate area as a share of the image (%, log scale)"); ax[1].set_ylabel("Plates"); ax[1].set_title("Plate size in the training set")
save(fig, "fig4_1_dataset")

fig, ax = plt.subplots(1, 2, figsize=(9.2, 3.3))
c = collections.Counter(min(x, 6) for x in S["train"]["per"]); ks = sorted(c)
ax[0].bar([("6+" if k == 6 else str(k)) for k in ks], [c[k] for k in ks], color=TEAL, width=0.65)
for i, k in enumerate(ks): ax[0].text(i, c[k] + 250, f"{c[k]:,}", ha="center", fontsize=7.5)
ax[0].set_xlabel("Plates per image"); ax[0].set_ylabel("Images"); ax[0].set_title("Plates per image (training set)"); ax[0].set_ylim(0, max(c.values()) * 1.12)
asp = np.clip(np.array(S["train"]["asp"]), 0, 8)
ax[1].hist(asp, bins=40, color=ORANGE, edgecolor="white"); ax[1].axvline(np.median(asp), color=NAVY, ls="--", lw=1.5)
ax[1].text(np.median(asp) + 0.15, ax[1].get_ylim()[1] * 0.88, f"median {np.median(asp):.2f}", color=NAVY, fontsize=8)
ax[1].set_xlabel("Plate width divided by height"); ax[1].set_ylabel("Plates"); ax[1].set_title("Plate shape (training set)")
save(fig, "fig4_2_boxstats")

# ---------- release flow ----------
fig, ax = plt.subplots(figsize=(9.6, 4.3)); ax.set_xlim(0, 100); ax.set_ylim(0, 46); ax.axis("off")
def bx(x, y, w, h, t, fc, fs=7.8):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.2,rounding_size=1.2", fc=fc, ec="none")); ax.text(x + w / 2, y + h / 2, t, ha="center", va="center", color="white", fontsize=fs, fontweight="bold", linespacing=1.3)
def ar(p, q, c=NAVY): ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=11, color=c, lw=1.5))
bx(1, 20, 14, 10, "Trigger\n(schedule, labels,\ndrift, manual)", NAVY, 7.2); bx(20, 20, 12, 10, "Guard\nLambda", BLUE); bx(37, 20, 13, 10, "Prepare\nand train", TEAL); bx(55, 20, 13, 10, "Evaluate on\ngolden set", TEAL)
bx(73, 20, 12, 10, "Release\nrule met?", ORANGE); bx(89, 20, 10, 10, "Register\n(pending)", TEAL, 7.2)
for a_, b_ in [(15, 20), (32, 37), (50, 55), (68, 73), (85, 89)]: ar((a_ + .3, 25), (b_ - .3, 25))
bx(73, 36, 12, 8, "Log result,\nkeep live model", RED, 7.2); ar((79, 30.3), (79, 35.8), c=RED); ax.text(80.3, 32.8, "no", color=RED, fontsize=8, fontweight="bold")
ax.text(86.1, 26.6, "yes", color=GREEN, fontsize=8, fontweight="bold")
bx(89, 3, 10, 10, "Approve in\nModel\nRegistry", BLUE, 7); ar((94, 19.8), (94, 13.2))
bx(73, 3, 12, 10, "Blue/green\nupdate", GREEN); ar((88.8, 8), (85.2, 8))
bx(55, 3, 13, 10, "Bake period,\nwatch alarms", TEAL, 7.2); ar((72.8, 8), (68.2, 8))
bx(37, 3, 13, 10, "Alarm trips:\nrollback", RED, 7.2); ar((54.8, 8), (50.2, 8), c=RED)
ax.text(1, 8, "Only the release rule (new AP50 at least 0.01\nabove the live model, recall no worse) can send a\nmodel on to registration.", ha="left", va="center", fontsize=8, color=GRAY, style="italic")
save(fig, "fig3_2_release_flow")

# ---------- results ----------
pr = E1["pr_curve"]; t = [r["thr"] for r in pr]; p = [r["p"] for r in pr]; rc = [r["r"] for r in pr]; f1 = [r["f1"] for r in pr]
fig, ax = plt.subplots(1, 2, figsize=(9.2, 3.5))
ax[0].plot(rc, p, "-o", color=BLUE, ms=4); ax[0].set_xlabel("Recall"); ax[0].set_ylabel("Precision"); ax[0].set_title("Precision against recall"); ax[0].set_xlim(0.05, 0.9); ax[0].set_ylim(0, 1.05)
i4 = t.index(0.4); ax[0].plot(rc[i4], p[i4], "o", color=ORANGE, ms=9, zorder=3); ax[0].annotate("chosen: 0.4", (rc[i4], p[i4]), xytext=(rc[i4] - 0.33, p[i4] - 0.28), arrowprops=dict(arrowstyle="->", color=ORANGE), color=ORANGE, fontsize=8)
ax[1].plot(t, p, "-o", color=BLUE, ms=3.5, label="Precision"); ax[1].plot(t, rc, "-o", color=TEAL, ms=3.5, label="Recall"); ax[1].plot(t, f1, "-o", color=ORANGE, ms=3.5, label="F1 score")
ax[1].axvline(0.4, color=GRAY, ls="--", lw=1); ax[1].set_xlabel("Score threshold"); ax[1].set_title("Effect of the score threshold"); ax[1].legend(frameon=False, fontsize=8, loc="lower center", ncol=3); ax[1].set_ylim(0, 1.05)
save(fig, "fig5_1_pr")

fig, ax = plt.subplots(figsize=(8.6, 3.5))
sets = [("Full validation\nset (2,546)", E1["full_val"]), ("Sources not in\nthe subset (2,282)", E1["clean_vs_2k_subset"]), ("Sources shared with\ntraining set (1,865)", E1["leaky_val"]), ("Held-out sources\n(681)", E1["clean_holdout"])]
x = np.arange(len(sets)); w = 0.36
a50 = [s[1]["AP50"] for s in sets]; ap = [s[1]["AP"] for s in sets]
b1 = ax.bar(x - w / 2, a50, w, color=BLUE, label="AP at IoU 0.50"); b2 = ax.bar(x + w / 2, ap, w, color=TEAL, label="AP at IoU 0.50 to 0.95")
for r in list(b1) + list(b2): ax.text(r.get_x() + r.get_width() / 2, r.get_height() + 0.012, f"{r.get_height():.3f}", ha="center", fontsize=8)
ax.set_xticks(x); ax.set_xticklabels([s[0] for s in sets], fontsize=8); ax.set_ylim(0, 1.12); ax.set_ylabel("Average precision"); ax.legend(frameon=False, loc="upper right", fontsize=8, ncol=2)
ax.set_title("Detector accuracy by evaluation set")
save(fig, "fig5_2_accuracy")

fig, ax = plt.subplots(2, 3, figsize=(9.6, 5.2), sharex="col")
fam = [("brightness", "Brightness factor (1 = original)", True), ("blur", "Blur strength (sigma)", False), ("noise", "Noise strength (sigma)", False)]
for j, (k, xl, inv) in enumerate(fam):
    rows = E3[k]; xs = [float(r["level"]) for r in rows]
    ax[0, j].plot(xs, [r["ap50"] for r in rows], "-o", color=BLUE, ms=4); ax[0, j].set_ylim(0.3, 0.85); ax[0, j].set_title(xl.split(" (")[0])
    ax[1, j].plot(xs, [r["mean_top_conf"] for r in rows], "-o", color=TEAL, ms=4, label="Mean top confidence")
    ax[1, j].plot(xs, [r["no_det_rate"] for r in rows], "-s", color=ORANGE, ms=4, label="Share with no plate found")
    ax[1, j].axhline(0.70, color=RED, ls="--", lw=1); ax[1, j].set_xlabel(xl, fontsize=8); ax[1, j].set_ylim(0, 0.9)
    if inv: ax[1, j].invert_xaxis()
    if inv: ax[0, j].invert_xaxis()
ax[0, 0].set_ylabel("AP at IoU 0.50"); ax[1, 0].set_ylabel("Drift signals"); ax[1, 1].legend(frameon=False, fontsize=7.5, loc="center right")
ax[1, 2].text(69, 0.715, "alarm line 0.70", color=RED, fontsize=7.5, ha="right", va="bottom")
fig.suptitle("Accuracy and drift signals as the input images degrade (golden set, 150 images)", fontsize=10, fontweight="bold")
save(fig, "fig5_3_drift")

fig, ax = plt.subplots(1, 2, figsize=(9.2, 3.2), gridspec_kw={"width_ratios": [1.5, 1]})
lab = ["OpenVINO\n(served)", "ONNX Runtime\n(reference)"]
pre = [E2["openvino_2threads"]["preprocess_ms"]["median"], E2["openvino_2threads"]["preprocess_ms"]["median"]]
inf = [E2["openvino_2threads"]["inference_ms"]["median"], E2["onnxruntime_2threads"]["inference_ms"]["median"]]
ax[0].barh(lab, pre, color=GRAY, label="Image preparation", height=0.5); ax[0].barh(lab, inf, left=pre, color=BLUE, label="Model inference", height=0.5)
for i in range(2): ax[0].text(pre[i] + inf[i] + 0.6, i, f"{pre[i] + inf[i]:.1f} ms", va="center", fontsize=8.5, fontweight="bold")
ax[0].set_xlim(0, 36); ax[0].set_xlabel("Median time per image (milliseconds, 2 CPU threads)"); ax[0].legend(frameon=False, fontsize=8, loc="upper right"); ax[0].invert_yaxis(); ax[0].set_title("Time to process one image")
sz = E2["sizes_mb"]; nm = ["Training\ncheckpoint", "ONNX", "OpenVINO\n(served)"]; vv = [sz["checkpoint"], sz["onnx"], sz["openvino"]]
bb = ax[1].bar(nm, vv, color=[GRAY, BLUE, TEAL], width=0.6)
for r, v in zip(bb, vv): ax[1].text(r.get_x() + r.get_width() / 2, v + 0.05, f"{v:.2f}", ha="center", fontsize=8.5)
ax[1].set_ylabel("Size (MB)"); ax[1].set_ylim(0, 3.6); ax[1].set_title("Model file size")
save(fig, "fig5_4_latency")

items = [("Endpoint (60 session-hours,\npriced at the xlarge rate)", 13.80), ("Training (6 runs x 2 hours)", 2.76), ("Data preparation and evaluation", 2.30), ("Auto-labelling (3,000 images)", 1.71), ("Lambda, API Gateway, S3, DynamoDB,\nSQS, CloudWatch, ECR", 5.0)]
fig, ax = plt.subplots(figsize=(8.6, 3.2)); y = np.arange(len(items))[::-1]
cols = [TEAL, BLUE, NAVY, ORANGE, GRAY]
bb = ax.barh(y, [v for _, v in items], color=cols, height=0.6)
for yy, (_, v) in zip(y, items): ax.text(v + 0.2, yy, f"\\${v:.2f}", va="center", fontsize=8.5)
ax.set_yticks(y); ax.set_yticklabels([n for n, _ in items], fontsize=8); ax.set_xlim(0, 17); ax.set_xlabel("Estimated spend (US dollars)")
ax.set_title(r"Estimated cost: about \$26 of the \$100 sign-up credit")
save(fig, "fig5_5_cost")
print("figures done")
