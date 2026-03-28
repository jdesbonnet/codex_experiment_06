#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, List

from template_reader import build_reader_context, read_one_image, read_one_image_with_context
from common import ReaderConfig, resolve_calibration_root


FIELD_MAP = {
    "systolic_mmhg": "sys_mmhg",
    "diastolic_mmhg": "dia_mmhg",
    "pulse_bpm": "pulse_bpm",
    "lcd_time": "lcd_time",
    "lcd_day": "lcd_day",
    "lcd_month": "lcd_month",
    "user_number": "user_number",
    "blue_backlight_on": "blue_backlight_on",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare BP monitor reader output against ground truth CSV.")
    parser.add_argument("--ground-truth", type=Path, default=Path("experiments/bp_monitor_ground_truth.csv"))
    parser.add_argument("--calibration-root", type=Path, default=None)
    parser.add_argument("--exclude-input-from-calibration", action="store_true")
    return parser.parse_args()


def normalize_truth(field: str, value: str) -> object:
    value = (value or "").strip()
    if value == "":
        return ""
    if field == "blue_backlight_on":
        return value.lower() == "true"
    if field in {"systolic_mmhg", "diastolic_mmhg", "pulse_bpm"}:
        return int(value)
    return value


def main() -> int:
    args = parse_args()
    calibration_root = resolve_calibration_root(args.calibration_root)
    config = ReaderConfig(calibration_root=calibration_root)

    with args.ground_truth.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    shared_context = None
    if not args.exclude_input_from_calibration:
        shared_context = build_reader_context(config)

    total_compared = 0
    mismatches: List[Dict[str, object]] = []
    field_match_count: Dict[str, int] = {field: 0 for field in FIELD_MAP}
    field_compared_count: Dict[str, int] = {field: 0 for field in FIELD_MAP}

    for row in rows:
        image_path = calibration_root / row["filename"]
        if shared_context is not None:
            result = read_one_image_with_context(
                image_path=image_path,
                config=config,
                context=shared_context,
                verbose=False,
            )
        else:
            result = read_one_image(
                image_path=image_path,
                config=config,
                exclude_input_from_calibration=True,
                verbose=False,
            )
        for truth_field, result_field in FIELD_MAP.items():
            truth_value = normalize_truth(truth_field, row.get(truth_field, ""))
            if truth_value == "":
                continue
            predicted_value = result[result_field]
            field_compared_count[truth_field] += 1
            total_compared += 1
            if predicted_value == truth_value:
                field_match_count[truth_field] += 1
            else:
                mismatches.append(
                    {
                        "filename": row["filename"],
                        "field": truth_field,
                        "truth": truth_value,
                        "predicted": predicted_value,
                    }
                )

    summary = {
        "images": len(rows),
        "total_compared_fields": total_compared,
        "mismatch_count": len(mismatches),
        "field_compared_count": field_compared_count,
        "field_match_count": field_match_count,
        "mismatches": mismatches,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if not mismatches else 1


if __name__ == "__main__":
    raise SystemExit(main())
