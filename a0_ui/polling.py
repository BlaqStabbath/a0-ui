"""polling: HTTP polling transport for the embedded terminal.

This module is split into:
- Transport-agnostic functions (get_output, post_input) that operate on
  any object exposing read_since(seq) -> (seq, bytes) and write(data).
  These are unit-tested in tests/test_polling.py.
- A stdlib http.server-based HTTP server (serve_polling) that wires
  those functions to GET /pty/output and POST /pty/input. The server is
  exercised manually; the functions are what matters.
"""
from __future__ import annotations

import asyncio
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Protocol
from urllib.parse import parse_qs, urlparse


class BridgeLike(Protocol):
    def read_since(self, seq: int) -> tuple[int, bytes]: ...
    def write(self, data: bytes) -> None: ...


def get_output(bridge: BridgeLike, since: int = 0) -> tuple[int, bytes]:
    """Read PTY output bytes from `bridge` with sequence > `since`."""
    return bridge.read_since(since)


def post_input(bridge: BridgeLike, data: bytes) -> None:
    """Write input bytes to the PTY via `bridge`."""
    bridge.write(data)


def serve_polling(bridge: BridgeLike, host: str, port: int) -> ThreadingHTTPServer:
    """Start a stdlib HTTP server in this thread. Blocks until shutdown."""
    bridge_ref = bridge

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def _send_cors_headers(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

        def do_OPTIONS(self):
            self.send_response(204)
            self._send_cors_headers()
            self.end_headers()

        def do_GET(self):
            if self.path.startswith("/pty/output"):
                qs = parse_qs(urlparse(self.path).query)
                since = int(qs.get("since", ["0"])[0])
                seq, data = get_output(bridge_ref, since=since)
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("X-Pty-Seq", str(seq))
                self._send_cors_headers()
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_response(404)
                self._send_cors_headers()
                self.end_headers()

        def do_POST(self):
            if self.path.startswith("/pty/input"):
                length = int(self.headers.get("Content-Length", "0"))
                data = self.rfile.read(length) if length else b""
                post_input(bridge_ref, data)
                self.send_response(204)
                self._send_cors_headers()
                self.end_headers()
            else:
                self.send_response(404)
                self._send_cors_headers()
                self.end_headers()

    server = ThreadingHTTPServer((host, port), Handler)
    server.serve_forever()
    return server
