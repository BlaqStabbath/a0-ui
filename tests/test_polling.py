"""Tests for polling endpoint functions (transport-agnostic).

The HTTP server wiring is exercised manually; these tests cover the
contract that GET /pty/output and POST /pty/input implement.
"""
import socket
import sys
import threading
import time
import urllib.request
from unittest import mock

import pytest

from a0_ui.polling import get_output, post_input, serve_polling
from a0_ui.pty_bridge import PtyBridge


def test_get_output_returns_seq_and_bytes_from_bridge():
    bridge = mock.MagicMock()
    bridge.read_since.return_value = (42, b"hello")

    seq, data = get_output(bridge, since=10)

    assert seq == 42
    assert data == b"hello"
    bridge.read_since.assert_called_once_with(10)


def test_get_output_passes_since_zero_by_default():
    bridge = mock.MagicMock()
    bridge.read_since.return_value = (0, b"")

    get_output(bridge)

    bridge.read_since.assert_called_once_with(0)


def test_post_input_writes_bytes_to_bridge():
    bridge = mock.MagicMock()

    post_input(bridge, b"abc")

    bridge.write.assert_called_once_with(b"abc")


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only test (uses bash)")
def test_polling_server_serves_get_output():
    port = _free_port()
    bridge = PtyBridge('bash -c "echo hello-from-polling; sleep 0.1"')
    bridge.start()
    time.sleep(0.3)

    server_thread = threading.Thread(
        target=serve_polling, args=(bridge, "127.0.0.1", port), daemon=True
    )
    server_thread.start()
    time.sleep(0.2)

    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/pty/output?since=0", timeout=2
        ) as resp:
            body = resp.read()
            seq_header = int(resp.headers.get("X-Pty-Seq", "0"))
        assert seq_header > 0
        assert b"hello-from-polling" in body
    finally:
        bridge.stop()

