# Blood Pressure Monitor LCD Reader Proposal

## Purpose

This document captures a concrete proposal for reading a blood pressure monitor
LCD locally on this Raspberry Pi 5 without using cloud OCR or cloud vision
models.

The immediate target is the small image set already in `experiments/`:

- `experiments/20260324_151209.jpg`
- `experiments/20260324_200920.jpg`
- `experiments/20260324_200932.jpg`
- `experiments/20260327_173714.jpg`
- `experiments/20260327_173727.jpg`

The task is narrow:

- one device family
- one known LCD layout
- mostly fixed labels
- large numeric fields for `SYS`, `DIA`, and `PUL`

That means we do not need a fully general visual assistant. We need a local
reader that is robust on this instrument.

## Goal

Produce a local tool that:

1. takes a JPEG image of the monitor
2. extracts:
   - systolic pressure
   - diastolic pressure
   - pulse
3. returns structured output
4. optionally writes an annotated debug image

Example output:

```json
{
  "sys_mmhg": 127,
  "dia_mmhg": 80,
  "pulse_bpm": 69,
  "confidence": 0.93,
  "source_image": "experiments/20260324_200932.jpg"
}
```

## Constraints

Host assumptions:

- Raspberry Pi 5
- `16 GB` RAM
- CPU-only
- no discrete GPU

Operational assumptions:

- internet access is not required for inference once models are installed
- images may have:
  - perspective skew
  - reflections
  - backlight variations
  - partial rotation

## Model Options Considered

### 1. PaddleOCR

This is the strongest practical first choice if the task is "read text from a
display image locally".

Why it fits:

- purpose-built OCR toolkit
- strong document and scene-text tooling
- practical local deployment story
- lower system complexity than a general multimodal chat model

Official source:

- <https://www.paddleocr.ai/main/en/index.html>

Relevant current note from the official docs:

- PaddleOCR now includes `PaddleOCR-VL`, described as a `0.9B` multilingual
  document parsing VLM
- the same docs still position PaddleOCR as the main OCR toolkit

For this narrow LCD-reading task, the likely first implementation would **not**
need PaddleOCR-VL. Standard PaddleOCR-style text detection/recognition is
probably enough.

### 2. Florence-2

This is the best "small local AI model" option if the requirement is explicitly
"use an AI model, not only classical OCR".

Why it fits:

- smaller than the heavier general VLMs
- official model card explicitly supports OCR tasks
- more flexible than a pure OCR toolkit

Official model card:

- <https://huggingface.co/microsoft/Florence-2-base-ft>

Why it is not the first recommendation:

- more moving parts than plain OCR
- less narrowly optimized for this task than PaddleOCR
- still heavier than a classical OCR pipeline

### 3. Qwen2.5-VL-3B-Instruct

This is a plausible local CPU option for experimentation, but not the most
pragmatic first implementation.

Why it is interesting:

- strong general multimodal reasoning
- can answer prompted questions like:
  - "Read the SYS, DIA, and PUL values from this monitor"

Official model card:

- <https://huggingface.co/Qwen/Qwen2.5-VL-3B-Instruct>

Why it is not the first recommendation:

- substantially heavier than OCR-first tools
- higher inference latency on CPU
- more likely to hallucinate or paraphrase than a narrow OCR pipeline
- less deterministic for a measurement-extraction task

### 4. Moondream2

This is another small local VLM candidate.

Official model card:

- <https://huggingface.co/vikhyatk/moondream2>

Why it is not first:

- general image understanding model, not primarily an OCR-specialist tool
- likely useful for quick experiments, less compelling than PaddleOCR or
  Florence-2 for this measurement-reading task

## Recommendation

Use a two-stage plan:

### Stage 1: Practical Local Reader

Implement the first local version with:

- `Python`
- `OpenCV`
- `PaddleOCR`

Reason:

- highest chance of fast success
- good CPU-only fit
- easiest to debug
- easiest to turn into a deterministic tool

### Stage 2: AI-Model Comparison

After Stage 1 works, add an experiment path for:

- `Florence-2-base-ft`

Optionally later:

- `Qwen2.5-VL-3B-Instruct`

Reason:

- this gives a clean comparison between:
  - OCR-first extraction
  - small local VLM extraction

That is a better engineering sequence than starting with Qwen.

## Proposed Architecture

### Pipeline A: OCR-First Local Reader

1. input image load
2. optional orientation correction
3. optional monitor/LCD crop
4. OCR pass over the screen
5. post-processing:
   - identify `SYS`, `DIA`, `PUL` regions
   - map nearby numeric groups to each label
6. confidence and plausibility checks
7. JSON output
8. annotated debug image

This is the recommended first implementation.

### Pipeline B: Local VLM Reader

1. input image load
2. optional resize/crop
3. prompt local VLM with a narrow extraction request
4. parse structured response
5. apply numeric validation
6. return JSON output

Example prompt:

```text
Read the blood pressure monitor LCD.
Return only JSON with integer fields:
sys_mmhg, dia_mmhg, pulse_bpm.
If uncertain, include a confidence field from 0 to 1.
```

## Why Validation Matters

For an instrument reader, raw model output is not enough.

We should enforce:

- `SYS` and `DIA` must be integers
- `PUL` must be an integer
- `SYS > DIA`
- all values inside plausible human ranges

Suggested sanity ranges:

- `SYS`: `60..260`
- `DIA`: `30..180`
- `PUL`: `20..240`

If validation fails:

- mark result low-confidence
- preserve raw OCR/VLM output for inspection

## CPU-Only Feasibility on Pi 5

### PaddleOCR

Feasible.

Expected profile:

- best latency of the candidate set
- most practical for repeated local runs
- easiest to productionize on this host

### Florence-2-base-ft

Feasible, but slower than PaddleOCR.

Expected role:

- second implementation for comparison
- useful if we want a more model-centric approach without moving straight to a
  heavier VLM

### Qwen2.5-VL-3B-Instruct

Technically possible in a CPU-only environment with enough RAM, but not the
right first tool here.

Expected issues:

- slower startup and inference
- prompt-sensitive output
- less deterministic extraction behavior

For this task, Qwen is more likely to be a research comparison path than the
best deployed solution.

## Proposed Repository Layout

Suggested files:

- `tools/bp_monitor_reader/README.md`
- `tools/bp_monitor_reader/ocr_reader.py`
- `tools/bp_monitor_reader/vlm_reader.py`
- `tools/bp_monitor_reader/common.py`
- `results/bp_monitor_reader/`

Suggested commands:

```bash
python3 tools/bp_monitor_reader/ocr_reader.py \
  --input experiments/20260324_200932.jpg \
  --output-json results/bp_monitor_reader/20260324_200932.json \
  --output-annotated results/bp_monitor_reader/20260324_200932_annotated.jpg
```

```bash
python3 tools/bp_monitor_reader/vlm_reader.py \
  --model florence \
  --input experiments/20260324_200932.jpg
```

## Evaluation Plan

Use the current image set as a fixed benchmark.

Known readings from prior manual interpretation:

- `experiments/20260324_151209.jpg`
  - `SYS 134`
  - `DIA 84`
  - `PUL 78`
- `experiments/20260324_200920.jpg`
  - `SYS 127`
  - `DIA 80`
  - `PUL 69`
- `experiments/20260324_200932.jpg`
  - `SYS 127`
  - `DIA 80`
  - `PUL 69`

The two `20260327_*.jpg` images should be added to the same benchmark set once
we confirm their readings manually.

Success criteria for the first milestone:

- correct extraction on all currently validated images
- deterministic output
- failure mode is explicit, not silent

## Decision

The practical implementation path should be:

1. write a local OCR-first reader using `PaddleOCR`
2. add structured validation and debug output
3. only then compare against a local AI model such as `Florence-2`
4. treat `Qwen2.5-VL-3B` as an optional research comparison, not the baseline

## Sources

- PaddleOCR official documentation:
  - <https://www.paddleocr.ai/main/en/index.html>
- Florence-2 official model card:
  - <https://huggingface.co/microsoft/Florence-2-base-ft>
- Qwen2.5-VL-3B-Instruct official model card:
  - <https://huggingface.co/Qwen/Qwen2.5-VL-3B-Instruct>
- Moondream2 official model card:
  - <https://huggingface.co/vikhyatk/moondream2>
