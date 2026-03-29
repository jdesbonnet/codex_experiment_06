#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path

PATCH_RULES = {
    'configuration_florence2.py': [
        (
            '        forced_eos_token_id=2,\n        **kwargs,\n    ):\n',
            '        forced_eos_token_id=2,\n        forced_bos_token_id=None,\n        **kwargs,\n    ):\n',
        ),
        (
            '        self.classifier_dropout = classifier_dropout\n        self.use_cache = use_cache\n        self.num_hidden_layers = encoder_layers\n',
            '        self.classifier_dropout = classifier_dropout\n        self.use_cache = use_cache\n        self.num_hidden_layers = encoder_layers\n        self.forced_bos_token_id = forced_bos_token_id\n        self.forced_eos_token_id = forced_eos_token_id\n',
        ),
        (
            '            decoder_start_token_id=decoder_start_token_id,\n            forced_eos_token_id=forced_eos_token_id,\n            **kwargs,\n        )\n',
            '            decoder_start_token_id=decoder_start_token_id,\n            forced_bos_token_id=forced_bos_token_id,\n            forced_eos_token_id=forced_eos_token_id,\n            **kwargs,\n        )\n',
        ),
    ],
    'processing_florence2.py': [
        (
            "                'additional_special_tokens': \\\n                    tokenizer.additional_special_tokens + \\\n",
            "                'additional_special_tokens': \\\n                    getattr(tokenizer, 'additional_special_tokens', []) + \\\n",
        ),
    ],
    'modeling_florence2.py': [
        (
            '    is_flash_attn_greater_or_equal_2_10,\n)\n',
            ')\n\ntry:\n    from transformers.utils import is_flash_attn_greater_or_equal_2_10\nexcept ImportError:\n    def is_flash_attn_greater_or_equal_2_10():\n        return False\n\n',
        ),
        (
            '        return self.language_model._supports_flash_attn_2\n',
            '        if not hasattr(self, "language_model"):\n            return False\n        return self.language_model._supports_flash_attn_2\n',
        ),
        (
            '        return self.language_model._supports_sdpa\n',
            '        if not hasattr(self, "language_model"):\n            return False\n        return self.language_model._supports_sdpa\n',
        ),
        (
            '        dpr = [x.item() for x in torch.linspace(0, drop_path_rate, sum(depths)*2)]\n',
            '        dpr = [float(x) for x in torch.linspace(0, drop_path_rate, sum(depths)*2, device="cpu")]\n',
        ),
    ],
}



NORMALIZE_REPLACEMENTS = [
    (
        '        self.forced_bos_token_id = forced_bos_token_id\n        self.forced_eos_token_id = forced_eos_token_id\n        self.forced_bos_token_id = forced_bos_token_id\n        self.forced_eos_token_id = forced_eos_token_id\n',
        '        self.forced_bos_token_id = forced_bos_token_id\n        self.forced_eos_token_id = forced_eos_token_id\n',
    ),
    (
        '        if not hasattr(self, "language_model"):\n            return False\n        if not hasattr(self, "language_model"):\n            return False\n',
        '        if not hasattr(self, "language_model"):\n            return False\n',
    ),
]

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Patch a locally cached Florence-2 snapshot for the current Pi CPU environment.')
    parser.add_argument('--hf-home', default=os.environ.get('HF_HOME', '/tmp/hf_cache'))
    parser.add_argument('--verbose', action='store_true')
    return parser.parse_args()


def candidate_files(hf_home: Path) -> list[Path]:
    paths: list[Path] = []
    root = hf_home / 'hub' / 'models--microsoft--Florence-2-base-ft'
    refs_main = root / 'refs' / 'main'
    if refs_main.exists():
        revision = refs_main.read_text().strip()
        snapshot = root / 'snapshots' / revision
        for name in PATCH_RULES:
            path = snapshot / name
            if path.exists():
                paths.append(path)
    module_root = hf_home / 'modules' / 'transformers_modules'
    if module_root.exists():
        for name in PATCH_RULES:
            paths.extend(module_root.rglob(name))
    dedup: list[Path] = []
    seen = set()
    for path in paths:
        if path not in seen:
            dedup.append(path)
            seen.add(path)
    return dedup


def patch_file(path: Path) -> tuple[int, int]:
    rules = PATCH_RULES.get(path.name, [])
    text = path.read_text()
    applied = 0
    already = 0
    for old, new in rules:
        if old in text:
            text = text.replace(old, new, 1)
            applied += 1
        elif new in text:
            already += 1
    for old, new in NORMALIZE_REPLACEMENTS:
        if old in text:
            text = text.replace(old, new)
    path.write_text(text)
    return applied, already


def main() -> int:
    args = parse_args()
    hf_home = Path(args.hf_home)
    files = candidate_files(hf_home)
    if not files:
        print(f'no Florence-2 cached files found under {hf_home}')
        return 1
    total_applied = 0
    total_already = 0
    for path in files:
        applied, already = patch_file(path)
        total_applied += applied
        total_already += already
        if args.verbose:
            print(f'{path}: applied={applied} already={already}')
    print(f'patched_files={len(files)} replacements_applied={total_applied} already_present={total_already}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
