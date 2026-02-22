#!/usr/bin/env python3
"""
tiny_vm bytecode assembler (v0).

Syntax:
  - comments start with '#'
  - labels: name:
  - instructions:
      NOP
      PUSH8 <int8>
      ADD | SUB | DUP | DROP | SWAP | HALT
      EQ | LT
      HOST <u8>
      LGET <u8>
      LSET <u8>
      JMP <label|u16>
      JZ <label|u16>
"""

from __future__ import annotations

import argparse
import pathlib
import re
import struct
import sys

OPCODES = {
    "NOP": 0x00,
    "PUSH8": 0x01,
    "ADD": 0x02,
    "SUB": 0x03,
    "DUP": 0x04,
    "DROP": 0x05,
    "SWAP": 0x06,
    "JMP": 0x07,
    "JZ": 0x08,
    "HOST": 0x09,
    "LGET": 0x0A,
    "LSET": 0x0B,
    "EQ": 0x0C,
    "LT": 0x0D,
    "HALT": 0xFF,
}

ONE_U8 = {"PUSH8", "HOST", "LGET", "LSET"}
ONE_U16 = {"JMP", "JZ"}


def parse_int(token: str) -> int:
    return int(token, 0)


def clean_line(line: str) -> str:
    return line.split("#", 1)[0].strip()


def tokenize(path: pathlib.Path) -> list[str]:
    tokens: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = clean_line(raw)
        if not line:
            continue
        tokens.append(line)
    return tokens


def first_pass(lines: list[str]) -> dict[str, int]:
    labels: dict[str, int] = {}
    pc = 0
    for line in lines:
        if line.endswith(":"):
            label = line[:-1].strip()
            if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", label):
                raise ValueError(f"invalid label '{label}'")
            if label in labels:
                raise ValueError(f"duplicate label '{label}'")
            labels[label] = pc
            continue

        parts = line.split()
        op = parts[0].upper()
        if op not in OPCODES:
            raise ValueError(f"unknown opcode '{op}'")

        pc += 1
        if op in ONE_U8:
            if len(parts) != 2:
                raise ValueError(f"{op} requires one operand")
            pc += 1
        elif op in ONE_U16:
            if len(parts) != 2:
                raise ValueError(f"{op} requires one operand")
            pc += 2
        elif len(parts) != 1:
            raise ValueError(f"{op} takes no operands")
    return labels


def second_pass(lines: list[str], labels: dict[str, int]) -> bytes:
    out = bytearray()
    for line in lines:
        if line.endswith(":"):
            continue

        parts = line.split()
        op = parts[0].upper()
        out.append(OPCODES[op])

        if op in ONE_U8:
            value = parse_int(parts[1])
            if op == "PUSH8":
                if value < -128 or value > 127:
                    raise ValueError(f"PUSH8 out of range: {value}")
                out.append(value & 0xFF)
            else:
                if value < 0 or value > 0xFF:
                    raise ValueError(f"{op} out of range: {value}")
                out.append(value)
        elif op in ONE_U16:
            target_token = parts[1]
            if target_token in labels:
                value = labels[target_token]
            else:
                value = parse_int(target_token)
            if value < 0 or value > 0xFFFF:
                raise ValueError(f"{op} target out of range: {value}")
            out.extend(struct.pack("<H", value))
    return bytes(out)


def main() -> int:
    parser = argparse.ArgumentParser(description="Assemble tiny_vm source to bytecode")
    parser.add_argument("input", type=pathlib.Path, help="input assembly file")
    parser.add_argument("-o", "--output", type=pathlib.Path, required=True, help="output .bin file")
    args = parser.parse_args()

    try:
        lines = tokenize(args.input)
        labels = first_pass(lines)
        code = second_pass(lines, labels)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    args.output.write_bytes(code)
    print(f"wrote {len(code)} bytes to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
