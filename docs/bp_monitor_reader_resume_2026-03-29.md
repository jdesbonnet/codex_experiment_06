# BP Monitor Reader Resume Notes 2026-03-29

## Purpose

This note captures the BP-monitor LCD reader state after the first local
multi-backend implementation pass, so work can resume later without
reconstructing the environment by hand.

## Repository State

Relevant in-repo files currently changed but not committed:

- `docs/bp_monitor_local_ai_reader_proposal.md`
- `docs/local_lcd_ai_reader_project_plan.md`
- `tools/bp_monitor_reader/README.md`
- `tools/bp_monitor_reader/check_ground_truth.py`
- `tools/bp_monitor_reader/backend_api.py`
- `tools/bp_monitor_reader/backend_template.py`
- `tools/bp_monitor_reader/backend_tesseract.py`
- `tools/bp_monitor_reader/backend_paddleocr.py`
- `tools/bp_monitor_reader/backend_florence.py`
- `tools/bp_monitor_reader/evaluate_backend.py`
- `tools/bp_monitor_reader/run_backend.py`
- `tools/bp_monitor_reader/patch_florence_snapshot.py`
- `tools/bp_monitor_reader/setup_florence_cpu_env.sh`

These changes are isolated to the BP-reader docs/tools and should be safe to
commit separately.

## What Exists Now

There is now a shared backend harness under `tools/bp_monitor_reader/`.

Backends implemented:

- `template`
- `tesseract`
- `paddleocr`
- `florence`

Common entry points:

- `python3 tools/bp_monitor_reader/run_backend.py --backend <name> ...`
- `python3 tools/bp_monitor_reader/evaluate_backend.py --backend <name>`

The old `check_ground_truth.py` is now a thin wrapper around
`evaluate_backend.py`.

## Verified Results

### Template backend

This is still the only production-usable path.

Verified command:

```bash
python3 tools/bp_monitor_reader/evaluate_backend.py --backend template
```

Verified result:

- `23` images
- `169` populated fields compared
- `0` mismatches

This remains the benchmark and fallback path.

### Tesseract backend

This backend runs locally and is useful only as a weak OCR comparison point.

Observed behavior on a known-good sample:

```bash
python3 tools/bp_monitor_reader/run_backend.py --backend tesseract experiments/20260324_200932.jpg
```

Representative bad output:

- `sys_mmhg=7`
- `dia_mmhg=0`
- `pulse_bpm=0`
- `lcd_time=0:00`

Conclusion:

- the backend runs
- accuracy is not acceptable
- do not invest more in Tesseract for this device

### PaddleOCR backend

Status:

- backend code exists
- model download/load path works
- inference currently segfaults on this Pi 5

Environment used:

- `/tmp/bp_reader_venv`
- model/cache path under `/tmp/paddlex_cache`

Conclusion:

- not currently usable
- likely blocked by Paddle/PaddleOCR runtime issues on this ARM64 Pi stack

### Florence backend

Status:

- backend code exists
- CPU-only environment is staged
- model snapshot is cached locally
- compatibility patching is required
- generation is still too slow to be practical on this Pi

Key observed facts:

- processor and model can now be loaded from local snapshot cache
- a single-field OCR generation test timed out at `90 s`
- the path is now reproducible enough to resume, but not fast enough to use

Conclusion:

- technically promising
- operationally not practical yet on CPU-only Pi 5

## System Packages Installed

These packages were installed system-wide and should persist across reboot:

- `python3-torch` `2.6.0+dfsg-7`
- `python3-onnxruntime` `1.21.0+dfsg-1`
- `python3-torchvision` `0.21.0-3`
- `python3-sentencepiece` `0.2.0-1+b4`
- `python3-safetensors` `0.5.2-1+b1`
- `python3-regex` `0.1.20241106-1+b1`

These are the useful persistent ML-side system changes from this pass.

## Ephemeral State In /tmp

These paths currently exist, but they are ephemeral and should be assumed
disposable:

- `/tmp/bp_reader_venv`
- `/tmp/bp_florence_venv`
- `/tmp/hf_cache`

Important:

- `/tmp/bp_reader_venv` contains the PaddleOCR experiment environment
- `/tmp/bp_florence_venv` contains the lightweight Florence CPU environment
- `/tmp/hf_cache` contains the Florence-2 local snapshot and dynamically loaded
  module copies

If `/tmp` is cleared, the repo scripts are intended to make reconstruction
possible, but the working cache state will be gone.

## Florence Reproducibility Helpers

Two new helpers were added specifically so the Florence path can be resumed:

- `tools/bp_monitor_reader/setup_florence_cpu_env.sh`
- `tools/bp_monitor_reader/patch_florence_snapshot.py`

Intended workflow:

1. ensure the system packages listed above are installed
2. create the lightweight venv:

```bash
tools/bp_monitor_reader/setup_florence_cpu_env.sh
```

3. download or restore a Florence-2 snapshot into `HF_HOME` / `/tmp/hf_cache`
4. patch the cached snapshot and dynamic module copies:

```bash
python3 tools/bp_monitor_reader/patch_florence_snapshot.py --verbose
```

5. run the backend:

```bash
HF_HOME=/tmp/hf_cache \
TRANSFORMERS_CACHE=/tmp/hf_cache/transformers \
/tmp/bp_florence_venv/bin/python \
tools/bp_monitor_reader/run_backend.py \
  --backend florence \
  experiments/20260324_200932.jpg
```

Current reality:

- this is reproducible enough to resume
- it is not yet performant enough to adopt

## Known Florence Compatibility Issues Encountered

The cached Florence code needed local patching for this Pi environment and the
current `transformers` stack. The scripted patch currently handles problems in:

- `configuration_florence2.py`
- `processing_florence2.py`
- `modeling_florence2.py`

Examples of issues encountered:

- missing `forced_bos_token_id` handling
- tokenizer `additional_special_tokens` attribute assumptions
- missing `is_flash_attn_greater_or_equal_2_10`
- meta-tensor issue in DaViT drop-path initialization
- pre-init `_supports_sdpa` / `_supports_flash_attn_2` access

Those are exactly why `patch_florence_snapshot.py` exists.

## Recommended Next Step

The pragmatic next step is not more patching of Florence.

Recommended order:

1. commit the current BP-reader backend/doc work
2. keep the `template` backend as the working baseline
3. stop investing in `tesseract`
4. treat `paddleocr` as blocked unless a different runtime path is found
5. try a smaller local VLM or OCR-specific ONNX path instead of continuing to
   force Florence on CPU

Reason:

- the current question is no longer "can a local AI stack be staged?"
- that has been answered: yes
- the current question is "which model path is practical on this Pi?"
- so far, none of the AI-backed paths are practical replacements for the
  calibrated baseline

## Useful Commands To Resume Quickly

Baseline regression:

```bash
python3 tools/bp_monitor_reader/evaluate_backend.py --backend template
```

Single-image baseline:

```bash
python3 tools/bp_monitor_reader/run_backend.py --backend template experiments/20260324_200932.jpg
```

Single-image Tesseract comparison:

```bash
python3 tools/bp_monitor_reader/run_backend.py --backend tesseract experiments/20260324_200932.jpg
```

Rebuild Florence lightweight environment:

```bash
tools/bp_monitor_reader/setup_florence_cpu_env.sh
python3 tools/bp_monitor_reader/patch_florence_snapshot.py --verbose
```

## Bottom Line

The BP-reader project is in a good state operationally because the local
template baseline is solid.

The AI-model investigation is no longer hypothetical:

- `tesseract`: implemented, poor
- `paddleocr`: implemented, crashes
- `florence`: implemented, loads, too slow

So if resuming later, do not restart from architecture. Start from backend
selection and performance triage.
