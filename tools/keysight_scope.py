#!/usr/bin/env python3
"""
Minimal Keysight/Agilent InfiniiVision 3000 X-Series USBTMC helper.

This script is intentionally small and dependency-free. It uses one USBTMC
open/close cycle per SCPI transaction because that has proven more reliable on
this host than holding the device node open across long command sequences.
"""

from __future__ import annotations

import argparse
import errno
import os
import struct
import sys
import time
from dataclasses import dataclass
from pathlib import Path


def eprint(message: str) -> None:
    print(message, file=sys.stderr)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Keysight DSO-X 3014A USBTMC helper")
    parser.add_argument("--device", default="/dev/usbtmc0", help="USBTMC device path")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("idn", help="Query *IDN?")

    query_parser = subparsers.add_parser("query", help="Send a text SCPI query")
    query_parser.add_argument("scpi", help="SCPI query string")

    screenshot_parser = subparsers.add_parser("screenshot", help="Capture display image")
    screenshot_parser.add_argument("--output", required=True, help="Output PNG path")
    screenshot_parser.add_argument("--palette", default="COLor", choices=("COLor", "GRAYscale"))

    measure_parser = subparsers.add_parser("measure", help="Query a small set of measurements")
    measure_parser.add_argument("--source", default="CHANnel1", help="Measurement source")

    waveform_parser = subparsers.add_parser("waveform", help="Capture waveform CSV")
    waveform_parser.add_argument("--source", default="CHANnel1", help="Waveform source")
    waveform_parser.add_argument("--points-mode", default="RAW", choices=("RAW", "NORMal", "MAXimum"))
    waveform_parser.add_argument("--points", type=int, default=1000, help="Requested waveform points")
    waveform_parser.add_argument("--format", default="BYTE", choices=("BYTE", "WORD"))
    waveform_parser.add_argument("--byte-order", default="LSBF", choices=("LSBF", "MSBF"))
    waveform_parser.add_argument("--output", required=True, help="Output CSV path")

    setup_parser = subparsers.add_parser("setup-blink", help="Apply simple manual settings for a 0-3.3V blink signal")
    setup_parser.add_argument("--channel", default="CHANnel1", help="Input channel")
    setup_parser.add_argument("--scale", type=float, default=1.0, help="Vertical scale in V/div")
    setup_parser.add_argument("--offset", type=float, default=1.5, help="Vertical offset in V")
    setup_parser.add_argument("--time-scale", type=float, default=0.1, help="Time scale in s/div")
    setup_parser.add_argument("--trigger-level", type=float, default=1.5, help="Trigger level in V")

    return parser.parse_args()


@dataclass
class WaveformPreamble:
    wave_format: int
    acquire_type: int
    points: int
    average_count: int
    x_increment: float
    x_origin: float
    x_reference: float
    y_increment: float
    y_origin: float
    y_reference: float


class KeysightScope:
    def __init__(self, device: str, verbose: bool = False) -> None:
        self.device = device
        self.verbose = verbose

    def _log(self, message: str) -> None:
        if self.verbose:
            print(message)

    def _open(self) -> int:
        try:
            return os.open(self.device, os.O_RDWR)
        except PermissionError as exc:
            raise RuntimeError(
                f"Permission denied opening {self.device}. Install the Keysight udev rule or re-run with sufficient access."
            ) from exc
        except FileNotFoundError as exc:
            raise RuntimeError(f"Scope device {self.device} was not found.") from exc

    def _read_once(self, fd: int) -> bytes:
        try:
            return os.read(fd, 65536)
        except OSError as exc:
            if exc.errno in (errno.EAGAIN, errno.ETIMEDOUT, 110):
                return b""
            raise

    def write(self, scpi: str, settle_s: float = 0.05) -> None:
        self._log(f"> {scpi}")
        fd = self._open()
        try:
            os.write(fd, (scpi + "\n").encode("ascii"))
            time.sleep(settle_s)
        finally:
            os.close(fd)

    def query_text(self, scpi: str, settle_s: float = 0.1, timeout_s: float = 2.0) -> str:
        self._log(f"> {scpi}")
        fd = self._open()
        try:
            os.write(fd, (scpi + "\n").encode("ascii"))
            time.sleep(settle_s)
            deadline = time.time() + timeout_s
            chunks: list[bytes] = []
            quiet_deadline: float | None = None
            while time.time() < deadline:
                chunk = self._read_once(fd)
                if chunk:
                    chunks.append(chunk)
                    quiet_deadline = time.time() + 0.10
                elif quiet_deadline is not None and time.time() >= quiet_deadline:
                    break
                else:
                    time.sleep(0.01)
        finally:
            os.close(fd)
        response = b"".join(chunks).decode("ascii", errors="replace").strip()
        self._log(f"< {response}")
        return response

    def query_ieee_block(self, scpi: str, settle_s: float = 0.1, timeout_s: float = 5.0) -> bytes:
        self._log(f"> {scpi}")
        fd = self._open()
        try:
            os.write(fd, (scpi + "\n").encode("ascii"))
            time.sleep(settle_s)
            deadline = time.time() + timeout_s
            data = b""
            while time.time() < deadline:
                chunk = self._read_once(fd)
                if chunk:
                    data += chunk
                    if data.startswith(b"#") and len(data) >= 2:
                        digits = int(chr(data[1]))
                        if len(data) >= 2 + digits:
                            payload_len = int(data[2:2 + digits].decode("ascii"))
                            total = 2 + digits + payload_len
                            if len(data) >= total:
                                block = data[2 + digits:total]
                                self._log(f"< IEEE block {len(block)} bytes")
                                return block
                else:
                    time.sleep(0.01)
        finally:
            os.close(fd)
        raise RuntimeError(f"No IEEE block response received for {scpi!r}.")

    def idn(self) -> str:
        return self.query_text("*IDN?")

    def screenshot(self, output: Path, palette: str) -> None:
        self.write(":HARDcopy:INKSaver OFF")
        payload = self.query_ieee_block(f":DISPlay:DATA? PNG, {palette}", settle_s=0.2, timeout_s=10.0)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(payload)

    def setup_blink(self, channel: str, scale_v: float, offset_v: float, time_scale_s: float, trigger_level_v: float) -> None:
        commands = [
            "*CLS",
            f":{channel}:DISPlay ON",
            f":{channel}:PROBe 1",
            f":{channel}:SCALe {scale_v}",
            f":{channel}:OFFSet {offset_v}",
            f":TIMebase:SCALe {time_scale_s}",
            ":TRIGger:MODE EDGE",
            f":TRIGger:EDGE:SOURce {channel}",
            f":TRIGger:EDGE:LEVel {trigger_level_v}",
            ":RUN",
        ]
        for command in commands:
            self.write(command)

    def measure(self, source: str) -> dict[str, str]:
        self.write(f":MEASure:SOURce {source}")
        return {
            "source": self.query_text(":MEASure:SOURce?"),
            "frequency_hz": self.query_text(f":MEASure:FREQuency? {source}"),
            "period_s": self.query_text(f":MEASure:PERiod? {source}"),
            "vpp_v": self.query_text(f":MEASure:VPP? {source}"),
            "vmax_v": self.query_text(f":MEASure:VMAX? {source}"),
            "vmin_v": self.query_text(f":MEASure:VMIN? {source}"),
        }

    def waveform(self, source: str, points_mode: str, points: int, fmt: str, byte_order: str, output: Path) -> WaveformPreamble:
        self.write(f":WAVeform:SOURce {source}")
        self.write(f":WAVeform:POINts:MODE {points_mode}")
        self.write(f":WAVeform:POINts {points}")
        self.write(f":WAVeform:FORMat {fmt}")
        if fmt == "WORD":
            self.write(f":WAVeform:BYTeorder {byte_order}")

        preamble_text = self.query_text(":WAVeform:PREamble?", settle_s=0.1, timeout_s=3.0)
        if not preamble_text:
            raise RuntimeError("No waveform preamble returned by the scope.")

        preamble_values = [float(part) for part in preamble_text.split(",")]
        if len(preamble_values) != 10:
            raise RuntimeError(f"Unexpected waveform preamble: {preamble_text!r}")

        preamble = WaveformPreamble(
            wave_format=int(preamble_values[0]),
            acquire_type=int(preamble_values[1]),
            points=int(preamble_values[2]),
            average_count=int(preamble_values[3]),
            x_increment=preamble_values[4],
            x_origin=preamble_values[5],
            x_reference=preamble_values[6],
            y_increment=preamble_values[7],
            y_origin=preamble_values[8],
            y_reference=preamble_values[9],
        )

        payload = self.query_ieee_block(":WAVeform:DATA?", settle_s=0.2, timeout_s=5.0)
        if fmt == "BYTE":
            values = struct.unpack(f"{len(payload)}B", payload)
        else:
            word_count = len(payload) // 2
            endian = "<" if byte_order == "LSBF" else ">"
            values = struct.unpack(f"{endian}{word_count}H", payload[: word_count * 2])

        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="ascii") as handle:
            handle.write("time_s,voltage_v\n")
            for index, value in enumerate(values):
                time_s = preamble.x_origin + (index * preamble.x_increment)
                voltage_v = ((value - preamble.y_reference) * preamble.y_increment) + preamble.y_origin
                handle.write(f"{time_s:.12e},{voltage_v:.9f}\n")

        return preamble


def main() -> int:
    args = parse_args()
    scope = KeysightScope(args.device, verbose=args.verbose)
    try:
        if args.command == "idn":
            print(scope.idn())
            return 0

        if args.command == "query":
            print(scope.query_text(args.scpi))
            return 0

        if args.command == "screenshot":
            output = Path(args.output)
            scope.screenshot(output, args.palette)
            print(output)
            return 0

        if args.command == "setup-blink":
            scope.setup_blink(args.channel, args.scale, args.offset, args.time_scale, args.trigger_level)
            print("scope configured")
            return 0

        if args.command == "measure":
            results = scope.measure(args.source)
            for key, value in results.items():
                print(f"{key}={value}")
            return 0

        if args.command == "waveform":
            preamble = scope.waveform(
                args.source,
                args.points_mode,
                args.points,
                args.format,
                args.byte_order,
                Path(args.output),
            )
            print(f"wave_format={preamble.wave_format}")
            print(f"acquire_type={preamble.acquire_type}")
            print(f"points={preamble.points}")
            print(f"x_increment={preamble.x_increment}")
            print(f"y_increment={preamble.y_increment}")
            print(args.output)
            return 0

    except RuntimeError as exc:
        eprint(str(exc))
        return 2

    eprint(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
