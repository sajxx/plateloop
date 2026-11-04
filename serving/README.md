Phase 2: SageMaker inference handlers (inference.py), model.tar.gz packaging, deploy/delete-endpoint scripts, capture Lambda.
Model source: models/v1/onnx/plate_detector.onnx (verify in ONNX Runtime first; it does not compile on OpenVINO CPU).
Preprocessing: models/v1/paddle_inference/infer_cfg.yml (resize 416x416 no aspect ratio, ImageNet mean/std).
