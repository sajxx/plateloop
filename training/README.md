Run everything from training/paddledet/ with the project venv (../../.venv).

Eval v1:   ../../.venv/bin/python tools/eval.py -c configs/picodet/picodet_xs_plate.yml -o weights=../../models/v1/checkpoint/model_final use_gpu=false
Train:     ../../.venv/bin/python tools/train.py -c configs/picodet/picodet_xs_plate.yml --eval   (CPU: add -o use_gpu=false)
Fine-tune: add  -o pretrain_weights=../../models/v1/checkpoint/model_final  and a low base_lr.

configs/datasets/license_plate_subset.yml = the 2,000-image set v1 was trained on; license_plate_full.yml = all 22,906 train images.
The exact v1 training command was not recorded; the above is the standard PaddleDetection invocation.
Trimmed copy of PaddleDetection (upstream commit b25522a0f); pretrain_weights in the config downloads LCNet_x0_35 from the internet only for from-scratch training.
