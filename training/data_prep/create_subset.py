import json
import random

random.seed(42)

N_IMAGES = 2000

with open("dataset/train.json") as f:
    coco = json.load(f)

images = coco["images"]
anns = coco["annotations"]

selected_images = images[:]
random.shuffle(selected_images)
selected_images = selected_images[:N_IMAGES]

selected_ids = {img["id"] for img in selected_images}

selected_anns = [
    ann
    for ann in anns
    if ann["image_id"] in selected_ids
]

subset = {
    "images": selected_images,
    "annotations": selected_anns,
    "categories": coco["categories"]
}

with open("dataset_subset/train.json", "w") as f:
    json.dump(subset, f)

print("images:", len(selected_images))
print("annotations:", len(selected_anns))
