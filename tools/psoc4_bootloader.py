#!/usr/bin/env python3
"""
PSoC 4 UART bootloader probe and uploader for CY8CKIT-049-42xx.

References:
- datasheets/PSoC4_CY8CKIT-049-42xx/CY8CKIT-049-4xxx_PSoC_4_Prototyping_Kit_Guide_001-90711_RevJ.pdf
- datasheets/PSoC4_CY8CKIT-049-42xx/AN68272_UART_Bootloader.pdf

Protocol summary from AN68272:
- packets start with 0x01 and end with 0x17
- packet checksum excludes the start byte, checksum bytes, and end byte
- packet checksum type is either:
  - basic summation in 2's complement form
  - CRC-16-CCITT

The .cyacd file format is ASCII hex:
- header: [4-byte silicon id][1-byte silicon rev][1-byte packet checksum type]
- rows:   [1-byte array id][2-byte row number][2-byte data length][N bytes data][1-byte row checksum]

The row checksum inside the .cyacd data records is always the basic 8-bit 2's complement checksum,
independent of the packet checksum mode used on the UART link.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import select
import sys
import termios
import time
from dataclasses import dataclass


START_BYTE = 0x01
END_BYTE = 0x17

CMD_VERIFY_CHECKSUM = 0x31
CMD_GET_FLASH_SIZE = 0x32
CMD_SYNC_BOOTLOADER = 0x35
CMD_SEND_DATA = 0x37
CMD_ENTER_BOOTLOADER = 0x38
CMD_PROGRAM_ROW = 0x39
CMD_VERIFY_ROW = 0x3A
CMD_EXIT_BOOTLOADER = 0x3B

ERR_LABELS = {
    0x00: "CYRET_SUCCESS",
    0x02: "BOOTLOADER_ERR_VERIFY",
    0x03: "BOOTLOADER_ERR_LENGTH",
    0x04: "BOOTLOADER_ERR_DATA",
    0x05: "BOOTLOADER_ERR_CMD",
    0x06: "BOOTLOADER_ERR_DEVICE",
    0x07: "BOOTLOADER_ERR_VERSION",
    0x08: "BOOTLOADER_ERR_CHECKSUM",
    0x09: "BOOTLOADER_ERR_ARRAY",
    0x0A: "BOOTLOADER_ERR_ROW",
    0x0C: "BOOTLOADER_ERR_APP",
    0x0D: "BOOTLOADER_ERR_ACTIVE",
    0x0F: "BOOTLOADER_ERR_UNK",
}

PACKET_CHECKSUM_SUM = 0
PACKET_CHECKSUM_CRC16 = 1

PACKET_DATA_MAX = 57
PROGRAM_ROW_DATA_MAX = PACKET_DATA_MAX - 3

READ_CHUNK = 256

BAUD_MAP = {
    115200: termios.B115200,
    57600: termios.B57600,
}


class BootloaderError(RuntimeError):
    pass


@dataclass
class CyacdRow:
    array_id: int
    row_number: int
    data: bytes
    row_checksum: int


@dataclass
class CyacdImage:
    silicon_id: int
    silicon_rev: int
    packet_checksum_type: int
    rows: list[CyacdRow]


def eprint(msg: str) -> None:
    print(msg, file=sys.stderr)


def checksum_sum16(payload: bytes) -> int:
    return (1 + (~sum(payload))) & 0xFFFF


def checksum_crc16_ccitt(payload: bytes) -> int:
    crc = 0xFFFF
    for byte in payload:
        crc ^= byte << 8
        for _ in range(8):
            if (crc & 0x8000) != 0:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def checksum_row8(payload: bytes) -> int:
    return (1 + (~sum(payload))) & 0xFF


def packet_checksum(payload: bytes, checksum_type: int) -> int:
    if checksum_type == PACKET_CHECKSUM_SUM:
        return checksum_sum16(payload)
    if checksum_type == PACKET_CHECKSUM_CRC16:
        return checksum_crc16_ccitt(payload)
    raise ValueError(f"unsupported checksum type {checksum_type}")


def packet_checksum_name(checksum_type: int) -> str:
    if checksum_type == PACKET_CHECKSUM_SUM:
        return "sum"
    if checksum_type == PACKET_CHECKSUM_CRC16:
        return "crc16"
    return f"unknown({checksum_type})"


def build_packet(command: int, data: bytes, checksum_type: int) -> bytes:
    body = bytes([command]) + len(data).to_bytes(2, "little") + data
    checksum = packet_checksum(body, checksum_type)
    return bytes([START_BYTE]) + body + checksum.to_bytes(2, "little") + bytes([END_BYTE])


def set_raw_serial(fd: int, baud: int) -> None:
    if baud not in BAUD_MAP:
        raise BootloaderError(f"Unsupported baud rate: {baud}. Supported: {', '.join(map(str, sorted(BAUD_MAP)))}")

    attrs = termios.tcgetattr(fd)
    attrs[0] = termios.IGNPAR
    attrs[1] = 0
    attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    attrs[2] &= ~(termios.PARENB | termios.CSTOPB | termios.CRTSCTS)
    attrs[3] = 0
    attrs[4] = BAUD_MAP[baud]
    attrs[5] = BAUD_MAP[baud]
    attrs[6][termios.VMIN] = 0
    attrs[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    termios.tcflush(fd, termios.TCIOFLUSH)


def open_serial(path: str, baud: int) -> int:
    try:
        fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    except OSError as exc:
        raise BootloaderError(f"Could not open serial port {path}: {exc.strerror}") from exc
    try:
        set_raw_serial(fd, baud)
    except Exception:
        os.close(fd)
        raise
    return fd


def read_exact(fd: int, length: int, timeout_s: float) -> bytes:
    deadline = time.monotonic() + timeout_s
    out = bytearray()
    while len(out) < length:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"Timed out waiting for {length} bytes from bootloader")
        ready, _, _ = select.select([fd], [], [], min(0.1, remaining))
        if not ready:
            continue
        try:
            chunk = os.read(fd, min(READ_CHUNK, length - len(out)))
        except BlockingIOError:
            continue
        if not chunk:
            continue
        out.extend(chunk)
    return bytes(out)


def flush_input(fd: int, drain_s: float = 0.1) -> None:
    end = time.monotonic() + drain_s
    while time.monotonic() < end:
        ready, _, _ = select.select([fd], [], [], 0.01)
        if not ready:
            continue
        try:
            chunk = os.read(fd, READ_CHUNK)
        except BlockingIOError:
            continue
        if not chunk:
            break


def recv_packet(fd: int, checksum_type: int, timeout_s: float, verbose: bool) -> tuple[int, bytes]:
    deadline = time.monotonic() + timeout_s

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Timed out waiting for bootloader response")
        first = read_exact(fd, 1, remaining)
        if first[0] == START_BYTE:
            break

    header = read_exact(fd, 3, max(0.01, deadline - time.monotonic()))
    status = header[0]
    data_len = int.from_bytes(header[1:3], "little")
    data = read_exact(fd, data_len, max(0.01, deadline - time.monotonic()))
    trailer = read_exact(fd, 3, max(0.01, deadline - time.monotonic()))
    checksum_rx = int.from_bytes(trailer[:2], "little")
    end = trailer[2]
    if end != END_BYTE:
        raise BootloaderError(f"Malformed response packet: expected end byte 0x17, got 0x{end:02X}")

    body = bytes([status]) + data_len.to_bytes(2, "little") + data
    checksum_calc = packet_checksum(body, checksum_type)
    if checksum_rx != checksum_calc:
        raise BootloaderError(
            f"Response checksum mismatch: got 0x{checksum_rx:04X}, expected 0x{checksum_calc:04X}"
        )

    if verbose:
        print(f"rx: {bytes([START_BYTE]) + body + trailer[:2] + bytes([END_BYTE])!r}")

    return status, data


def send_command(
    fd: int,
    checksum_type: int,
    command: int,
    data: bytes = b"",
    *,
    timeout_s: float = 1.0,
    expect_response: bool = True,
    verbose: bool = False,
) -> tuple[int, bytes]:
    packet = build_packet(command, data, checksum_type)
    if verbose:
        print(f"tx: {packet!r}")
    os.write(fd, packet)
    if not expect_response:
        return 0, b""
    return recv_packet(fd, checksum_type, timeout_s, verbose)


def parse_hex_record(text: str) -> bytes:
    stripped = text.strip()
    if not stripped:
        return b""
    while stripped and stripped[0] in ":;":
        stripped = stripped[1:]
    if len(stripped) % 2 != 0:
        raise BootloaderError(f"Invalid .cyacd record length: {text.strip()}")
    try:
        return bytes.fromhex(stripped)
    except ValueError as exc:
        raise BootloaderError(f"Invalid .cyacd hex record: {text.strip()}") from exc


def parse_cyacd(path: pathlib.Path) -> CyacdImage:
    if not path.is_file():
        raise BootloaderError(f"Image file not found: {path}")

    lines = [line.strip() for line in path.read_text(encoding="utf-8", errors="strict").splitlines() if line.strip()]
    if not lines:
        raise BootloaderError(f"Image file is empty: {path}")

    header = parse_hex_record(lines[0])
    if len(header) != 6:
        raise BootloaderError("Invalid .cyacd header length; expected 6 bytes")
    silicon_id = int.from_bytes(header[0:4], "big")
    silicon_rev = header[4]
    packet_cksum_type = header[5]
    rows: list[CyacdRow] = []

    for idx, line in enumerate(lines[1:], start=2):
        record = parse_hex_record(line)
        if len(record) < 7:
            raise BootloaderError(f"Invalid .cyacd record on line {idx}: too short")
        array_id = record[0]
        row_number = int.from_bytes(record[1:3], "big")
        data_len = int.from_bytes(record[3:5], "big")
        data = record[5:-1]
        row_checksum = record[-1]
        if len(data) != data_len:
            raise BootloaderError(
                f"Invalid .cyacd record on line {idx}: length field says {data_len} bytes, record has {len(data)}"
            )
        checksum_calc = checksum_row8(record[:-1])
        if checksum_calc != row_checksum:
            raise BootloaderError(
                f"Invalid .cyacd record on line {idx}: row checksum 0x{row_checksum:02X}, expected 0x{checksum_calc:02X}"
            )
        rows.append(CyacdRow(array_id=array_id, row_number=row_number, data=data, row_checksum=row_checksum))

    return CyacdImage(
        silicon_id=silicon_id,
        silicon_rev=silicon_rev,
        packet_checksum_type=packet_cksum_type,
        rows=rows,
    )


def decode_enter_bootloader_response(data: bytes) -> tuple[int, int, tuple[int, int, int]]:
    if len(data) != 8:
        raise BootloaderError(f"Unexpected Enter Bootloader response length: {len(data)}")
    silicon_id = int.from_bytes(data[0:4], "little")
    silicon_rev = data[4]
    version = (data[5], data[6], data[7])
    return silicon_id, silicon_rev, version


def status_label(status: int) -> str:
    return ERR_LABELS.get(status, f"0x{status:02X}")


def require_success(status: int, context: str) -> None:
    if status != 0x00:
        raise BootloaderError(f"{context} failed: {status_label(status)}")


def probe_bootloader(fd: int, checksum_mode: str, timeout_s: float, verbose: bool) -> tuple[int, int, tuple[int, int, int], int]:
    modes = []
    if checksum_mode == "auto":
        modes = [PACKET_CHECKSUM_SUM, PACKET_CHECKSUM_CRC16]
    elif checksum_mode == "sum":
        modes = [PACKET_CHECKSUM_SUM]
    elif checksum_mode == "crc16":
        modes = [PACKET_CHECKSUM_CRC16]
    else:
        raise BootloaderError(f"Unsupported checksum mode: {checksum_mode}")

    last_error: Exception | None = None
    for mode in modes:
        flush_input(fd)
        try:
            status, data = send_command(
                fd,
                mode,
                CMD_ENTER_BOOTLOADER,
                b"",
                timeout_s=timeout_s,
                expect_response=True,
                verbose=verbose,
            )
            require_success(status, "Enter Bootloader")
            silicon_id, silicon_rev, version = decode_enter_bootloader_response(data)
            return silicon_id, silicon_rev, version, mode
        except Exception as exc:
            last_error = exc
            try:
                send_command(fd, mode, CMD_SYNC_BOOTLOADER, b"", timeout_s=timeout_s, expect_response=True, verbose=verbose)
            except Exception:
                pass

    raise BootloaderError(
        "No valid bootloader response detected on the serial port. "
        "If this is a CY8CKIT-049-42xx, hold SW1 while plugging the board in until the blue LED blinks rapidly, "
        "then retry."
    ) from last_error


def open_and_probe(
    port: str,
    baud: int,
    checksum_mode: str,
    timeout_s: float,
    retry_seconds: float,
    verbose: bool,
) -> tuple[int, int, int, tuple[int, int, int], int]:
    deadline = time.monotonic() + max(0.0, retry_seconds)
    last_error: Exception | None = None

    while True:
        fd = -1
        try:
            fd = open_serial(port, baud)
            silicon_id, silicon_rev, version, mode = probe_bootloader(fd, checksum_mode, timeout_s, verbose)
            return fd, silicon_id, silicon_rev, version, mode
        except Exception as exc:
            last_error = exc
            if fd >= 0:
                os.close(fd)
            if time.monotonic() >= deadline:
                if isinstance(exc, BootloaderError):
                    raise exc
                if isinstance(exc, TimeoutError):
                    raise exc
                raise BootloaderError(str(exc)) from exc
            time.sleep(0.25)


def iter_program_chunks(data: bytes) -> tuple[list[bytes], bytes]:
    buffered: list[bytes] = []
    pos = 0
    while len(data) - pos > PROGRAM_ROW_DATA_MAX:
        chunk_len = min(PACKET_DATA_MAX, len(data) - pos - PROGRAM_ROW_DATA_MAX)
        buffered.append(data[pos : pos + chunk_len])
        pos += chunk_len
    return buffered, data[pos:]


def do_probe(args: argparse.Namespace) -> int:
    fd, silicon_id, silicon_rev, version, mode = open_and_probe(
        args.port,
        args.baud,
        args.checksum,
        args.timeout,
        args.retry_seconds,
        args.verbose,
    )
    try:
        pass
    finally:
        os.close(fd)

    print("Bootloader detected:")
    print(f"  port: {args.port}")
    print(f"  baud: {args.baud}")
    print(f"  packet checksum: {packet_checksum_name(mode)}")
    print(f"  silicon id: 0x{silicon_id:08X}")
    print(f"  silicon rev: 0x{silicon_rev:02X}")
    print(f"  bootloader version: {version[0]}.{version[1]}.{version[2]}")
    return 0


def do_upload(args: argparse.Namespace) -> int:
    image = parse_cyacd(args.image)
    fd, silicon_id, silicon_rev, version, detected_checksum = open_and_probe(
        args.port,
        args.baud,
        args.checksum,
        args.timeout,
        args.retry_seconds,
        args.verbose,
    )
    try:
        checksum_type = image.packet_checksum_type if args.checksum == "auto" else detected_checksum
        if checksum_type not in (PACKET_CHECKSUM_SUM, PACKET_CHECKSUM_CRC16):
            raise BootloaderError(
                f"Unsupported packet checksum type in .cyacd header: {image.packet_checksum_type}"
            )

        if not args.force and silicon_id != image.silicon_id:
            raise BootloaderError(
                f"Silicon ID mismatch: target 0x{silicon_id:08X}, image 0x{image.silicon_id:08X}. "
                "Use --force to override."
            )
        if not args.force and silicon_rev != image.silicon_rev:
            raise BootloaderError(
                f"Silicon revision mismatch: target 0x{silicon_rev:02X}, image 0x{image.silicon_rev:02X}. "
                "Use --force to override."
            )

        if args.verbose:
            print(
                f"target silicon=0x{silicon_id:08X} rev=0x{silicon_rev:02X} "
                f"bootloader={version[0]}.{version[1]}.{version[2]}"
            )
            print(
                f"image silicon=0x{image.silicon_id:08X} rev=0x{image.silicon_rev:02X} "
                f"packet_checksum={packet_checksum_name(image.packet_checksum_type)} rows={len(image.rows)}"
            )

        arrays = sorted({row.array_id for row in image.rows})
        for array_id in arrays:
            status, data = send_command(
                fd,
                checksum_type,
                CMD_GET_FLASH_SIZE,
                bytes([array_id]),
                timeout_s=args.timeout,
                verbose=args.verbose,
            )
            require_success(status, f"Get Flash Size array 0x{array_id:02X}")
            if len(data) == 4 and args.verbose:
                first_row = int.from_bytes(data[0:2], "little")
                last_row = int.from_bytes(data[2:4], "little")
                print(f"array 0x{array_id:02X}: rows {first_row}..{last_row}")

        programmed = 0
        for row in image.rows:
            buffered, final_chunk = iter_program_chunks(row.data)
            for chunk in buffered:
                status, _ = send_command(
                    fd,
                    checksum_type,
                    CMD_SEND_DATA,
                    chunk,
                    timeout_s=args.timeout,
                    verbose=args.verbose,
                )
                require_success(status, f"Send Data row {row.row_number}")

            payload = bytes([row.array_id]) + row.row_number.to_bytes(2, "little") + final_chunk
            status, _ = send_command(
                fd,
                checksum_type,
                CMD_PROGRAM_ROW,
                payload,
                timeout_s=max(args.timeout, 2.0),
                verbose=args.verbose,
            )
            require_success(status, f"Program Row array 0x{row.array_id:02X} row {row.row_number}")

            status, verify_data = send_command(
                fd,
                checksum_type,
                CMD_VERIFY_ROW,
                bytes([row.array_id]) + row.row_number.to_bytes(2, "little"),
                timeout_s=args.timeout,
                verbose=args.verbose,
            )
            require_success(status, f"Verify Row array 0x{row.array_id:02X} row {row.row_number}")
            if len(verify_data) != 1:
                raise BootloaderError(
                    f"Verify Row returned {len(verify_data)} bytes for array 0x{row.array_id:02X} row {row.row_number}"
                )
            if verify_data[0] != row.row_checksum:
                raise BootloaderError(
                    f"Verify Row checksum mismatch for array 0x{row.array_id:02X} row {row.row_number}: "
                    f"target 0x{verify_data[0]:02X}, image 0x{row.row_checksum:02X}"
                )

            programmed += 1
            if args.verbose or programmed % 16 == 0 or programmed == len(image.rows):
                print(f"programmed {programmed}/{len(image.rows)} rows")

        status, verify_data = send_command(
            fd,
            checksum_type,
            CMD_VERIFY_CHECKSUM,
            b"",
            timeout_s=args.timeout,
            verbose=args.verbose,
        )
        require_success(status, "Verify Checksum")
        if len(verify_data) != 1:
            raise BootloaderError(f"Verify Checksum returned {len(verify_data)} bytes")
        if verify_data[0] == 0:
            raise BootloaderError("Target reported an invalid application checksum after programming")

        send_command(
            fd,
            checksum_type,
            CMD_EXIT_BOOTLOADER,
            b"",
            timeout_s=0.1,
            expect_response=False,
            verbose=args.verbose,
        )
    finally:
        os.close(fd)

    print("Upload complete:")
    print(f"  image: {args.image}")
    print(f"  port: {args.port}")
    print(f"  rows: {len(image.rows)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Probe or program the CY8CKIT-049-42xx UART bootloader")
    subparsers = parser.add_subparsers(dest="command", required=True)

    probe = subparsers.add_parser("probe", help="probe the UART bootloader on a serial port")
    probe.add_argument("--port", default="/dev/ttyACM2", help="serial port (default: /dev/ttyACM2)")
    probe.add_argument("--baud", type=int, default=115200, help="baud rate (default: 115200)")
    probe.add_argument(
        "--checksum",
        choices=["auto", "sum", "crc16"],
        default="auto",
        help="packet checksum mode to try (default: auto)",
    )
    probe.add_argument("--timeout", type=float, default=1.0, help="response timeout in seconds (default: 1.0)")
    probe.add_argument(
        "--retry-seconds",
        type=float,
        default=0.0,
        help="keep retrying until the bootloader responds or this timeout expires (default: 0)",
    )
    probe.add_argument("--verbose", action="store_true", help="print packet-level debugging information")
    probe.set_defaults(func=do_probe)

    upload = subparsers.add_parser("upload", help="upload a .cyacd image over the UART bootloader")
    upload.add_argument("image", type=pathlib.Path, help="path to the .cyacd image")
    upload.add_argument("--port", default="/dev/ttyACM2", help="serial port (default: /dev/ttyACM2)")
    upload.add_argument("--baud", type=int, default=115200, help="baud rate (default: 115200)")
    upload.add_argument(
        "--checksum",
        choices=["auto", "sum", "crc16"],
        default="auto",
        help="packet checksum mode override (default: auto)",
    )
    upload.add_argument("--timeout", type=float, default=1.0, help="response timeout in seconds (default: 1.0)")
    upload.add_argument(
        "--retry-seconds",
        type=float,
        default=0.0,
        help="keep retrying for bootloader entry until this timeout expires (default: 0)",
    )
    upload.add_argument("--force", action="store_true", help="allow upload despite silicon ID/revision mismatch")
    upload.add_argument("--verbose", action="store_true", help="print packet-level debugging information")
    upload.set_defaults(func=do_upload)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except BootloaderError as exc:
        eprint(str(exc))
        return 1
    except TimeoutError as exc:
        eprint(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
