#!/usr/bin/env python3
"""Local HTTP + WebSocket bridge for the ultrasonic waveform web app."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import socket
import threading
import time
from dataclasses import dataclass
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import serial


STATIC_DIR = Path(__file__).resolve().parent / "static"
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def recv_exact(sock: socket.socket, length: int) -> bytes:
    data = bytearray()
    while len(data) < length:
        chunk = sock.recv(length - len(data))
        if not chunk:
            raise ConnectionError("socket closed")
        data.extend(chunk)
    return bytes(data)


def send_ws_text(sock: socket.socket, payload: str, send_lock: threading.Lock) -> None:
    data = payload.encode("utf-8")
    header = bytearray()
    header.append(0x81)
    length = len(data)
    if length < 126:
        header.append(length)
    elif length <= 0xFFFF:
        header.append(126)
        header.extend(length.to_bytes(2, "big"))
    else:
        header.append(127)
        header.extend(length.to_bytes(8, "big"))
    with send_lock:
        sock.sendall(bytes(header) + data)


def send_ws_pong(sock: socket.socket, payload: bytes, send_lock: threading.Lock) -> None:
    header = bytearray([0x8A])
    length = len(payload)
    if length < 126:
        header.append(length)
    elif length <= 0xFFFF:
        header.append(126)
        header.extend(length.to_bytes(2, "big"))
    else:
        header.append(127)
        header.extend(length.to_bytes(8, "big"))
    with send_lock:
        sock.sendall(bytes(header) + payload)


def recv_ws_frame(sock: socket.socket) -> tuple[int, bytes]:
    first = recv_exact(sock, 2)
    opcode = first[0] & 0x0F
    masked = bool(first[1] & 0x80)
    length = first[1] & 0x7F
    if length == 126:
        length = int.from_bytes(recv_exact(sock, 2), "big")
    elif length == 127:
        length = int.from_bytes(recv_exact(sock, 8), "big")
    mask = recv_exact(sock, 4) if masked else b""
    payload = recv_exact(sock, length) if length else b""
    if masked:
        payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    return opcode, payload


def read_http_headers(sock: socket.socket) -> tuple[str, dict[str, str]]:
    data = bytearray()
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("socket closed during handshake")
        data.extend(chunk)
        if len(data) > 65536:
            raise ConnectionError("HTTP header too large")
    raw_headers = bytes(data).split(b"\r\n\r\n", 1)[0].decode("latin1")
    lines = raw_headers.split("\r\n")
    request_line = lines[0]
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    return request_line, headers


@dataclass
class BridgeStatus:
    serial_state: str
    message: str
    port: str
    baud: int


class WebSocketClient:
    def __init__(self, sock: socket.socket, address: tuple[str, int], bridge: "SerialBridge", verbose: bool) -> None:
        self.sock = sock
        self.address = address
        self.bridge = bridge
        self.verbose = verbose
        self.send_lock = threading.Lock()
        self.closed = False

    def send_json(self, payload: dict[str, Any]) -> None:
        if self.closed:
            return
        send_ws_text(self.sock, json.dumps(payload, separators=(",", ":")), self.send_lock)

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            self.sock.close()
        except OSError:
            pass


class SerialBridge:
    def __init__(self, port: str, baud: int, verbose: bool) -> None:
        self.port = port
        self.baud = baud
        self.verbose = verbose
        self._stop = threading.Event()
        self._clients: set[WebSocketClient] = set()
        self._clients_lock = threading.Lock()
        self._serial_lock = threading.Lock()
        self._serial: serial.Serial | None = None
        self._line_buffer = bytearray()
        self._status = BridgeStatus(
            serial_state="starting",
            message="serial bridge starting",
            port=self.port,
            baud=self.baud,
        )
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)

    def start(self) -> None:
        self._reader_thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._reader_thread.join(timeout=1.0)
        self._close_serial()

    def log(self, message: str) -> None:
        if self.verbose:
            print(message)

    def add_client(self, client: WebSocketClient) -> None:
        with self._clients_lock:
            self._clients.add(client)
        client.send_json(
            {
                "type": "hello",
                "transport": "websocket",
                "serial_port": self.port,
                "serial_baud": self.baud,
            }
        )
        client.send_json(
            {
                "type": "status",
                "serial": self._status.serial_state,
                "message": self._status.message,
                "port": self._status.port,
                "baud": self._status.baud,
            }
        )

    def remove_client(self, client: WebSocketClient) -> None:
        with self._clients_lock:
            self._clients.discard(client)
        client.close()

    def _broadcast(self, payload: dict[str, Any]) -> None:
        stale: list[WebSocketClient] = []
        with self._clients_lock:
            clients = list(self._clients)
        for client in clients:
            try:
                client.send_json(payload)
            except OSError:
                stale.append(client)
        if stale:
            with self._clients_lock:
                for client in stale:
                    self._clients.discard(client)
            for client in stale:
                client.close()

    def _set_status(self, serial_state: str, message: str) -> None:
        status = BridgeStatus(serial_state=serial_state, message=message, port=self.port, baud=self.baud)
        if status == self._status:
            return
        self._status = status
        self.log(f"bridge status: {serial_state}: {message}")
        self._broadcast(
            {
                "type": "status",
                "serial": serial_state,
                "message": message,
                "port": self.port,
                "baud": self.baud,
            }
        )

    def send_line(self, line: str) -> None:
        with self._serial_lock:
            if self._serial is None:
                raise RuntimeError("serial port is not open")
            self._serial.write(f"{line}\r\n".encode("ascii"))
            self._serial.flush()

    def _open_serial(self) -> None:
        with self._serial_lock:
            if self._serial is not None:
                return
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baud,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.05,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False,
            )
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()

    def _close_serial(self) -> None:
        with self._serial_lock:
            if self._serial is not None:
                try:
                    self._serial.close()
                except serial.SerialException:
                    pass
                self._serial = None

    def _emit_serial_lines(self, chunk: bytes) -> None:
        self._line_buffer.extend(chunk)
        while True:
            newline_index = self._line_buffer.find(b"\n")
            if newline_index < 0:
                break
            raw = bytes(self._line_buffer[:newline_index])
            del self._line_buffer[: newline_index + 1]
            if raw.endswith(b"\r"):
                raw = raw[:-1]
            if not raw:
                continue
            line = raw.decode("latin1", errors="replace")
            self._broadcast({"type": "line", "line": line})

    def _reader_loop(self) -> None:
        retry_delay_s = 0.5
        while not self._stop.is_set():
            if self._serial is None:
                try:
                    self._open_serial()
                    self._set_status("connected", "serial connected")
                except serial.SerialException as exc:
                    self._set_status("error", f"serial open failed: {exc}")
                    time.sleep(retry_delay_s)
                    continue

            try:
                assert self._serial is not None
                chunk = self._serial.read(4096)
                if chunk:
                    self._emit_serial_lines(chunk)
            except (serial.SerialException, TypeError, OSError) as exc:
                if self._stop.is_set():
                    break
                self._set_status("error", f"serial read failed: {exc}")
                self._close_serial()
                time.sleep(retry_delay_s)


class WebSocketBridgeServer:
    def __init__(self, host: str, port: int, bridge: SerialBridge, verbose: bool) -> None:
        self.host = host
        self.port = port
        self.bridge = bridge
        self.verbose = verbose
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._listener: socket.socket | None = None

    def log(self, message: str) -> None:
        if self.verbose:
            print(message)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._listener is not None:
            try:
                self._listener.close()
            except OSError:
                pass
        self._thread.join(timeout=1.0)

    def _serve(self) -> None:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((self.host, self.port))
        listener.listen()
        listener.settimeout(0.5)
        self._listener = listener
        self.log(f"WebSocket bridge listening on ws://{self.host}:{self.port}/")
        while not self._stop.is_set():
            try:
                conn, address = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            thread = threading.Thread(target=self._handle_client, args=(conn, address), daemon=True)
            thread.start()

    def _handle_client(self, conn: socket.socket, address: tuple[str, int]) -> None:
        client = WebSocketClient(conn, address, self.bridge, self.verbose)
        try:
            request_line, headers = read_http_headers(conn)
            if not request_line.startswith("GET "):
                raise ConnectionError("invalid WebSocket request line")
            key = headers.get("sec-websocket-key")
            upgrade = headers.get("upgrade", "").lower()
            if not key or upgrade != "websocket":
                raise ConnectionError("missing websocket upgrade headers")
            accept = base64.b64encode(hashlib.sha1((key + WS_GUID).encode("ascii")).digest()).decode("ascii")
            response = (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {accept}\r\n"
                "\r\n"
            )
            conn.sendall(response.encode("ascii"))
            self.bridge.add_client(client)
            self.log(f"WebSocket client connected: {address[0]}:{address[1]}")

            while not self._stop.is_set() and not client.closed:
                opcode, payload = recv_ws_frame(conn)
                if opcode == 0x8:
                    break
                if opcode == 0x9:
                    send_ws_pong(conn, payload, client.send_lock)
                    continue
                if opcode != 0x1:
                    continue
                try:
                    message = json.loads(payload.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    client.send_json({"type": "error", "message": "invalid JSON"})
                    continue
                self._handle_message(client, message)
        except (ConnectionError, OSError) as exc:
            self.log(f"WebSocket client disconnected: {address[0]}:{address[1]} ({exc})")
        finally:
            self.bridge.remove_client(client)

    def _handle_message(self, client: WebSocketClient, message: dict[str, Any]) -> None:
        message_type = message.get("type")
        if message_type == "send_line":
            line = str(message.get("line", ""))
            if not line:
                client.send_json({"type": "error", "message": "empty command"})
                return
            try:
                self.bridge.send_line(line)
            except RuntimeError as exc:
                client.send_json({"type": "error", "message": str(exc)})
        elif message_type == "ping":
            client.send_json({"type": "pong"})
        else:
            client.send_json({"type": "error", "message": f"unsupported message type: {message_type}"})


class AppHandler(SimpleHTTPRequestHandler):
    bridge: SerialBridge | None = None
    ws_port: int = 8788

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def do_GET(self) -> None:
        if self.path == "/api/health":
            bridge = type(self).bridge
            body = json.dumps(
                {
                    "status": "ok",
                    "ws_port": type(self).ws_port,
                    "serial_port": bridge.port if bridge else None,
                    "serial_baud": bridge.baud if bridge else None,
                }
            ).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return super().do_GET()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the ultrasonic waveform web app with a local serial bridge")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP and WebSocket bind host, default: 127.0.0.1")
    parser.add_argument("--port", type=int, default=8787, help="HTTP bind port, default: 8787")
    parser.add_argument("--ws-port", type=int, default=8788, help="WebSocket bind port, default: 8788")
    parser.add_argument("--uart-port", default="/dev/ttyACM0", help="UART device path, default: /dev/ttyACM0")
    parser.add_argument("--uart-baud", type=int, default=230400, help="UART baud rate, default: 230400")
    parser.add_argument("--verbose", action="store_true", help="Print bridge status and connection logs")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    bridge = SerialBridge(port=args.uart_port, baud=args.uart_baud, verbose=args.verbose)
    bridge.start()

    websocket_server = WebSocketBridgeServer(args.host, args.ws_port, bridge, args.verbose)
    websocket_server.start()

    AppHandler.bridge = bridge
    AppHandler.ws_port = args.ws_port
    httpd = ThreadingHTTPServer((args.host, args.port), AppHandler)

    print(f"Serving ultrasonic waveform web app at http://{args.host}:{args.port}/")
    print(f"WebSocket bridge available at ws://{args.host}:{args.ws_port}/")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        websocket_server.stop()
        bridge.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
