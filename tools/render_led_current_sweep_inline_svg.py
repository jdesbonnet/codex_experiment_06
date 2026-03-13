#!/usr/bin/env python3
"""
Render a family-of-curves LED spectrum sweep plot with inline trace labels.

The renderer is intended for documentation-quality plots where direct trace
labels are preferred over a separate legend. It reads the existing summary and
spectra CSV files produced by ``tools/sweep_led_spectra.py`` and writes a new
SVG without altering the source data.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Curve:
    label: str
    measured_current_ma: float
    saturated_pixels: int
    points: list[tuple[float, float]]

    @property
    def peak_value(self) -> float:
        return max(value for _, value in self.points)

    @property
    def peak_index(self) -> int:
        peak = self.peak_value
        for index, (_, value) in enumerate(self.points):
            if value == peak:
                return index
        return 0


def fail(message: str) -> int:
    print(message, file=sys.stderr)
    return 1


def read_curves(summary_csv: Path, spectra_csv: Path) -> list[Curve]:
    if not summary_csv.exists():
        raise FileNotFoundError(f"summary CSV not found: {summary_csv}")
    if not spectra_csv.exists():
        raise FileNotFoundError(f"spectra CSV not found: {spectra_csv}")

    with spectra_csv.open("r", encoding="utf-8", newline="") as handle:
        spectra_rows = list(csv.DictReader(handle))
    with summary_csv.open("r", encoding="utf-8", newline="") as handle:
        summary_rows = list(csv.DictReader(handle))

    grouped_points: dict[str, list[tuple[float, float]]] = {}
    for row in spectra_rows:
        current_key = row["measured_current_ma"]
        grouped_points.setdefault(current_key, []).append((float(row["wavelength_nm"]), float(row["subtracted"])))

    curves: list[Curve] = []
    for row in summary_rows:
        current_key = row["measured_current_ma"]
        points = grouped_points.get(current_key)
        if not points:
            continue
        measured_current_ma = float(current_key)
        saturated_pixels = int(row["saturated_pixels"])
        label = f"IF = {measured_current_ma:.2f} mA"
        if saturated_pixels > 0:
            label += f" ({saturated_pixels} sat)"
        curves.append(
            Curve(
                label=label,
                measured_current_ma=measured_current_ma,
                saturated_pixels=saturated_pixels,
                points=sorted(points, key=lambda point: point[0]),
            )
        )

    curves.sort(key=lambda curve: curve.measured_current_ma)
    return curves


def round_down(value: float, step: float) -> float:
    return math.floor(value / step) * step


def round_up(value: float, step: float) -> float:
    return math.ceil(value / step) * step


def choose_tick_step(span: float, max_ticks: int) -> float:
    for step in (1, 2, 5, 10, 20, 25, 50, 100, 200):
        if span / step <= max_ticks:
            return float(step)
    return max(1.0, span / max_ticks)


def significant_x_range(curves: list[Curve]) -> tuple[float, float]:
    significant_wavelengths: list[float] = []
    for curve in curves:
        threshold = max(4.0, curve.peak_value * 0.03)
        peak_index = curve.peak_index

        left = peak_index
        while left > 0 and curve.points[left - 1][1] >= threshold:
            left -= 1

        right = peak_index
        while right + 1 < len(curve.points) and curve.points[right + 1][1] >= threshold:
            right += 1

        significant_wavelengths.extend(wavelength_nm for wavelength_nm, _ in curve.points[left : right + 1])
    if not significant_wavelengths:
        all_x = [wavelength_nm for curve in curves for wavelength_nm, _ in curve.points]
        return min(all_x), max(all_x)
    return min(significant_wavelengths), max(significant_wavelengths)


def interpolate_y(curve: Curve, wavelength_nm: float) -> float:
    points = curve.points
    if wavelength_nm <= points[0][0]:
        return points[0][1]
    if wavelength_nm >= points[-1][0]:
        return points[-1][1]

    for index in range(1, len(points)):
        left_x, left_y = points[index - 1]
        right_x, right_y = points[index]
        if wavelength_nm <= right_x:
            if right_x == left_x:
                return right_y
            fraction = (wavelength_nm - left_x) / (right_x - left_x)
            return left_y + fraction * (right_y - left_y)
    return points[-1][1]


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def format_current_value_label(current_ma: float) -> str:
    return f"{current_ma:.2f}".rstrip("0").rstrip(".")


def write_inline_svg(
    output_path: Path,
    curves: list[Curve],
    title: str,
    x_min_override: float | None,
    x_max_override: float | None,
    label_mode: str,
    label_font_size: float,
    unit_box_text: str,
    verbose: bool,
) -> None:
    if not curves:
        raise ValueError("no curves found in the supplied CSV files")

    width = 980
    height = 560
    margin_left = 72
    margin_right = 44
    margin_top = 54
    margin_bottom = 60
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom

    signal_x_min, signal_x_max = significant_x_range(curves)
    x_min = x_min_override if x_min_override is not None else round_down(signal_x_min - 10.0, 5.0)
    if x_max_override is not None:
        x_max = x_max_override
    elif label_mode == "peak":
        x_max = round_up(signal_x_max + 8.0, 5.0)
    else:
        x_max = round_up(signal_x_max + 18.0, 5.0)
    if x_max <= x_min:
        raise ValueError("x-axis range is invalid")

    raw_y_max = max(curve.peak_value for curve in curves)
    y_max = round_up(raw_y_max * 1.08, 10.0)
    if y_max <= 0:
        y_max = 10.0

    x_span = x_max - x_min

    def x_coord(wavelength_nm: float) -> float:
        return margin_left + ((wavelength_nm - x_min) / x_span) * plot_width

    def y_coord(value: float) -> float:
        return margin_top + plot_height - ((value / y_max) * plot_height)

    x_tick_step = choose_tick_step(x_span, 7)
    y_tick_step = choose_tick_step(y_max, 7)

    label_specs: list[dict[str, float | str]] = []
    leader_lines = True
    if label_mode == "stacked":
        signal_span = signal_x_max - signal_x_min
        label_anchor_nm = signal_x_min + (signal_span * 0.54)
        for curve in curves:
            anchor_value = interpolate_y(curve, label_anchor_nm)
            anchor_x_nm = label_anchor_nm
            anchor_x = x_coord(anchor_x_nm)
            anchor_y = y_coord(anchor_value)
            desired_label_x = clamp(anchor_x + 16.0, margin_left + (plot_width * 0.58), width - margin_right - 112.0)
            label_specs.append(
                {
                    "label": curve.label,
                    "anchor_x": anchor_x,
                    "anchor_y": anchor_y,
                    "label_x": desired_label_x,
                    "label_y": anchor_y,
                    "text_anchor": "start",
                }
            )

        label_specs.sort(key=lambda item: float(item["anchor_y"]))
        min_gap_px = label_font_size
        min_label_y = margin_top + 12.0
        max_label_y = height - margin_bottom - 10.0
        previous_y = min_label_y - min_gap_px
        for item in label_specs:
            desired_y = float(item["label_y"])
            placed_y = max(desired_y, previous_y + min_gap_px)
            item["label_y"] = placed_y
            previous_y = placed_y

        if label_specs and float(label_specs[-1]["label_y"]) > max_label_y:
            overflow = float(label_specs[-1]["label_y"]) - max_label_y
            for item in reversed(label_specs):
                item["label_y"] = float(item["label_y"]) - overflow
                overflow = max(0.0, min_gap_px - (float(item["label_y"]) - min_label_y))
            previous_y = max_label_y + min_gap_px
            for item in reversed(label_specs):
                current_y = float(item["label_y"])
                max_y = previous_y - min_gap_px
                item["label_y"] = min(current_y, max_y)
                previous_y = float(item["label_y"])

        for item in label_specs:
            item["label_y"] = clamp(float(item["label_y"]), min_label_y, max_label_y)
    else:
        leader_lines = False
        placed_boxes: list[tuple[float, float, float, float]] = []
        candidate_offsets_nm = [0.0, -1.5, 1.5, -3.0, 3.0, -4.5, 4.5, -6.0, 6.0]
        curves_by_peak = sorted(curves, key=lambda curve: curve.peak_value, reverse=True)
        for curve in curves_by_peak:
            peak_x_nm, peak_value = curve.points[curve.peak_index]
            label = format_current_value_label(curve.measured_current_ma)
            width_estimate = len(label) * label_font_size * 0.58
            height_estimate = label_font_size * 0.95
            chosen = None
            for offset_nm in candidate_offsets_nm:
                candidate_x_nm = clamp(peak_x_nm + offset_nm, x_min + 2.0, x_max - 2.0)
                candidate_y_value = interpolate_y(curve, candidate_x_nm)
                candidate_x = x_coord(candidate_x_nm)
                candidate_y = y_coord(candidate_y_value)
                left = candidate_x - (width_estimate / 2.0)
                right = candidate_x + (width_estimate / 2.0)
                top = candidate_y - (height_estimate / 2.0)
                bottom = candidate_y + (height_estimate / 2.0)
                overlaps = False
                for other_left, other_top, other_right, other_bottom in placed_boxes:
                    if not (right < other_left or left > other_right or bottom < other_top or top > other_bottom):
                        overlaps = True
                        break
                if not overlaps:
                    chosen = (candidate_x, candidate_y, left, top, right, bottom)
                    break
            if chosen is None:
                candidate_x = x_coord(peak_x_nm)
                candidate_y = y_coord(peak_value)
                left = candidate_x - (width_estimate / 2.0)
                top = candidate_y - (height_estimate / 2.0)
                right = candidate_x + (width_estimate / 2.0)
                bottom = candidate_y + (height_estimate / 2.0)
                chosen = (candidate_x, candidate_y, left, top, right, bottom)
            candidate_x, candidate_y, left, top, right, bottom = chosen
            placed_boxes.append((left, top, right, bottom))
            label_specs.append(
                {
                    "label": label,
                    "anchor_x": candidate_x,
                    "anchor_y": candidate_y,
                    "label_x": candidate_x,
                    "label_y": candidate_y,
                    "text_anchor": "middle",
                }
            )

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<style>",
        "svg { background: transparent; }",
        "text { font-family: 'Nimbus Sans', Arial, sans-serif; fill: #111111; }",
        ".axis { stroke: #111111; stroke-width: 1.2; }",
        ".grid { stroke: #d6d6d6; stroke-width: 1; }",
        ".trace { fill: none; stroke: #111111; stroke-width: 1.6; stroke-linecap: round; stroke-linejoin: round; }",
        f".trace-label {{ font-size: {label_font_size:.1f}px; dominant-baseline: middle; paint-order: stroke fill; stroke: #ffffff; stroke-width: 4; stroke-linejoin: round; }}",
        ".leader { fill: none; stroke: #111111; stroke-width: 0.9; stroke-linecap: round; stroke-linejoin: round; }",
        ".unit-box { fill: #ffffff; fill-opacity: 0.88; stroke: #111111; stroke-width: 0.9; }",
        "</style>",
        f'<text x="{width / 2:.0f}" y="28" text-anchor="middle" font-size="20">{title}</text>',
        f'<line class="axis" x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{height - margin_bottom}" />',
        f'<line class="axis" x1="{margin_left}" y1="{height - margin_bottom}" x2="{width - margin_right}" y2="{height - margin_bottom}" />',
    ]

    y_tick = 0.0
    while y_tick <= y_max + 1e-9:
        y = y_coord(y_tick)
        lines.append(f'<line class="grid" x1="{margin_left}" y1="{y:.2f}" x2="{width - margin_right}" y2="{y:.2f}" />')
        lines.append(f'<text x="{margin_left - 10}" y="{y + 4:.2f}" text-anchor="end" font-size="12">{y_tick:.0f}</text>')
        y_tick += y_tick_step

    x_tick = round_up(x_min, x_tick_step)
    while x_tick <= x_max + 1e-9:
        x = x_coord(x_tick)
        lines.append(f'<line class="grid" x1="{x:.2f}" y1="{margin_top}" x2="{x:.2f}" y2="{height - margin_bottom}" />')
        lines.append(f'<text x="{x:.2f}" y="{height - margin_bottom + 22}" text-anchor="middle" font-size="12">{x_tick:.0f}</text>')
        x_tick += x_tick_step

    for curve in curves:
        points = []
        for wavelength_nm, value in curve.points:
            if x_min <= wavelength_nm <= x_max:
                points.append(f"{x_coord(wavelength_nm):.2f},{y_coord(value):.2f}")
        lines.append(f'<polyline class="trace" points="{" ".join(points)}" />')

    if unit_box_text:
        unit_box_width = 112
        unit_box_height = 24
        unit_box_x = width - margin_right - unit_box_width
        unit_box_y = margin_top + 10
        lines.append(
            f'<rect class="unit-box" x="{unit_box_x}" y="{unit_box_y}" width="{unit_box_width}" height="{unit_box_height}" rx="3" ry="3" />'
        )
        lines.append(
            f'<text x="{unit_box_x + (unit_box_width / 2):.2f}" y="{unit_box_y + (unit_box_height / 2) + 1:.2f}" text-anchor="middle" font-size="12">{unit_box_text}</text>'
        )

    for item in label_specs:
        anchor_x = float(item["anchor_x"])
        anchor_y = float(item["anchor_y"])
        label_x = float(item["label_x"])
        label_y = float(item["label_y"])
        if leader_lines and (abs(label_x - anchor_x) > 8.0 or abs(label_y - anchor_y) > 3.0):
            elbow_x = anchor_x + 10.0
            lines.append(
                f'<polyline class="leader" points="{anchor_x:.2f},{anchor_y:.2f} {elbow_x:.2f},{anchor_y:.2f} {label_x - 6.0:.2f},{label_y:.2f}" />'
            )
        lines.append(
            f'<text class="trace-label" x="{label_x:.2f}" y="{label_y:.2f}" text-anchor="{item["text_anchor"]}">{item["label"]}</text>'
        )

    lines.append(
        f'<text x="{margin_left + (plot_width / 2):.2f}" y="{height - 18}" text-anchor="middle" font-size="14">'
        "Wavelength (nm)</text>"
    )
    lines.append(
        f'<text x="22" y="{margin_top + (plot_height / 2):.2f}" transform="rotate(-90 22 {margin_top + (plot_height / 2):.2f})" '
        'text-anchor="middle" font-size="14">Background-subtracted counts</text>'
    )
    lines.append("</svg>")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")

    if verbose:
        print(
            f"wrote {output_path} with x-range {x_min:.1f}..{x_max:.1f} nm and y-range 0..{y_max:.1f} counts",
            flush=True,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Render inline-labeled SVG curves from an LED sweep CSV pair")
    parser.add_argument("--summary-csv", type=Path, required=True, help="summary CSV generated by sweep_led_spectra.py")
    parser.add_argument("--spectra-csv", type=Path, required=True, help="spectra CSV generated by sweep_led_spectra.py")
    parser.add_argument("--output", type=Path, required=True, help="output SVG path")
    parser.add_argument("--title", default="LED Spectrum Current Sweep", help="plot title")
    parser.add_argument("--xmin", type=float, default=None, help="override x-axis minimum wavelength")
    parser.add_argument("--xmax", type=float, default=None, help="override x-axis maximum wavelength")
    parser.add_argument(
        "--label-mode",
        choices=("stacked", "peak"),
        default="stacked",
        help="stacked keeps labels beside the family of curves; peak places numeric labels on the curves near their peaks",
    )
    parser.add_argument("--label-font-size", type=float, default=12.0, help="inline label font size in px")
    parser.add_argument("--unit-box-text", default="Labels: mA", help="small unit note shown in a corner box")
    parser.add_argument("--verbose", action="store_true", help="print rendering details")
    args = parser.parse_args()

    try:
        curves = read_curves(args.summary_csv, args.spectra_csv)
        write_inline_svg(
            args.output,
            curves,
            args.title,
            args.xmin,
            args.xmax,
            args.label_mode,
            args.label_font_size,
            args.unit_box_text,
            args.verbose,
        )
    except FileNotFoundError as exc:
        return fail(str(exc))
    except (KeyError, ValueError) as exc:
        return fail(f"unable to render plot: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
