#!/usr/bin/env python3
"""
Minimal Rigol DP832 USBTMC control helper for LED/spectrometer experiments.
"""

from __future__ import annotations

import os
import time


class RigolDP832:
    def __init__(self, device: str = "/dev/usbtmc0", channel: int = 1, timeout_s: float = 0.1) -> None:
        if channel not in (1, 2, 3):
            raise ValueError("channel must be 1, 2, or 3")
        self.device = device
        self.channel = channel
        self.timeout_s = timeout_s

    def _open(self) -> int:
        try:
            return os.open(self.device, os.O_RDWR)
        except PermissionError as exc:
            raise RuntimeError(
                f"Permission denied opening {self.device}. Re-run under sudo or add a udev rule for the Rigol DP832."
            ) from exc
        except FileNotFoundError as exc:
            raise RuntimeError(f"Rigol DP832 device {self.device} was not found.") from exc

    def write(self, cmd: str) -> None:
        fd = self._open()
        try:
            os.write(fd, (cmd + "\n").encode("ascii"))
            time.sleep(self.timeout_s)
        finally:
            os.close(fd)

    def query(self, cmd: str) -> str:
        fd = self._open()
        try:
            os.write(fd, (cmd + "\n").encode("ascii"))
            time.sleep(self.timeout_s)
            data = os.read(fd, 4096)
        finally:
            os.close(fd)
        return data.decode("ascii", errors="replace").strip()

    def session_start(self) -> None:
        self.write("*CLS")

    def set_output(self, on: bool) -> None:
        self.write(f":OUTP CH{self.channel},{'ON' if on else 'OFF'}")

    def set_metering(self, on: bool) -> None:
        _ = on

    def set_voltage(self, v: float) -> None:
        self.write(f":SOUR{self.channel}:VOLT {float(v):.6f}")

    def set_current_limit(self, a: float) -> None:
        self.write(f":SOUR{self.channel}:CURR {float(a):.6f}")

    def get_output_measurements(self) -> tuple[float, float, float]:
        response = self.query(f":MEAS:ALL? CH{self.channel}")
        parts = [part.strip() for part in response.split(",")]
        if len(parts) != 3:
            raise RuntimeError(f"Unexpected Rigol DP832 measurement response: {response!r}")
        voltage_v, current_a, power_w = (float(part) for part in parts)
        return voltage_v, current_a, power_w

    def close(self) -> None:
        return
