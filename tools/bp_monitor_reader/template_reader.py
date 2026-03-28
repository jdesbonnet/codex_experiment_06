#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import cv2

from common import (
    AUX_CELL_ORDER,
    CELL_BOXES,
    CELL_ORDER,
    PRESSURE_CELL_ORDER,
    ReaderConfig,
    annotate_aligned_image,
    aux_fields_from_digits,
    build_template_bank,
    build_warnings,
    classify_digit,
    compute_alignment_homography,
    crop_digit_from_cell,
    detect_blue_backlight,
    field_text_from_digits,
    load_color_image,
    load_grayscale_image,
    resolve_calibration_root,
    warp_to_reference,
)

ReaderContext = Tuple[object, object, object, object, object]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read Sanitas blood pressure monitor photos locally.")
    parser.add_argument("inputs", nargs="+", help="input image paths")
    parser.add_argument("--calibration-root", type=Path, default=None, help="directory containing calibration images")
    parser.add_argument("--output-dir", type=Path, default=None, help="write JSON and debug images here")
    parser.add_argument(
        "--exclude-input-from-calibration",
        action="store_true",
        help="exclude any input image basename from the template bank when scoring it",
    )
    parser.add_argument("--verbose", action="store_true", help="print progress details")
    return parser.parse_args()


def resolve_inputs(raw_inputs: List[str]) -> List[Path]:
    paths = [Path(item) for item in raw_inputs]
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise FileNotFoundError("missing input image(s): " + ", ".join(missing))
    return paths


def build_reader_context(config: ReaderConfig, exclude_basenames: set[str] | None = None) -> ReaderContext:
    reference_image, orb, reference_keypoints, reference_descriptors, template_bank = build_template_bank(
        config,
        exclude_basenames=exclude_basenames or set(),
    )
    missing_cells = [cell for cell in CELL_ORDER if not template_bank[cell]]
    if missing_cells:
        raise RuntimeError("template bank is incomplete for cells: " + ", ".join(missing_cells))
    return reference_image, orb, reference_keypoints, reference_descriptors, template_bank


def read_one_image_with_context(
    image_path: Path,
    config: ReaderConfig,
    context: ReaderContext,
    verbose: bool,
) -> Dict[str, object]:
    reference_image, orb, reference_keypoints, reference_descriptors, template_bank = context

    input_image = load_grayscale_image(image_path)
    homography_full, good_match_count = compute_alignment_homography(
        input_image,
        reference_image,
        orb,
        reference_keypoints,
        reference_descriptors,
        config.orb_size,
    )
    aligned = warp_to_reference(input_image, homography_full, reference_image.shape)
    aligned_color = warp_to_reference(load_color_image(image_path), homography_full, reference_image.shape)

    digits: Dict[str, str] = {}
    cell_confidence: Dict[str, float] = {}
    raw_scores: Dict[str, Dict[str, float]] = {}
    for cell_name in CELL_ORDER:
        candidate = crop_digit_from_cell(aligned, CELL_BOXES[cell_name], config.input_size)
        digit, confidence, scores = classify_digit(template_bank[cell_name], candidate)
        digits[cell_name] = digit
        cell_confidence[cell_name] = confidence
        raw_scores[cell_name] = scores

    reading = field_text_from_digits(digits)
    reading.update(aux_fields_from_digits(digits))
    backlight_on, backlight_score = detect_blue_backlight(aligned_color)
    reading["blue_backlight_on"] = backlight_on
    reading["backlight_score"] = backlight_score

    warnings = build_warnings(reading, cell_confidence)
    pressure_confidence = min(cell_confidence[name] for name in PRESSURE_CELL_ORDER)
    aux_confidence = min(cell_confidence[name] for name in AUX_CELL_ORDER)

    if verbose:
        print(
            f"{image_path}: matches={good_match_count} "
            f"sys={reading['sys_mmhg']} dia={reading['dia_mmhg']} pulse={reading['pulse_bpm']} "
            f"time={reading['lcd_time'] or '-'} day={reading['lcd_day'] or '-'} month={reading['lcd_month'] or '-'} "
            f"user={reading['user_number'] or '-'} backlight={reading['blue_backlight_on']} "
            f"confidence={pressure_confidence:.3f}/{aux_confidence:.3f}",
            file=sys.stderr,
        )

    return {
        "source_image": str(image_path),
        "method": "orb_template_bank_v2",
        "alignment_good_matches": good_match_count,
        "sys_mmhg": reading["sys_mmhg"],
        "dia_mmhg": reading["dia_mmhg"],
        "pulse_bpm": reading["pulse_bpm"],
        "lcd_time": reading["lcd_time"],
        "lcd_day": reading["lcd_day"],
        "lcd_month": reading["lcd_month"],
        "user_number": reading["user_number"],
        "blue_backlight_on": reading["blue_backlight_on"],
        "backlight_score": backlight_score,
        "confidence": pressure_confidence,
        "aux_confidence": aux_confidence,
        "cell_digits": digits,
        "cell_confidence": cell_confidence,
        "cell_scores": raw_scores,
        "warnings": warnings,
        "_aligned_image": aligned,
    }


def read_one_image(
    image_path: Path,
    config: ReaderConfig,
    exclude_input_from_calibration: bool,
    verbose: bool,
) -> Dict[str, object]:
    excluded = {image_path.name} if exclude_input_from_calibration else set()
    context = build_reader_context(config, exclude_basenames=excluded)
    return read_one_image_with_context(image_path, config, context, verbose)


def write_outputs(result: Dict[str, object], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    source_path = Path(str(result["source_image"]))
    stem = source_path.stem

    aligned = result.pop("_aligned_image")
    json_path = output_dir / f"{stem}.json"
    aligned_path = output_dir / f"{stem}_aligned.png"
    annotated_path = output_dir / f"{stem}_annotated.png"

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

    calibration_root = resolve_calibration_root(args.calibration_root)
    config = ReaderConfig(calibration_root=calibration_root)

    shared_context = None
    if not args.exclude_input_from_calibration:
        shared_context = build_reader_context(config)

    exit_code = 0
    for image_path in inputs:
        try:
            if shared_context is not None:
                result = read_one_image_with_context(
                    image_path=image_path,
                    config=config,
                    context=shared_context,
                    verbose=args.verbose,
                )
            else:
                result = read_one_image(
                    image_path=image_path,
                    config=config,
                    exclude_input_from_calibration=True,
                    verbose=args.verbose,
                )
        except Exception as exc:  # pragma: no cover - CLI path
            print(f"{image_path}: {exc}", file=sys.stderr)
            exit_code = 1
            continue

        printable = {key: value for key, value in result.items() if not key.startswith("_")}
        print(json.dumps(printable, sort_keys=True))

        if args.output_dir is not None:
            write_outputs(dict(result), args.output_dir)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
