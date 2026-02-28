#!/usr/bin/env python3
"""
Run hardware regression tests for finite-output tiny_vm demo programs.

This script:
- flashes the LPC1114 tiny_vm runtime (default)
- auto-detects debugprobe primary/mirror UART ports
- compiles each selected test case to bytecode
- resets the target into run state
- uploads the bytecode
- captures mirror UART output
- verifies the expected application output and terminal "tiny_vm: halt"

It intentionally excludes `demos/blink.cvm.c` because that demo does not halt and does
not emit UART output, so it is not suitable for line-by-line UART verification.
"""

from __future__ import annotations

import argparse
import os
import select
import subprocess
import sys
import tempfile
import termios
import time
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
FLASH_SCRIPT = ROOT / "tools" / "flash.sh"
VM_CC = ROOT / "tools" / "vm_cc.py"
VM_UPLOAD = ROOT / "tools" / "vm_upload.py"
UART_PORTS = ROOT / "tools" / "find_debugprobe_uart_ports.sh"
OPENOCD_CFG = ROOT / "openocd" / "base.cfg"
OPENOCD_SCRIPTS = Path("/usr/share/openocd/scripts")
PROJECT_OPENOCD = ROOT / "openocd"

BOOT_STABILIZE_S = 0.8
READ_CHUNK = 256


@dataclass(frozen=True)
class TestCase:
    name: str
    source: Path
    timeout_s: float

    def expected_lines(self) -> list[str]:
        if self.name == "count10":
            return [str(i) for i in range(1, 11)]
        if self.name == "primes1000":
            return [str(v) for v in primes_upto(1000)]
        if self.name == "collatz_max":
            return ["97", "118"]
        if self.name == "checksum8":
            return ["15"]
        raise ValueError(f"unknown test case {self.name}")


TEST_CASES = [
    TestCase("count10", ROOT / "projects" / "tiny_vm" / "tests" / "count10.cvm.c", 8.0),
    TestCase("primes1000", ROOT / "projects" / "tiny_vm" / "tests" / "primes1000.cvm.c", 20.0),
    TestCase("collatz_max", ROOT / "projects" / "tiny_vm" / "tests" / "collatz_max.cvm.c", 8.0),
    TestCase("checksum8", ROOT / "projects" / "tiny_vm" / "tests" / "checksum8.cvm.c", 8.0),
]


def primes_upto(limit: int) -> list[int]:
    out: list[int] = []
    for n in range(2, limit + 1):
        prime = True
        d = 2
        while d * d <= n:
            if n % d == 0:
                prime = False
                break
            d += 1
        if prime:
            out.append(n)
    return out


def run(cmd: list[str], *, timeout: float | None = None, quiet: bool = False) -> None:
    subprocess.run(
        cmd,
        cwd=ROOT,
        check=True,
        timeout=timeout,
        capture_output=quiet,
        text=quiet,
    )


def run_capture(cmd: list[str], *, timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=ROOT,
        check=True,
        timeout=timeout,
        capture_output=True,
        text=True,
    )


def detect_uart_ports() -> tuple[str, str]:
    result = run_capture(["bash", str(UART_PORTS), "--env"], timeout=2.0)
    values: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    primary = values.get("DEBUGPROBE_UART_PRIMARY", "")
    mirror = values.get("DEBUGPROBE_UART_MIRROR", "")
    if not primary or not mirror:
        raise RuntimeError(
            "Could not detect both debugprobe UART ports. "
            "Check tools/find_debugprobe_uart_ports.sh and the dual-CDC probe."
        )
    return primary, mirror


def configure_uart(fd: int) -> None:
    attrs = termios.tcgetattr(fd)
    attrs[0] = 0
    attrs[1] = 0
    attrs[2] = attrs[2] | termios.CLOCAL | termios.CREAD | termios.CS8
    attrs[2] = attrs[2] & ~(termios.PARENB | termios.CSTOPB | termios.CRTSCTS)
    attrs[3] = 0
    attrs[4] = termios.B57600
    attrs[5] = termios.B57600
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


def reset_target_run() -> None:
    cmd = [
        "openocd",
        "-s",
        str(OPENOCD_SCRIPTS),
        "-s",
        str(PROJECT_OPENOCD),
        "-f",
        str(OPENOCD_CFG),
        "-c",
        "init; reset run; shutdown",
    ]
    run(cmd, timeout=8.0, quiet=True)


def flash_runtime() -> None:
    run(
        [str(FLASH_SCRIPT), "--target", "lpc1114", "--lang", "c", "--project", "tiny_vm"],
        timeout=30.0,
        quiet=True,
    )


def compile_case(case: TestCase) -> Path:
    tmp = tempfile.NamedTemporaryFile(prefix=f"{case.name}_", suffix=".bin", delete=False)
    tmp.close()
    out = Path(tmp.name)
    run([str(VM_CC), str(case.source), "-o", str(out)], timeout=10.0, quiet=True)
    return out


def upload_program(bin_path: Path, primary_port: str) -> None:
    run([str(VM_UPLOAD), str(bin_path), "--port", primary_port, "--baud", "57600"], timeout=10.0, quiet=True)


def capture_case_output(fd: int, timeout_s: float) -> tuple[str, list[str]]:
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
        if "tiny_vm: halt" in text:
            break
    text = bytes(data).replace(b"\x00", b"").decode("utf-8", errors="replace")
    lines = [line.strip() for line in text.replace("\r", "").split("\n") if line.strip()]
    return text, lines


def verify_output(case: TestCase, lines: list[str]) -> None:
    expected = ["tiny_vm: image loaded", *case.expected_lines(), "tiny_vm: halt"]
    # Ignore boot-banner chatter and match the final image-loaded block.
    start = -1
    for idx, line in enumerate(lines):
        if line == "tiny_vm: image loaded":
            start = idx
    if start < 0:
        raise AssertionError(f"{case.name}: missing 'tiny_vm: image loaded' in UART output")
    tail = lines[start : start + len(expected)]
    if tail != expected:
        raise AssertionError(
            f"{case.name}: unexpected UART output.\n"
            f"expected tail: {expected}\n"
            f"actual tail  : {tail}"
        )


def run_case(case: TestCase, primary_port: str, mirror_fd: int) -> None:
    print(f"[tiny_vm] case={case.name}: compile")
    bin_path = compile_case(case)
    try:
        flush_uart(mirror_fd)
        print(f"[tiny_vm] case={case.name}: reset run")
        reset_target_run()
        time.sleep(BOOT_STABILIZE_S)
        print(f"[tiny_vm] case={case.name}: upload")
        upload_program(bin_path, primary_port)
        print(f"[tiny_vm] case={case.name}: capture/verify")
        raw_text, lines = capture_case_output(mirror_fd, case.timeout_s)
        verify_output(case, lines)
        print(f"[tiny_vm] case={case.name}: PASS")
        log_path = Path("/tmp") / f"tiny_vm_{case.name}.log"
        log_path.write_text(raw_text, encoding="utf-8")
    finally:
        try:
            bin_path.unlink()
        except OSError:
            pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run hardware UART regression tests for tiny_vm demos")
    parser.add_argument(
        "--no-flash",
        action="store_true",
        help="skip reflashing the LPC1114 tiny_vm runtime before running test cases",
    )
    parser.add_argument(
        "--only",
        choices=[case.name for case in TEST_CASES],
        action="append",
        help="run only the named case (may be passed multiple times)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    selected = [case for case in TEST_CASES if not args.only or case.name in args.only]
    primary_port, mirror_port = detect_uart_ports()
    print(f"[tiny_vm] primary={primary_port} mirror={mirror_port}")

    if not args.no_flash:
        print("[tiny_vm] flashing LPC1114 tiny_vm runtime")
        flash_runtime()

    mirror_fd = open_uart(mirror_port)
    try:
        for case in selected:
            run_case(case, primary_port, mirror_fd)
    finally:
        os.close(mirror_fd)

    print("[tiny_vm] all selected cases: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
