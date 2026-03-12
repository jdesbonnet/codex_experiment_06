#!/usr/bin/env python3
"""
Sweep the STM32F103C8 SD write benchmark across multiple SPI prescalers.

The benchmark project creates or overwrites CODXBEN.BIN on the FAT32 boot
partition. This script rebuilds and flashes the benchmark repeatedly, captures
UART output, and prints a compact results table.
"""

from __future__ import annotations

import argparse
import os
import re
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
BENCH_DIR = ROOT / "projects" / "sd_write_bench" / "stm32f103c8_c"
BENCH_IMAGE = BENCH_DIR / "sd_write_bench.elf"
READ_CHUNK = 256
BAUD = termios.B57600


@dataclass
class BenchResult:
    divider: int
    sysclk_hz: int | None
    spi_hz: int | None
    write_ms: int | None
    sync_close_ms: int | None
    total_ms: int | None
    write_rate_kbps: float | None
    total_rate_kbps: float | None
    ok: bool
    detail: str


def run_capture(cmd: list[str], *, timeout: float | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=ROOT,
        check=True,
        timeout=timeout,
        capture_output=True,
        text=True,
        env=env,
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
        raise RuntimeError("Could not detect the debugprobe primary UART.")
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
    fd = os.open(path, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
    configure_uart(fd)
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


def capture_until(fd: int, timeout_s: float, marker: str) -> str:
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
        if marker in text:
            return text
    return bytes(data).replace(b"\x00", b"").decode("utf-8", errors="replace")


def parse_result(divider: int, uart_text: str) -> BenchResult:
    def match_ints(pattern: str) -> tuple[int, ...] | None:
        m = re.search(pattern, uart_text)
        if not m:
            return None
        return tuple(int(group) for group in m.groups())

    def match_floats(pattern: str) -> tuple[float, ...] | None:
        m = re.search(pattern, uart_text)
        if not m:
            return None
        return tuple(float(group) for group in m.groups())

    sysclk_info = match_ints(r"sd_write_bench: sysclk_hz=(\d+)")
    spi_info = match_ints(r"bench: file=.* spi_prescaler=/(\d+) spi_hz=(\d+)")
    time_info = match_ints(r"bench: write_ms=(\d+) sync_close_ms=(\d+) total_ms=(\d+)")
    rate_info = match_floats(r"bench: write_rate_kBps=([0-9]+\.[0-9]) total_rate_kBps=([0-9]+\.[0-9])")

    if "sd_write_bench: complete" not in uart_text or spi_info is None or time_info is None or rate_info is None:
        tail = uart_text.strip().splitlines()[-1] if uart_text.strip().splitlines() else "no UART output"
        return BenchResult(
            divider=divider,
            sysclk_hz=sysclk_info[0] if sysclk_info is not None else None,
            spi_hz=spi_info[1] if spi_info is not None else None,
            write_ms=None if time_info is None else time_info[0],
            sync_close_ms=None if time_info is None else time_info[1],
            total_ms=None if time_info is None else time_info[2],
            write_rate_kbps=None if rate_info is None else rate_info[0],
            total_rate_kbps=None if rate_info is None else rate_info[1],
            ok=False,
            detail=tail,
        )

    return BenchResult(
        divider=divider,
        sysclk_hz=sysclk_info[0] if sysclk_info is not None else None,
        spi_hz=spi_info[1],
        write_ms=time_info[0],
        sync_close_ms=time_info[1],
        total_ms=time_info[2],
        write_rate_kbps=rate_info[0],
        total_rate_kbps=rate_info[1],
        ok=True,
        detail="ok",
    )


def run_one(divider: int, fd: int, timeout_s: float, verbose: bool, sysclk_hz: int, total_bytes: int) -> BenchResult:
    flush_uart(fd)
    env = dict(os.environ)
    env["SD_SPI_BENCH_DIV"] = str(divider)
    env["STM32_BENCH_SYSCLK_HZ"] = str(sysclk_hz)
    env["SD_WRITE_BENCH_BYTES"] = str(total_bytes)
    build = subprocess.run(
        ["make", "-C", str(BENCH_DIR), "clean", "all"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60.0,
        env=env,
    )
    if build.returncode != 0:
        detail = build.stderr.strip().splitlines()[-1] if build.stderr.strip() else "build failed"
        return BenchResult(divider, None, None, None, None, None, None, None, False, detail)

    result = subprocess.run(
        [
            str(FLASH_SCRIPT),
            "--target",
            "stm32f103c8",
            "--lang",
            "c",
            "--project",
            "sd_write_bench",
            "--image",
            str(BENCH_IMAGE),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60.0,
        env=env,
    )
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "flash failed"
        return BenchResult(divider, None, None, None, None, None, None, None, False, detail)
    uart_text = capture_until(fd, timeout_s, "sd_write_bench: complete")
    if verbose:
        print(f"--- divider /{divider} UART ---")
        print(uart_text, end="" if uart_text.endswith("\n") else "\n")
    return parse_result(divider, uart_text)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dividers",
        default="2,4,8,16,32,64",
        help="Comma-separated SPI prescalers to test (default: 2,4,8,16,32,64).",
    )
    parser.add_argument(
        "--sysclk-hz",
        type=int,
        default=8000000,
        help="MCU system clock for the benchmark build (default: 8000000).",
    )
    parser.add_argument(
        "--bytes",
        type=int,
        default=65536,
        help="Benchmark file size in bytes (default: 65536).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="UART capture timeout per divider in seconds (default: 20).",
    )
    parser.add_argument(
        "--uart-port",
        help="Override the auto-detected debugprobe primary UART path.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print full UART logs for each divider.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        dividers = [int(part.strip()) for part in args.dividers.split(",") if part.strip()]
        uart_port = args.uart_port or detect_uart_port()
        fd = open_uart(uart_port)
        try:
            print(f"UART: {uart_port}")
            print("divider,sysclk_hz,spi_hz,write_ms,sync_close_ms,total_ms,write_rate_kBps,total_rate_kBps,status")
            overall_ok = True
            for divider in dividers:
                result = run_one(divider, fd, args.timeout, args.verbose, args.sysclk_hz, args.bytes)
                status = "PASS" if result.ok else f"FAIL:{result.detail}"
                sysclk_hz = "" if result.sysclk_hz is None else str(result.sysclk_hz)
                spi_hz = "" if result.spi_hz is None else str(result.spi_hz)
                write_ms = "" if result.write_ms is None else str(result.write_ms)
                sync_close_ms = "" if result.sync_close_ms is None else str(result.sync_close_ms)
                total_ms = "" if result.total_ms is None else str(result.total_ms)
                write_rate = "" if result.write_rate_kbps is None else f"{result.write_rate_kbps:.1f}"
                total_rate = "" if result.total_rate_kbps is None else f"{result.total_rate_kbps:.1f}"
                print(f"{divider},{sysclk_hz},{spi_hz},{write_ms},{sync_close_ms},{total_ms},{write_rate},{total_rate},{status}")
                overall_ok = overall_ok and result.ok
        finally:
            os.close(fd)
        return 0 if overall_ok else 1
    except subprocess.TimeoutExpired as exc:
        print(f"Timeout while running {' '.join(exc.cmd)}.", file=sys.stderr)
        return 1
    except (RuntimeError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
