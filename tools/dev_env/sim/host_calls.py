"""
Default mocked host services for the tiny_vm simulator.

These IDs match the firmware dispatch in
projects/tiny_vm/lpc1114_c/main.c::vm_host_call (and the same enum in the
other per-target main.c files):

    0  HOST_LED_WRITE         - pop value, latch LED state
    1  HOST_DELAY_MS          - pop ms, advance virtual time
    2  HOST_UART_PRINTLN_U32  - pop value, emit signed decimal + newline
    3  HOST_UART_PRINTLN_HEX32 - pop value, emit 8 uppercase hex + newline

The mocks never touch real I/O; they record into a HostLog the IDE and tests
can inspect.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING


HOST_LED_WRITE = 0
HOST_DELAY_MS = 1
HOST_UART_PRINTLN_U32 = 2
HOST_UART_PRINTLN_HEX32 = 3


if TYPE_CHECKING:  # avoid circular import at runtime
    from .tiny_vm_sim import TinyVmSim


@dataclass
class LogEntry:
    virtual_time_ms: int
    host_id: int
    name: str
    value: int | None = None


@dataclass
class HostLog:
    entries: list[LogEntry] = field(default_factory=list)
    stdout: list[str] = field(default_factory=list)
    led_state: int = 0
    virtual_time_ms: int = 0

    def record(self, host_id: int, name: str, value: int | None) -> None:
        self.entries.append(
            LogEntry(self.virtual_time_ms, host_id, name, value)
        )

    @property
    def stdout_text(self) -> str:
        return "".join(self.stdout)


class DefaultHostCalls:
    """Mocked host services. Implements the HostCalls protocol."""

    def __init__(self, log: HostLog | None = None) -> None:
        self.log = log if log is not None else HostLog()

    def call(self, vm: "TinyVmSim", host_id: int) -> int:
        if host_id == HOST_LED_WRITE:
            v = vm.pop()
            self.log.led_state = 1 if v != 0 else 0
            self.log.record(host_id, "led_write", v)
            return 0
        if host_id == HOST_DELAY_MS:
            v = vm.pop()
            if v < 0:
                v = 0
            self.log.virtual_time_ms += int(v)
            self.log.record(host_id, "delay_ms", v)
            return 0
        if host_id == HOST_UART_PRINTLN_U32:
            v = vm.pop()
            text = f"{v}\n"
            self.log.stdout.append(text)
            self.log.record(host_id, "print_u32", v)
            return 0
        if host_id == HOST_UART_PRINTLN_HEX32:
            v = vm.pop()
            text = f"{v & 0xFFFFFFFF:08X}\n"
            self.log.stdout.append(text)
            self.log.record(host_id, "print_hex32", v)
            return 0
        # Unknown host id: log it and report failure (matches firmware default branch).
        self.log.record(host_id, f"host_{host_id}", None)
        return -1
