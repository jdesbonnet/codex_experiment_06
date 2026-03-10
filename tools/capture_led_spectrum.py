#!/usr/bin/env python3
"""
Capture a background-subtracted LED spectrum using the DPS-150 and a serial
spectrometer that streams CSV records as:

    frame_counter,sample0,sample1,...,sample287

The script averages background and illuminated frames separately, subtracts the
background, and writes CSV, SVG, and Markdown outputs.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import serial

# Reuse the existing PSU transport instead of duplicating the protocol.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dps150_sweep import DPS150, MAX_CURRENT_A  # noqa: E402


PIXEL_COUNT = 288

# Calibration from the user's spectrometer notes in:
# https://github.com/jdesbonnet/hamamatsu_c12880ma/blob/master/README.md
# Serial number noted there: 22G03276
WAVELENGTH_COEFFS = (
    3.120790493e02,
    2.681652834e00,
    -8.061777879e-04,
    -1.052906745e-05,
    1.925845957e-08,
    -7.465510101e-12,
)


@dataclass
class CaptureResult:
    frames: int
    mean_spectrum: list[float]
    first_frame_id: int
    last_frame_id: int


class Spectrometer:
    def __init__(self, port: str, timeout: float = 2.0) -> None:
        try:
            self.ser = serial.Serial(
                port=port,
                baudrate=115200,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=timeout,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False,
            )
        except serial.SerialException as exc:
            raise RuntimeError(f"Unable to open spectrometer port {port}: {exc}") from exc

    def close(self) -> None:
        self.ser.close()

    def _read_valid_frame(self) -> tuple[int, list[int]]:
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            raw = self.ser.readline()
            if not raw:
                continue
            try:
                line = raw.decode("ascii", errors="strict").strip()
            except UnicodeDecodeError:
                continue
            if not line:
                continue
            parts = line.split(",")
            if len(parts) != PIXEL_COUNT + 1:
                continue
            try:
                values = [int(part) for part in parts]
            except ValueError:
                continue
            return values[0], values[1:]
        raise RuntimeError("Timed out waiting for a valid spectrometer frame")

    def capture_mean(self, discard_frames: int, sample_frames: int) -> CaptureResult:
        self.ser.reset_input_buffer()
        for _ in range(discard_frames):
            self._read_valid_frame()

        accum = [0.0] * PIXEL_COUNT
        first_frame_id = -1
        last_frame_id = -1
        for index in range(sample_frames):
            frame_id, pixels = self._read_valid_frame()
            if index == 0:
                first_frame_id = frame_id
            last_frame_id = frame_id
            for pixel_index, value in enumerate(pixels):
                accum[pixel_index] += float(value)

        mean = [value / sample_frames for value in accum]
        return CaptureResult(
            frames=sample_frames,
            mean_spectrum=mean,
            first_frame_id=first_frame_id,
            last_frame_id=last_frame_id,
        )


def pixel_to_wavelength_nm(pixel: int) -> float:
    a0, b1, b2, b3, b4, b5 = WAVELENGTH_COEFFS
    value = float(pixel)
    return a0 + (b1 * value) + (b2 * value**2) + (b3 * value**3) + (b4 * value**4) + (b5 * value**5)


def write_spectrum_csv(path: Path, spectra: dict[str, list[float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["pixel", "wavelength_nm", *spectra.keys()])
        for pixel in range(PIXEL_COUNT):
            row = [pixel, f"{pixel_to_wavelength_nm(pixel):.6f}"]
            for values in spectra.values():
                row.append(f"{values[pixel]:.6f}")
            writer.writerow(row)


def wavelength_to_rgb_hex(wavelength_nm: float) -> str:
    # Approximate visible-spectrum mapping for SVG styling.
    # Based on a common Dan Bruton-style piecewise approximation.
    gamma = 0.8

    if wavelength_nm < 380.0 or wavelength_nm > 780.0:
        return "#9aa0a6"

    if wavelength_nm < 440.0:
        red = -(wavelength_nm - 440.0) / (440.0 - 380.0)
        green = 0.0
        blue = 1.0
    elif wavelength_nm < 490.0:
        red = 0.0
        green = (wavelength_nm - 440.0) / (490.0 - 440.0)
        blue = 1.0
    elif wavelength_nm < 510.0:
        red = 0.0
        green = 1.0
        blue = -(wavelength_nm - 510.0) / (510.0 - 490.0)
    elif wavelength_nm < 580.0:
        red = (wavelength_nm - 510.0) / (580.0 - 510.0)
        green = 1.0
        blue = 0.0
    elif wavelength_nm < 645.0:
        red = 1.0
        green = -(wavelength_nm - 645.0) / (645.0 - 580.0)
        blue = 0.0
    else:
        red = 1.0
        green = 0.0
        blue = 0.0

    if wavelength_nm < 420.0:
        factor = 0.3 + 0.7 * (wavelength_nm - 380.0) / (420.0 - 380.0)
    elif wavelength_nm <= 700.0:
        factor = 1.0
    else:
        factor = 0.3 + 0.7 * (780.0 - wavelength_nm) / (780.0 - 700.0)

    def scale(channel: float) -> int:
        if channel <= 0.0:
            return 0
        return int(round(255.0 * ((channel * factor) ** gamma)))

    return f"#{scale(red):02x}{scale(green):02x}{scale(blue):02x}"


def svg_polyline_points(
    wavelengths_nm: list[float], values: list[float], width: int, height: int, margin: int
) -> str:
    plot_width = width - (2 * margin)
    plot_height = height - (2 * margin)
    y_max = max(values) if values else 1.0
    if y_max <= 0:
        y_max = 1.0
    x_min = min(wavelengths_nm)
    x_max = max(wavelengths_nm)
    x_span = x_max - x_min if x_max > x_min else 1.0

    points: list[str] = []
    for wavelength_nm, value in zip(wavelengths_nm, values):
        x = margin + ((wavelength_nm - x_min) / x_span) * plot_width
        y = margin + plot_height - ((value / y_max) * plot_height)
        points.append(f"{x:.2f},{y:.2f}")
    return " ".join(points)


def write_svg(path: Path, values: list[float], title: str) -> None:
    width = 960
    height = 520
    margin = 56
    plot_width = width - (2 * margin)
    plot_height = height - (2 * margin)
    y_max = max(values) if values else 1.0
    if y_max <= 0:
        y_max = 1.0
    wavelengths_nm = [pixel_to_wavelength_nm(pixel) for pixel in range(PIXEL_COUNT)]
    x_min = min(wavelengths_nm)
    x_max = max(wavelengths_nm)
    x_span = x_max - x_min if x_max > x_min else 1.0

    def y_tick(value: float) -> float:
        return margin + plot_height - ((value / y_max) * plot_height)

    def x_tick(wavelength_nm: float) -> float:
        return margin + ((wavelength_nm - x_min) / x_span) * plot_width

    y_ticks = [0.0, y_max * 0.25, y_max * 0.5, y_max * 0.75, y_max]
    polyline = svg_polyline_points(wavelengths_nm, values, width, height, margin)
    x_ticks = [350, 400, 450, 500, 550, 600, 650, 700, 750, 800]
    gradient_stops = []
    for wavelength_nm in range(math.ceil(x_min), math.floor(x_max) + 1, 10):
        offset = ((wavelength_nm - x_min) / x_span) * 100.0
        gradient_stops.append(
            f'<stop offset="{offset:.2f}%" stop-color="{wavelength_to_rgb_hex(float(wavelength_nm))}" />'
        )

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<style>',
        'text { font-family: monospace; fill: #1e2933; }',
        '.axis { stroke: #475866; stroke-width: 1; }',
        '.grid { stroke: #d5dde5; stroke-width: 1; }',
        '.trace { fill: none; stroke: url(#spectrumGradient); stroke-width: 3; stroke-linecap: round; stroke-linejoin: round; }',
        '</style>',
        '<defs>',
        f'<linearGradient id="spectrumGradient" x1="{margin}" y1="0" x2="{width - margin}" y2="0" gradientUnits="userSpaceOnUse">',
        *gradient_stops,
        '</linearGradient>',
        '</defs>',
        f'<text x="{width / 2:.0f}" y="28" text-anchor="middle" font-size="20">{title}</text>',
        f'<line class="axis" x1="{margin}" y1="{margin}" x2="{margin}" y2="{height - margin}" />',
        f'<line class="axis" x1="{margin}" y1="{height - margin}" x2="{width - margin}" y2="{height - margin}" />',
    ]

    for tick in y_ticks:
        y = y_tick(tick)
        lines.append(f'<line class="grid" x1="{margin}" y1="{y:.2f}" x2="{width - margin}" y2="{y:.2f}" />')
        lines.append(f'<text x="{margin - 8}" y="{y + 4:.2f}" text-anchor="end" font-size="12">{tick:.1f}</text>')

    for wavelength_nm in x_ticks:
        if wavelength_nm < x_min or wavelength_nm > x_max:
            continue
        x = x_tick(float(wavelength_nm))
        lines.append(f'<line class="grid" x1="{x:.2f}" y1="{margin}" x2="{x:.2f}" y2="{height - margin}" />')
        lines.append(
            f'<text x="{x:.2f}" y="{height - margin + 20}" text-anchor="middle" font-size="12">{wavelength_nm}</text>'
        )

    lines.append(f'<polyline class="trace" points="{polyline}" />')
    lines.append(f'<text x="{width / 2:.0f}" y="{height - 16}" text-anchor="middle" font-size="14">Wavelength (nm)</text>')
    lines.append(
        f'<text x="18" y="{height / 2:.0f}" transform="rotate(-90 18 {height / 2:.0f})" text-anchor="middle" font-size="14">'
        'Background-subtracted counts</text>'
    )
    lines.append("</svg>")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_report(
    path: Path,
    svg_path: Path,
    csv_path: Path,
    current_ma: float,
    voltage_v: float,
    power_mw: float,
    background: CaptureResult,
    illuminated: CaptureResult,
    subtracted: list[float],
) -> None:
    peak_value = max(subtracted)
    peak_pixel = subtracted.index(peak_value)
    peak_wavelength_nm = pixel_to_wavelength_nm(peak_pixel)
    text = f"""# Blue LED Spectrum Report (2026-03-10)

## Setup
- Spectrometer port: `/dev/ttyUSB0`
- DPS-150 current limit: `{current_ma:.3f} mA`
- DPS-150 measured LED voltage: `{voltage_v:.4f} V`
- DPS-150 measured LED current: `{current_ma:.3f} mA`
- DPS-150 measured LED power: `{power_mw:.3f} mW`
- Background frames averaged: `{background.frames}` (frame IDs `{background.first_frame_id}` to `{background.last_frame_id}`)
- Illuminated frames averaged: `{illuminated.frames}` (frame IDs `{illuminated.first_frame_id}` to `{illuminated.last_frame_id}`)

## Result
The plot below shows the background-subtracted LED spectrum using the wavelength calibration polynomial from:
- `https://github.com/jdesbonnet/hamamatsu_c12880ma/blob/master/README.md`

Calibration applied:
- `lambda(i) = A0 + B1*i + B2*i^2 + B3*i^3 + B4*i^4 + B5*i^5`
- `A0=312.0790493`
- `B1=2.681652834`
- `B2=-8.061777879e-04`
- `B3=-1.052906745e-05`
- `B4=1.925845957e-08`
- `B5=-7.465510101e-12`

Peak response:
- Pixel: `{peak_pixel}`
- Wavelength: `{peak_wavelength_nm:.2f} nm`
- Background-subtracted counts: `{peak_value:.3f}`

![Background-subtracted blue LED spectrum]({svg_path.as_posix()})

Raw data:
- Combined CSV: `{csv_path.as_posix()}`
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def wait_for_led_current(psu: DPS150, timeout_s: float) -> tuple[float, float, float]:
    deadline = time.monotonic() + timeout_s
    last = (0.0, 0.0, 0.0)
    while time.monotonic() < deadline:
        last = psu.get_output_measurements()
        if last[1] >= 0.0001:
            return last
        time.sleep(0.15)
    return last


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture a background-subtracted LED spectrum")
    parser.add_argument("--spectrometer-port", default="/dev/ttyUSB0", help="spectrometer serial port")
    parser.add_argument(
        "--psu-port",
        default="/dev/serial/by-id/usb-Artery_AT32_Virtual_Com_Port_13F50CF82565-if00",
        help="DPS-150 serial port",
    )
    parser.add_argument("--frames", type=int, default=24, help="number of averaged frames per state")
    parser.add_argument("--discard", type=int, default=8, help="frames to discard after each state change")
    parser.add_argument("--current-ma", type=float, default=5.0, help="LED drive current in mA (max 20)")
    parser.add_argument("--voltage-v", type=float, default=3.50, help="PSU voltage limit for the LED")
    parser.add_argument("--settle-ms", type=int, default=500, help="delay after switching LED state")
    parser.add_argument(
        "--out-prefix",
        type=Path,
        default=Path("results/blue_led_spectrum"),
        help="output prefix for CSV/SVG products",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("docs/blue_led_spectrum_report_2026-03-10.md"),
        help="Markdown report path",
    )
    args = parser.parse_args()

    if args.frames <= 0:
        raise SystemExit("--frames must be > 0")
    if args.discard < 0:
        raise SystemExit("--discard must be >= 0")
    if args.current_ma <= 0 or args.current_ma > (MAX_CURRENT_A * 1000.0):
        raise SystemExit("--current-ma must be in (0, 20]")

    current_a = args.current_ma / 1000.0
    csv_path = args.out_prefix.with_suffix(".csv")
    svg_path = args.out_prefix.with_suffix(".svg")

    spectrometer = Spectrometer(args.spectrometer_port)
    psu = DPS150(args.psu_port)
    try:
        psu.session_start()
        psu.set_output(False)
        psu.set_metering(True)
        psu.set_current_limit(current_a)
        psu.set_voltage(args.voltage_v)
        time.sleep(max(args.settle_ms, 0) / 1000.0)

        background = spectrometer.capture_mean(args.discard, args.frames)

        psu.set_output(True)
        # The DPS-150 occasionally needs the voltage setpoint resent after
        # output enable before it settles at the expected operating point.
        psu.set_voltage(args.voltage_v)
        time.sleep(max(args.settle_ms, 0) / 1000.0)
        measured_v, measured_i, measured_p = wait_for_led_current(psu, timeout_s=2.0)
        if measured_i < 0.0001:
            raise RuntimeError("LED current is effectively zero after output enable; check wiring and polarity")
        illuminated = spectrometer.capture_mean(args.discard, args.frames)
        measured_v, measured_i, measured_p = psu.get_output_measurements()

        subtracted = [max(0.0, lit - dark) for dark, lit in zip(background.mean_spectrum, illuminated.mean_spectrum)]

        write_spectrum_csv(
            csv_path,
            {
                "background_mean": background.mean_spectrum,
                "illuminated_mean": illuminated.mean_spectrum,
                "subtracted": subtracted,
            },
        )
        write_svg(svg_path, subtracted, "Blue LED Spectrum (Background Subtracted)")
        write_report(
            args.report,
            svg_path,
            csv_path,
            measured_i * 1000.0,
            measured_v,
            measured_p * 1000.0,
            background,
            illuminated,
            subtracted,
        )

        print(f"csv={csv_path}")
        print(f"svg={svg_path}")
        print(f"report={args.report}")
        print(f"measured_voltage_v={measured_v:.6f}")
        print(f"measured_current_ma={measured_i * 1000.0:.3f}")
        print(f"peak_pixel={subtracted.index(max(subtracted))}")
        print(f"peak_wavelength_nm={pixel_to_wavelength_nm(subtracted.index(max(subtracted))):.6f}")
        print(f"peak_counts={max(subtracted):.3f}")
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
