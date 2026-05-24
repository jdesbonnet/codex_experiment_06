#!/usr/bin/env python3
"""
Debug Adapter Protocol server for tiny_vm.

Speaks DAP framing (Content-Length headers + JSON body). Two transports:

  --stdio       talk DAP over stdin/stdout (used by Theia / VS Code adapters)
  default       TCP listener on --host:--port (host tooling, our own tests)

In TCP mode the chosen port is printed on stdout as one JSON line so the
spawning process can read it back:

    {"port": 12345}

Usage:
    python3 tools/theia/dap/server.py --stdio
    python3 tools/theia/dap/server.py [--port N] [--host 127.0.0.1] [--once]
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import socket
import sys
import threading


_HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from dap.handlers import DapSession  # noqa: E402


def _read_message(sock: socket.socket, buf: bytearray) -> dict | None:
    while True:
        sep = buf.find(b"\r\n\r\n")
        if sep != -1:
            header = bytes(buf[:sep]).decode("ascii", errors="replace")
            length = 0
            for line in header.split("\r\n"):
                if line.lower().startswith("content-length:"):
                    length = int(line.split(":", 1)[1].strip())
                    break
            if len(buf) < sep + 4 + length:
                # need more bytes
                pass
            else:
                body = bytes(buf[sep + 4 : sep + 4 + length])
                del buf[: sep + 4 + length]
                return json.loads(body.decode("utf-8"))
        chunk = sock.recv(4096)
        if not chunk:
            return None
        buf.extend(chunk)


def _write_message(sock: socket.socket, message: dict, lock: threading.Lock) -> None:
    body = json.dumps(message).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    with lock:
        sock.sendall(header + body)


def serve_one(client: socket.socket) -> None:
    send_lock = threading.Lock()

    def send(message: dict) -> None:
        try:
            _write_message(client, message, send_lock)
        except OSError:
            pass

    session = DapSession(send)
    buf = bytearray()
    try:
        while True:
            msg = _read_message(client, buf)
            if msg is None:
                break
            if not session.handle(msg):
                break
    finally:
        try:
            client.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        client.close()


def _read_message_stdio(buf: bytearray) -> dict | None:
    stdin_fd = sys.stdin.buffer.fileno()
    while True:
        sep = buf.find(b"\r\n\r\n")
        if sep != -1:
            header = bytes(buf[:sep]).decode("ascii", errors="replace")
            length = 0
            for line in header.split("\r\n"):
                if line.lower().startswith("content-length:"):
                    length = int(line.split(":", 1)[1].strip())
                    break
            if len(buf) >= sep + 4 + length:
                body = bytes(buf[sep + 4 : sep + 4 + length])
                del buf[: sep + 4 + length]
                return json.loads(body.decode("utf-8"))
        chunk = os.read(stdin_fd, 4096)
        if not chunk:
            return None
        buf.extend(chunk)


def serve_stdio() -> None:
    send_lock = threading.Lock()
    stdout_fd = sys.stdout.buffer.fileno()

    def send(message: dict) -> None:
        body = json.dumps(message).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        with send_lock:
            try:
                os.write(stdout_fd, header + body)
            except OSError:
                pass

    session = DapSession(send)
    buf = bytearray()
    while True:
        msg = _read_message_stdio(buf)
        if msg is None:
            break
        if not session.handle(msg):
            break


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a tiny_vm DAP server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0, help="TCP port (0 = auto)")
    parser.add_argument(
        "--once",
        action="store_true",
        help="serve exactly one client then exit (handy for tests)",
    )
    parser.add_argument(
        "--stdio",
        action="store_true",
        help="speak DAP on stdin/stdout instead of TCP (Theia/VS Code mode)",
    )
    args = parser.parse_args()

    if args.stdio:
        serve_stdio()
        return 0

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((args.host, args.port))
    srv.listen(1)
    port = srv.getsockname()[1]
    # Single-line, machine-readable announcement.
    sys.stdout.write(json.dumps({"port": port}) + "\n")
    sys.stdout.flush()

    try:
        while True:
            client, _addr = srv.accept()
            serve_one(client)
            if args.once:
                break
    except KeyboardInterrupt:
        pass
    finally:
        srv.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
