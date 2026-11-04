"""Freeze the golden set: 150 images sampled (seed 42) from validation images whose source picture is absent from train.json."""
import json, random, shutil, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from common import *
tr, va, _ = load_split()
clean = sorted(clean_holdout(va, tr), key=lambda i: i["id"])
gold = random.Random(42).sample(clean, 150)
ids = {i["id"] for i in gold}
out = f"{ROOT}/golden"; os.makedirs(f"{out}/images", exist_ok=True)
for i in gold: shutil.copyfile(f"{DATA}/images/{i['file_name']}", f"{out}/images/{i['file_name']}")
ann = [a for a in json.load(open(f"{DATA}/val.json"))["annotations"] if a["image_id"] in ids]
json.dump({"images": gold, "annotations": ann, "categories": va["categories"]}, open(f"{out}/annotations.json", "w"))
print(len(gold), "images", len(ann), "boxes")
