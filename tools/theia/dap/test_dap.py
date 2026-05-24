#!/usr/bin/env python3
"""
End-to-end DAP server tests for tiny_vm.

Spawns server.py as a subprocess, reads its port announcement, then drives
the protocol over TCP to verify the acceptance scenario in
docs/theia_proposal.md M3:

    A scripted DAP client can set a .cvm.c source breakpoint on the count10
    test, hit it, inspect the loop counter local, and continue to halt.
    stepInstruction advances PC by exactly one opcode.
"""

from __future__ import annotations

import json
import pathlib
import socket
import subprocess
import sys
import tempfile
import threading
import time


ROOT = pathlib.Path(__file__).resolve().parents[3]


# ---- DAP framing helpers ---------------------------------------------------


class DapClient:
    def __init__(self, host: str, port: int) -> None:
        self.sock = socket.create_connection((host, port), timeout=5.0)
        self.sock.settimeout(5.0)
        self._buf = bytearray()
        self._seq = 0
        self._events: list[dict] = []
        self._lock = threading.Lock()

    def close(self) -> None:
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()

    def _read_one(self, *, timeout: float = 5.0) -> dict:
        deadline = time.monotonic() + timeout
        while True:
            sep = self._buf.find(b"\r\n\r\n")
            if sep != -1:
                header = bytes(self._buf[:sep]).decode("ascii", errors="replace")
                length = 0
                for line in header.split("\r\n"):
                    if line.lower().startswith("content-length:"):
                        length = int(line.split(":", 1)[1].strip())
                        break
                if len(self._buf) >= sep + 4 + length:
                    body = bytes(self._buf[sep + 4 : sep + 4 + length])
                    del self._buf[: sep + 4 + length]
                    return json.loads(body.decode("utf-8"))
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("dap client read timeout")
            self.sock.settimeout(remaining)
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("dap server closed connection")
            self._buf.extend(chunk)

    def send_request(self, command: str, arguments: dict | None = None) -> int:
        self._seq += 1
        body = {
            "seq": self._seq,
            "type": "request",
            "command": command,
            "arguments": arguments or {},
        }
        raw = json.dumps(body).encode("utf-8")
        header = f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii")
        self.sock.sendall(header + raw)
        return self._seq

    def wait_for_response(self, seq: int, *, timeout: float = 5.0) -> dict:
        deadline = time.monotonic() + timeout
        while True:
            msg = self._read_one(timeout=max(0.1, deadline - time.monotonic()))
            if msg.get("type") == "event":
                self._events.append(msg)
                continue
            if msg.get("type") == "response" and msg.get("request_seq") == seq:
                if not msg.get("success", False):
                    raise AssertionError(
                        f"{msg.get('command')} failed: {msg.get('message')}"
                    )
                return msg

    def wait_for_event(self, event: str, *, timeout: float = 5.0) -> dict:
        deadline = time.monotonic() + timeout
        # check already-queued events
        for i, ev in enumerate(self._events):
            if ev.get("event") == event:
                return self._events.pop(i)
        while True:
            msg = self._read_one(timeout=max(0.1, deadline - time.monotonic()))
            if msg.get("type") == "event":
                if msg.get("event") == event:
                    return msg
                self._events.append(msg)
                continue
            # unexpected response while waiting for event: stash it
            self._events.append(msg)

    def drain_events(self, *, until: float = 0.2) -> list[dict]:
        end = time.monotonic() + until
        try:
            while time.monotonic() < end:
                self.sock.settimeout(max(0.01, end - time.monotonic()))
                try:
                    msg = self._read_one(timeout=max(0.01, end - time.monotonic()))
                    self._events.append(msg)
                except TimeoutError:
                    break
        finally:
            self.sock.settimeout(5.0)
        out = list(self._events)
        self._events.clear()
        return out


# ---- server lifecycle ------------------------------------------------------


class ServerHandle:
    def __init__(self, proc: subprocess.Popen, host: str, port: int) -> None:
        self.proc = proc
        self.host = host
        self.port = port

    def stop(self) -> None:
        try:
            self.proc.terminate()
            self.proc.wait(timeout=3.0)
        except Exception:
            self.proc.kill()


def start_server() -> ServerHandle:
    proc = subprocess.Popen(
        [
            sys.executable,
            str(ROOT / "tools" / "theia" / "dap" / "server.py"),
            "--once",
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    line = proc.stdout.readline().strip()
    if not line:
        err = proc.stderr.read()
        raise RuntimeError(f"server did not announce port; stderr: {err}")
    announce = json.loads(line)
    return ServerHandle(proc, "127.0.0.1", int(announce["port"]))


# ---- test ------------------------------------------------------------------


def _compile_count10(tdp: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
    src = ROOT / "projects" / "tiny_vm" / "tests" / "count10.cvm.c"
    out = tdp / "count10.bin"
    subprocess.run(
        ["./tools/vm_cc.py", str(src), "-o", str(out), "--map"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return src, out, pathlib.Path(str(out) + ".map")


def _expect_stopped(events: list[dict], reason: str) -> dict:
    for ev in events:
        if ev.get("event") == "stopped" and ev.get("body", {}).get("reason") == reason:
            return ev
    raise AssertionError(f"expected stopped reason={reason}, events were: {events}")


def test_count10_scenario() -> None:
    handle = start_server()
    client: DapClient | None = None
    try:
        with tempfile.TemporaryDirectory() as td:
            tdp = pathlib.Path(td)
            src, prog, sm_path = _compile_count10(tdp)
            client = DapClient(handle.host, handle.port)

            # initialize
            seq = client.send_request("initialize", {"clientID": "test"})
            resp = client.wait_for_response(seq)
            body = resp["body"]
            assert body.get("supportsConfigurationDoneRequest") is True
            client.wait_for_event("initialized")

            # launch with stopOnEntry so we control timing
            seq = client.send_request(
                "launch",
                {
                    "program": str(prog),
                    "source": str(src),
                    "sourceMap": str(sm_path),
                    "stopOnEntry": True,
                },
            )
            client.wait_for_response(seq)

            # set breakpoint on source line 3 (the print_u32(i) call)
            seq = client.send_request(
                "setBreakpoints",
                {
                    "source": {"path": str(src)},
                    "breakpoints": [{"line": 3}],
                },
            )
            resp = client.wait_for_response(seq)
            bps = resp["body"]["breakpoints"]
            assert len(bps) == 1 and bps[0]["verified"] is True, f"unexpected bps: {bps}"

            # configurationDone -> stopped(entry)
            seq = client.send_request("configurationDone")
            client.wait_for_response(seq)
            stop = client.wait_for_event("stopped")
            assert stop["body"]["reason"] == "entry", stop

            # stackTrace - we're at entry (pc 0, line 1)
            seq = client.send_request("stackTrace", {"threadId": 1})
            resp = client.wait_for_response(seq)
            frames = resp["body"]["stackFrames"]
            assert frames and frames[0]["line"] == 1, f"bad initial stackTrace: {frames}"

            # continue -> hit breakpoint at line 3, with i=1
            seq = client.send_request("continue", {"threadId": 1})
            client.wait_for_response(seq)
            stop = client.wait_for_event("stopped")
            assert stop["body"]["reason"] == "breakpoint", stop

            seq = client.send_request("stackTrace", {"threadId": 1})
            resp = client.wait_for_response(seq)
            line = resp["body"]["stackFrames"][0]["line"]
            assert line == 3, f"expected line 3 at first breakpoint hit, got {line}"

            # inspect locals -> 'i' must be 1
            seq = client.send_request("scopes", {"frameId": 1})
            resp = client.wait_for_response(seq)
            scope_locals = next(s for s in resp["body"]["scopes"] if s["name"] == "Locals")

            seq = client.send_request(
                "variables", {"variablesReference": scope_locals["variablesReference"]}
            )
            resp = client.wait_for_response(seq)
            vars_ = {v["name"]: v["value"] for v in resp["body"]["variables"]}
            assert vars_.get("i") == "1", f"expected i=1, got {vars_}"

            # stepInstruction must advance PC by one opcode
            seq = client.send_request("stackTrace", {"threadId": 1})
            resp = client.wait_for_response(seq)
            pc_before = int(resp["body"]["stackFrames"][0]["instructionPointerReference"], 0)

            seq = client.send_request("next", {"threadId": 1, "granularity": "instruction"})
            client.wait_for_response(seq)
            client.wait_for_event("stopped")
            seq = client.send_request("stackTrace", {"threadId": 1})
            resp = client.wait_for_response(seq)
            pc_after = int(resp["body"]["stackFrames"][0]["instructionPointerReference"], 0)
            assert pc_after > pc_before, f"stepInstruction did not advance PC: {pc_before}->{pc_after}"
            assert pc_after - pc_before in (1, 2, 3, 5), f"unexpected step size {pc_after - pc_before}"

            # continue through the rest of the loop, collecting output and counting bp hits.
            bp_hits = 1  # already had one
            outputs: list[str] = []
            terminated = False
            for _ in range(40):  # plenty of headroom
                seq = client.send_request("continue", {"threadId": 1})
                client.wait_for_response(seq)
                # wait for either stopped or terminated
                while True:
                    events = client.drain_events(until=0.6)
                    if not events:
                        # explicit wait
                        try:
                            ev = client._read_one(timeout=2.0)
                            events = [ev]
                        except TimeoutError:
                            break
                    for ev in events:
                        if ev.get("event") == "output":
                            outputs.append(ev["body"].get("output", ""))
                        elif ev.get("event") == "stopped":
                            if ev["body"].get("reason") == "breakpoint":
                                bp_hits += 1
                            elif ev["body"].get("reason") == "halt":
                                terminated = True
                        elif ev.get("event") == "terminated":
                            terminated = True
                    if terminated or any(
                        e.get("event") == "stopped" and e.get("body", {}).get("reason") == "breakpoint"
                        for e in events
                    ):
                        break
                if terminated:
                    break
            assert terminated, f"program did not terminate, bp_hits={bp_hits}, outputs={outputs}"
            assert bp_hits == 10, f"expected 10 bp hits (one per loop iteration), got {bp_hits}"
            combined = "".join(outputs)
            lines = [l for l in combined.splitlines() if l]
            assert lines == [str(i) for i in range(1, 11)], f"unexpected outputs: {lines}"

            seq = client.send_request("disconnect")
            client.wait_for_response(seq)
    finally:
        if client is not None:
            client.close()
        handle.stop()


def test_instruction_breakpoint_and_disassemble() -> None:
    handle = start_server()
    client: DapClient | None = None
    try:
        with tempfile.TemporaryDirectory() as td:
            tdp = pathlib.Path(td)
            src, prog, sm_path = _compile_count10(tdp)
            client = DapClient(handle.host, handle.port)

            seq = client.send_request("initialize", {})
            client.wait_for_response(seq)
            client.wait_for_event("initialized")

            seq = client.send_request(
                "launch",
                {"program": str(prog), "sourceMap": str(sm_path), "stopOnEntry": True},
            )
            client.wait_for_response(seq)

            # Set an instruction breakpoint at pc=0x000C (start of body, per count10.map)
            seq = client.send_request(
                "setInstructionBreakpoints",
                {"breakpoints": [{"instructionReference": "0x000C"}]},
            )
            resp = client.wait_for_response(seq)
            assert resp["body"]["breakpoints"][0]["verified"] is True

            seq = client.send_request("configurationDone")
            client.wait_for_response(seq)
            client.wait_for_event("stopped")  # entry

            seq = client.send_request("continue", {"threadId": 1})
            client.wait_for_response(seq)
            stop = client.wait_for_event("stopped")
            assert stop["body"]["reason"] == "breakpoint", stop

            seq = client.send_request("stackTrace", {"threadId": 1})
            resp = client.wait_for_response(seq)
            pc = int(resp["body"]["stackFrames"][0]["instructionPointerReference"], 0)
            assert pc == 0x000C, f"expected pc 0x000C at instr bp, got 0x{pc:04x}"

            # Disassemble around current PC
            seq = client.send_request(
                "disassemble",
                {"memoryReference": "0x000C", "offset": 0, "instructionCount": 3},
            )
            resp = client.wait_for_response(seq)
            instrs = resp["body"]["instructions"]
            assert len(instrs) == 3
            assert instrs[0]["address"] == "0x000c"
            # First instruction at pc 0x0C is "LGET 0" per the count10 listing.
            assert instrs[0]["instruction"].startswith("LGET"), f"got {instrs[0]}"

            seq = client.send_request("disconnect")
            client.wait_for_response(seq)
    finally:
        if client is not None:
            client.close()
        handle.stop()


def test_setExceptionBreakpoints_succeeds() -> None:
    """Regression: Theia calls setExceptionBreakpoints during launch even
    when we don't advertise filters. Returning failure tears the session
    down, so the server must accept it."""
    handle = start_server()
    client: DapClient | None = None
    try:
        client = DapClient(handle.host, handle.port)
        seq = client.send_request("initialize", {})
        client.wait_for_response(seq)
        client.wait_for_event("initialized")
        seq = client.send_request(
            "setExceptionBreakpoints", {"filters": []}
        )
        resp = client.wait_for_response(seq)
        assert resp["success"] is True, resp
        # Also exercise the other launch-time stubs Theia tends to send.
        for cmd in ("setFunctionBreakpoints", "setDataBreakpoints"):
            seq = client.send_request(cmd, {"breakpoints": []})
            resp = client.wait_for_response(seq)
            assert resp["success"] is True, (cmd, resp)
        seq = client.send_request("disconnect")
        client.wait_for_response(seq)
    finally:
        if client is not None:
            client.close()
        handle.stop()


def test_infinite_loop_pauses() -> None:
    """A program that loops forever (blink demo style) must hit the soft
    step cap or respect an explicit pause, not freeze the server."""
    handle = start_server()
    client: DapClient | None = None
    try:
        with tempfile.TemporaryDirectory() as td:
            tdp = pathlib.Path(td)
            src = tdp / "loop.cvm.c"
            src.write_text("while (1) { led_write(1); led_write(0); }\n", encoding="utf-8")
            out = tdp / "loop.bin"
            subprocess.run(
                ["./tools/vm_cc.py", str(src), "-o", str(out), "--map"],
                cwd=ROOT, check=True, capture_output=True,
            )

            client = DapClient(handle.host, handle.port)
            seq = client.send_request("initialize", {})
            client.wait_for_response(seq)
            client.wait_for_event("initialized")
            seq = client.send_request(
                "launch",
                {
                    "program": str(out),
                    "source": str(src),
                    "sourceMap": str(out) + ".map",
                    "stopOnEntry": True,
                },
            )
            client.wait_for_response(seq)
            seq = client.send_request("configurationDone")
            client.wait_for_response(seq)
            client.wait_for_event("stopped")  # entry

            # Kick off continue, then pause shortly after.
            seq = client.send_request("continue", {"threadId": 1})
            client.wait_for_response(seq)
            time.sleep(0.1)
            seq = client.send_request("pause", {"threadId": 1})
            client.wait_for_response(seq)
            stop = client.wait_for_event("stopped", timeout=10.0)
            assert stop["body"]["reason"] == "pause", stop

            seq = client.send_request("disconnect")
            client.wait_for_response(seq)
    finally:
        if client is not None:
            client.close()
        handle.stop()


def main() -> int:
    tests = [
        test_count10_scenario,
        test_instruction_breakpoint_and_disassemble,
        test_setExceptionBreakpoints_succeeds,
        test_infinite_loop_pauses,
    ]
    for fn in tests:
        fn()
        print(f"  ok   {fn.__name__}")
    print("dap tests: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
