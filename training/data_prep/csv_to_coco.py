#!/usr/bin/env python3

import json
import random
from pathlib import Path

import pandas as pd
from PIL import Image


DATASET_DIR = Path("dataset")
CSV_PATH = DATASET_DIR / "annotations.csv"

TRAIN_JSON = DATASET_DIR / "train.json"
VAL_JSON = DATASET_DIR / "val.json"

TRAIN_RATIO = 0.9
SEED = 42


def build_coco(df, image_paths):
    images = []
    annotations = []

    image_id = 1
    ann_id = 1

    image_id_map = {}

    for img_path in image_paths:
        img_path = Path(img_path)

        with Image.open(img_path) as img:
            width, height = img.size

        image_id_map[str(img_path)] = image_id

        images.append(
            {
                "id": image_id,
                "file_name": img_path.name,
                "width": width,
                "height": height,
            }
        )

        image_id += 1

    for _, row in df.iterrows():
        img_path = row["image_path"]

        if img_path not in image_id_map:
            continue

        xmin = float(row["xmin"])
        ymin = float(row["ymin"])
        xmax = float(row["xmax"])
        ymax = float(row["ymax"])

        w = xmax - xmin
        h = ymax - ymin

        annotations.append(
            {
                "id": ann_id,
                "image_id": image_id_map[img_path],
                "category_id": 1,
                "bbox": [xmin, ymin, w, h],
                "area": w * h,
                "iscrowd": 0,
            }
        )

        ann_id += 1

    return {
        "images": images,
        "annotations": annotations,
        "categories": [
            {
                "id": 1,
                "name": "license_plate",
            }
        ],
    }


def main():
    random.seed(SEED)

    df = pd.read_csv(CSV_PATH)

    unique_images = sorted(df["image_path"].unique())
    random.shuffle(unique_images)

    split_idx = int(len(unique_images) * TRAIN_RATIO)

    train_images = unique_images[:split_idx]
    val_images = unique_images[split_idx:]

    train_df = df[df["image_path"].isin(train_images)]
    val_df = df[df["image_path"].isin(val_images)]

    train_coco = build_coco(train_df, train_images)
    val_coco = build_coco(val_df, val_images)

    with open(TRAIN_JSON, "w") as f:
        json.dump(train_coco, f)

    with open(VAL_JSON, "w") as f:
        json.dump(val_coco, f)

    print(f"Train images: {len(train_coco['images'])}")
    print(f"Train annotations: {len(train_coco['annotations'])}")

    print(f"Val images: {len(val_coco['images'])}")
    print(f"Val annotations: {len(val_coco['annotations'])}")

    print(f"Saved:")
    print(f"  {TRAIN_JSON}")
    print(f"  {VAL_JSON}")


if __name__ == "__main__":
    main()
