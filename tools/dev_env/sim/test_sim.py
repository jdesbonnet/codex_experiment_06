#!/usr/bin/env python3
"""
Unit + regression tests for the host-side tiny_vm simulator.

Strategy:
  - Compile every .cvm.c under projects/tiny_vm/tests/ with vm_cc.py.
  - Run each .bin through the sim with DefaultHostCalls.
  - Compare emitted stdout against the same expected_lines() that the
    on-hardware regression suite uses (tools/test_tiny_vm_hardware.py).
  - Also unit-test individual opcodes via tiny hand-assembled byte sequences.

Run:
    python3 tools/dev_env/sim/test_sim.py
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile


def _ensure_package_on_path() -> None:
    here = pathlib.Path(__file__).resolve().parent
    sys.path.insert(0, str(here.parent))


_ensure_package_on_path()

from sim.host_calls import DefaultHostCalls, HostLog  # noqa: E402
from sim.sourcemap import load as load_sourcemap  # noqa: E402
from sim.tiny_vm_sim import (  # noqa: E402
    TinyVmSim,
    TINY_VM_HALT,
    TINY_VM_ERR_STACK_OVERFLOW,
    TINY_VM_ERR_STACK_UNDERFLOW,
    TINY_VM_ERR_MEM_OOB,
    TINY_VM_ERR_BAD_OPCODE,
    OP_PUSH8,
    OP_PUSH16,
    OP_PUSH32,
    OP_ADD,
    OP_SUB,
    OP_MUL,
    OP_DIV,
    OP_MOD,
    OP_AND,
    OP_OR,
    OP_XOR,
    OP_NOT,
    OP_SHL,
    OP_SHR,
    OP_ROL,
    OP_ROR,
    OP_MGET,
    OP_MSET,
    OP_MGET32,
    OP_MSET32,
    OP_LGET,
    OP_LSET,
    OP_DUP,
    OP_DROP,
    OP_SWAP,
    OP_JMP,
    OP_JZ,
    OP_EQ,
    OP_LT,
    OP_HOST,
    OP_HALT,
)


ROOT = pathlib.Path(__file__).resolve().parents[3]


# ---- helpers ----------------------------------------------------------------


def _compile(src_path: pathlib.Path, out_path: pathlib.Path, *, with_map: bool = False) -> None:
    cmd = ["./tools/vm_cc.py", str(src_path), "-o", str(out_path)]
    if with_map:
        cmd.append("--map")
    subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True)


def _run(code: bytes) -> tuple[int, HostLog]:
    log = HostLog()
    vm = TinyVmSim(code, host=DefaultHostCalls(log))
    status = vm.run()
    return status, log


def _expect_halt(status: int) -> None:
    if status != TINY_VM_HALT:
        raise AssertionError(f"expected HALT, got status={status}")


# ---- unit tests on hand-built bytecode --------------------------------------


def test_push8_arith() -> None:
    code = bytes([OP_PUSH8, 5, OP_PUSH8, 3, OP_ADD, OP_HALT])
    vm = TinyVmSim(code)
    _expect_halt(vm.run())
    if vm.stack != [8]:
        raise AssertionError(f"expected [8], got {vm.stack}")


def test_push8_negative() -> None:
    code = bytes([OP_PUSH8, 0xFF, OP_HALT])  # -1 signed
    vm = TinyVmSim(code)
    _expect_halt(vm.run())
    if vm.stack != [-1]:
        raise AssertionError(f"expected [-1], got {vm.stack}")


def test_push16_le() -> None:
    code = bytes([OP_PUSH16, 0x2C, 0x01, OP_HALT])  # 300
    vm = TinyVmSim(code)
    _expect_halt(vm.run())
    if vm.stack != [300]:
        raise AssertionError(f"expected [300], got {vm.stack}")


def test_push32_le_negative() -> None:
    code = bytes([OP_PUSH32, 0xFF, 0xFF, 0xFF, 0xFF, OP_HALT])  # -1
    vm = TinyVmSim(code)
    _expect_halt(vm.run())
    if vm.stack != [-1]:
        raise AssertionError(f"expected [-1], got {vm.stack}")


def test_div_mod_signed() -> None:
    # C trunc-towards-zero: -7 / 2 = -3, -7 % 2 = -1
    code = bytes([OP_PUSH8, 0xF9, OP_PUSH8, 2, OP_DIV, OP_HALT])  # -7 / 2
    vm = TinyVmSim(code)
    _expect_halt(vm.run())
    if vm.stack != [-3]:
        raise AssertionError(f"DIV: expected [-3], got {vm.stack}")

    code = bytes([OP_PUSH8, 0xF9, OP_PUSH8, 2, OP_MOD, OP_HALT])  # -7 % 2
    vm = TinyVmSim(code)
    _expect_halt(vm.run())
    if vm.stack != [-1]:
        raise AssertionError(f"MOD: expected [-1], got {vm.stack}")


def test_div_by_zero_is_host_err() -> None:
    code = bytes([OP_PUSH8, 1, OP_PUSH8, 0, OP_DIV, OP_HALT])
    vm = TinyVmSim(code)
    status = vm.run()
    if status >= 0:
        raise AssertionError(f"expected error on div by zero, got status={status}")


def test_bitwise_and_shifts() -> None:
    # 0xAAAAAAAA & 0x0000FFFF
    code = bytes(
        [
            OP_PUSH32, 0xAA, 0xAA, 0xAA, 0xAA,
            OP_PUSH32, 0xFF, 0xFF, 0x00, 0x00,
            OP_AND,
            OP_HALT,
        ]
    )
    vm = TinyVmSim(code)
    _expect_halt(vm.run())
    if vm.stack != [0x0000AAAA]:
        raise AssertionError(f"AND: expected [0xAAAA], got {[hex(x) for x in vm.stack]}")

    # SHL by 4 of 0x0FFFFFFF -> 0xFFFFFFF0 (as int32 = -16)
    code = bytes(
        [
            OP_PUSH32, 0xFF, 0xFF, 0xFF, 0x0F,
            OP_PUSH8, 4,
            OP_SHL,
            OP_HALT,
        ]
    )
    vm = TinyVmSim(code)
    _expect_halt(vm.run())
    if vm.stack != [-16]:
        raise AssertionError(f"SHL: expected [-16], got {vm.stack}")


def test_rotates() -> None:
    # ROL 0x12345678 by 8 -> 0x34567812
    code = bytes(
        [
            OP_PUSH32, 0x78, 0x56, 0x34, 0x12,
            OP_PUSH8, 8,
            OP_ROL,
            OP_HALT,
        ]
    )
    vm = TinyVmSim(code)
    _expect_halt(vm.run())
    if vm.stack != [0x34567812]:
        raise AssertionError(f"ROL: expected [0x34567812], got {[hex(x) for x in vm.stack]}")


def test_memory_byte_and_word() -> None:
    # store32le(4, 0x12345678); push load32le(4)
    code = bytes(
        [
            OP_PUSH8, 4,
            OP_PUSH32, 0x78, 0x56, 0x34, 0x12,
            OP_MSET32,
            OP_PUSH8, 4,
            OP_MGET32,
            OP_HALT,
        ]
    )
    vm = TinyVmSim(code)
    _expect_halt(vm.run())
    if vm.stack != [0x12345678]:
        raise AssertionError(f"MGET32: expected [0x12345678], got {[hex(x) for x in vm.stack]}")
    if list(vm.mem[4:8]) != [0x78, 0x56, 0x34, 0x12]:
        raise AssertionError(f"unexpected bytes in mem: {list(vm.mem[4:8])}")


def test_stack_overflow_detected() -> None:
    # 17 pushes overflow stack of 16
    code = bytes([OP_PUSH8, 1] * 17 + [OP_HALT])
    vm = TinyVmSim(code)
    status = vm.run()
    if status != TINY_VM_ERR_STACK_OVERFLOW:
        raise AssertionError(f"expected stack overflow, got {status}")


def test_stack_underflow_detected() -> None:
    code = bytes([OP_DROP, OP_HALT])
    vm = TinyVmSim(code)
    status = vm.run()
    if status != TINY_VM_ERR_STACK_UNDERFLOW:
        raise AssertionError(f"expected stack underflow, got {status}")


def test_mem_oob_detected() -> None:
    code = bytes([OP_PUSH8, 127, OP_MGET32, OP_HALT])  # 127 > 128 - 4
    vm = TinyVmSim(code)
    status = vm.run()
    if status != TINY_VM_ERR_MEM_OOB:
        raise AssertionError(f"expected mem OOB, got {status}")


def test_bad_opcode_detected() -> None:
    code = bytes([0x7F, OP_HALT])  # 0x7F is undefined
    vm = TinyVmSim(code)
    status = vm.run()
    if status != TINY_VM_ERR_BAD_OPCODE:
        raise AssertionError(f"expected bad opcode, got {status}")


def test_step_trace_listener() -> None:
    code = bytes([OP_PUSH8, 1, OP_PUSH8, 2, OP_ADD, OP_HALT])
    traced: list[int] = []
    vm = TinyVmSim(code)
    vm.add_trace_listener(lambda r: traced.append(r.op))
    _expect_halt(vm.run())
    if traced != [OP_PUSH8, OP_PUSH8, OP_ADD, OP_HALT]:
        raise AssertionError(f"unexpected trace: {traced}")


# ---- regression: every existing .cvm.c test program -------------------------


_EXPECTED: dict[str, list[str]] = {
    "count10": [str(i) for i in range(1, 11)],
    "collatz_max": ["97", "118"],
    "checksum8": ["15"],
    "rotate32": ["34567812", "78123456"],
    "mem32": ["12345678", "A5A5A5A5"],
    "crc32": ["CBF43926"],
    "sha1_abc": ["A9993E36", "4706816A", "BA3E2571", "7850C26C", "9CD0D89D"],
}


def _primes_upto(limit: int) -> list[int]:
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


def test_existing_cvm_tests_match_hardware_expected_output() -> None:
    test_dir = ROOT / "projects" / "tiny_vm" / "tests"
    with tempfile.TemporaryDirectory() as td:
        tdp = pathlib.Path(td)
        for src in sorted(test_dir.glob("*.cvm.c")):
            name = src.name.removesuffix(".cvm.c")
            out = tdp / (name + ".bin")
            _compile(src, out)
            status, log = _run(out.read_bytes())
            if status != TINY_VM_HALT:
                raise AssertionError(f"{name}: sim did not halt cleanly: status={status}")
            got_lines = log.stdout_text.splitlines()
            if name == "primes1000":
                expected = [str(v) for v in _primes_upto(1000)]
            else:
                expected = _EXPECTED[name]
            if got_lines != expected:
                raise AssertionError(
                    f"{name}: sim output mismatch.\n"
                    f"  expected (first 8): {expected[:8]} ... ({len(expected)} lines)\n"
                    f"  got (first 8)     : {got_lines[:8]} ... ({len(got_lines)} lines)"
                )


# ---- source-map integration -------------------------------------------------


def test_sourcemap_pc_lookups() -> None:
    src = ROOT / "projects" / "tiny_vm" / "tests" / "count10.cvm.c"
    with tempfile.TemporaryDirectory() as td:
        tdp = pathlib.Path(td)
        out = tdp / "count10.bin"
        _compile(src, out, with_map=True)
        sm = load_sourcemap(str(out) + ".map")
        # PC 0 corresponds to first statement (line 1: int i = 1;)
        e0 = sm.entry_for_pc(0)
        if e0 is None or e0.line != 1:
            raise AssertionError(f"unexpected entry at pc 0: {e0}")
        # The local 'i' lives in slot 0
        if sm.name_for_local(0) != "i":
            raise AssertionError(f"expected local 'i' at slot 0, got {sm.name_for_local(0)}")
        # pc_for_line_at_or_after(99) returns None (past end)
        if sm.pc_for_line_at_or_after(99) is not None:
            raise AssertionError("expected None for line past end of source")


# ---- entrypoint -------------------------------------------------------------


def main() -> int:
    tests = [
        test_push8_arith,
        test_push8_negative,
        test_push16_le,
        test_push32_le_negative,
        test_div_mod_signed,
        test_div_by_zero_is_host_err,
        test_bitwise_and_shifts,
        test_rotates,
        test_memory_byte_and_word,
        test_stack_overflow_detected,
        test_stack_underflow_detected,
        test_mem_oob_detected,
        test_bad_opcode_detected,
        test_step_trace_listener,
        test_existing_cvm_tests_match_hardware_expected_output,
        test_sourcemap_pc_lookups,
    ]
    for fn in tests:
        fn()
        print(f"  ok   {fn.__name__}")
    print("sim tests: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
