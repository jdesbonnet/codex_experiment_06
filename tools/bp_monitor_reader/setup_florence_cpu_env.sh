#!/usr/bin/env bash
set -euo pipefail

VENV_PATH="${1:-/tmp/bp_florence_venv}"
HF_HOME_PATH="${HF_HOME:-/tmp/hf_cache}"

python3 -m venv --system-site-packages "$VENV_PATH"
"$VENV_PATH/bin/pip" install --no-deps transformers huggingface_hub tokenizers
"$VENV_PATH/bin/pip" install --no-deps httpx httpcore anyio h11 hf_xet regex einops timm

mkdir -p "$HF_HOME_PATH"

echo "created $VENV_PATH"
echo "HF_HOME=$HF_HOME_PATH"
echo "next: download a Florence-2 snapshot, then run tools/bp_monitor_reader/patch_florence_snapshot.py"
