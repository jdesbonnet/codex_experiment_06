#!/usr/bin/env python3
"""
Sweep LED current while capturing background-subtracted spectra from the
connected spectrometer. The tool records when the LED first becomes detectable
above the dark-noise floor and when the spectrometer begins to clip.
"""

from __future__ import annotations

import argparse
import csv
import math
import serial
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from capture_led_spectrum import PIXEL_COUNT, Spectrometer, pixel_to_wavelength_nm, wait_for_led_current
from dps150_sweep import DPS150, MAX_CURRENT_A
from rigol_dp832 import RigolDP832


@dataclass
class SweepPoint:
    current_set_ma: float
    measured_voltage_v: float
    measured_current_ma: float
    measured_power_mw: float
    peak_pixel: int
    peak_wavelength_nm: float
    peak_counts: float
    saturated_pixels: int
    illuminated_max: float
    subtracted: list[float]
    illuminated: list[float]


def measure_noise(background_a: list[float], background_b: list[float]) -> tuple[float, float]:
    diffs = [abs(b - a) for a, b in zip(background_a, background_b)]
    peak = max(diffs)
    rms = math.sqrt(sum(value * value for value in diffs) / len(diffs))
    return peak, rms


def capture_sweep_point(
    spectrometer: Spectrometer,
    psu: DPS150,
    current_ma: float,
    voltage_v: float,
    discard_frames: int,
    sample_frames: int,
    settle_ms: int,
    background: list[float],
) -> SweepPoint:
    current_a = current_ma / 1000.0
    psu.set_current_limit(current_a)
    psu.set_output(True)
    psu.set_voltage(voltage_v)
    time.sleep(max(settle_ms, 0) / 1000.0)
    measured_v, measured_i, measured_p = wait_for_led_current(psu, timeout_s=2.0)
    illuminated_capture = spectrometer.capture_mean(discard_frames, sample_frames)
    measured_v, measured_i, measured_p = psu.get_output_measurements()

    subtracted = [max(0.0, lit - dark) for dark, lit in zip(background, illuminated_capture.mean_spectrum)]
    peak_counts = max(subtracted)
    peak_pixel = subtracted.index(peak_counts)
    illuminated_max = max(illuminated_capture.mean_spectrum)
    saturated_pixels = sum(1 for value in illuminated_capture.mean_spectrum if value >= 1000.0)

    return SweepPoint(
        current_set_ma=current_ma,
        measured_voltage_v=measured_v,
        measured_current_ma=measured_i * 1000.0,
        measured_power_mw=measured_p * 1000.0,
        peak_pixel=peak_pixel,
        peak_wavelength_nm=pixel_to_wavelength_nm(peak_pixel),
        peak_counts=peak_counts,
        saturated_pixels=saturated_pixels,
        illuminated_max=illuminated_max,
        subtracted=subtracted,
        illuminated=illuminated_capture.mean_spectrum,
    )


def write_summary_csv(path: Path, points: list[SweepPoint]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "current_set_ma",
                "measured_voltage_v",
                "measured_current_ma",
                "measured_power_mw",
                "peak_pixel",
                "peak_wavelength_nm",
                "peak_counts",
                "saturated_pixels",
                "illuminated_max",
            ]
        )
        for point in points:
            writer.writerow(
                [
                    f"{point.current_set_ma:.6f}",
                    f"{point.measured_voltage_v:.6f}",
                    f"{point.measured_current_ma:.6f}",
                    f"{point.measured_power_mw:.6f}",
                    point.peak_pixel,
                    f"{point.peak_wavelength_nm:.6f}",
                    f"{point.peak_counts:.6f}",
                    point.saturated_pixels,
                    f"{point.illuminated_max:.6f}",
                ]
            )


def write_spectra_csv(path: Path, points: list[SweepPoint], background: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "current_set_ma",
                "measured_current_ma",
                "pixel",
                "wavelength_nm",
                "background_mean",
                "illuminated_mean",
                "subtracted",
            ]
        )
        for point in points:
            for pixel in range(PIXEL_COUNT):
                writer.writerow(
                    [
                        f"{point.current_set_ma:.6f}",
                        f"{point.measured_current_ma:.6f}",
                        pixel,
                        f"{pixel_to_wavelength_nm(pixel):.6f}",
                        f"{background[pixel]:.6f}",
                        f"{point.illuminated[pixel]:.6f}",
                        f"{point.subtracted[pixel]:.6f}",
                    ]
                )


def write_overlay_svg(path: Path, points: list[SweepPoint], title: str) -> None:
    width = 960
    height = 560
    margin = 64
    plot_width = width - (2 * margin)
    plot_height = height - (2 * margin)
    wavelengths_nm = [pixel_to_wavelength_nm(pixel) for pixel in range(PIXEL_COUNT)]
    x_min = min(wavelengths_nm)
    x_max = max(wavelengths_nm)
    x_span = x_max - x_min if x_max > x_min else 1.0
    y_max = max(max(point.subtracted) for point in points) if points else 1.0
    if y_max <= 0:
        y_max = 1.0

    palette = [
        "#1f77b4",
        "#2ca02c",
        "#ff7f0e",
        "#d62728",
        "#9467bd",
        "#8c564b",
        "#17becf",
        "#bcbd22",
        "#7f7f7f",
    ]

    def x_coord(wavelength_nm: float) -> float:
        return margin + ((wavelength_nm - x_min) / x_span) * plot_width

    def y_coord(value: float) -> float:
        return margin + plot_height - ((value / y_max) * plot_height)

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<style>",
        "text { font-family: monospace; fill: #1e2933; }",
        ".axis { stroke: #475866; stroke-width: 1; }",
        ".grid { stroke: #d5dde5; stroke-width: 1; }",
        ".trace { fill: none; stroke-width: 2.25; stroke-linecap: round; stroke-linejoin: round; }",
        "</style>",
        f'<text x="{width / 2:.0f}" y="28" text-anchor="middle" font-size="20">{title}</text>',
        f'<line class="axis" x1="{margin}" y1="{margin}" x2="{margin}" y2="{height - margin}" />',
        f'<line class="axis" x1="{margin}" y1="{height - margin}" x2="{width - margin}" y2="{height - margin}" />',
    ]

    for tick in [0.0, y_max * 0.25, y_max * 0.5, y_max * 0.75, y_max]:
        y = y_coord(tick)
        lines.append(f'<line class="grid" x1="{margin}" y1="{y:.2f}" x2="{width - margin}" y2="{y:.2f}" />')
        lines.append(f'<text x="{margin - 8}" y="{y + 4:.2f}" text-anchor="end" font-size="12">{tick:.1f}</text>')

    for tick_nm in [350, 400, 450, 500, 550, 600, 650, 700, 750, 800]:
        if tick_nm < x_min or tick_nm > x_max:
            continue
        x = x_coord(float(tick_nm))
        lines.append(f'<line class="grid" x1="{x:.2f}" y1="{margin}" x2="{x:.2f}" y2="{height - margin}" />')
        lines.append(f'<text x="{x:.2f}" y="{height - margin + 22}" text-anchor="middle" font-size="12">{tick_nm}</text>')

    for index, point in enumerate(points):
        pts = []
        for wavelength_nm, value in zip(wavelengths_nm, point.subtracted):
            pts.append(f"{x_coord(wavelength_nm):.2f},{y_coord(value):.2f}")
        color = palette[index % len(palette)]
        lines.append(f'<polyline class="trace" stroke="{color}" points="{" ".join(pts)}" />')

    legend_x = width - margin - 180
    legend_y = margin + 10
    lines.append(f'<rect x="{legend_x - 12}" y="{legend_y - 18}" width="192" height="{24 * len(points) + 16}" fill="#ffffff" fill-opacity="0.82" stroke="#b7c2cc" />')
    for index, point in enumerate(points):
        color = palette[index % len(palette)]
        y = legend_y + (24 * index)
        label = f"{point.measured_current_ma:.2f} mA"
        if point.saturated_pixels > 0:
            label += f" ({point.saturated_pixels} sat)"
        lines.append(f'<line x1="{legend_x}" y1="{y:.2f}" x2="{legend_x + 18}" y2="{y:.2f}" stroke="{color}" stroke-width="3" />')
        lines.append(f'<text x="{legend_x + 26}" y="{y + 4:.2f}" font-size="12">{label}</text>')

    lines.append(f'<text x="{width / 2:.0f}" y="{height - 18}" text-anchor="middle" font-size="14">Wavelength (nm)</text>')
    lines.append(
        f'<text x="20" y="{height / 2:.0f}" transform="rotate(-90 20 {height / 2:.0f})" text-anchor="middle" font-size="14">'
        "Background-subtracted counts</text>"
    )
    lines.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_report(
    path: Path,
    overlay_svg_path: Path,
    summary_csv_path: Path,
    spectra_csv_path: Path,
    points: list[SweepPoint],
    noise_peak: float,
    noise_rms: float,
    detection_threshold: float,
) -> None:
    first_detected = next((point for point in points if point.peak_counts >= detection_threshold), None)
    first_clipped = next((point for point in points if point.saturated_pixels > 0), None)
    measured_currents = [point.measured_current_ma for point in points]
    current_steps = [round(b - a, 6) for a, b in zip(measured_currents, measured_currents[1:])]
    unique_steps = sorted(set(current_steps))

    lines = [
        "# Blue LED Current Sweep Spectrum Report (2026-03-10)",
        "",
        "## Method",
        "- One averaged dark capture was taken with the LED off.",
        "- A second dark capture was taken to estimate the subtraction noise floor.",
        "- The LED was then swept upward in current and a background-subtracted spectrum was captured at each point.",
        "- The sweep stopped on the first clipped spectrum (`illuminated_mean >= 1000` for at least one pixel) or at the requested maximum current.",
        "",
        "## Noise Floor",
        f"- Dark-to-dark peak absolute difference: `{noise_peak:.3f}` counts",
        f"- Dark-to-dark RMS difference: `{noise_rms:.3f}` counts",
        f"- Detection threshold used: `{detection_threshold:.3f}` counts",
        "",
        "## Findings",
    ]

    if first_detected is None:
        lines.append("- No LED spectrum rose above the chosen detection threshold in this sweep.")
    else:
        lines.append(
            f"- First detected spectrum: `{first_detected.measured_current_ma:.3f} mA` "
            f"(peak `{first_detected.peak_counts:.3f}` counts at `{first_detected.peak_wavelength_nm:.2f} nm`)."
        )

    if first_clipped is None:
        lines.append("- No clipped spectrum was reached in this sweep.")
    else:
        lines.append(
            f"- First clipped spectrum: `{first_clipped.measured_current_ma:.3f} mA` "
            f"with `{first_clipped.saturated_pixels}` saturated pixels."
        )

    if unique_steps:
        lines.append(f"- Observed measured-current steps: `{', '.join(f'{step:.3f}' for step in unique_steps if step > 0)}` mA")

    lines.extend(
        [
            "",
            "## Plot",
            f"![LED spectrum current sweep]({overlay_svg_path.as_posix()})",
            "",
            "## Data",
            f"- Summary CSV: `{summary_csv_path.as_posix()}`",
            f"- Spectra CSV: `{spectra_csv_path.as_posix()}`",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def frange(start: float, stop: float, step: float) -> list[float]:
    values = []
    current = start
    while current <= stop + 1e-12:
        values.append(round(current, 6))
        current += step
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description="Sweep LED current and capture spectra")
    parser.add_argument("--spectrometer-port", default="/dev/ttyUSB0", help="spectrometer serial port")
    parser.add_argument(
        "--psu-type",
        choices=("dps150", "rigol-dp832"),
        default="dps150",
        help="power-supply backend",
    )
    parser.add_argument(
        "--psu-port",
        default="/dev/serial/by-id/usb-Artery_AT32_Virtual_Com_Port_13F50CF82565-if00",
        help="DPS-150 serial port",
    )
    parser.add_argument("--rigol-device", default="/dev/usbtmc0", help="Rigol DP832 USBTMC device")
    parser.add_argument("--rigol-channel", type=int, default=1, help="Rigol DP832 channel number")
    parser.add_argument("--start-ma", type=float, default=0.50, help="starting LED current in mA")
    parser.add_argument("--stop-ma", type=float, default=2.00, help="maximum LED current in mA")
    parser.add_argument("--step-ma", type=float, default=0.05, help="LED current step in mA")
    parser.add_argument("--voltage-v", type=float, default=3.50, help="PSU voltage limit")
    parser.add_argument("--frames", type=int, default=12, help="averaged frames per capture")
    parser.add_argument("--discard", type=int, default=6, help="frames to discard after state change")
    parser.add_argument("--settle-ms", type=int, default=400, help="settle time after current changes")
    parser.add_argument("--detect-multiplier", type=float, default=3.0, help="multiplier applied to dark-noise peak")
    parser.add_argument(
        "--out-prefix",
        type=Path,
        default=Path("results/blue_led_current_sweep"),
        help="output prefix for summary/spectra/svg files",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("docs/blue_led_current_sweep_report_2026-03-10.md"),
        help="Markdown report path",
    )
    args = parser.parse_args()

    if args.start_ma <= 0 or args.stop_ma <= 0 or args.step_ma <= 0:
        raise SystemExit("Current sweep values must be > 0")
    if args.start_ma > args.stop_ma:
        raise SystemExit("--start-ma must be <= --stop-ma")
    if args.stop_ma > (MAX_CURRENT_A * 1000.0):
        raise SystemExit("--stop-ma must be <= 20")

    currents_ma = frange(args.start_ma, args.stop_ma, args.step_ma)
    summary_csv_path = args.out_prefix.with_name(args.out_prefix.name + "_summary.csv")
    spectra_csv_path = args.out_prefix.with_name(args.out_prefix.name + "_spectra.csv")
    overlay_svg_path = args.out_prefix.with_suffix(".svg")

    spectrometer = Spectrometer(args.spectrometer_port)
    if args.psu_type == "dps150":
        psu = DPS150(args.psu_port)
    else:
        psu = RigolDP832(args.rigol_device, channel=args.rigol_channel)
    points: list[SweepPoint] = []
    try:
        psu.session_start()
        psu.set_output(False)
        psu.set_metering(True)
        psu.set_voltage(args.voltage_v)
        time.sleep(max(args.settle_ms, 0) / 1000.0)

        background = spectrometer.capture_mean(args.discard, args.frames)
        background_check = spectrometer.capture_mean(args.discard, args.frames)
        noise_peak, noise_rms = measure_noise(background.mean_spectrum, background_check.mean_spectrum)
        detection_threshold = max(args.detect_multiplier * noise_peak, 5.0)

        for current_ma in currents_ma:
            attempts = 0
            while True:
                try:
                    point = capture_sweep_point(
                        spectrometer,
                        psu,
                        current_ma=current_ma,
                        voltage_v=args.voltage_v,
                        discard_frames=args.discard,
                        sample_frames=args.frames,
                        settle_ms=args.settle_ms,
                        background=background.mean_spectrum,
                    )
                    break
                except serial.SerialTimeoutException:
                    attempts += 1
                    if attempts > 2:
                        raise
                    try:
                        psu.close()
                    except Exception:
                        pass
                    if args.psu_type != "dps150":
                        raise
                    psu = DPS150(args.psu_port)
                    psu.session_start()
                    psu.set_output(False)
                    psu.set_metering(True)
                    psu.set_voltage(args.voltage_v)
                    time.sleep(max(args.settle_ms, 0) / 1000.0)
            points.append(point)
            print(
                f"current_set_ma={point.current_set_ma:.3f} measured_current_ma={point.measured_current_ma:.3f} "
                f"peak_counts={point.peak_counts:.3f} saturated_pixels={point.saturated_pixels}",
                flush=True,
            )
            if point.saturated_pixels > 0:
                break

        write_summary_csv(summary_csv_path, points)
        write_spectra_csv(spectra_csv_path, points, background.mean_spectrum)
        write_overlay_svg(overlay_svg_path, points, "Blue LED Spectrum Current Sweep")
        write_report(
            args.report,
            overlay_svg_path,
            summary_csv_path,
            spectra_csv_path,
            points,
            noise_peak,
            noise_rms,
            detection_threshold,
        )
        return 0
    finally:
        try:
            psu.set_output(False)
        except Exception:
            pass
        try:
            psu.close()
        except Exception:
            pass
        spectrometer.close()


if __name__ == "__main__":
    raise SystemExit(main())
