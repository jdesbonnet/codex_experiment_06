#!/usr/bin/env python3
"""
Upload tiny_vm bytecode frame over UART.

Frame format:
  magic:  'TVM1' (4 bytes)
  len:    little-endian uint16 payload length
  code:   payload bytes
  cksum:  uint8 sum(payload) mod 256
"""

from __future__ import annotations

import argparse
import os
import pathlib
import termios


BAUD_MAP = {
    57600: termios.B57600,
    115200: termios.B115200,
}


def set_raw_serial(fd: int, baud: int) -> None:
    if baud not in BAUD_MAP:
        raise ValueError(f"unsupported baud {baud}")
    attrs = termios.tcgetattr(fd)
    attrs[0] = termios.IGNPAR
    attrs[1] = 0
    attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    attrs[3] = 0
    attrs[4] = BAUD_MAP[baud]
    attrs[5] = BAUD_MAP[baud]
    attrs[6][termios.VMIN] = 0
    attrs[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    termios.tcflush(fd, termios.TCIOFLUSH)


def build_frame(code: bytes) -> bytes:
    if len(code) == 0 or len(code) > 0xFFFF:
        raise ValueError("code length must be 1..65535")
    checksum = sum(code) & 0xFF
    return b"TVM1" + len(code).to_bytes(2, "little") + code + bytes([checksum])


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload tiny_vm bytecode to MCU over UART")
    parser.add_argument("image", type=pathlib.Path, help="bytecode .bin file")
    parser.add_argument("--port", required=True, help="serial device, e.g. /dev/ttyACM1")
    parser.add_argument("--baud", type=int, default=57600, help="baud rate (default: 57600)")
    args = parser.parse_args()

    code = args.image.read_bytes()
    frame = build_frame(code)

    fd = os.open(args.port, os.O_RDWR | os.O_NOCTTY | os.O_SYNC)
    try:
        set_raw_serial(fd, args.baud)
        written = os.write(fd, frame)
    finally:
        os.close(fd)

    print(f"wrote frame bytes: {written} (payload {len(code)}) to {args.port} @ {args.baud}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
