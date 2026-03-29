#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

import cv2

from backend_api import BackendError
from backend_template import TemplateBackend
from common import ReaderConfig, annotate_aligned_image, resolve_calibration_root


def load_backend(name: str):
    if name == "template":
        return TemplateBackend()
    if name == "tesseract":
        from backend_tesseract import TesseractBackend

        return TesseractBackend()
    if name == "paddleocr":
        from backend_paddleocr import PaddleOCRBackend

        return PaddleOCRBackend()
    if name == "florence":
        from backend_florence import FlorenceBackend

        return FlorenceBackend()
    raise BackendError(f"unknown backend: {name}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a BP monitor reader backend.")
    parser.add_argument("--backend", choices=["template", "tesseract", "paddleocr", "florence"], default="template")
    parser.add_argument("inputs", nargs="+", help="input image paths")
    parser.add_argument("--calibration-root", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--exclude-input-from-calibration", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def resolve_inputs(raw_inputs: List[str]) -> List[Path]:
    paths = [Path(item) for item in raw_inputs]
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise FileNotFoundError("missing input image(s): " + ", ".join(missing))
    return paths


def write_outputs(result: Dict[str, object], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    source_path = Path(str(result["source_image"]))
    stem = source_path.stem
    aligned = result.pop("_aligned_image")
    json_path = output_dir / f"{stem}.{result['method']}.json"
    aligned_path = output_dir / f"{stem}.{result['method']}_aligned.png"
    annotated_path = output_dir / f"{stem}.{result['method']}_annotated.png"

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")

    cv2.imwrite(str(aligned_path), aligned)
    annotated = annotate_aligned_image(
        aligned,
        {
            "sys_mmhg": int(result["sys_mmhg"]),
            "dia_mmhg": int(result["dia_mmhg"]),
            "pulse_bpm": int(result["pulse_bpm"]),
            "lcd_time": result["lcd_time"],
            "lcd_day": result["lcd_day"],
            "lcd_month": result["lcd_month"],
            "user_number": result["user_number"],
        },
        dict(result["cell_confidence"]),
        list(result["warnings"]),
    )
    cv2.imwrite(str(annotated_path), annotated)


def main() -> int:
    args = parse_args()
    try:
        inputs = resolve_inputs(args.inputs)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    config = ReaderConfig(calibration_root=resolve_calibration_root(args.calibration_root))
    try:
        backend = load_backend(args.backend)
    except BackendError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    shared_context = None
    if not args.exclude_input_from_calibration:
        try:
            shared_context = backend.build_context(config)
        except Exception as exc:
            print(str(exc), file=sys.stderr)
            return 1

    exit_code = 0
    for image_path in inputs:
        try:
            if shared_context is not None:
                result = backend.read_image(image_path=image_path, config=config, context=shared_context, verbose=args.verbose)
            else:
                context = backend.build_context(config, exclude_basenames={image_path.name})
                result = backend.read_image(image_path=image_path, config=config, context=context, verbose=args.verbose)
        except Exception as exc:
            print(f"{image_path}: {exc}", file=sys.stderr)
            exit_code = 1
            continue
        printable = {key: value for key, value in result.items() if not key.startswith('_')}
        print(json.dumps(printable, sort_keys=True))
        if args.output_dir is not None:
            write_outputs(dict(result), args.output_dir)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
