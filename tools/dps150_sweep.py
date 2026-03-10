#!/usr/bin/env python3
"""
FNIRSI DPS-150/DC supply sweep test for a 2-terminal DUT.

Safety policy:
- Never set current limit above 20 mA.
- Turn output OFF on startup and best-effort OFF on exit.
"""

from __future__ import annotations

import argparse
import csv
import struct
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import serial


# Protocol bytes (reverse-engineered)
FRAME_OUT = 0xF1
FRAME_IN = 0xF0

CMD_GET = 0xA1
CMD_BAUD = 0xB0
CMD_SET = 0xB1
CMD_SESSION = 0xC1

TYPE_OUTPUT_SET_VOLTAGE = 193
TYPE_OUTPUT_SET_CURRENT = 194
TYPE_OUTPUT_VOLTAGE = 195
TYPE_TEMPERATURE = 196
TYPE_METERING_ENABLE = 216
TYPE_OUTPUT_STATE = 219
TYPE_MODEL_NAME = 222
TYPE_HW_VERSION = 223
TYPE_FW_VERSION = 224

MAX_CURRENT_A = 0.020  # hard ceiling


@dataclass
class Frame:
    cmd: int
    typ: int
    data: bytes


class DPS150:
    def __init__(self, port: str, baud: int = 115200, timeout: float = 0.2, verbose: bool = False) -> None:
        self.verbose = verbose
        try:
            self.ser = serial.Serial(
                port=port,
                baudrate=baud,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=timeout,
                write_timeout=1.0,
                rtscts=True,
            )
        except serial.SerialException as exc:
            raise RuntimeError(f"Unable to open serial port {port}: {exc}") from exc
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()

    def close(self) -> None:
        self.ser.close()

    @staticmethod
    def checksum(typ: int, data: bytes) -> int:
        return (typ + len(data) + sum(data)) & 0xFF

    def send_frame(self, cmd: int, typ: int, data: bytes = b"") -> None:
        if len(data) > 255:
            raise ValueError("payload too large")
        frame = bytes([FRAME_OUT, cmd & 0xFF, typ & 0xFF, len(data) & 0xFF]) + data
        frame += bytes([self.checksum(typ, data)])
        self.ser.write(frame)
        self.ser.flush()
        if self.verbose:
            print(f"tx cmd=0x{cmd:02X} typ={typ} len={len(data)}")

    def read_frame(self, deadline_s: float = 1.0) -> Frame | None:
        deadline = time.monotonic() + deadline_s
        while time.monotonic() < deadline:
            b = self.ser.read(1)
            if not b:
                continue
            if b[0] != FRAME_IN:
                continue
            hdr = self.ser.read(3)
            if len(hdr) != 3:
                continue
            cmd, typ, length = hdr[0], hdr[1], hdr[2]
            data = self.ser.read(length)
            if len(data) != length:
                continue
            chk = self.ser.read(1)
            if len(chk) != 1:
                continue
            if chk[0] != self.checksum(typ, data):
                continue
            if self.verbose:
                print(f"rx cmd=0x{cmd:02X} typ={typ} len={len(data)} data={data.hex()}")
            return Frame(cmd=cmd, typ=typ, data=data)
        return None

    def xfer(self, cmd: int, typ: int, data: bytes = b"", retries: int = 3) -> Frame:
        for _ in range(retries):
            self.send_frame(cmd, typ, data)
            fr = self.read_frame(deadline_s=1.0)
            if fr is None:
                continue
            # Accept matching cmd or known command responses after set/get.
            if fr.cmd in (cmd, CMD_GET, CMD_SET, CMD_SESSION, CMD_BAUD):
                return fr
        raise TimeoutError(f"no valid response for cmd=0x{cmd:02X} type={typ}")

    def session_start(self) -> None:
        # From public reverse-engineering: session command with payload [1].
        self.xfer(CMD_SESSION, 0, b"\x01")
        # Keep device at 115200 (baud index 5 in the reverse-engineered client).
        self.xfer(CMD_BAUD, 0, b"\x05")

    def set_output(self, on: bool) -> None:
        self.xfer(CMD_SET, TYPE_OUTPUT_STATE, bytes([1 if on else 0]))

    def set_metering(self, on: bool) -> None:
        self.xfer(CMD_SET, TYPE_METERING_ENABLE, bytes([1 if on else 0]))

    def set_voltage(self, v: float) -> None:
        self.xfer(CMD_SET, TYPE_OUTPUT_SET_VOLTAGE, struct.pack("<f", float(v)))

    def set_current_limit(self, a: float) -> None:
        if a > MAX_CURRENT_A + 1e-9:
            raise ValueError("current limit exceeds 20 mA safety ceiling")
        self.xfer(CMD_SET, TYPE_OUTPUT_SET_CURRENT, struct.pack("<f", float(a)))

    def get_float(self, typ: int) -> float:
        self.send_frame(CMD_GET, typ, b"")
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline:
            fr = self.read_frame(deadline_s=0.3)
            if fr is None:
                continue
            if fr.cmd == CMD_GET and fr.typ == typ and len(fr.data) >= 4:
                return float(struct.unpack("<f", fr.data[:4])[0])
        raise RuntimeError(f"bad float response for type {typ}")

    def get_output_measurements(self) -> tuple[float, float, float]:
        self.send_frame(CMD_GET, TYPE_OUTPUT_VOLTAGE, b"")
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline:
            fr = self.read_frame(deadline_s=0.3)
            if fr is None:
                continue
            # Type 195 returns 3 floats: output voltage, current, power.
            if fr.cmd == CMD_GET and fr.typ == TYPE_OUTPUT_VOLTAGE and len(fr.data) >= 12:
                v, i, p = struct.unpack("<fff", fr.data[:12])
                return float(v), float(i), float(p)
        raise RuntimeError("bad measurement response for type 195")

    def get_string(self, typ: int) -> str:
        self.send_frame(CMD_GET, typ, b"")
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline:
            fr = self.read_frame(deadline_s=0.3)
            if fr is None:
                continue
            if fr.cmd == CMD_GET and fr.typ == typ:
                return fr.data.split(b"\x00", 1)[0].decode("utf-8", errors="replace").strip()
        return ""


def linreg_through_origin(xs: list[float], ys: list[float]) -> tuple[float, float]:
    # y = kx
    num = sum(x * y for x, y in zip(xs, ys))
    den = sum(x * x for x in xs)
    if den <= 0:
        return 0.0, 0.0
    k = num / den
    yhat = [k * x for x in xs]
    sse = sum((y - yh) ** 2 for y, yh in zip(ys, yhat))
    sst = sum((y - (sum(ys) / len(ys))) ** 2 for y in ys) if len(ys) > 1 else 0.0
    r2 = 1.0 - (sse / sst) if sst > 0 else 1.0
    return k, r2


def classify_device(points: list[tuple[float, float]]) -> str:
    # points: (V, I[A])
    if len(points) < 4:
        return "Insufficient data"
    vs = [v for v, _ in points]
    is_ = [i for _, i in points]
    # Use only non-zero current points above 0.5 mA for rough fit.
    filt = [(v, i) for v, i in points if i > 0.0005]
    if len(filt) >= 4:
        fv = [v for v, _ in filt]
        fi = [i for _, i in filt]
        k, r2 = linreg_through_origin(fv, fi)
        if k > 1e-6 and r2 > 0.985:
            r_est = 1.0 / k
            return f"Likely resistive load, approximately {r_est:.1f} ohm (R^2={r2:.4f})"
    # Look for diode-like knee: very low current at low V, then steep rise.
    low = [i for v, i in points if v <= 0.8]
    high = [i for v, i in points if v >= 1.8]
    if low and high:
        if max(low) < 0.001 and max(high) > 0.008:
            return "Likely diode/LED-like nonlinear load (clear knee behavior)"
    # Fallback
    i_max = max(is_)
    if i_max < 0.0002:
        return "Likely open circuit / very high impedance device"
    return "Nonlinear or mixed behavior; no high-confidence single-component identification"


def main() -> int:
    parser = argparse.ArgumentParser(description="Sweep-test a 2-terminal DUT with FNIRSI DPS-150")
    parser.add_argument("--port", default="/dev/ttyACM2", help="serial port (default: /dev/ttyACM2)")
    parser.add_argument("--v-start", type=float, default=0.0, help="start voltage")
    parser.add_argument("--v-stop", type=float, default=5.0, help="stop voltage")
    parser.add_argument("--v-step", type=float, default=0.25, help="voltage step")
    parser.add_argument("--i-limit-ma", type=float, default=20.0, help="current limit in mA (max 20)")
    parser.add_argument("--settle-ms", type=int, default=250, help="settle time per point")
    parser.add_argument("--out-csv", type=Path, default=Path("results/dps150_sweep.csv"))
    parser.add_argument("--verbose", action="store_true", help="print protocol/debug detail")
    args = parser.parse_args()

    if args.i_limit_ma <= 0 or args.i_limit_ma > 20.0:
        raise SystemExit("Refusing to run: --i-limit-ma must be in (0, 20].")
    if args.v_step <= 0:
        raise SystemExit("--v-step must be > 0.")
    if args.v_stop < args.v_start:
        raise SystemExit("--v-stop must be >= --v-start.")

    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    i_limit_a = args.i_limit_ma / 1000.0

    psu = DPS150(args.port, verbose=args.verbose)
    model = ""
    hw = ""
    fw = ""
    points: list[tuple[float, float, float]] = []  # set_v, meas_v, meas_i

    try:
        psu.session_start()
        # Always force safe state first.
        psu.set_output(False)
        psu.set_metering(True)
        psu.set_current_limit(i_limit_a)
        psu.set_voltage(args.v_start)
        time.sleep(0.2)

        model = psu.get_string(TYPE_MODEL_NAME)
        hw = psu.get_string(TYPE_HW_VERSION)
        fw = psu.get_string(TYPE_FW_VERSION)

        psu.set_output(True)
        v = args.v_start
        while v <= args.v_stop + 1e-12:
            psu.set_voltage(v)
            time.sleep(max(0.01, args.settle_ms / 1000.0))
            meas_v, meas_i, _ = psu.get_output_measurements()
            points.append((v, meas_v, meas_i))
            # Hard safety stop near limit.
            if meas_i >= (MAX_CURRENT_A * 0.995):
                break
            v += args.v_step
    except Exception as exc:
        print(f"Sweep failed: {exc}", file=sys.stderr)
        return 1
    finally:
        # Best-effort safe shutdown.
        try:
            psu.set_output(False)
        except Exception:
            pass
        psu.close()

    with args.out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["set_voltage_v", "measured_voltage_v", "measured_current_a"])
        for row in points:
            w.writerow([f"{row[0]:.6f}", f"{row[1]:.6f}", f"{row[2]:.6f}"])

    iv_points = [(mv, mi) for _, mv, mi in points]
    guess = classify_device(iv_points)

    print(f"port={args.port}")
    print(f"model={model!r} hw={hw!r} fw={fw!r}")
    print(f"points={len(points)}")
    print(f"csv={args.out_csv}")
    print(f"guess={guess}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
