# BP Monitor Reader

Local reader for the Sanitas blood pressure monitor photos in `experiments/`.

Current implementation status:

- fully local
- CPU-only
- no network or cloud services
- uses OpenCV feature alignment plus a small template bank built from the
  known sample images and `experiments/bp_monitor_ground_truth.csv`

This is a calibrated local pipeline, not yet a general OCR or VLM backend. It
is intended to read the current benchmark image set reliably and to provide a
concrete baseline that can later be compared against `PaddleOCR`,
`Florence-2`, or another local model path.

## Inputs

Calibration sources:

- pressure digit templates from the original reference set in `experiments/`
- time/date/user templates from `experiments/bp_monitor_ground_truth.csv`

## Usage

Read one or more images and print JSON to stdout:

```bash
python3 tools/bp_monitor_reader/template_reader.py \
  experiments/20260324_151209.jpg \
  experiments/20260324_200932.jpg
```

Write per-image JSON and debug overlays:

```bash
python3 tools/bp_monitor_reader/template_reader.py \
  experiments/*.jpg \
  --output-dir results/bp_monitor_reader \
  --verbose
```

Run a regression check against the current ground-truth CSV:

```bash
python3 tools/bp_monitor_reader/check_ground_truth.py
```

Force a stricter leave-one-out style check for an image that is also part of the
calibration set:

```bash
python3 tools/bp_monitor_reader/template_reader.py \
  experiments/20260324_200932.jpg \
  --exclude-input-from-calibration
```

## Output

Each result includes:

- `sys_mmhg`
- `dia_mmhg`
- `pulse_bpm`
- `lcd_time`
- `lcd_day`
- `lcd_month`
- `user_number`
- `blue_backlight_on`
- `backlight_score`
- `confidence`
- `aux_confidence`
- `cell_confidence`
- `warnings`

If `--output-dir` is provided, the tool writes:

- `<stem>.json`
- `<stem>_aligned.png`
- `<stem>_annotated.png`

## Limits

Current limits are explicit:

- the template bank is tied to this specific monitor family and framing style
- user-number recognition is currently only calibrated for the observed value
  `1`
- unseen date/time glyph shapes or materially different framing may fail
- `--exclude-input-from-calibration` is still the more honest mode for judging
  generalization on images already present in the calibration set

The next engineering step is still the one described in
`docs/bp_monitor_local_ai_reader_proposal.md`:

1. keep this calibrated path as a local benchmark
2. add a stronger OCR/model backend when local dependencies are available


## Backends

The reader now has a shared backend harness:

- `template`
  - current known-good calibrated baseline
- `tesseract`
  - OCR baseline using the local `tesseract` binary already present on this Pi
  - verified to run locally, but current accuracy is poor on the benchmark images
  - example on `20260324_200932.jpg`: predicted `7/0`, pulse `0`, time `0:00`
- `paddleocr`
  - first OCR backend experiment
  - currently installed in `/tmp/bp_reader_venv` on this Pi
  - current status on this Pi 5: model download/load works, but inference currently
    segfaults inside Paddle/PaddleOCR
- `florence`
  - first small VLM backend experiment
  - local CPU-only stack is installed in `/tmp/bp_florence_venv`
  - model and processor can now be loaded from the local Hugging Face cache in `/tmp/hf_cache`
  - current status on this Pi 5: generation is not yet practical; a single-field OCR test timed out after `90 s`


### Florence CPU setup

Current reproducibility helpers:

- `tools/bp_monitor_reader/setup_florence_cpu_env.sh`
- `tools/bp_monitor_reader/patch_florence_snapshot.py`

Current local workflow on this Pi:

1. install CPU-side system packages such as `python3-torch`, `python3-onnxruntime`, and `python3-torchvision`
2. create the lightweight venv with:
   - `tools/bp_monitor_reader/setup_florence_cpu_env.sh`
3. download a Florence-2 snapshot into `HF_HOME` / `/tmp/hf_cache`
4. patch the cached snapshot and module files with:
   - `python3 tools/bp_monitor_reader/patch_florence_snapshot.py --verbose`
5. run the backend with:
   - `HF_HOME=/tmp/hf_cache TRANSFORMERS_CACHE=/tmp/hf_cache/transformers /tmp/bp_florence_venv/bin/python tools/bp_monitor_reader/run_backend.py --backend florence experiments/20260324_200932.jpg`

This is still experimental. It makes the Florence path reproducible, but it does not make it fast.

Run a backend explicitly:

```bash
python3 tools/bp_monitor_reader/run_backend.py --backend template experiments/*.jpg
python3 tools/bp_monitor_reader/run_backend.py --backend tesseract experiments/*.jpg
```

Evaluate a backend against the ground truth CSV:

```bash
python3 tools/bp_monitor_reader/evaluate_backend.py --backend template
python3 tools/bp_monitor_reader/evaluate_backend.py --backend tesseract
```
