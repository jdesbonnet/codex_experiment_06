#!/usr/bin/env python3
"""
Run hardware regression tests for the STM32F103C8 SD-card projects.

This script:
- detects the debugprobe UART ports and uses the primary R/W endpoint by default
- flashes each selected STM32 SD-card project
- captures UART output at 57600 8N1
- verifies stable markers in the captured log

The default expectations match a Raspberry Pi OS SD card with a FAT32 boot
partition containing CMDLINE.TXT and CONFIG.TXT.

Note: the sd_fatfs case performs a controlled write test by creating or
overwriting CODXWR.TXT on the boot partition.
"""

from __future__ import annotations

import argparse
import os
import select
import subprocess
import sys
import termios
import time
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
FLASH_SCRIPT = ROOT / "tools" / "flash.sh"
UART_PORTS = ROOT / "tools" / "find_debugprobe_uart_ports.sh"
BAUD = termios.B57600
READ_CHUNK = 256
FLASH_TIMEOUT_S = 30.0


@dataclass(frozen=True)
class TestCase:
    name: str
    project: str
    timeout_s: float
    markers: tuple[str, ...]


TEST_CASES = {
    "sd_spi_probe": TestCase(
        name="sd_spi_probe",
        project="sd_spi_probe",
        timeout_s=8.0,
        markers=(
            "sd: CMD0 R1=0x01",
            "sd: CMD8 R1=0x01",
            "sd: OCR=",
            "sd: part0",
            "sd: selected partition type 0x0C",
            "sd: filesystem=FAT32",
            "sd: probe complete",
        ),
    ),
    "sd_fatfs": TestCase(
        name="sd_fatfs",
        project="sd_fatfs",
        timeout_s=10.0,
        markers=(
            "fatfs: f_mount -> 0",
            "fatfs: f_opendir -> 0",
            "fatfs: FILE CMDLINE.TXT",
            "fatfs: FILE CONFIG.TXT",
            "fatfs: f_open 0:/CMDLINE.TXT -> 0",
            "fatfs: f_open 0:/CONFIG.TXT -> 0",
            "fatfs: f_open 0:/CODXWR.TXT write -> 0",
            "fatfs: f_write 0:/CODXWR.TXT -> 0",
            "fatfs: f_sync 0:/CODXWR.TXT -> 0",
            "fatfs: f_open 0:/CODXWR.TXT verify -> 0",
            "fatfs: f_read 0:/CODXWR.TXT -> 0",
            "fatfs: 0:/CODXWR.TXT verify: codex sd write test\\r\\n",
            "sd_fatfs: complete",
        ),
    ),
}


def run_capture(cmd: list[str], *, timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=ROOT,
        check=True,
        timeout=timeout,
        capture_output=True,
        text=True,
    )


def detect_uart_port() -> str:
    result = run_capture(["bash", str(UART_PORTS), "--env"], timeout=2.0)
    values: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()

    primary = values.get("DEBUGPROBE_UART_PRIMARY", "")
    if not primary:
        raise RuntimeError(
            "Could not detect the debugprobe primary UART. "
            "Check tools/find_debugprobe_uart_ports.sh and the probe USB connection."
        )
    return primary


def configure_uart(fd: int) -> None:
    attrs = termios.tcgetattr(fd)
    attrs[0] = 0
    attrs[1] = 0
    attrs[2] = attrs[2] | termios.CLOCAL | termios.CREAD | termios.CS8
    attrs[2] = attrs[2] & ~(termios.PARENB | termios.CSTOPB | termios.CRTSCTS)
    attrs[3] = 0
    attrs[4] = BAUD
    attrs[5] = BAUD
    attrs[6][termios.VMIN] = 0
    attrs[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, attrs)


def open_uart(path: str) -> int:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
    except OSError as exc:
        raise RuntimeError(f"Could not open UART {path}: {exc.strerror}.") from exc
    try:
        configure_uart(fd)
    except Exception:
        os.close(fd)
        raise
    return fd


def flush_uart(fd: int, drain_s: float = 0.25) -> None:
    end = time.monotonic() + drain_s
    while time.monotonic() < end:
        ready, _, _ = select.select([fd], [], [], 0.02)
        if not ready:
            continue
        try:
            chunk = os.read(fd, READ_CHUNK)
        except BlockingIOError:
            continue
        if not chunk:
            break


def flash_project(project: str, verbose: bool) -> str:
    cmd = [str(FLASH_SCRIPT), "--target", "stm32f103c8", "--lang", "c", "--project", project]
    result = subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=FLASH_TIMEOUT_S,
    )
    if result.returncode != 0:
        detail = extract_failure_detail(result.stdout, result.stderr)
        if verbose:
            if result.stdout:
                print(result.stdout, end="")
            if result.stderr:
                print(result.stderr, end="", file=sys.stderr)
        raise RuntimeError(f"Flashing {project} failed: {detail}")
    if verbose and result.stdout:
        print(result.stdout, end="")
    return result.stdout


def capture_until(fd: int, timeout_s: float, markers: tuple[str, ...]) -> str:
    deadline = time.monotonic() + timeout_s
    data = bytearray()
    while time.monotonic() < deadline:
        remaining = max(0.05, deadline - time.monotonic())
        ready, _, _ = select.select([fd], [], [], min(0.25, remaining))
        if not ready:
            continue
        try:
            chunk = os.read(fd, READ_CHUNK)
        except BlockingIOError:
            continue
        if not chunk:
            continue
        data.extend(chunk)
        text = bytes(data).replace(b"\x00", b"").decode("utf-8", errors="replace")
        if all(marker in text for marker in markers):
            return text
    return bytes(data).replace(b"\x00", b"").decode("utf-8", errors="replace")


def verify_case(case: TestCase, uart_text: str) -> None:
    missing = [marker for marker in case.markers if marker not in uart_text]
    if missing:
        raise AssertionError(
            f"{case.name}: missing UART markers: {', '.join(missing)}"
        )


def extract_failure_detail(stdout: str, stderr: str) -> str:
    for blob in (stderr, stdout):
        lines = [line.strip() for line in blob.splitlines() if line.strip()]
        if lines:
            return lines[-1]
    return "command returned a non-zero exit status"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tests",
        default="sd_spi_probe,sd_fatfs",
        help="Comma-separated list of tests to run (default: sd_spi_probe,sd_fatfs).",
    )
    parser.add_argument(
        "--uart-port",
        help="Override the auto-detected debugprobe primary UART path.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print flash logs and captured UART output.",
    )
    return parser.parse_args()


def resolve_cases(names: str) -> list[TestCase]:
    out: list[TestCase] = []
    for raw_name in names.split(","):
        name = raw_name.strip()
        if not name:
            continue
        case = TEST_CASES.get(name)
        if case is None:
            valid = ", ".join(sorted(TEST_CASES))
            raise RuntimeError(f"Unknown test '{name}'. Valid choices: {valid}.")
        out.append(case)
    if not out:
        raise RuntimeError("No tests selected.")
    return out


def main() -> int:
    args = parse_args()
    try:
        cases = resolve_cases(args.tests)
        uart_port = args.uart_port or detect_uart_port()
        fd = open_uart(uart_port)
        try:
            print(f"UART: {uart_port}")
            for case in cases:
                flush_uart(fd)
                flash_project(case.project, args.verbose)
                uart_text = capture_until(fd, case.timeout_s, case.markers)
                if args.verbose:
                    print(f"--- {case.name} UART ---")
                    print(uart_text, end="" if uart_text.endswith("\n") else "\n")
                verify_case(case, uart_text)
                print(f"{case.name}: PASS")
        finally:
            os.close(fd)
        print("All STM32 SD hardware tests passed.")
        return 0
    except AssertionError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    except subprocess.TimeoutExpired as exc:
        print(f"Timeout while running {' '.join(exc.cmd)}.", file=sys.stderr)
        return 1
    except (RuntimeError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
