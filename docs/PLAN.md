# PlateLoop: Build Plan

2026-10-26 · @Sajin Santhosh

## Scope and constraints

PlateLoop is a closed-loop plate-detection demo: your PicoDet-XS plate detector (416×416 input, one class, exported to ONNX) runs on an AWS endpoint, every image it sees is auto-labeled, and a pipeline retrains and redeploys the model when new data or drift justifies it. All of it must run on the AWS Free plan without a rupee charged to your card.

**The free-tier wall, and how this plan respects it**

- Sign up on the **Free plan**, not the Paid plan. It gives $100 in credits at sign-up plus up to $100 more for trying services, and it cannot bill you unless you upgrade. Never click Upgrade.
- You must be a **brand-new AWS customer**. Anyone who has ever had an AWS account is ineligible for the Free plan and its credits, and accounts created before 15 July 2025 stay on the legacy free tier, which has no credit shield. Check this first.
- The Free plan **ends at 6 months or when credits run out**, and it cannot be extended. AWS then suspends the account and keeps the data for 90 days, but getting it back requires upgrading to the Paid plan. Copy your code, model files and results out before expiry, and create the account only when you start building.
- Student credit programs such as AWS Educate are not reliable in 2026, so nothing here depends on them.
- The Free plan can only use services on its list. SageMaker AI, Bedrock, Lambda, S3, DynamoDB, EventBridge, Step Functions, API Gateway, ECR, CodeBuild and CloudWatch are on it; Amazon Textract and SageMaker Ground Truth are not. GPU instances may be blocked or have zero quota, so this plan is **CPU-only**.

**Region depends on how you sign up.** AWS's new sign-up experience (a limited release) assigns your Regional resources automatically, and for India that is Sydney (ap-southeast-2). The classic advanced sign-up lets you choose, for example Mumbai (ap-south-1). Everything below keeps the Region as one config value, so either works.

**In scope**

- Hosting the model on demand, with a start/stop routine
- Capturing every request (image, prediction, confidence)
- Automatic labeling of captured images
- A retraining pipeline with an evaluation gate and a model registry
- Triggers: schedule, new-label count, drift alarm, manual button
- Safe redeploy with rollback, drift monitoring, cost guardrails
- A scripted end-to-end demo

**Out of scope**

- Reading plate characters (OCR), assuming your model only detects plates
- GPU training, multi-camera ingestion, production security and compliance
- A human review UI (optional add-on, covered under risks)

**Assumptions to confirm**

1. The model outputs plate bounding boxes only.
2. Checked on 26 October 2026: the original training setup still exists in ALPRCPU (config, final checkpoint and a 25,470-image dataset), so the model can be fine-tuned. See Model provenance.
3. You will use your own, public or consented images, because plates are personal data.
4. You have a laptop with Docker, Python 3.10+ and the AWS CLI.

## Model provenance

`plate_detector_ov` is a PicoDet-XS trained on 3 June 2026 in `ALPRCPU/PaddleDetection`, not in any `NumberPlateDetector` folder, and its config and checkpoint still exist (checked 26 October 2026).

| Stage | Location under ~/dev/Ivertoai/ALPRCPU | Created (UTC) |
|---|---|---|
| Dataset conversion | `Picodet/tools/csv_to_coco.py` writes `Picodet/dataset`: 25,470 images, 22,906 train and 2,546 val | 3 Jun 07:30 |
| 2,000-image subset | `Picodet/tools/create_subset.py` writes `Picodet/dataset_subset` | 3 Jun 09:52 |
| Config | `PaddleDetection/configs/picodet/picodet_xs_plate.yml` with `datasets/license_plate_subset.yml` | 3 Jun 10:05 |
| Training | `PaddleDetection/output/model_final.pdparams`, 50 epochs | 3 Jun 10:35 |
| Paddle export | `PaddleDetection/output_inference/picodet_xs_plate/` | 3 Jun 10:47 |
| ONNX | `PaddleDetection/plate_detector_static.onnx` | 4 Jun 08:02 |
| OpenVINO | `PaddleDetection/model.xml` and `model.bin`, copied to `Picodet/models/openvino/plate_detector_ov.*` | 4 Jun 08:10, 08:13 |
| Later copies | `ocr+plate/models`, `ocr+plate/update/models`, `update/prod/models`, `Edge-Alpr-prod/models` | 22 Jun to 6 Jul |

`ocr+plate/models`, `ocr+plate/update/model``s` and `Edge-Alpr-prod``/models` match the original by SHA-256; `update/``prod/models` matches by file size only.

- **Weights match exactly.** The ONNX files exported on 4 June equal `model_final.pdparams` in all 102 convolution tensors. The 3 June `PaddleDetection/models/plate_detector.onnx` equals `best_model.pdparams` instead. Neither matches checkpoints 49, 59, 69 or any `.pdema`, so the export used the non-EMA weights.
- **Settings.** LCNet 0.35 backbone, 96-channel LCPAN, PicoHeadV2, 416×416 input, one class (`license_plate`), batch 32, base learning rate 0.16, EMA on. It trained on only 2,000 images (2,170 boxes), so the other 20,900 training images are unused and can serve as the original data in Phase 4.
- **Near-duplicate configs.** `picodet_xs_plate.yml.bak` (batch 56, learning rate 0.28) was replaced 13 seconds later by the version above. `picodet_xs_plate_2k.yml` is an identical copy made that evening. `picodet_xs_plate_25k.yml` (full dataset, 80 epochs) probably produced checkpoints 49 to 69 (3 to 4 June), which fed no export I found. No shell history records the training command; the config is inferred from the 10:05 edit preceding the first checkpoint at 10:12.
- **Earlier folders ruled out.** `NumberPlateDetector`, `v2` and `v3` (18 to 26 May) are built around YOLO, RT-DETR and PP-YOLO judging by their file names, and no checkpoint there was compared.
- **Conversion check and serving caveats.** The ONNX-to-`_ov` step is now confirmed numerically: ONNX Runtime and the OpenVINO model give identical top detections on real validation images (box counts differ by one on 2 of 60 images). The ONNX fails to compile on OpenVINO CPU (dynamic-rank Squeeze), which probably explains why `_ov` exists. ONNX Runtime crashes on this ONNX whenever exactly one box survives NMS (2 of 60 images tested), and the graph returns up to 100 boxes of any score, so serving must apply the 0.3 score threshold itself. Of the five OpenVINO IRs I tried, only `plate_detector_ov` loaded.
- **Leak risk.** Filenames carry Roboflow augmentation hashes (`.rf.`) and the train/val split is random 90/10 (seed 42), so val images may be augmented copies of training images. Keep the hand-boxed golden set as the release gate. Baseline on that val set: AP50 0.923, AP50:95 0.634, so treat it as optimistic.

## Architecture

Images flow clockwise through six stations, and only the gate at station 5 decides whether a retrained model replaces the live one.


Read from the top left. A weekly schedule, 200 new labels, a drift alarm or a manual run can each start retraining, and a guard allows one run at a time. Rejected models are logged and the live model stays in place.

## Key decisions

Seven picks keep every service on the Free plan. The biggest change from earlier advice is replacing Ground Truth, which is closed to new customers, with prompt-based auto-labeling on Bedrock.

| Decision | Pick | Rejected | Why |
|---|---|---|---|
| Serving | SageMaker real-time endpoint on a small CPU instance (ml.m5.large), deleted after each demo session | Lambda container with ONNX Runtime (kept as the fallback); async or serverless endpoints | PicoDet-XS (2.9 MB as ONNX, 1.4 MB as OpenVINO weights) is small enough for CPU. SageMaker endpoints cannot be paused, so scripts delete and recreate them. If instance quota is zero, switch to the Lambda fallback. |
| Capture | Lambda behind API Gateway stores each image in S3 and its metadata in DynamoDB, then calls the endpoint | SageMaker Data Capture | You control file names and can compute drift metrics in the same function. |
| Auto-labeling | Amazon Nova 2 Lite on Bedrock, prompted to box license plates, accepted only under agreement rules (below) | Ground Truth and A2I (closed to new customers); Label Studio on EC2 (server upkeep, manual); Textract (Paid plan only) | AWS shows Nova 2 Lite returning bounding boxes from a text prompt with no training, at roughly $5.69 per 10,000 images. |
| Training | SageMaker training job on ml.m5.xlarge (CPU), PaddleDetection installed through a requirements file | Custom container in ECR (fallback); any GPU instance | A small detector fine-tunes acceptably on CPU. A container is only needed if the install is too slow or fragile. |
| Orchestration | SageMaker Pipelines | Step Functions; MWAA (managed Airflow) | Pipelines links training, evaluation and the Model Registry natively. MWAA is on the Free plan list, but its environment bills by the hour and would drain credits. |
| Drift detection | Per-request stats computed in the inference Lambda, sent as CloudWatch custom metrics, with an alarm that starts the pipeline | SageMaker Model Monitor | Model Monitor analyzes tabular data only, so it cannot see image inputs. |
| Redeploy | Model Registry approval triggers an endpoint update with blue/green rollout and alarm-based rollback | Manual redeploy | Shows a real release gate and costs only a few extra instance-minutes. |

**Keeping auto-labels trustworthy.** Nova is prompted, not trained on your task, and its boxes can be loose. Training on its raw output would let errors compound, so three rules apply:

1. **Agreement:** if Nova's box and your model's box overlap with IoU of at least 0.5, accept the label.
2. **Hard positives:** if only Nova finds a plate, accept it only when the box has a plausible plate shape and size, and cap these at about 30% of a training batch.
3. **Quarantine:** if only your model finds a plate, or the two disagree on position, keep the image out of training and store it for review.

A **golden set** of 100 to 200 images, boxed by hand once in Label Studio on your laptop, is never used for training. Every candidate model must beat the current one on it before promotion.

Hosted labeling services outside AWS, such as Roboflow or CVAT, exist but I have not verified their current free limits, and they would break the all-AWS goal.

## Build plan

Nine phases, each with a done-when check so you always know whether to move on. Effort figures are my rough estimates for part-time work; the full build is roughly 4 to 6 weeks. Phase 0 is mostly local, so create the AWS account at the start of Phase 1 to protect your 6-month window.

### Phase 0: Prerequisites (1–2 days, local)

- [ ] Copy out of ALPRCPU the PicoDet-XS config (picodet_xs_plate.yml), the last `.pdparams` checkpoint (model_final, plus its .pdema and .pdopt) and the COCO-format dataset in Picodet/dataset
- [ ] Build the golden set: box 100 to 200 varied plate images by hand in Label Studio on your laptop and export COCO JSON
- [ ] Install Python 3.10+, Docker and AWS CLI v2, then `pip install boto3 sagemaker onnxruntime pycocotools pillow numpy`
- [ ] Create a repo with folders `infra`, `serving`, `training`, `labeling`, `pipeline`, `monitoring`, `scripts` and a `config.yaml` holding REGION, bucket names and thresholds

**Done when:** the golden set is exported, you can run your ONNX model locally on it, and you have a reproducible local training command.

### Phase 1: Account and storage (1 day)

- [ ] Sign up on the Free plan, note your Region, and record the sign-up date (your 6-month deadline)
- [ ] In Service Quotas, check you have at least 1 for SageMaker endpoint usage on ml.m5.large and training-job usage on ml.m5.xlarge; if either is 0, request an increase now because approval can take days
- [ ] In the Bedrock console, enable access to Amazon Nova 2 Lite
- [ ] Create one S3 bucket with prefixes `raw/`, `labels/auto/`, `quarantine/`, `datasets/`, `golden/`, `models/`; turn on versioning, block public access, and add a lifecycle rule that expires `raw/` after 30 days
- [ ] Create DynamoDB tables `plateloop-requests` (one row per image, with a TTL) and `plateloop-state` (counters and run lock)
- [ ] Create a budget alert and tag every resource `project=plateloop`

**Done when:** you can upload a file to S3 and write a row to DynamoDB from the CLI, and the quotas are at least 1.

### Phase 2: Serve the model (3–4 days)

- [ ] Write `inference.py` with the four SageMaker handlers: decode the image, resize and normalise as in your training config, run ONNX Runtime, and return boxes and scores as JSON. The existing OpenVINO model already includes NMS (inputs image [N,3,416,416] and scale_factor [1,2]; outputs a 100×6 detection array and a count). ONNX Runtime matches it, except that the ONNX crashes when exactly one box survives NMS. Either serve the OpenVINO model or re-export the ONNX, and apply the 0.3 score threshold in code, because the graph returns up to 100 boxes of any score
- [ ] Package `model.tar.gz` (the `.onnx` file plus `code/inference.py` and `requirements.txt`) and upload it to `models/v1/`
- [ ] Write `scripts/up.py` to create the model, endpoint config and endpoint (ml.m5.large, one instance) on a prebuilt Python inference container, and `scripts/down.py` to delete the endpoint only, keeping the model and config
- [ ] Build the `ingest` Lambda behind an API Gateway HTTP API: save the image to S3, call the endpoint, compute per-image stats (detections, top confidence, box area, brightness, blur score) with numpy, write the DynamoDB row, and return JSON. Return a clear 503 when the endpoint is down
- [ ] Time 50 requests and record median and 95th-percentile latency

**Done when:** `curl` with a test image returns plate boxes, the image and row appear in S3 and DynamoDB, and `down.py` followed by `up.py` restores service.

### Phase 3: Auto-labeler (3–4 days)

- [ ] Wire S3 uploads on `raw/` to an SQS queue and then to an `autolabel` Lambda with low reserved concurrency, so Bedrock rate limits never drop images
- [ ] Call Nova 2 Lite through the Bedrock Converse API with a plate-only detection prompt, using AWS's open sample as the template. Nova returns boxes on a 0 to 1000 scale, so convert to pixels
- [ ] Check early that your Region can reach Nova 2 Lite. If the Region has no in-Region model, call Bedrock in a Region that has it, since Bedrock inference calls are allowed across Regions in the new experience
- [ ] Apply the three agreement rules from Key decisions, write accepted labels to `labels/auto/`, send the rest to `quarantine/`, update DynamoDB, and bump the new-label counter
- [ ] Run the labeler on the golden set and measure its precision and recall against your hand labels

**Done when:** at least 95% of golden-set images return parseable output, and you have a measured precision. Suggested gate: continue only if auto-label precision is 0.90 or higher, otherwise tighten the rules.

### Phase 4: Training job (4–5 days)

- [ ] Write `train.py` for the SageMaker training channel: read a dataset folder (images plus COCO JSON), mix about 70% original data with 30% newly auto-labeled data so the model does not forget, fine-tune from the previous checkpoint at a low learning rate, and export ONNX with paddle2onnx
- [ ] Store each version's `.pdparams` and `.onnx` under `models/vN/`, since the next run needs the checkpoint
- [ ] Test the script on 20 images on your laptop before touching the cloud
- [ ] Launch it as a SageMaker training job on ml.m5.xlarge using a prebuilt Python container with a `requirements.txt` that installs PaddlePaddle and PaddleDetection. Set a maximum run time of 2 hours as a cost cap. Fall back to a custom ECR image only if the install is slow or fragile
- [ ] Confirm the exported ONNX gives the same boxes as your laptop run on the same images

**Done when:** a cloud run on a small dataset produces an ONNX file whose outputs match the local run within tolerance.

### Phase 5: Evaluation and registry (2–3 days)

- [ ] Write an evaluation script that runs ONNX Runtime on the golden set and computes mAP at IoU 0.5 and recall with pycocotools, plus CPU latency, and saves `evaluation.json`
- [ ] Evaluate your current production model the same way and store its numbers as the baseline
- [ ] Define the release rule, for example: new mAP at least 0.01 above baseline and recall no worse
- [ ] Create a Model Registry group `plateloop` and register passing models as pending approval, with the metrics attached

**Done when:** a run ends either with a registered version 2 or with a clean, logged rejection.

### Phase 6: Pipeline and triggers (3–4 days)

- [ ] Define a SageMaker Pipeline with five steps: prepare dataset (collect labels since the last version, merge with the original data, write `datasets/vN/`), train, evaluate, condition, register
- [ ] Add a guard Lambda that starts the pipeline only if no run is active (a conditional write on `plateloop-state`) and at least 24 hours have passed since the last run
- [ ] Add four triggers that all call the guard: a weekly EventBridge schedule, a new-label count of at least 200 (checked after each labeled image), a CloudWatch drift alarm, and a manual `scripts/retrain.py`

**Done when:** each trigger starts exactly one execution, and firing two at once still starts only one.

### Phase 7: Release and rollback (2–3 days)

- [ ] Add an EventBridge rule on the Model Registry's package state change to Approved, which calls a `deploy` Lambda
- [ ] In `deploy`: create a new endpoint config for the approved model, then update the endpoint with a blue/green deployment and alarm-based automatic rollback (alarm on 5xx errors or 95th-percentile latency). If the endpoint is currently deleted, just record the latest approved version in DynamoDB so `up.py` starts with it
- [ ] Keep approval manual in the console by default, and add an optional auto-approve flag for large gains
- [ ] Return the model version in every API response so you can see which model answered
- [ ] Test rollback by deploying a deliberately broken model and confirming the endpoint reverts

**Done when:** approving version 2 makes the API report version 2, and the broken model rolls back on its own.

### Phase 8: Drift monitoring (2–3 days)

- [ ] Compute a baseline from the golden set (mean top confidence, no-detection rate, brightness and blur distributions) and save it as `monitoring/baseline.json`
- [ ] Publish at most five custom CloudWatch metrics from the `ingest` Lambda: mean top confidence, no-detection rate, mean brightness, mean blur, mean box size
- [ ] Create alarms such as top confidence two standard deviations below baseline, or no-detection rate three times baseline, with missing data treated as not breaching because traffic is sparse
- [ ] Route alarm state changes through EventBridge to the guard Lambda from Phase 6
- [ ] Write `scripts/inject_drift.py` to send darkened, blurred and noisy copies of test images

**Done when:** sending 100 degraded images raises an alarm and starts one pipeline execution.

### Phase 9: Guardrails, infrastructure as code and polish (3–5 days)

- [ ] Add an idle-shutdown Lambda on a 15-minute EventBridge schedule that deletes the endpoint when it is running and CloudWatch shows zero invocations in the last 30 minutes
- [ ] Write `scripts/credits.py` to print your remaining credits and days left using the Free plan's account-state API, and run it before and after every session
- [ ] Define everything except the endpoint as code (CDK in Python or CloudFormation) and add one command that tears the whole project down
- [ ] Add GitHub Actions for linting and unit tests on `inference.py` and the labeling rules
- [ ] Write the README with an architecture diagram, the cost table and the demo steps

**Done when:** a fresh checkout can deploy and tear down the project with one command each.

## Cost and free-tier guardrails

The whole project should use about $26 of your $100 base credits, and the only real way to blow the budget is leaving an endpoint running. Prices are AWS's list rates of $0.23 per hour for ml.m5.xlarge and, for Nova, AWS's own estimate of $5.69 per 10,000 images. Regional prices vary a little, so check yours.

| Item | Assumption | Estimate (USD) |
|---|---|---|
| Endpoint | 60 session-hours, budgeted at the ml.m5.xlarge rate to be safe | 13.80 |
| Training | 6 runs × 2 hours on ml.m5.xlarge | 2.76 |
| Dataset prep and evaluation | 10 hours on ml.m5.xlarge | 2.30 |
| Auto-labeling | 3,000 images through Nova 2 Lite | 1.71 |
| Lambda, API Gateway, S3, DynamoDB, SQS, CloudWatch, ECR | Low volume; my estimate | about 5 |
| **Total** |  | **about 26** |

**Guardrails, in order of importance**

1. **Stay on the Free plan and never click Upgrade.** When credits run out, the plan ends instead of billing your card.
2. **Never leave the endpoint running.** A forgotten ml.m5.xlarge endpoint costs about $168 a month, more than your whole credit balance. Run `scripts/down.py` after every session and keep the idle-shutdown Lambda from Phase 9.
3. **Cap every job.** Set a maximum run time on every training and processing job.
4. **Develop locally.** Do not keep SageMaker Studio or notebook instances open, since they bill by the hour. Use your laptop or CloudShell.
5. **Avoid always-on services.** Skip MWAA, SageMaker Feature Store online stores and extra tracking servers.
6. **Check before you close the laptop.** Run `aws sagemaker list-endpoints` and `aws sagemaker list-training-jobs --status-equals InProgress`; both should be empty.
7. **Watch the clock too.** Run `scripts/credits.py` each session and note the date your plan ends.

## Risks and fallbacks

Three risks can stop the project outright: missing training code, a blocked instance type, and weak auto-labels. Test each in the first week.

| Risk | What happens | Fallback |
|---|---|---|
| No training code or checkpoint for the ONNX model (not the case: both found on 26 October, see Model provenance) | You can serve and monitor the model but not retrain it | Retrain PicoDet-XS from scratch with PaddleDetection on an open plate dataset plus your images, and treat that as version 1 |
| SageMaker instance quota is 0 or the Free plan blocks the type | Endpoint or training job will not start | Serve from a Lambda container with ONNX Runtime; run training in CodeBuild or a short-lived EC2 instance and keep Step Functions as the orchestrator |
| Nova boxes are too loose (precision under 0.90 on the golden set) | Auto-labels degrade the model | Raise the IoU threshold to 0.6, shrink the hard-positive cap, or review the quarantine folder yourself in Label Studio |
| Nova 2 Lite is not reachable from your Region | Labeling Lambda fails | Call Bedrock in a Region where the model is available in-Region, or use the global inference profile; if neither is allowed, label by hand until it is |
| Self-training reinforces the model's own mistakes | Accuracy drifts without anyone noticing | Mix in original data every run, never train on the golden set, and gate every release on it |
| Free plan ends or credits run out | Account is suspended | Track the end date, run `scripts/credits.py`, and export code, models and results before expiry |
| Plates are personal data | Privacy exposure in a college demo | Use your own, public or consented images, expire `raw/` after 30 days, keep buckets private, and blur plates in any screenshots you publish |

## Demo, evaluation and deliverables

The demo shows one full loop in about ten minutes: serve, degrade the input, detect drift, retrain, approve and redeploy, with numbers on screen. Run the real retraining the day before, because CPU training will not finish while an audience waits.

**Demo script**

1. Start the endpoint with `scripts/up.py` before the audience arrives, then send a clean image and show the response with `model_version: v1`.
2. Send 50 normal images and show the DynamoDB rows and auto-labels appearing in S3.
3. Run `scripts/inject_drift.py` and show the confidence metric dropping on the CloudWatch dashboard until the alarm fires.
4. Show the pipeline starting by itself, with its five steps in the SageMaker console. Open the finished execution from the day before.
5. Open `evaluation.json` comparing v2 with v1 on the golden set, then approve v2 in the Model Registry.
6. Show the blue/green update finishing and the API now answering as v2, with better results on the degraded images.
7. Run `scripts/down.py` and `scripts/credits.py` to show that the endpoint is gone and the spend is small.

**Numbers to report**

- Golden-set mAP at IoU 0.5 and recall for v1 and v2
- The same metrics on the degraded subset, before and after retraining
- Auto-label precision and recall against your hand labels
- Median and 95th-percentile latency, plus endpoint start-up time
- Time from drift alarm to a registered model
- Actual credits used versus the estimate in this plan

**Deliverables**

- Repository with infrastructure code, scripts and unit tests
- README with an architecture diagram and setup steps
- A short recorded demo, as insurance against a slow endpoint start
- A report covering the problem, architecture, decisions, results, limitations and future work. The Ground Truth closure and the move to prompt-based labeling make a good design-trade-off story
- Future work worth naming: reading plate characters, a human review queue, GPU training, and multi-Region serving

## Sources

Pages opened and checked on 26 October 2026. Prices and Free plan rules change, so recheck the cost and quota pages before you sign up.

- AWS Free Tier FAQs: credits, 6-month limit, expiry and eligibility
- Supported AWS services for the new sign-up: which services the Free plan includes
- AWS Regions for your projects: India maps to Sydney in the new sign-up
- Compare sign-up options: new versus advanced sign-up
- Object detection with Amazon Nova 2 Lite: prompt-based boxes and per-image cost
- Amazon SageMaker AI pricing: instance rates and pricing examples
- SageMaker Ground Truth documentation: closed to new customers
- SageMaker Model Monitor data quality: tabular data only
