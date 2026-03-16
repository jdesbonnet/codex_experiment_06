#!/usr/bin/env python3
"""Small localhost server for the ultrasonic waveform web app."""

from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


STATIC_DIR = Path(__file__).resolve().parent / "static"


class AppHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def do_GET(self) -> None:
        if self.path == "/api/health":
            body = json.dumps({"status": "ok"}).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return super().do_GET()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the ultrasonic waveform web app")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host, default: 127.0.0.1")
    parser.add_argument("--port", type=int, default=8787, help="Bind port, default: 8787")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    httpd = ThreadingHTTPServer((args.host, args.port), AppHandler)
    print(f"Serving ultrasonic waveform web app at http://{args.host}:{args.port}/")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
