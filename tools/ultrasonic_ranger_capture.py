#!/usr/bin/env python3
"""Interact with the LPC824 ultrasonic ranger over UART and capture frames."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import serial


ASCII_FORMATS = {"COMPACT", "TEXT", "ENV"}
DEFAULT_BAUD = 230400
DEFAULT_TIMEOUT_S = 0.05
DEFAULT_IDLE_SETTLE_S = 0.3
DEFAULT_COMMAND_TIMEOUT_S = 2.0
DEFAULT_CAPTURE_TIMEOUT_S = 5.0


@dataclass
class FrameRecord:
    kind: str
    samples: list[int]
    raw_line: str


@dataclass
class TextRecord:
    kind: str
    line: str


class UltrasonicClient:
    def __init__(self, port: str, baud: int, timeout_s: float, verbose: bool) -> None:
        self._verbose = verbose
        self._buffer = bytearray()
        try:
            self._ser = serial.Serial(
                port=port,
                baudrate=baud,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=timeout_s,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False,
            )
        except serial.SerialException as exc:
            raise RuntimeError(f"Unable to open UART {port}: {exc}") from exc

    def close(self) -> None:
        self._ser.close()

    def log(self, message: str) -> None:
        if self._verbose:
            print(message)

    def reset_buffers(self) -> None:
        self._ser.reset_input_buffer()
        self._ser.reset_output_buffer()
        self._buffer.clear()

    def send_line(self, line: str) -> None:
        self.log(f">>> {line}")
        self._ser.write(f"{line}\r\n".encode("ascii"))
        self._ser.flush()

    def _read_some(self) -> bytes:
        return self._ser.read(4096)

    def drain_ascii(self, settle_s: float) -> list[TextRecord | FrameRecord]:
        deadline = time.monotonic() + settle_s
        records: list[TextRecord | FrameRecord] = []
        while time.monotonic() < deadline:
            chunk = self._read_some()
            if not chunk:
                continue
            self._buffer.extend(chunk)
            records.extend(self._parse_available_lines())
        self._buffer.clear()
        return records

    def read_records_until(
        self,
        predicate,
        timeout_s: float,
    ) -> list[TextRecord | FrameRecord]:
        deadline = time.monotonic() + timeout_s
        records: list[TextRecord | FrameRecord] = []
        while time.monotonic() < deadline:
            chunk = self._read_some()
            if chunk:
                self._buffer.extend(chunk)
                for record in self._parse_available_lines():
                    records.append(record)
                    if predicate(record, records):
                        return records
        return records

    def _parse_available_lines(self) -> list[TextRecord | FrameRecord]:
        records: list[TextRecord | FrameRecord] = []
        while True:
            newline_index = self._buffer.find(b"\n")
            if newline_index < 0:
                break
            raw = bytes(self._buffer[:newline_index])
            del self._buffer[: newline_index + 1]
            if raw.endswith(b"\r"):
                raw = raw[:-1]
            if not raw:
                continue
            record = self._parse_line(raw)
            if record is not None:
                records.append(record)
        return records

    def _parse_line(self, raw: bytes) -> TextRecord | FrameRecord | None:
        try:
            line = raw.decode("latin1")
        except UnicodeDecodeError:
            return TextRecord(kind="binary-garble", line=raw.hex())

        if line.startswith("W "):
            try:
                return FrameRecord(kind="waveform", samples=self._decode_compact_payload(line[2:]), raw_line=line)
            except RuntimeError as exc:
                return TextRecord(kind="malformed-frame", line=f"W decode error: {exc}")
        if line.startswith("E "):
            try:
                return FrameRecord(kind="envelope", samples=self._decode_compact_payload(line[2:]), raw_line=line)
            except RuntimeError as exc:
                return TextRecord(kind="malformed-frame", line=f"E decode error: {exc}")
        if line.startswith("T seq="):
            try:
                return FrameRecord(kind="waveform", samples=self._decode_text_payload(line), raw_line=line)
            except RuntimeError as exc:
                return TextRecord(kind="malformed-frame", line=f"T decode error: {exc}")
        if line == "OK":
            return TextRecord(kind="ok", line=line)
        if line.startswith("ERROR"):
            return TextRecord(kind="error", line=line)
        if line.startswith("+INFO:"):
            return TextRecord(kind="info", line=line)
        if line.startswith("+CFG:"):
            return TextRecord(kind="config", line=line)
        if line.startswith("+DONE:"):
            return TextRecord(kind="done", line=line)
        return TextRecord(kind="text", line=line)

    @staticmethod
    def _decode_compact_payload(payload: str) -> list[int]:
        if len(payload) % 2 != 0:
            raise RuntimeError("Compact payload length is odd")
        samples: list[int] = []
        for index in range(0, len(payload), 2):
            hi = ord(payload[index]) - 63
            lo = ord(payload[index + 1]) - 63
            if hi < 0 or hi > 63 or lo < 0 or lo > 63:
                raise RuntimeError("Compact payload character out of range")
            samples.append((hi << 6) | lo)
        return samples

    @staticmethod
    def _decode_text_payload(line: str) -> list[int]:
        parts = line.split(" ", 3)
        if len(parts) < 4:
            raise RuntimeError(f"Malformed text frame: {line}")
        values = parts[3].split(",")
        return [int(value) for value in values if value]


def maybe_reset_target(args: argparse.Namespace) -> None:
    if not getattr(args, "reset_target", False):
        return

    command = [
        "openocd",
        "-s",
        "/usr/share/openocd/scripts",
        "-s",
        "./openocd",
        "-f",
        "targets/lpc824/openocd/base.cfg",
        "-c",
        "init; reset run; shutdown",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip() or "openocd reset failed"
        raise RuntimeError(f"Target reset failed: {stderr}")
    time.sleep(0.2)


def parse_cfg_line(line: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for part in line[len("+CFG:") :].split(","):
        item = part.strip()
        if not item or "=" not in item:
            continue
        key, value = item.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def ensure_ok(records: Iterable[TextRecord | FrameRecord], context: str) -> None:
    saw_ok = False
    for record in records:
        if isinstance(record, TextRecord):
            if record.kind == "error":
                raise RuntimeError(f"{context} failed: {record.line}")
            if record.kind == "ok":
                saw_ok = True
    if not saw_ok:
        raise RuntimeError(f"{context} failed: no OK received")


def log_text_record(client: UltrasonicClient, record: TextRecord) -> None:
    if record.kind in {"text", "malformed-frame", "binary-garble"}:
        return
    client.log(f"<<< {record.line}")


def write_frame_csv(path: Path, frame: FrameRecord) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["index", "value"])
        for index, value in enumerate(frame.samples):
            writer.writerow([index, value])


def capture_subcommand(args: argparse.Namespace) -> int:
    capture_format = args.format.upper()
    if capture_format not in ASCII_FORMATS:
        raise RuntimeError(f"Unsupported format for this script: {capture_format}")

    mode = args.mode.upper()
    if mode not in {"SINGLE", "NSHOT", "CONTINUOUS"}:
        raise RuntimeError(f"Unsupported mode: {mode}")

    if mode == "SINGLE":
        frame_target = 1
    elif mode == "NSHOT":
        frame_target = args.nshot
    else:
        frame_target = args.frames

    if frame_target <= 0:
        raise RuntimeError("Frame target must be at least 1")

    maybe_reset_target(args)
    client = UltrasonicClient(args.port, args.baud, DEFAULT_TIMEOUT_S, args.verbose)
    try:
        client.reset_buffers()
        client.drain_ascii(DEFAULT_IDLE_SETTLE_S)

        client.send_line("ATSTOP")
        stop_records = client.read_records_until(
            lambda record, _: isinstance(record, TextRecord) and record.kind in {"done", "ok", "error"},
            DEFAULT_COMMAND_TIMEOUT_S,
        )
        for record in stop_records:
            if isinstance(record, TextRecord):
                log_text_record(client, record)

        commands = [
            f"ATMODE={mode}",
            f"ATFMT={capture_format}",
            f"ATTXFREQ={args.txfreq}",
            f"ATTXCYCLES={args.txcycles}",
            f"ATSRATE={args.srate}",
        ]
        if mode == "NSHOT":
            commands.insert(1, f"ATNSHOT={args.nshot}")

        config_line = None
        for line in commands:
            client.send_line(line)
            records = client.read_records_until(
                lambda record, _: isinstance(record, TextRecord) and record.kind in {"ok", "error"},
                DEFAULT_COMMAND_TIMEOUT_S,
            )
            for record in records:
                if isinstance(record, TextRecord):
                    log_text_record(client, record)
            ensure_ok(records, line)

        client.send_line("ATCFG?")
        cfg_records = client.read_records_until(
            lambda record, _: isinstance(record, TextRecord) and record.kind in {"ok", "error"},
            DEFAULT_COMMAND_TIMEOUT_S,
        )
        for record in cfg_records:
            if isinstance(record, TextRecord):
                log_text_record(client, record)
                if record.kind == "config":
                    config_line = record.line
        ensure_ok(cfg_records, "ATCFG?")

        client.send_line("ATGO")
        go_records = client.read_records_until(
            lambda record, _: isinstance(record, TextRecord) and record.kind in {"ok", "error"},
                DEFAULT_COMMAND_TIMEOUT_S,
        )
        for record in go_records:
            if isinstance(record, TextRecord):
                log_text_record(client, record)
        ensure_ok(go_records, "ATGO")

        frames: list[FrameRecord] = []
        timeout_s = max(DEFAULT_CAPTURE_TIMEOUT_S, args.timeout)
        if mode == "CONTINUOUS":
            timeout_s = max(timeout_s, args.timeout)

        records = client.read_records_until(
            lambda record, all_records: (
                isinstance(record, FrameRecord)
                and len([item for item in all_records if isinstance(item, FrameRecord)]) >= frame_target
            )
            or (isinstance(record, TextRecord) and record.kind == "error"),
            timeout_s,
        )
        for record in records:
            if isinstance(record, FrameRecord):
                frames.append(record)
            else:
                log_text_record(client, record)

        if len(frames) < frame_target:
            raise RuntimeError(
                f"Timed out waiting for {frame_target} frame(s); received {len(frames)}"
            )

        if mode == "CONTINUOUS":
            client.send_line("ATSTOP")
            done_records = client.read_records_until(
                lambda record, _: isinstance(record, TextRecord) and record.kind in {"done", "error"},
                DEFAULT_COMMAND_TIMEOUT_S,
            )
            for record in done_records:
                if isinstance(record, TextRecord):
                    log_text_record(client, record)

        timestamp = time.strftime("%Y-%m-%dT%H-%M-%SZ", time.gmtime())
        output_dir = args.output_dir or (Path("results") / f"ultrasonic_capture_{timestamp}")
        output_dir.mkdir(parents=True, exist_ok=True)

        manifest = {
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "port": args.port,
            "baud": args.baud,
            "mode": mode,
            "format": capture_format,
            "txfreq_hz": args.txfreq,
            "txcycles": args.txcycles,
            "srate_hz": args.srate,
            "frames_requested": frame_target,
            "frames_captured": len(frames),
            "config": parse_cfg_line(config_line) if config_line else None,
            "files": [],
        }

        for index, frame in enumerate(frames, start=1):
            name = f"{frame.kind}_{index:03d}.csv"
            path = output_dir / name
            write_frame_csv(path, frame)
            manifest["files"].append(
                {
                    "path": str(path),
                    "kind": frame.kind,
                    "samples": len(frame.samples),
                }
            )

        manifest_path = output_dir / "capture_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        print(f"Captured {len(frames)} frame(s) to {output_dir}")
        if config_line:
            print(config_line)
        for item in manifest["files"]:
            print(f"{item['kind']}: {item['samples']} samples -> {item['path']}")
        print(f"manifest: {manifest_path}")
        return 0
    finally:
        client.close()


def query_subcommand(args: argparse.Namespace) -> int:
    maybe_reset_target(args)
    client = UltrasonicClient(args.port, args.baud, DEFAULT_TIMEOUT_S, args.verbose)
    try:
        client.reset_buffers()
        client.drain_ascii(DEFAULT_IDLE_SETTLE_S)

        client.send_line("ATSTOP")
        stop_records = client.read_records_until(
            lambda record, _: isinstance(record, TextRecord) and record.kind in {"done", "ok", "error"},
            DEFAULT_COMMAND_TIMEOUT_S,
        )
        for record in stop_records:
            if isinstance(record, TextRecord):
                log_text_record(client, record)

        for line in ("ATI", "ATCFG?"):
            client.send_line(line)
            records = client.read_records_until(
                lambda record, _: isinstance(record, TextRecord) and record.kind in {"ok", "error"},
                DEFAULT_COMMAND_TIMEOUT_S,
            )
            for record in records:
                if isinstance(record, TextRecord):
                    print(record.line)
            ensure_ok(records, line)
        return 0
    finally:
        client.close()


def monitor_subcommand(args: argparse.Namespace) -> int:
    maybe_reset_target(args)
    client = UltrasonicClient(args.port, args.baud, DEFAULT_TIMEOUT_S, args.verbose)
    try:
        client.reset_buffers()
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            chunk = client._read_some()
            if not chunk:
                continue
            client._buffer.extend(chunk)
            for record in client._parse_available_lines():
                if isinstance(record, FrameRecord):
                    print(f"{record.kind}: {len(record.samples)} samples")
                else:
                    print(record.line)
        return 0
    finally:
        client.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Interact with the LPC824 ultrasonic ranger UART")
    parser.add_argument("--port", default="/dev/ttyACM0", help="UART device path")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD, help=f"Baud rate, default {DEFAULT_BAUD}")
    parser.add_argument("--reset-target", action="store_true", help="Reset the LPC824 over OpenOCD before opening UART")
    parser.add_argument("--verbose", action="store_true", help="Print command/response progress")

    subparsers = parser.add_subparsers(dest="command", required=True)

    query_parser = subparsers.add_parser("query", help="Query firmware info and current config")
    query_parser.set_defaults(func=query_subcommand)

    capture_parser = subparsers.add_parser("capture", help="Configure the device and capture frames")
    capture_parser.add_argument("--mode", default="SINGLE", help="SINGLE, NSHOT, or CONTINUOUS")
    capture_parser.add_argument("--format", default="COMPACT", help="COMPACT, TEXT, or ENV")
    capture_parser.add_argument("--nshot", type=int, default=3, help="Frame count for NSHOT mode")
    capture_parser.add_argument("--frames", type=int, default=3, help="Frame count to collect in CONTINUOUS mode")
    capture_parser.add_argument("--txfreq", type=int, default=40000, help="Excitation frequency in Hz")
    capture_parser.add_argument("--txcycles", type=int, default=1, help="Excitation cycles")
    capture_parser.add_argument("--srate", type=int, default=500000, help="ADC sample rate in Hz")
    capture_parser.add_argument("--timeout", type=float, default=DEFAULT_CAPTURE_TIMEOUT_S, help="Capture timeout in seconds")
    capture_parser.add_argument("--output-dir", type=Path, help="Directory for captured CSV files")
    capture_parser.set_defaults(func=capture_subcommand)

    monitor_parser = subparsers.add_parser("monitor", help="Print decoded UART traffic for a short interval")
    monitor_parser.add_argument("--seconds", type=float, default=3.0, help="Monitor duration in seconds")
    monitor_parser.set_defaults(func=monitor_subcommand)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except RuntimeError as exc:
        print(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
