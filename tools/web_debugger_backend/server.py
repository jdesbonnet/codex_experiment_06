#!/usr/bin/env python3
"""
Minimal backend for the web debugger visualization MVP.

This version replaces the original stubs with real OpenOCD process control for
the LPC1114 path:
- spawn/stop OpenOCD
- own the OpenOCD Tcl socket
- serialize run-control requests
- read registers and memory over the Tcl API

The frontend contract is still intentionally small. This is the first real
backend step, not the full finished debugger service.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import socket
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlparse


WS_MAGIC = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
TCL_TERM = b"\x1a"
REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = Path(__file__).resolve().parent / "static"
HALTED_SAMPLE_INTERVAL_S = 0.1
RUNNING_METRICS_INTERVAL_S = 1.0
MIN_HALTED_SAMPLE_HZ = 1
MAX_HALTED_SAMPLE_HZ = 20
REGISTER_ORDER = [
    "r0",
    "r1",
    "r2",
    "r3",
    "r4",
    "r5",
    "r6",
    "r7",
    "r8",
    "r9",
    "r10",
    "r11",
    "r12",
    "sp",
    "lr",
    "pc",
    "xpsr",
]


def iso8601_utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class SessionError(RuntimeError):
    def __init__(self, error: str, detail: str):
        super().__init__(detail)
        self.error = error
        self.detail = detail


class OpenOCDController:
    """Owns one OpenOCD process and its Tcl RPC socket."""

    def __init__(
        self,
        openocd_bin: str = "openocd",
        script_dir: Path = Path("/usr/share/openocd/scripts"),
        project_script_dir: Path = REPO_ROOT / "openocd",
        config_path: Path = REPO_ROOT / "openocd" / "base.cfg",
        host: str = "127.0.0.1",
        tcl_port: int = 6666,
    ):
        self.openocd_bin = openocd_bin
        self.script_dir = script_dir
        self.project_script_dir = project_script_dir
        self.config_path = config_path
        self.host = host
        self.tcl_port = tcl_port
        self.process: Optional[subprocess.Popen] = None
        self.sock: Optional[socket.socket] = None
        self.lock = threading.Lock()

    def start(self) -> None:
        with self.lock:
            if self.process is not None:
                return

            cmd = [
                self.openocd_bin,
                "-s",
                str(self.script_dir),
                "-s",
                str(self.project_script_dir),
                "-f",
                str(self.config_path),
                "-c",
                f"tcl_port {self.tcl_port}",
                "-c",
                "telnet_port disabled",
                "-c",
                "gdb_port disabled",
            ]

            self.process = subprocess.Popen(
                cmd,
                cwd=str(REPO_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )

            try:
                self.sock = self._connect_tcl_socket(timeout_s=3.0)
            except Exception as exc:
                self._stop_locked(force=True)
                raise SessionError("openocd_start_failed", self._format_start_failure(str(exc))) from exc

    def stop(self) -> None:
        with self.lock:
            self._stop_locked(force=False)

    def command(self, command: str, timeout_s: float = 2.0) -> str:
        with self.lock:
            if self.process is None or self.sock is None:
                raise SessionError("not_connected", "OpenOCD session is not active")
            if self.process.poll() is not None:
                self._stop_locked(force=True)
                raise SessionError("openocd_exited", "OpenOCD process exited unexpectedly")

            try:
                self.sock.settimeout(timeout_s)
                self.sock.sendall(command.encode("utf-8") + TCL_TERM)
                data = bytearray()
                while True:
                    chunk = self.sock.recv(4096)
                    if not chunk:
                        raise SessionError("tcl_socket_closed", "OpenOCD Tcl socket closed unexpectedly")
                    data.extend(chunk)
                    if TCL_TERM in chunk or data.endswith(TCL_TERM):
                        break
                payload = bytes(data)
                if TCL_TERM in payload:
                    payload = payload.split(TCL_TERM, 1)[0]
                return payload.decode("utf-8", errors="replace").strip()
            except socket.timeout as exc:
                raise SessionError("openocd_timeout", f"Tcl command timed out: {command}") from exc
            except OSError as exc:
                raise SessionError("openocd_io_error", str(exc)) from exc

    def _connect_tcl_socket(self, timeout_s: float) -> socket.socket:
        deadline = time.monotonic() + timeout_s
        last_error: Optional[Exception] = None
        while time.monotonic() < deadline:
            if self.process is not None and self.process.poll() is not None:
                break
            try:
                sock = socket.create_connection((self.host, self.tcl_port), timeout=0.5)
                sock.settimeout(2.0)
                return sock
            except OSError as exc:
                last_error = exc
                time.sleep(0.1)
        if self.process is not None and self.process.poll() is not None:
            raise RuntimeError("OpenOCD exited before opening the Tcl socket")
        raise RuntimeError(f"Could not connect to OpenOCD Tcl socket: {last_error}")

    def _stop_locked(self, force: bool) -> None:
        process = self.process
        sock = self.sock
        self.sock = None
        self.process = None

        if sock is not None:
            try:
                if not force and process is not None and process.poll() is None:
                    try:
                        sock.settimeout(1.0)
                        sock.sendall(b"shutdown" + TCL_TERM)
                    except OSError:
                        pass
                sock.close()
            except OSError:
                pass

        if process is None:
            return

        try:
            process.wait(timeout=1.5)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1.0)

    def _format_start_failure(self, reason: str) -> str:
        details = [reason]
        if self.process is not None and self.process.stdout is not None:
            try:
                tail = self.process.stdout.read()
            except OSError:
                tail = ""
            if tail:
                details.append(tail.strip())
        return " | ".join(part for part in details if part)


class WebSocketClient:
    def __init__(self, request_handler: BaseHTTPRequestHandler):
        self.connection = request_handler.connection
        self.lock = threading.Lock()
        self.closed = False

    def send_json(self, message: Dict) -> None:
        payload = json.dumps(message, separators=(",", ":")).encode("utf-8")
        frame = bytearray()
        frame.append(0x81)
        length = len(payload)
        if length < 126:
            frame.append(length)
        elif length < 65536:
            frame.append(126)
            frame.extend(length.to_bytes(2, "big"))
        else:
            frame.append(127)
            frame.extend(length.to_bytes(8, "big"))
        frame.extend(payload)
        with self.lock:
            if self.closed:
                raise ConnectionError("websocket client closed")
            self.connection.sendall(frame)

    def close(self) -> None:
        with self.lock:
            self.closed = True
            try:
                self.connection.close()
            except OSError:
                pass


@dataclass
class DebugSession:
    state: str = "disconnected"
    target: Optional[str] = None
    transport: Optional[str] = None
    arch: str = "armv6m"
    seq: int = 0
    watches: Dict[str, Dict[str, int]] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)
    controller: Optional[OpenOCDController] = None
    target_name: str = "lpc11xx.cpu"

    def connect(self, target: str, transport: str) -> Dict:
        if target != "lpc1114":
            raise SessionError("unsupported_target", "This backend step currently supports only target=lpc1114")
        if transport != "swd":
            raise SessionError("unsupported_transport", "This backend step currently supports only transport=swd")

        with self.lock:
            if self.controller is not None:
                self.controller.stop()
                self.controller = None
                self.watches.clear()

            self.state = "connecting"
            self.target = target
            self.transport = transport
            self.controller = OpenOCDController()

            try:
                self.controller.start()
                self.controller.command("init", timeout_s=3.0)
                self.controller.command("reset halt", timeout_s=3.0)
                self.state = self._read_target_state_locked()
                if self.state not in ("halted", "running"):
                    self.state = "halted"
            except SessionError:
                self.state = "error"
                if self.controller is not None:
                    self.controller.stop()
                    self.controller = None
                raise
            except Exception as exc:
                self.state = "error"
                if self.controller is not None:
                    self.controller.stop()
                    self.controller = None
                raise SessionError("connect_failed", str(exc)) from exc

            return {"ok": True, "state": self.state}

    def disconnect(self) -> Dict:
        with self.lock:
            if self.controller is not None:
                self.controller.stop()
                self.controller = None
            self.state = "disconnected"
            self.watches.clear()
            return {"ok": True, "state": self.state}

    def run(self) -> Dict:
        with self.lock:
            self._require_connected_locked()
            self.controller.command("resume", timeout_s=2.0)
            self.state = "running"
            return {"ok": True, "state": self.state}

    def halt(self) -> Dict:
        with self.lock:
            self._require_connected_locked()
            self.controller.command("halt", timeout_s=2.0)
            self.state = self._read_target_state_locked()
            return {"ok": True, "state": self.state}

    def step(self, count: int) -> Dict:
        count = max(count, 1)
        with self.lock:
            self._require_connected_locked()
            for _ in range(count):
                self.controller.command("step", timeout_s=2.0)
            self.state = self._read_target_state_locked()
            return {"ok": True, "state": self.state}

    def reset(self, mode: str) -> Dict:
        if mode not in ("halt", "run"):
            raise SessionError("bad_request", "reset mode must be 'halt' or 'run'")
        with self.lock:
            self._require_connected_locked()
            self.seq = 0
            self.controller.command(f"reset {mode}", timeout_s=3.0)
            self.state = self._read_target_state_locked()
            if mode == "run" and self.state == "halted":
                # Some probes/targets re-halt immediately; report the observed state.
                pass
            return {"ok": True, "state": self.state}

    def set_watch(self, name: str, address: int, length: int) -> Dict:
        if length <= 0:
            raise SessionError("bad_request", "watch length must be greater than zero")
        with self.lock:
            self.watches[name] = {"address": address, "length": length}
            return {"ok": True}

    def remove_watch(self, name: str) -> Dict:
        with self.lock:
            if name not in self.watches:
                raise SessionError("not_found", f"Watch '{name}' does not exist")
            del self.watches[name]
            return {"ok": True}

    def list_watches(self) -> List[Dict[str, int | str]]:
        with self.lock:
            items: List[Dict[str, int | str]] = []
            for name, watch in sorted(self.watches.items()):
                items.append(
                    {
                        "name": name,
                        "address": f"0x{watch['address']:08x}",
                        "length": watch["length"],
                    }
                )
            return items

    def next_seq(self) -> int:
        self.seq += 1
        return self.seq

    def register_snapshot(self) -> Dict:
        with self.lock:
            self._require_connected_locked()
            registers = self._read_registers_locked()
            seq = self.next_seq()
            return {
                "type": "register_snapshot",
                "ts": iso8601_utc_now(),
                "arch": self.arch,
                "seq": seq,
                "registers": registers,
            }

    def sample_halted(self) -> Optional[Dict[str, object]]:
        """Take one coherent halted-state sample under a single session lock.

        This avoids racing a run/halt transition between separate register and
        memory reads, which can desynchronize the OpenOCD Tcl stream.
        """
        with self.lock:
            self._require_connected_locked()
            if self.state != "halted":
                return None

            registers = self._read_registers_locked()
            seq = self.next_seq()
            register_snapshot = {
                "type": "register_snapshot",
                "ts": iso8601_utc_now(),
                "arch": self.arch,
                "seq": seq,
                "registers": registers,
            }

            memory_snapshots: List[Dict] = []
            for name, watch in self.watches.items():
                data = self._read_memory_bytes_locked(watch["address"], watch["length"])
                memory_snapshots.append(
                    {
                        "type": "memory_snapshot",
                        "ts": iso8601_utc_now(),
                        "seq": seq,
                        "name": name,
                        "address": f"0x{watch['address']:08x}",
                        "length": watch["length"],
                        "data_hex": data.hex(),
                    }
                )

            return {
                "register_snapshot": register_snapshot,
                "memory_snapshots": memory_snapshots,
            }

    def read_memory(self, address: int, length: int) -> bytes:
        if length < 0:
            raise SessionError("bad_request", "memory length must not be negative")
        with self.lock:
            self._require_connected_locked()
            return self._read_memory_bytes_locked(address, length)

    def memory_snapshots(self) -> List[Dict]:
        with self.lock:
            self._require_connected_locked()
            snapshots: List[Dict] = []
            seq = self.seq
            for name, watch in self.watches.items():
                data = self._read_memory_bytes_locked(watch["address"], watch["length"])
                snapshots.append(
                    {
                        "type": "memory_snapshot",
                        "ts": iso8601_utc_now(),
                        "seq": seq,
                        "name": name,
                        "address": f"0x{watch['address']:08x}",
                        "length": watch["length"],
                        "data_hex": data.hex(),
                    }
                )
            return snapshots

    def _require_connected_locked(self) -> None:
        if self.controller is None or self.state == "disconnected":
            raise SessionError("not_connected", "No active target session")

    def _read_target_state_locked(self) -> str:
        response = self.controller.command(f"{self.target_name} curstate")
        state = response.strip().lower()
        if state in ("running", "halted", "reset", "unknown"):
            return "halted" if state == "reset" else state
        return self.state

    def _read_registers_locked(self) -> Dict[str, str]:
        response = self._capture_command_output_locked("reg")
        registers = self._parse_register_dump(response)
        if registers:
            return registers

        fallback: Dict[str, str] = {}
        for name in REGISTER_ORDER:
            reg_response = self._capture_command_output_locked(f"reg {name}")
            single = self._parse_register_dump(reg_response)
            if name in single:
                fallback[name] = single[name]
                continue
            match = re.search(r"(0x[0-9a-fA-F]+)", reg_response)
            if match:
                fallback[name] = self._format_u32(match.group(1))
        if not fallback:
            raise SessionError("register_read_failed", "Could not parse register output from OpenOCD")
        return fallback

    def _capture_command_output_locked(self, command: str) -> str:
        response = self.controller.command(f"capture {{{command}}}")
        if "invalid command name \"capture\"" in response.lower():
            return self.controller.command(command)
        return response

    def _parse_register_dump(self, text: str) -> Dict[str, str]:
        registers: Dict[str, str] = {}
        pattern = re.compile(
            r"\b(r1[0-2]|r[0-9]|sp|lr|pc|xpsr|xPSR)\b[^0-9A-Fa-f]*(0x[0-9A-Fa-f]+)",
            re.MULTILINE,
        )
        for match in pattern.finditer(text):
            raw_name = match.group(1)
            name = "xpsr" if raw_name.lower() == "xpsr" else raw_name.lower()
            registers[name] = self._format_u32(match.group(2))
        return registers

    def _read_memory_bytes_locked(self, address: int, length: int) -> bytes:
        if length == 0:
            return b""
        response = self.controller.command(f"read_memory 0x{address:x} 8 {length}", timeout_s=3.0)
        cleaned = response.replace("{", " ").replace("}", " ")
        values: List[int] = []
        for token in cleaned.split():
            try:
                values.append(int(token, 0) & 0xFF)
            except ValueError:
                continue
        if len(values) < length:
            raise SessionError(
                "memory_read_failed",
                f"Expected {length} bytes from OpenOCD, got {len(values)}; raw response={response!r}",
            )
        return bytes(values[:length])

    def _format_u32(self, value: str) -> str:
        return f"0x{int(value, 0) & 0xFFFFFFFF:08x}"


class AppState:
    def __init__(self) -> None:
        self.session = DebugSession()
        self.clients: List[WebSocketClient] = []
        self.clients_lock = threading.Lock()
        self.halted_sample_hz = int(round(1.0 / HALTED_SAMPLE_INTERVAL_S))
        self.config_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.sampler_thread = threading.Thread(target=self._sampler_loop, name="backend-sampler", daemon=True)
        self.sampler_thread.start()

    def add_client(self, client: WebSocketClient) -> None:
        with self.clients_lock:
            self.clients.append(client)

    def remove_client(self, client: WebSocketClient) -> None:
        with self.clients_lock:
            self.clients = [c for c in self.clients if c is not client]
        client.close()

    def broadcast(self, message: Dict) -> None:
        stale: List[WebSocketClient] = []
        with self.clients_lock:
            clients = list(self.clients)
        for client in clients:
            try:
                client.send_json(message)
            except (OSError, ConnectionError):
                stale.append(client)
        for client in stale:
            self.remove_client(client)

    def broadcast_status(self, reason: str) -> None:
        self.broadcast(
            {
                "type": "session_status",
                "ts": iso8601_utc_now(),
                "state": self.session.state,
                "target": self.session.target,
                "reason": reason,
            }
        )

    def stop(self) -> None:
        self.stop_event.set()
        self.sampler_thread.join(timeout=1.0)

    def get_config(self) -> Dict[str, int]:
        with self.config_lock:
            return {"halted_sample_hz": self.halted_sample_hz}

    def set_config(self, halted_sample_hz: int) -> Dict[str, int]:
        if halted_sample_hz < MIN_HALTED_SAMPLE_HZ or halted_sample_hz > MAX_HALTED_SAMPLE_HZ:
            raise SessionError(
                "bad_request",
                f"halted_sample_hz must be in range {MIN_HALTED_SAMPLE_HZ}..{MAX_HALTED_SAMPLE_HZ}",
            )
        with self.config_lock:
            self.halted_sample_hz = halted_sample_hz
            return {"halted_sample_hz": self.halted_sample_hz}

    def _sampler_loop(self) -> None:
        last_running_metrics_ts = 0.0
        while not self.stop_event.is_set():
            if not self._has_clients():
                self.stop_event.wait(0.1)
                continue

            state = self.session.state
            if state == "halted":
                config = self.get_config()
                sample_hz_target = config["halted_sample_hz"]
                interval_s = 1.0 / max(sample_hz_target, 1)
                start = time.monotonic()
                try:
                    sample = self.session.sample_halted()
                except SessionError as exc:
                    self.broadcast(
                        {
                            "type": "event",
                            "ts": iso8601_utc_now(),
                            "event": "error",
                            "detail": exc.detail,
                        }
                    )
                    self.stop_event.wait(interval_s)
                    continue

                if sample is None:
                    self.stop_event.wait(interval_s)
                    continue

                register_snapshot = sample["register_snapshot"]
                memory_snapshots = sample["memory_snapshots"]
                self.broadcast(register_snapshot)
                for snapshot in memory_snapshots:
                    self.broadcast(snapshot)

                elapsed_ms = int((time.monotonic() - start) * 1000)
                sample_hz = sample_hz_target
                if elapsed_ms > int(interval_s * 1000) and elapsed_ms > 0:
                    sample_hz = max(1, int(round(1000.0 / elapsed_ms)))
                self.broadcast(
                    {
                        "type": "metrics",
                        "ts": iso8601_utc_now(),
                        "sample_hz": sample_hz,
                        "backend_latency_ms": elapsed_ms,
                        "dropped_frames": 0,
                    }
                )
                self.stop_event.wait(interval_s)
                continue

            now = time.monotonic()
            if now - last_running_metrics_ts >= RUNNING_METRICS_INTERVAL_S:
                self.broadcast(
                    {
                        "type": "metrics",
                        "ts": iso8601_utc_now(),
                        "sample_hz": 0,
                        "backend_latency_ms": 0,
                        "dropped_frames": 0,
                    }
                )
                last_running_metrics_ts = now
            self.stop_event.wait(0.1)

    def _has_clients(self) -> bool:
        with self.clients_lock:
            return bool(self.clients)


APP = AppState()


class DebugHTTPRequestHandler(BaseHTTPRequestHandler):
    server_version = "WebDebuggerBackend/0.2"

    def log_message(self, fmt: str, *args) -> None:
        print(f"{iso8601_utc_now()} {self.address_string()} {fmt % args}")

    def do_GET(self) -> None:
        try:
            self._do_get()
        except SessionError as exc:
            self.log_message('api error "%s %s": %s (%s)', self.command, self.path, exc.error, exc.detail)
            self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": exc.error, "detail": exc.detail},
            )
        except Exception as exc:
            self.log_message('api exception "%s %s": %s', self.command, self.path, str(exc))
            self._json_response(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"ok": False, "error": "internal_error", "detail": str(exc)},
            )

    def do_POST(self) -> None:
        try:
            self._do_post()
        except SessionError as exc:
            self.log_message('api error "%s %s": %s (%s)', self.command, self.path, exc.error, exc.detail)
            self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": exc.error, "detail": exc.detail},
            )
        except Exception as exc:
            self.log_message('api exception "%s %s": %s', self.command, self.path, str(exc))
            self._json_response(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"ok": False, "error": "internal_error", "detail": str(exc)},
            )

    def do_DELETE(self) -> None:
        try:
            self._do_delete()
        except SessionError as exc:
            status = HTTPStatus.NOT_FOUND if exc.error == "not_found" else HTTPStatus.BAD_REQUEST
            self.log_message('api error "%s %s": %s (%s)', self.command, self.path, exc.error, exc.detail)
            self._json_response(
                status,
                {"ok": False, "error": exc.error, "detail": exc.detail},
            )
        except Exception as exc:
            self.log_message('api exception "%s %s": %s', self.command, self.path, str(exc))
            self._json_response(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"ok": False, "error": "internal_error", "detail": str(exc)},
            )

    def _do_get(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            self._serve_static("index.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/ws" and self.headers.get("Upgrade", "").lower() == "websocket":
            self._handle_websocket()
            return
        if parsed.path == "/api/v1/target/registers":
            self._json_response(HTTPStatus.OK, {"ok": True, **APP.session.register_snapshot()})
            return
        if parsed.path == "/api/v1/target/memory":
            self._handle_get_memory(parsed.query)
            return
        if parsed.path == "/api/v1/config":
            self._json_response(HTTPStatus.OK, {"ok": True, **APP.get_config()})
            return
        if parsed.path == "/api/v1/watches":
            self._json_response(HTTPStatus.OK, {"ok": True, "watches": APP.session.list_watches()})
            return
        if parsed.path == "/api/v1/session":
            self._json_response(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "state": APP.session.state,
                    "target": APP.session.target,
                    "transport": APP.session.transport,
                },
            )
            return
        self._json_response(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})

    def _do_post(self) -> None:
        parsed = urlparse(self.path)
        body = self._read_json_body()
        if parsed.path == "/api/v1/session/connect":
            target = body.get("target", "lpc1114")
            transport = body.get("transport", "swd")
            result = APP.session.connect(target, transport)
            APP.broadcast_status("connected")
            self._json_response(HTTPStatus.OK, result)
            return
        if parsed.path == "/api/v1/session/disconnect":
            result = APP.session.disconnect()
            APP.broadcast_status("disconnected")
            self._json_response(HTTPStatus.OK, result)
            return
        if parsed.path == "/api/v1/target/run":
            result = APP.session.run()
            APP.broadcast_status("run")
            self._json_response(HTTPStatus.OK, result)
            return
        if parsed.path == "/api/v1/target/halt":
            result = APP.session.halt()
            APP.broadcast_status("halt")
            self._json_response(HTTPStatus.OK, result)
            return
        if parsed.path == "/api/v1/target/step":
            try:
                count = int(body.get("count", 1))
            except ValueError:
                raise SessionError("bad_request", "step count must be an integer")
            result = APP.session.step(count)
            APP.broadcast_status("step")
            self._json_response(HTTPStatus.OK, result)
            APP.broadcast(APP.session.register_snapshot())
            for snapshot in APP.session.memory_snapshots():
                APP.broadcast(snapshot)
            return
        if parsed.path == "/api/v1/target/reset":
            mode = body.get("mode", "halt")
            result = APP.session.reset(mode)
            APP.broadcast_status("reset")
            self._json_response(HTTPStatus.OK, result)
            return
        if parsed.path == "/api/v1/watch":
            try:
                name = str(body["name"])
                address = int(str(body["address"]), 0)
                length = int(body["length"])
            except (KeyError, ValueError):
                raise SessionError("bad_request", "name, address, length required")
            result = APP.session.set_watch(name, address, length)
            self._json_response(HTTPStatus.OK, result)
            return
        if parsed.path == "/api/v1/config":
            try:
                halted_sample_hz = int(body["halted_sample_hz"])
            except (KeyError, ValueError, TypeError):
                raise SessionError("bad_request", "halted_sample_hz integer required")
            result = APP.set_config(halted_sample_hz)
            self._json_response(HTTPStatus.OK, {"ok": True, **result})
            return
        self._json_response(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})

    def _do_delete(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/v1/watch":
            params = parse_qs(parsed.query)
            name = params.get("name", [""])[0]
            if not name:
                raise SessionError("bad_request", "watch name is required")
            result = APP.session.remove_watch(name)
            self._json_response(HTTPStatus.OK, result)
            return
        self._json_response(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})

    def _handle_get_memory(self, query: str) -> None:
        params = parse_qs(query)
        try:
            address = int(params.get("address", ["0x10000000"])[0], 0)
            length = int(params.get("length", ["16"])[0], 0)
        except ValueError:
            raise SessionError("bad_request", "invalid address or length")
        data = APP.session.read_memory(address, length)
        self._json_response(
            HTTPStatus.OK,
            {
                "ok": True,
                "address": f"0x{address:08x}",
                "length": length,
                "data_hex": data.hex(),
            },
        )

    def _read_json_body(self) -> Dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def _json_response(self, status: HTTPStatus, payload: Dict) -> None:
        encoded = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def _serve_static(self, name: str, content_type: str) -> None:
        path = STATIC_DIR / name
        if not path.is_file():
            self._json_response(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
            return
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _handle_websocket(self) -> None:
        key = self.headers.get("Sec-WebSocket-Key")
        if not key:
            self.send_error(HTTPStatus.BAD_REQUEST, "Missing Sec-WebSocket-Key")
            return
        accept = base64.b64encode(hashlib.sha1((key + WS_MAGIC).encode("ascii")).digest()).decode("ascii")
        self.send_response(HTTPStatus.SWITCHING_PROTOCOLS)
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()

        client = WebSocketClient(self)
        APP.add_client(client)
        APP.broadcast_status("ws_client_connected")

        try:
            while True:
                time.sleep(1.0)
                if client.closed:
                    break
        except OSError:
            pass
        finally:
            APP.remove_client(client)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Web debugger backend")
    parser.add_argument("--host", default="127.0.0.1", help="bind address")
    parser.add_argument("--port", default=8765, type=int, help="TCP port")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), DebugHTTPRequestHandler)
    print(f"{iso8601_utc_now()} listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            APP.session.disconnect()
        except Exception:
            pass
        APP.stop()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
