"""
Host-side tiny_vm bytecode simulator.

Byte-for-byte equivalent to common/src/tiny_vm.c. The C runtime is the spec;
any divergence is a sim bug. See common/include/tiny_vm.h for the canonical
constants, opcode IDs, and status codes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol


# Constants — must match common/include/tiny_vm.h
TINY_VM_STACK_MAX = 16
TINY_VM_CODE_MAX = 512
TINY_VM_LOCALS_MAX = 16
TINY_VM_MEM_MAX = 128

# Status codes — must match tiny_vm_status_t in common/include/tiny_vm.h
TINY_VM_OK = 0
TINY_VM_HALT = 1
TINY_VM_STEP_LIMIT = 2
TINY_VM_ERR_PC_OOB = -1
TINY_VM_ERR_STACK_OVERFLOW = -2
TINY_VM_ERR_STACK_UNDERFLOW = -3
TINY_VM_ERR_BAD_OPCODE = -4
TINY_VM_ERR_HOST = -5
TINY_VM_ERR_CODE_TOO_LARGE = -6
TINY_VM_ERR_MEM_OOB = -7

# Opcodes — must match tiny_vm_opcode_t in common/include/tiny_vm.h
OP_NOP = 0x00
OP_PUSH8 = 0x01
OP_ADD = 0x02
OP_SUB = 0x03
OP_DUP = 0x04
OP_DROP = 0x05
OP_SWAP = 0x06
OP_JMP = 0x07
OP_JZ = 0x08
OP_HOST = 0x09
OP_LGET = 0x0A
OP_LSET = 0x0B
OP_EQ = 0x0C
OP_LT = 0x0D
OP_PUSH16 = 0x0E
OP_MOD = 0x0F
OP_MUL = 0x10
OP_DIV = 0x11
OP_MGET = 0x12
OP_MSET = 0x13
OP_PUSH32 = 0x14
OP_AND = 0x15
OP_OR = 0x16
OP_XOR = 0x17
OP_NOT = 0x18
OP_SHL = 0x19
OP_SHR = 0x1A
OP_ROL = 0x1B
OP_ROR = 0x1C
OP_MGET32 = 0x1D
OP_MSET32 = 0x1E
OP_HALT = 0xFF

MASK32 = 0xFFFFFFFF


def to_int32(v: int) -> int:
    """Truncate to 32-bit signed two's complement."""
    v &= MASK32
    if v >= 0x80000000:
        v -= 0x100000000
    return v


def to_uint32(v: int) -> int:
    return v & MASK32


def c_div(a: int, b: int) -> int:
    """C signed integer division: truncated towards zero."""
    q = abs(a) // abs(b)
    if (a < 0) != (b < 0):
        q = -q
    return q


def c_mod(a: int, b: int) -> int:
    """C signed modulo: sign of dividend, matching trunc-towards-zero division."""
    return a - c_div(a, b) * b


class StatusError(Exception):
    """Raised on a non-OK, non-HALT, non-STEP_LIMIT status from step()."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


STATUS_NAMES = {
    TINY_VM_OK: "OK",
    TINY_VM_HALT: "HALT",
    TINY_VM_STEP_LIMIT: "STEP_LIMIT",
    TINY_VM_ERR_PC_OOB: "ERR_PC_OOB",
    TINY_VM_ERR_STACK_OVERFLOW: "ERR_STACK_OVERFLOW",
    TINY_VM_ERR_STACK_UNDERFLOW: "ERR_STACK_UNDERFLOW",
    TINY_VM_ERR_BAD_OPCODE: "ERR_BAD_OPCODE",
    TINY_VM_ERR_HOST: "ERR_HOST",
    TINY_VM_ERR_CODE_TOO_LARGE: "ERR_CODE_TOO_LARGE",
    TINY_VM_ERR_MEM_OOB: "ERR_MEM_OOB",
}


def status_name(code: int) -> str:
    return STATUS_NAMES.get(code, f"UNKNOWN({code})")


class HostCalls(Protocol):
    """Protocol for host services exposed to a running program.

    Implementations get the live TinyVmSim so they can pop their arguments
    off the stack exactly like the C-runtime host_call dispatcher does.
    Return value mirrors the C convention: 0 on success, < 0 on failure.
    """

    def call(self, vm: "TinyVmSim", host_id: int) -> int:
        ...


@dataclass
class StepResult:
    status: int
    op: int
    pc_before: int
    pc_after: int


class TinyVmSim:
    """Python port of common/src/tiny_vm.c."""

    def __init__(
        self,
        bytecode: bytes | bytearray,
        *,
        host: HostCalls | None = None,
        code_max: int = TINY_VM_CODE_MAX,
        mem_max: int = TINY_VM_MEM_MAX,
        stack_max: int = TINY_VM_STACK_MAX,
        locals_max: int = TINY_VM_LOCALS_MAX,
    ) -> None:
        if len(bytecode) > code_max:
            raise StatusError(
                TINY_VM_ERR_CODE_TOO_LARGE,
                f"bytecode {len(bytecode)} bytes exceeds TINY_VM_CODE_MAX={code_max}",
            )
        self._code_max = code_max
        self._mem_max = mem_max
        self._stack_max = stack_max
        self._locals_max = locals_max
        self.code = bytearray(bytecode)
        self.code_len = len(bytecode)
        self.pc = 0
        self.stack: list[int] = []
        self.locals: list[int] = [0] * locals_max
        self.mem = bytearray(mem_max)
        self.host: HostCalls | None = host
        self._trace_listeners: list[Callable[[StepResult], None]] = []
        self.halted = False
        self.last_status = TINY_VM_OK

    # ---- public state ----

    @property
    def sp(self) -> int:
        return len(self.stack)

    @property
    def memory(self) -> bytes:
        return bytes(self.mem)

    def attach_host(self, host: HostCalls) -> None:
        self.host = host

    def add_trace_listener(self, fn: Callable[[StepResult], None]) -> None:
        self._trace_listeners.append(fn)

    # ---- primitives ----

    def push(self, v: int) -> None:
        if self.sp >= self._stack_max:
            raise StatusError(TINY_VM_ERR_STACK_OVERFLOW, "stack overflow")
        self.stack.append(to_int32(v))

    def pop(self) -> int:
        if not self.stack:
            raise StatusError(TINY_VM_ERR_STACK_UNDERFLOW, "stack underflow")
        return self.stack.pop()

    def _read_u8(self) -> int:
        if self.pc >= self.code_len:
            raise StatusError(TINY_VM_ERR_PC_OOB, "pc out of bounds reading u8")
        v = self.code[self.pc]
        self.pc += 1
        return v

    def _read_u16_le(self) -> int:
        lo = self._read_u8()
        hi = self._read_u8()
        return (hi << 8) | lo

    def _read_i16_le(self) -> int:
        v = self._read_u16_le()
        if v >= 0x8000:
            v -= 0x10000
        return v

    def _read_i32_le(self) -> int:
        b0 = self._read_u8()
        b1 = self._read_u8()
        b2 = self._read_u8()
        b3 = self._read_u8()
        u = (b3 << 24) | (b2 << 16) | (b1 << 8) | b0
        if u >= 0x80000000:
            u -= 0x100000000
        return u

    # ---- execution ----

    def step(self) -> StepResult:
        if self.halted:
            return StepResult(self.last_status, 0, self.pc, self.pc)
        pc_before = self.pc
        op = 0
        try:
            op = self._read_u8()
            self._execute(op)
            status = TINY_VM_OK
        except StatusError as e:
            self.halted = True
            self.last_status = e.status
            status = e.status
        result = StepResult(status, op, pc_before, self.pc)
        for fn in self._trace_listeners:
            fn(result)
        if status == TINY_VM_HALT:
            self.halted = True
            self.last_status = TINY_VM_HALT
        return result

    def run(self, step_budget: int | None = None) -> int:
        """Run until HALT or error. Returns final status. None = unlimited (still safe-capped)."""
        if step_budget is None:
            # safety cap so a runaway program in the sim does not hang the host
            step_budget = 10_000_000
        steps = 0
        while steps < step_budget and not self.halted:
            res = self.step()
            steps += 1
            if res.status != TINY_VM_OK:
                return res.status
        if self.halted:
            return self.last_status
        return TINY_VM_STEP_LIMIT

    def _execute(self, op: int) -> None:
        if op == OP_NOP:
            return
        if op == OP_PUSH8:
            v = self._read_u8()
            if v >= 0x80:
                v -= 0x100
            self.push(v)
            return
        if op == OP_PUSH16:
            self.push(self._read_i16_le())
            return
        if op == OP_PUSH32:
            self.push(self._read_i32_le())
            return
        if op == OP_ADD:
            b = self.pop()
            a = self.pop()
            self.push(to_int32(a + b))
            return
        if op == OP_SUB:
            b = self.pop()
            a = self.pop()
            self.push(to_int32(a - b))
            return
        if op == OP_DUP:
            if not self.stack:
                raise StatusError(TINY_VM_ERR_STACK_UNDERFLOW, "dup on empty stack")
            self.push(self.stack[-1])
            return
        if op == OP_DROP:
            self.pop()
            return
        if op == OP_SWAP:
            if len(self.stack) < 2:
                raise StatusError(TINY_VM_ERR_STACK_UNDERFLOW, "swap needs 2 items")
            self.stack[-1], self.stack[-2] = self.stack[-2], self.stack[-1]
            return
        if op == OP_JMP:
            target = self._read_u16_le()
            if target >= self.code_len:
                raise StatusError(TINY_VM_ERR_PC_OOB, f"jmp target {target} out of bounds")
            self.pc = target
            return
        if op == OP_JZ:
            target = self._read_u16_le()
            cond = self.pop()
            if cond == 0:
                if target >= self.code_len:
                    raise StatusError(TINY_VM_ERR_PC_OOB, f"jz target {target} out of bounds")
                self.pc = target
            return
        if op == OP_HOST:
            host_id = self._read_u8()
            if self.host is None:
                raise StatusError(TINY_VM_ERR_HOST, f"host call {host_id} with no host attached")
            rc = self.host.call(self, host_id)
            if rc < 0:
                raise StatusError(TINY_VM_ERR_HOST, f"host call {host_id} returned {rc}")
            return
        if op == OP_LGET:
            slot = self._read_u8()
            if slot >= self._locals_max:
                raise StatusError(TINY_VM_ERR_BAD_OPCODE, f"lget slot {slot} out of range")
            self.push(self.locals[slot])
            return
        if op == OP_LSET:
            slot = self._read_u8()
            if slot >= self._locals_max:
                raise StatusError(TINY_VM_ERR_BAD_OPCODE, f"lset slot {slot} out of range")
            self.locals[slot] = self.pop()
            return
        if op == OP_EQ:
            b = self.pop()
            a = self.pop()
            self.push(1 if a == b else 0)
            return
        if op == OP_LT:
            b = self.pop()
            a = self.pop()
            self.push(1 if a < b else 0)
            return
        if op == OP_MOD:
            b = self.pop()
            a = self.pop()
            if b == 0:
                raise StatusError(TINY_VM_ERR_HOST, "mod by zero")
            self.push(to_int32(c_mod(a, b)))
            return
        if op == OP_MUL:
            b = self.pop()
            a = self.pop()
            self.push(to_int32(a * b))
            return
        if op == OP_DIV:
            b = self.pop()
            a = self.pop()
            if b == 0:
                raise StatusError(TINY_VM_ERR_HOST, "div by zero")
            self.push(to_int32(c_div(a, b)))
            return
        if op == OP_MGET:
            idx = self.pop()
            if idx < 0 or idx >= self._mem_max:
                raise StatusError(TINY_VM_ERR_MEM_OOB, f"mget index {idx} out of range")
            self.push(self.mem[idx])
            return
        if op == OP_MSET:
            value = self.pop()
            idx = self.pop()
            if idx < 0 or idx >= self._mem_max:
                raise StatusError(TINY_VM_ERR_MEM_OOB, f"mset index {idx} out of range")
            self.mem[idx] = value & 0xFF
            return
        if op == OP_MGET32:
            idx = self.pop()
            if idx < 0 or idx > self._mem_max - 4:
                raise StatusError(TINY_VM_ERR_MEM_OOB, f"mget32 index {idx} out of range")
            v = (
                self.mem[idx]
                | (self.mem[idx + 1] << 8)
                | (self.mem[idx + 2] << 16)
                | (self.mem[idx + 3] << 24)
            )
            self.push(to_int32(v))
            return
        if op == OP_MSET32:
            value = self.pop()
            idx = self.pop()
            if idx < 0 or idx > self._mem_max - 4:
                raise StatusError(TINY_VM_ERR_MEM_OOB, f"mset32 index {idx} out of range")
            u = to_uint32(value)
            self.mem[idx] = u & 0xFF
            self.mem[idx + 1] = (u >> 8) & 0xFF
            self.mem[idx + 2] = (u >> 16) & 0xFF
            self.mem[idx + 3] = (u >> 24) & 0xFF
            return
        if op == OP_AND:
            b = self.pop()
            a = self.pop()
            self.push(to_int32(to_uint32(a) & to_uint32(b)))
            return
        if op == OP_OR:
            b = self.pop()
            a = self.pop()
            self.push(to_int32(to_uint32(a) | to_uint32(b)))
            return
        if op == OP_XOR:
            b = self.pop()
            a = self.pop()
            self.push(to_int32(to_uint32(a) ^ to_uint32(b)))
            return
        if op == OP_NOT:
            a = self.pop()
            self.push(to_int32((~to_uint32(a)) & MASK32))
            return
        if op == OP_SHL:
            b = self.pop()
            a = self.pop()
            shift = to_uint32(b) & 31
            self.push(to_int32((to_uint32(a) << shift) & MASK32))
            return
        if op == OP_SHR:
            b = self.pop()
            a = self.pop()
            shift = to_uint32(b) & 31
            self.push(to_int32(to_uint32(a) >> shift))
            return
        if op == OP_ROL:
            b = self.pop()
            a = self.pop()
            shift = to_uint32(b) & 31
            ua = to_uint32(a)
            r = ua if shift == 0 else ((ua << shift) | (ua >> (32 - shift))) & MASK32
            self.push(to_int32(r))
            return
        if op == OP_ROR:
            b = self.pop()
            a = self.pop()
            shift = to_uint32(b) & 31
            ua = to_uint32(a)
            r = ua if shift == 0 else ((ua >> shift) | (ua << (32 - shift))) & MASK32
            self.push(to_int32(r))
            return
        if op == OP_HALT:
            raise StatusError(TINY_VM_HALT, "halt")
        raise StatusError(TINY_VM_ERR_BAD_OPCODE, f"bad opcode 0x{op:02x}")
