"""Integration tests for shell_session.

Exercises the PTY <-> WebSocket bridge end-to-end with a real PTY and a
real WebSocket client. The test sets A0_CLI_CMD to a benign command and
verifies the expected output reaches the WebSocket.
"""
import asyncio
import os
import sys
import unittest.mock as mock

import pytest
import websockets

from a0_ui.shell_session import _handler


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only test (uses bash)")
def test_shell_session_echoes_entry_command_output_to_websocket():
    """Spawn a benign command via shell_session and verify WS output."""
    import socket
    import threading

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    command = 'bash -c "echo hello-from-shell-session; exec bash"'

    server_ready = threading.Event()

    async def runner():
        async with websockets.serve(
            lambda ws: _handler(ws, command), "127.0.0.1", port
        ):
            server_ready.set()
            await asyncio.Future()  # run until cancelled

    import time

    def server_thread():
        asyncio.run(runner())

    t = threading.Thread(target=server_thread, daemon=True)
    t.start()
    server_ready.wait(timeout=2.0)
    time.sleep(0.2)  # let the server fully bind

    async def client():
        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
            return msg

    output = asyncio.run(client())
    assert "hello-from-shell-session" in output
