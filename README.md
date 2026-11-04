# PlateLoop

A licence-plate detector that improves itself. A photo goes to a hosted detector, the result is stored, a second model (Amazon Nova) checks it, and when enough checked images pile up the system retrains, compares the new model with the live one, and only replaces it if it is clearly better. A local web panel runs all of it, so no command line is needed. 

- Detector: PicoDet-XS, served as an OpenVINO model. Score threshold 0.4, input 416x416.
- Measured accuracy of v1 (AP50): 0.923 on the full validation split, 0.768 on a held-out split, 0.761 on the hand-boxed golden set (0.760 when measured live in the cloud). About 17 ms per image on CPU.
- Cloud: AWS account `631603562462`, region `ap-southeast-2` (Sydney).

This folder is self-contained, except for two things that are not shipped: the AWS credentials (`.aws/`) and the 2 GB image dataset (`data/original/images/`). See "Setup".

## For humans: quick start

```bash
cd mlops-proj
python3.11 -m venv .venv
.venv/bin/pip install -r env/app-requirements.txt boto3 pyyaml pillow
scripts/panel.sh                  # open http://127.0.0.1:8000
```

In the panel, open Overview and press Start detector (about 3 minutes, about $0.10 per hour while it runs). The Detect page unlocks by itself when it is ready. The detector turns itself off after 30 idle minutes (changeable under Overview, Auto-shutdown).

### Setup

1. **AWS credentials.** Create `.aws/credentials` and `.aws/config` inside this folder with a profile named `mlops` for the account and region above. They are gitignored and not included in any zip. Never commit or paste the secret key.
2. **Dataset (only for retraining or re-uploading).** `data/original/` holds 25,452 images plus `train.json`, `val.json` and `train_2k.json` (COCO format, one class `license_plate`). A copy lives in S3 under `datasets/original/`, which is what the cloud retraining uses. You only need the local copy to re-upload it or to evaluate locally.
3. **CDK (only to redeploy infrastructure).** `cd infra && npm install aws-cdk` (or use `.tools/`), then `cdk deploy --all --profile mlops` with the `.aws` environment variables set. Python deps: `env/infra-requirements.txt`.

### What the panel does

| Page | What you can do |
|---|---|
| Overview | Start or stop the detector, set auto-shutdown, see stacks, alarms, counters, queue and budget |
| Detect | Upload a photo or pick a golden-set image, simulate a worse camera, see boxes and a step-by-step tracker. Sending the same image twice returns the saved result (idempotency) |
| Gallery | View the golden, training, auto-labelled, saved-upload and per-run images |
| Requests | Every processed image with boxes, status and statistics; refreshes every 5 s |
| Label review | Resolve images where the detector and Nova disagree |
| Retraining | Start or stop a run, follow the stages, see live vs candidate metrics |
| Models | Registered versions; approve (blue/green deploy with automatic rollback) or reject |
| Monitoring | Alarms and charts for confidence, no-plate share, brightness, sharpness, calls and latency |
| Evaluation | Measured accuracy, latency and drift results for v1 |
| Logs | Logs for each Lambda, the training jobs and the endpoint |

### Start and stop

| Task | Command |
|---|---|
| Start the panel | `scripts/panel.sh` (`PORT=9000` to change the port; Ctrl+C to stop; `pkill -9 -f app/server.py` if it hangs) |
| Start the detector | Overview, Start detector, or `.venv/bin/python scripts/up.py` |
| Stop the detector | Overview, Stop detector, or `.venv/bin/python scripts/down.py` |
| Retrain by hand | `.venv/bin/python scripts/retrain.py` |
| Safe UI tests | `.venv/bin/python app/tests/e2e_panel.py` (never touches the endpoint) |
| Full UI tests | add `--live`; starts and stops the paid endpoint, do not run while using the panel |

## How it works

```
photo -> API Gateway -> ingest Lambda -> SageMaker endpoint (detector)
                             |-> S3 raw/ + DynamoDB row -> SQS -> labeller Lambda -> Bedrock Nova
                                                                   agree: labels/auto/   disagree: quarantine/ (review)
triggers (weekly | 200 new labels | drift alarm) -> Step Functions -> CodeBuild: prepare, train, evaluate
   -> better by >= 0.01 AP50 on the golden set? -> SageMaker Model Registry -> approval -> blue/green deploy
```

Six CDK stacks in `infra/stacks/`:

| Stack | Holds |
|---|---|
| `plateloop-storage` | S3 bucket `plateloop-631603562462`; DynamoDB `plateloop-requests` and `plateloop-state` |
| `plateloop-serve` | ingest Lambda, HTTP API `/predict`, idle-shutdown Lambda (15-min schedule), SageMaker role |
| `plateloop-label` | SQS and dead-letter queue, labeller Lambda, four agreement rules |
| `plateloop-monitoring` | SNS alerts (to `config.yaml` `alerts.email`), 4 alarms, dashboard |
| `plateloop-pipeline` | Step Functions `plateloop-retrain`, CodeBuild, trigger/steps/deploy Lambdas, Model Registry group `plateloop-detector` |
| `plateloop-guardrails` | $20 monthly budget `plateloop-monthly-budget` |

The endpoint `plateloop-endpoint` (ml.m5.large) is created and deleted by `scripts/up.py` / `down.py` or the panel, not by CDK. When it is off, `/predict` returns 503 and saves nothing.

## Layout

| Path | Contents |
|---|---|
| `config.yaml` | Single source of truth: region, bucket, thresholds, schedules, alert email |
| `app/` | Control panel. `server.py` (FastAPI), `static/` (vanilla JS single-page app, vendored Chart.js), `tests/` (Playwright) |
| `serving/` | `code/` (inference handler), `lambdas/ingest` and `lambdas/idle_shutdown`, `package.py`, `test_local.py` |
| `labeling/` | `lambdas/labeller` (Nova check and agreement rules) |
| `pipeline/` | `stage.py` (prepare, train, evaluate), `buildspec.yml`, `lambdas/{trigger,steps,deploy}`, `package_code.py` |
| `monitoring/` | Notes only; the alarms and dashboard are defined in `infra/stacks/monitoring.py` |
| `infra/` | CDK app (`app.py`, `stacks/`) |
| `scripts/` | `panel.sh`, `up.py`, `down.py`, `retrain.py`, `test_labeller.py` |
| `models/v1/` | Current model: `checkpoint/`, `onnx/`, `openvino/`, `paddle_inference/`, `MANIFEST.json` (SHA-256 and origin of each file) |
| `training/` | Trimmed PaddleDetection with the PicoDet-XS plate configs; see `training/README.md` |
| `golden/` | Hand-boxed golden set (`images/`, `annotations.json`). The release gate. Never train on it |
| `report/` | Report build scripts, experiments and figures |
| `docs/` | `PLAN.md` and the final report (.docx) |
| `env/` | Pinned requirements for the app, pipeline and infra |

## For AI agents: read this first

**Hard rules**
- Never print, log, commit or paste secrets. Credentials live in `.aws/` only (profile `mlops`, gitignored). Do not read `.aws/credentials` into your output.
- The golden set must never reach training. The Detect page uses preview mode (`store=false`, direct endpoint call, nothing saved or labelled) for golden images. Keep it that way.
- The SageMaker endpoint costs money. Do not start it unless the task needs it, do not leave it running, and do not run `app/tests/e2e_panel.py --live` while a human is using the panel. The safe default never touches it.
- Stay inside this directory. It is self-contained.
- Test cleanup must delete only rows and objects the test created. An earlier version deleted a user's uploads; do not repeat it.
- Report only measured numbers. Do not invent metrics.

**Conventions**
- Region and names come from `config.yaml` and `scripts/_common.py` (`<project>-endpoint`, etc.). Do not hard-code them elsewhere.
- Idempotency: the `Idempotency-Key` header on `POST /predict` becomes the request id. The ingest Lambda claims it with a conditional DynamoDB put, returns the stored result with `duplicate: true` on repeats, returns 202 while in flight, takes over claims older than 90 s, and returns 503 without saving anything when the endpoint is off. The panel sends `img-<sha256 of the bytes>`.
- The panel binds to 127.0.0.1 only, rejects wrong Host headers and POSTs without header `X-PlateLoop: 1`. Keep these checks.
- Preprocessing for the detector: resize 416x416 (cubic, no aspect ratio), RGB, /255, ImageNet mean/std, `scale_factor` = [416/h, 416/w]. Output: [100,6] rows (class, score, x1, y1, x2, y2). Apply `model.score_threshold` (0.4) in the handler.
- Serve the OpenVINO IR in `models/v1/openvino/`. The ONNX crashes in ONNX Runtime when exactly one box survives NMS and does not compile on OpenVINO CPU.
- The export recipe is `tools/export_model.py` then `ov.convert_model(model.pdmodel)`. The training job finds weights with `rglob("model_final.pdparams")`.
- Retraining promotes a model only if its AP50 on the golden set beats the live model by at least `release.min_map50_gain` (0.01). A not-better run is a correct outcome, not a failure.
- Retraining compute is Step Functions plus CodeBuild (SageMaker training quota is 0 on this account).

**Where to look**
- Panel API and behaviour: `app/server.py`, `app/static/app.js`.
- Request path: `serving/lambdas/ingest/handler.py`; idle shutdown: `serving/lambdas/idle_shutdown/handler.py` (reads DynamoDB state key `idle_shutdown_minutes`, 0 means never).
- Retraining: `pipeline/stage.py`, `pipeline/lambdas/`, `infra/stacks/pipeline.py`.
- Infra deploy: `infra/stacks/*.py`; after editing a Lambda, redeploy that stack with CDK.
- Tests: `app/tests/e2e_panel.py` (`--only=<text>` runs one check, `--live` adds the lifecycle and retraining wait).

**Known open items**
- The report (`docs/*.docx`) says SageMaker Pipelines for retraining; the system uses Step Functions and CodeBuild.
- 40 stand-in labels (`labels/auto/test-seed-*`, `raw/test/test-seed-*`) remain in S3 and would mix into real retraining.
- The AWS access key should be rotated.
- Not yet exercised for real: approving and deploying a better model, the Stop-run button, the weekly/200-label/drift triggers, and the idle-shutdown Lambda deleting an endpoint.

## Gotchas
- Validation may leak from training (random split with augmented copies), so the golden set is the real gate.
- The exact v1 training command was not recorded; `training/README.md` has the standard one.
- `pretrain_weights` in the training config downloads from the internet; only needed for from-scratch training.
