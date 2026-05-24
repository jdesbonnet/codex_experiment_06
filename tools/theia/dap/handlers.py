"""
DAP request handlers and backend abstraction for tiny_vm.

The DebugBackend protocol isolates the protocol layer from the underlying
execution engine. In v1 the only implementation is SimBackend, wrapping
TinyVmSim. A future HardwareBackend (talking to the existing
tools/web_debugger_backend OpenOCD service) will plug in here without
changing the DAP layer.
"""

from __future__ import annotations

import pathlib
import sys
import threading
from dataclasses import dataclass
from typing import Callable, Optional, Protocol

# Allow running as a script: make `from sim ...` import resolve.
_HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from sim.host_calls import DefaultHostCalls, HostLog  # noqa: E402
from sim.sourcemap import SourceMap, load as load_sourcemap  # noqa: E402
from sim.tiny_vm_sim import (  # noqa: E402
    TINY_VM_HALT,
    TINY_VM_OK,
    TinyVmSim,
    status_name,
)


@dataclass
class StopReason:
    reason: str        # "entry" | "breakpoint" | "step" | "exception" | "halt" | "paused"
    description: str = ""


class DebugBackend(Protocol):
    bytecode: bytes
    source_map: SourceMap | None
    host_log: HostLog

    def step(self) -> StopReason:
        """Execute one bytecode instruction, return resulting stop reason."""

    def cont(self, pause_flag: threading.Event | None = None) -> StopReason:
        """Run until breakpoint / halt / error, or until pause_flag is set."""

    def next_line(self, pause_flag: threading.Event | None = None) -> StopReason:
        """Step until current source line changes, or step-instruction stops."""

    def set_source_breakpoints(self, lines: list[int]) -> list[tuple[bool, int | None]]:
        """For each source line, return (verified, resolved_pc)."""

    def set_instruction_breakpoints(self, pcs: list[int]) -> list[bool]:
        """For each pc, return verified flag."""

    def pc(self) -> int: ...
    def halted(self) -> bool: ...
    def status(self) -> int: ...
    def stack_snapshot(self) -> list[int]: ...
    def locals_snapshot(self) -> list[int]: ...
    def memory_snapshot(self) -> bytes: ...


class SimBackend:
    """Sim-backed implementation of the DebugBackend protocol."""

    def __init__(
        self,
        bytecode: bytes,
        source_map: SourceMap | None,
        on_output: Callable[[str, str], None] | None = None,
    ) -> None:
        self.bytecode = bytecode
        self.source_map = source_map
        self.host_log = HostLog()
        self._on_output = on_output
        self._host_stdout_seen = 0
        self._log_entries_seen = 0
        self._wrapped_host = self._make_wrapped_host()
        self.vm = TinyVmSim(bytecode, host=self._wrapped_host)
        self.breakpoint_pcs: set[int] = set()
        self.instr_breakpoint_pcs: set[int] = set()

    def _make_wrapped_host(self) -> DefaultHostCalls:
        return DefaultHostCalls(self.host_log)

    # ---- output forwarding (called after each step) ----

    def _drain_output(self) -> None:
        if self._on_output is None:
            return
        new_text = "".join(self.host_log.stdout[self._host_stdout_seen :])
        if new_text:
            self._on_output("stdout", new_text)
            self._host_stdout_seen = len(self.host_log.stdout)
        new_entries = self.host_log.entries[self._log_entries_seen :]
        for entry in new_entries:
            if entry.name in ("led_write", "delay_ms"):
                self._on_output(
                    "host",
                    f"[t+{entry.virtual_time_ms}ms] {entry.name}({entry.value})\n",
                )
        self._log_entries_seen = len(self.host_log.entries)

    # ---- protocol methods ----

    def step(self) -> StopReason:
        if self.vm.halted:
            return StopReason("halt", status_name(self.vm.last_status))
        res = self.vm.step()
        self._drain_output()
        if self.vm.halted:
            if self.vm.last_status == TINY_VM_HALT:
                return StopReason("halt", "HALT")
            return StopReason("exception", status_name(self.vm.last_status))
        return StopReason("step", "")

    # Soft upper bound on instructions per continue/next call. Programs that
    # halt naturally are well under this; infinite loops will hit it and we
    # return a "paused" reason so the UI stays responsive and the user can
    # set a breakpoint or terminate.
    SOFT_STEP_CAP = 2_000_000

    def cont(self, pause_flag: threading.Event | None = None) -> StopReason:
        # Step past any breakpoint we are currently parked on so resuming from
        # a hit breakpoint actually makes progress.
        first = True
        steps = 0
        while not self.vm.halted:
            if pause_flag is not None and pause_flag.is_set():
                return StopReason("pause", "paused")
            if not first and (
                self.vm.pc in self.breakpoint_pcs or self.vm.pc in self.instr_breakpoint_pcs
            ):
                return StopReason("breakpoint", f"pc=0x{self.vm.pc:04x}")
            self.vm.step()
            self._drain_output()
            first = False
            steps += 1
            if steps >= self.SOFT_STEP_CAP:
                return StopReason(
                    "pause",
                    f"soft step cap {self.SOFT_STEP_CAP} reached; resume to keep running",
                )
            if self.vm.halted:
                break
        if self.vm.last_status == TINY_VM_HALT:
            return StopReason("halt", "HALT")
        return StopReason("exception", status_name(self.vm.last_status))

    def next_line(self, pause_flag: threading.Event | None = None) -> StopReason:
        if self.source_map is None:
            return self.step()
        start_entry = self.source_map.entry_for_pc(self.vm.pc)
        start_line = start_entry.line if start_entry else None
        steps = 0
        while not self.vm.halted:
            if pause_flag is not None and pause_flag.is_set():
                return StopReason("pause", "paused")
            self.vm.step()
            self._drain_output()
            steps += 1
            if self.vm.halted:
                break
            if self.vm.pc in self.breakpoint_pcs or self.vm.pc in self.instr_breakpoint_pcs:
                return StopReason("breakpoint", f"pc=0x{self.vm.pc:04x}")
            cur = self.source_map.entry_for_pc(self.vm.pc)
            if cur is not None and cur.line != start_line:
                return StopReason("step", "")
            if steps >= self.SOFT_STEP_CAP:
                return StopReason("pause", "soft step cap reached")
        if self.vm.last_status == TINY_VM_HALT:
            return StopReason("halt", "HALT")
        return StopReason("exception", status_name(self.vm.last_status))

    def set_source_breakpoints(self, lines: list[int]) -> list[tuple[bool, int | None]]:
        self.breakpoint_pcs.clear()
        results: list[tuple[bool, int | None]] = []
        if self.source_map is None:
            for _ in lines:
                results.append((False, None))
            return results
        for line in lines:
            pc = self.source_map.pc_for_line_at_or_after(line)
            if pc is None:
                results.append((False, None))
            else:
                self.breakpoint_pcs.add(pc)
                results.append((True, pc))
        return results

    def set_instruction_breakpoints(self, pcs: list[int]) -> list[bool]:
        self.instr_breakpoint_pcs = set(pcs)
        return [True] * len(pcs)

    def pc(self) -> int:
        return self.vm.pc

    def halted(self) -> bool:
        return self.vm.halted

    def status(self) -> int:
        return self.vm.last_status

    def stack_snapshot(self) -> list[int]:
        return list(self.vm.stack)

    def locals_snapshot(self) -> list[int]:
        return list(self.vm.locals)

    def memory_snapshot(self) -> bytes:
        return bytes(self.vm.mem)


# ---- DAP request handlers ---------------------------------------------------


class DapSession:
    """Per-connection DAP session: routes commands to the backend."""

    def __init__(self, send_message: Callable[[dict], None]) -> None:
        self.send = send_message
        self.backend: DebugBackend | None = None
        self.stop_on_entry = False
        self.source_path: str | None = None
        self.terminated = False
        self._seq = 0
        # Concurrency: cont() / next_line() run on a worker thread so the
        # main read loop can service pause and disconnect during long runs.
        self._exec_thread: Optional[threading.Thread] = None
        self._pause_flag = threading.Event()
        self._backend_lock = threading.Lock()

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _send_event(self, event: str, body: dict | None = None) -> None:
        self.send(
            {
                "seq": self._next_seq(),
                "type": "event",
                "event": event,
                "body": body or {},
            }
        )

    def _respond(self, request: dict, body: dict | None = None, *, success: bool = True, message: str = "") -> None:
        msg = {
            "seq": self._next_seq(),
            "type": "response",
            "request_seq": request.get("seq"),
            "success": success,
            "command": request.get("command"),
        }
        if body is not None:
            msg["body"] = body
        if message:
            msg["message"] = message
        self.send(msg)

    def handle(self, request: dict) -> bool:
        """Dispatch a request. Return False once the session has terminated."""
        cmd = request.get("command", "")
        method = getattr(self, f"on_{cmd}", None)
        if method is None:
            self._respond(request, success=False, message=f"unknown command: {cmd}")
            return True
        try:
            method(request)
        except Exception as exc:  # surface adapter bugs cleanly to the client
            self._respond(request, success=False, message=f"adapter error: {exc!r}")
        return not self.terminated

    # ---- request handlers ----

    def on_initialize(self, req: dict) -> None:
        body = {
            "supportsConfigurationDoneRequest": True,
            "supportsStepInTargetsRequest": False,
            "supportsSteppingGranularity": True,
            "supportsInstructionBreakpoints": True,
            "supportsDisassembleRequest": True,
            "supportsTerminateRequest": True,
        }
        self._respond(req, body)
        self._send_event("initialized")

    def on_launch(self, req: dict) -> None:
        args = req.get("arguments", {})
        program_path = args.get("program")
        if not program_path:
            self._respond(req, success=False, message="launch requires 'program'")
            return
        self.source_path = args.get("source")
        self.stop_on_entry = bool(args.get("stopOnEntry", False))
        sm_path = args.get("sourceMap")
        bytecode = pathlib.Path(program_path).read_bytes()
        sm = load_sourcemap(sm_path) if sm_path else None
        if sm is not None and not self.source_path:
            self.source_path = sm.source

        def on_output(category: str, text: str) -> None:
            self._send_event(
                "output",
                {"category": category, "output": text},
            )

        self.backend = SimBackend(bytecode, sm, on_output=on_output)
        self._respond(req, {})

    def on_configurationDone(self, req: dict) -> None:
        self._respond(req, {})
        if self.backend is None:
            self._send_event("terminated")
            return
        if self.stop_on_entry:
            self._send_event(
                "stopped",
                {"reason": "entry", "threadId": 1, "allThreadsStopped": True},
            )
            return
        self._start_run("cont")

    def on_setBreakpoints(self, req: dict) -> None:
        args = req.get("arguments", {})
        bps_in = args.get("breakpoints") or []
        if self.backend is None:
            self._respond(req, {"breakpoints": [{"verified": False} for _ in bps_in]})
            return
        lines = [int(b["line"]) for b in bps_in]
        results = self.backend.set_source_breakpoints(lines)
        bps_out = []
        for (verified, pc), line in zip(results, lines):
            entry = {"verified": verified, "line": line}
            if pc is not None:
                entry["instructionReference"] = f"0x{pc:04x}"
            bps_out.append(entry)
        self._respond(req, {"breakpoints": bps_out})

    def on_setInstructionBreakpoints(self, req: dict) -> None:
        args = req.get("arguments", {})
        bps_in = args.get("breakpoints") or []
        if self.backend is None:
            self._respond(req, {"breakpoints": [{"verified": False} for _ in bps_in]})
            return
        pcs = []
        for b in bps_in:
            ref = b.get("instructionReference", "0")
            pcs.append(int(ref, 0))
        results = self.backend.set_instruction_breakpoints(pcs)
        bps_out = [
            {"verified": verified, "instructionReference": f"0x{pc:04x}"}
            for verified, pc in zip(results, pcs)
        ]
        self._respond(req, {"breakpoints": bps_out})

    def on_threads(self, req: dict) -> None:
        self._respond(req, {"threads": [{"id": 1, "name": "tiny_vm"}]})

    def on_stackTrace(self, req: dict) -> None:
        if self.backend is None:
            self._respond(req, {"stackFrames": [], "totalFrames": 0})
            return
        pc = self.backend.pc()
        frame: dict = {
            "id": 1,
            "name": f"pc=0x{pc:04x}",
            "column": 1,
            "line": 0,
            "instructionPointerReference": f"0x{pc:04x}",
        }
        sm = self.backend.source_map
        if sm is not None:
            entry = sm.entry_for_pc(pc)
            if entry is not None:
                frame["line"] = entry.line
                frame["column"] = entry.col or 1
                frame["name"] = f"line {entry.line}"
            if self.source_path:
                frame["source"] = {"path": str(pathlib.Path(self.source_path).resolve())}
        self._respond(req, {"stackFrames": [frame], "totalFrames": 1})

    def on_scopes(self, req: dict) -> None:
        scopes = [
            {"name": "Locals", "variablesReference": 100, "expensive": False},
            {"name": "Stack", "variablesReference": 200, "expensive": False},
            {"name": "Memory", "variablesReference": 300, "expensive": False},
        ]
        self._respond(req, {"scopes": scopes})

    def on_variables(self, req: dict) -> None:
        if self.backend is None:
            self._respond(req, {"variables": []})
            return
        ref = int(req.get("arguments", {}).get("variablesReference", 0))
        variables: list[dict] = []
        if ref == 100:  # Locals
            locs = self.backend.locals_snapshot()
            sm = self.backend.source_map
            for slot, value in enumerate(locs):
                name = (sm.name_for_local(slot) if sm else None) or f"slot{slot}"
                variables.append(
                    {"name": name, "value": str(value), "variablesReference": 0, "type": "int32"}
                )
        elif ref == 200:  # Stack (top first)
            for i, value in enumerate(reversed(self.backend.stack_snapshot())):
                variables.append(
                    {
                        "name": f"[-{i}]" if i > 0 else "top",
                        "value": str(value),
                        "variablesReference": 0,
                        "type": "int32",
                    }
                )
        elif ref == 300:  # Memory (paged 16 bytes per row)
            mem = self.backend.memory_snapshot()
            for offset in range(0, len(mem), 16):
                chunk = mem[offset : offset + 16]
                variables.append(
                    {
                        "name": f"0x{offset:02x}",
                        "value": " ".join(f"{b:02x}" for b in chunk),
                        "variablesReference": 0,
                        "type": "bytes",
                    }
                )
        self._respond(req, {"variables": variables})

    def on_continue(self, req: dict) -> None:
        self._respond(req, {"allThreadsContinued": True})
        if self.backend is None:
            self._send_event("terminated")
            return
        self._start_run("cont")

    def on_next(self, req: dict) -> None:
        self._respond(req, {})
        if self.backend is None:
            self._send_event("terminated")
            return
        granularity = req.get("arguments", {}).get("granularity")
        if granularity == "instruction":
            # Single opcode step: cheap, run synchronously.
            with self._backend_lock:
                stop = self.backend.step()
            self._emit_stop_or_terminate(stop)
        else:
            self._start_run("next")

    def on_stepIn(self, req: dict) -> None:
        # No calls in this language; identical to next.
        self.on_next(req)

    def on_stepOut(self, req: dict) -> None:
        self.on_next(req)

    def on_pause(self, req: dict) -> None:
        self._respond(req, {})
        self._pause_flag.set()

    # ---- DAP commands Theia sends but we treat as informational --------

    def on_setExceptionBreakpoints(self, req: dict) -> None:
        # We don't expose exception filters in `initialize`, but Theia still
        # sends an empty setExceptionBreakpoints during launch. Accept it.
        self._respond(req, {"breakpoints": []})

    def on_setFunctionBreakpoints(self, req: dict) -> None:
        bps = req.get("arguments", {}).get("breakpoints") or []
        self._respond(req, {"breakpoints": [{"verified": False} for _ in bps]})

    def on_setDataBreakpoints(self, req: dict) -> None:
        bps = req.get("arguments", {}).get("breakpoints") or []
        self._respond(req, {"breakpoints": [{"verified": False} for _ in bps]})

    def on_dataBreakpointInfo(self, req: dict) -> None:
        self._respond(req, {"dataId": None, "description": "not supported"})

    def on_loadedSources(self, req: dict) -> None:
        sources: list[dict] = []
        if self.source_path:
            sources.append({"path": str(pathlib.Path(self.source_path).resolve())})
        self._respond(req, {"sources": sources})

    def on_source(self, req: dict) -> None:
        args = req.get("arguments", {})
        source = args.get("source") or {}
        path = source.get("path")
        if path and pathlib.Path(path).is_file():
            try:
                content = pathlib.Path(path).read_text(encoding="utf-8")
                self._respond(req, {"content": content})
                return
            except OSError as exc:
                self._respond(req, success=False, message=f"read failed: {exc}")
                return
        self._respond(req, success=False, message="source not available")

    def on_exceptionInfo(self, req: dict) -> None:
        if self.backend is None:
            self._respond(req, {"exceptionId": "none", "breakMode": "always"})
            return
        msg = status_name(self.backend.status())
        self._respond(req, {"exceptionId": msg, "breakMode": "always", "description": msg})

    def on_evaluate(self, req: dict) -> None:
        # Read-only: only support trivial expressions like 'pc', 'sp', 'top'.
        args = req.get("arguments", {})
        expr = str(args.get("expression", "")).strip()
        if self.backend is None:
            self._respond(req, success=False, message="no backend")
            return
        if expr == "pc":
            self._respond(req, {"result": f"0x{self.backend.pc():04x}", "variablesReference": 0})
            return
        if expr == "sp":
            self._respond(req, {"result": str(len(self.backend.stack_snapshot())), "variablesReference": 0})
            return
        if expr == "top":
            stack = self.backend.stack_snapshot()
            self._respond(req, {"result": str(stack[-1] if stack else "<empty>"), "variablesReference": 0})
            return
        self._respond(req, success=False, message=f"evaluate: unsupported expression {expr!r}")

    def on_modules(self, req: dict) -> None:
        self._respond(req, {"modules": []})

    def on_completions(self, req: dict) -> None:
        self._respond(req, {"targets": []})

    def on_disassemble(self, req: dict) -> None:
        if self.backend is None:
            self._respond(req, {"instructions": []})
            return
        args = req.get("arguments", {})
        ref = int(args.get("memoryReference", "0"), 0)
        offset = int(args.get("offset", 0))
        count = int(args.get("instructionCount", 16))
        instructions = _disassemble_range(self.backend.bytecode, ref + offset, count)
        self._respond(req, {"instructions": instructions})

    def on_terminate(self, req: dict) -> None:
        self._respond(req, {})
        self._pause_flag.set()
        self._await_exec_thread()
        self.terminated = True
        self._send_event("terminated")

    def on_disconnect(self, req: dict) -> None:
        self._respond(req, {})
        self._pause_flag.set()
        self._await_exec_thread()
        self.terminated = True

    # ---- helpers ----

    def _start_run(self, mode: str) -> None:
        # Wait for any previous run to wind down first.
        self._await_exec_thread()
        self._pause_flag.clear()
        backend = self.backend
        assert backend is not None

        def run() -> None:
            with self._backend_lock:
                if mode == "cont":
                    stop = backend.cont(self._pause_flag)
                else:
                    stop = backend.next_line(self._pause_flag)
            self._emit_stop_or_terminate(stop)

        self._exec_thread = threading.Thread(target=run, daemon=True, name=f"tiny-vm-{mode}")
        self._exec_thread.start()

    def _await_exec_thread(self) -> None:
        t = self._exec_thread
        if t is not None and t.is_alive():
            t.join(timeout=3.0)
        self._exec_thread = None

    def _emit_stop_or_terminate(self, stop: StopReason) -> None:
        if stop.reason in ("halt", "exception"):
            self._send_event(
                "stopped",
                {
                    "reason": stop.reason,
                    "description": stop.description,
                    "threadId": 1,
                    "allThreadsStopped": True,
                },
            )
            self._send_event(
                "exited",
                {"exitCode": 0 if stop.reason == "halt" else 1},
            )
            self._send_event("terminated")
            return
        # DAP recognized stop reasons. "pause" is the spec name; we map our
        # internal "paused"/cap-reached to it.
        reason = "pause" if stop.reason == "pause" else stop.reason
        self._send_event(
            "stopped",
            {
                "reason": reason,
                "description": stop.description,
                "threadId": 1,
                "allThreadsStopped": True,
            },
        )


# ---- minimal disassembler ---------------------------------------------------


_OP_NAMES = {
    0x00: ("NOP", 0),
    0x01: ("PUSH8", 1),
    0x02: ("ADD", 0),
    0x03: ("SUB", 0),
    0x04: ("DUP", 0),
    0x05: ("DROP", 0),
    0x06: ("SWAP", 0),
    0x07: ("JMP", 2),
    0x08: ("JZ", 2),
    0x09: ("HOST", 1),
    0x0A: ("LGET", 1),
    0x0B: ("LSET", 1),
    0x0C: ("EQ", 0),
    0x0D: ("LT", 0),
    0x0E: ("PUSH16", 2),
    0x0F: ("MOD", 0),
    0x10: ("MUL", 0),
    0x11: ("DIV", 0),
    0x12: ("MGET", 0),
    0x13: ("MSET", 0),
    0x14: ("PUSH32", 4),
    0x15: ("AND", 0),
    0x16: ("OR", 0),
    0x17: ("XOR", 0),
    0x18: ("NOT", 0),
    0x19: ("SHL", 0),
    0x1A: ("SHR", 0),
    0x1B: ("ROL", 0),
    0x1C: ("ROR", 0),
    0x1D: ("MGET32", 0),
    0x1E: ("MSET32", 0),
    0xFF: ("HALT", 0),
}


def _disassemble_range(code: bytes, start: int, count: int) -> list[dict]:
    out: list[dict] = []
    pc = max(start, 0)
    emitted = 0
    while pc < len(code) and emitted < count:
        op = code[pc]
        name, operand_bytes = _OP_NAMES.get(op, (f"?0x{op:02x}", 0))
        if pc + 1 + operand_bytes > len(code):
            out.append(
                {
                    "address": f"0x{pc:04x}",
                    "instruction": f"{name} <truncated>",
                    "instructionBytes": " ".join(f"{b:02x}" for b in code[pc:]),
                }
            )
            pc = len(code)
            break
        operand_str = ""
        if operand_bytes:
            ob = code[pc + 1 : pc + 1 + operand_bytes]
            if name in ("PUSH8",):
                v = ob[0]
                if v >= 0x80:
                    v -= 0x100
                operand_str = f" {v}"
            elif name in ("PUSH16",):
                v = ob[0] | (ob[1] << 8)
                if v >= 0x8000:
                    v -= 0x10000
                operand_str = f" {v}"
            elif name in ("PUSH32",):
                v = ob[0] | (ob[1] << 8) | (ob[2] << 16) | (ob[3] << 24)
                if v >= 0x80000000:
                    v -= 0x100000000
                operand_str = f" {v}"
            elif name in ("JMP", "JZ"):
                t = ob[0] | (ob[1] << 8)
                operand_str = f" 0x{t:04x}"
            else:
                operand_str = f" {ob[0]}"
        bytes_hex = " ".join(f"{b:02x}" for b in code[pc : pc + 1 + operand_bytes])
        out.append(
            {
                "address": f"0x{pc:04x}",
                "instruction": f"{name}{operand_str}",
                "instructionBytes": bytes_hex,
            }
        )
        pc += 1 + operand_bytes
        emitted += 1
    return out
