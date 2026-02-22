#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import subprocess
import tempfile


ROOT = pathlib.Path(__file__).resolve().parent.parent


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, cwd=ROOT)


def test_vm_asm_basic() -> None:
    src = "PUSH8 1\nPUSH8 2\nADD\nHALT\n"
    with tempfile.TemporaryDirectory() as td:
        tdp = pathlib.Path(td)
        asm = tdp / "t.vm"
        out = tdp / "t.bin"
        asm.write_text(src, encoding="utf-8")
        run(["./tools/vm_asm.py", str(asm), "-o", str(out)])
        got = out.read_bytes()
        exp = bytes([0x01, 0x01, 0x01, 0x02, 0x02, 0xFF])
        if got != exp:
            raise AssertionError(f"vm_asm mismatch: got {got.hex()} exp {exp.hex()}")


def test_vm_cc_while_if() -> None:
    src = """
const int N = 3;
int i = 0;
while (i < N) {
  if (i == 1) { print_u32(99); } else { print_u32(i); }
  i = i + 1;
}
"""
    with tempfile.TemporaryDirectory() as td:
        tdp = pathlib.Path(td)
        cvm = tdp / "t.cvm.c"
        asm = tdp / "t.vm"
        out = tdp / "t.bin"
        cvm.write_text(src, encoding="utf-8")
        run(["./tools/vm_cc.py", str(cvm), "-S", str(asm), "-o", str(out)])
        text = asm.read_text(encoding="utf-8")
        for marker in ("LSET", "LGET", "LT", "EQ", "JZ", "HOST 2"):
            if marker not in text:
                raise AssertionError(f"expected marker {marker!r} in generated asm")
        if len(out.read_bytes()) == 0:
            raise AssertionError("compiler produced empty binary")


def main() -> int:
    test_vm_asm_basic()
    test_vm_cc_while_if()
    print("vm tool tests: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
