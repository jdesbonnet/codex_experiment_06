#!/usr/bin/env python3
"""
Generate a tiny_vm single-block SHA-1 regression program for a specific message.

This avoids changing the VM upload/runtime contract for now. The generated program:
- writes the fully padded 64-byte block into scratch memory
- runs the existing single-block SHA-1 compression logic
- prints the five 32-bit digest words as uppercase hex

Current limitation:
- `tiny_vm_load()` clears scratch memory on image load
- so a truly generic "load block externally, then run generic SHA-1 bytecode" path
  requires a future protocol/runtime change
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import sys


PROLOGUE = """/* SHA-1 single-block regression over a fixed message.
 * Reference: FIPS PUB 180-4, Secure Hash Standard (SHS), SHA-1.
 * Message: {message_repr}
 * Expected output:
{expected_lines}
 */

const int K0 = 0x5A827999;
const int K1 = 0x6ED9EBA1;
const int K2 = 0x8F1BBCDC;
const int K3 = 0xCA62C1D6;

const int H0_INIT = 0x67452301;
const int H1_INIT = 0xEFCDAB89;
const int H2_INIT = 0x98BADCFE;
const int H3_INIT = 0x10325476;
const int H4_INIT = 0xC3D2E1F0;

int i = 0;
int h0 = 0;
int h1 = 0;
int h2 = 0;
int h3 = 0;
int h4 = 0;
int a = 0;
int b = 0;
int c = 0;
int d = 0;
int e = 0;
int w = 0;
int f = 0;
int k = 0;
int s = 0;
int temp = 0;
"""

BLOCK_INIT = """
store32le({offset}, 0x{word:08X});
"""

ZERO_BLOCK = """
while (i < 64) {
    store32le(i, 0);
    i = i + 4;
}
"""

CORE = """
h0 = H0_INIT;
h1 = H1_INIT;
h2 = H2_INIT;
h3 = H3_INIT;
h4 = H4_INIT;

a = h0;
b = h1;
c = h2;
d = h3;
e = h4;

i = 0;
while (i < 80) {
    if (i < 16) {
        s = load32le(i * 4);
    } else {
        s = xor32(load32le(((i - 3) % 16) * 4), load32le(((i - 8) % 16) * 4));
        s = xor32(s, load32le(((i - 14) % 16) * 4));
        s = xor32(s, load32le(((i - 16) % 16) * 4));
        s = rol32(s, 1);
        store32le((i % 16) * 4, s);
    }

    w = s;

    if (i < 20) {
        f = or32(and32(b, c), and32(not32(b), d));
        k = K0;
    } else {
        if (i < 40) {
            f = xor32(xor32(b, c), d);
            k = K1;
        } else {
            if (i < 60) {
                f = or32(or32(and32(b, c), and32(b, d)), and32(c, d));
                k = K2;
            } else {
                f = xor32(xor32(b, c), d);
                k = K3;
            }
        }
    }

    temp = rol32(a, 5) + f;
    temp = temp + e;
    temp = temp + w;
    temp = temp + k;

    e = d;
    d = c;
    c = rol32(b, 30);
    b = a;
    a = temp;

    i = i + 1;
}

h0 = h0 + a;
h1 = h1 + b;
h2 = h2 + c;
h3 = h3 + d;
h4 = h4 + e;

print_hex32(h0);
print_hex32(h1);
print_hex32(h2);
print_hex32(h3);
print_hex32(h4);
"""


def build_single_block(message: bytes) -> bytes:
    if len(message) > 55:
        raise ValueError("message too long for single-block SHA-1 (max 55 bytes)")
    block = bytearray(64)
    block[0 : len(message)] = message
    block[len(message)] = 0x80
    bit_len = len(message) * 8
    block[56:64] = bit_len.to_bytes(8, "big")
    return bytes(block)


def block_to_sha1_words(block: bytes) -> list[int]:
    words: list[int] = []
    for offset in range(0, 64, 4):
        words.append(int.from_bytes(block[offset : offset + 4], "big"))
    return words


def format_expected_lines(digest_hex: str) -> str:
    lines = []
    for i in range(0, 40, 8):
        lines.append(f" *   {digest_hex[i:i+8]}")
    return "\n".join(lines)


def generate_source(message: bytes) -> str:
    digest_hex = hashlib.sha1(message).hexdigest().upper()
    block = build_single_block(message)
    words = block_to_sha1_words(block)
    parts: list[str] = [
        PROLOGUE.format(
            message_repr=repr(message.decode("utf-8", errors="backslashreplace")),
            expected_lines=format_expected_lines(digest_hex),
        )
    ]
    parts.append(ZERO_BLOCK)
    for index, word in enumerate(words):
        if word != 0:
            parts.append(BLOCK_INIT.format(offset=index * 4, word=word))
    parts.append(CORE)
    return "".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a tiny_vm single-block SHA-1 test case")
    parser.add_argument("message", help="ASCII/UTF-8 message, max 55 bytes")
    parser.add_argument("-o", "--output", type=pathlib.Path, help="output .cvm.c path")
    args = parser.parse_args()

    message = args.message.encode("utf-8")
    try:
        src = generate_source(message)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.output:
        args.output.write_text(src, encoding="utf-8")
    else:
        sys.stdout.write(src)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
