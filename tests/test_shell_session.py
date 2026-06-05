"""Integration tests for shell_session (WebSocket transport over PtyBridge)."""
import asyncio
import socket
import sys
import threading
import time
from unittest import mock

import pytest
import websockets

from a0_ui.pty_bridge import PtyBridge
from a0_ui import app
from a0_ui.shell_session import _handler  # noqa: F401  (smoke import)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only test (uses bash)")
def test_shell_session_echoes_entry_command_output_to_websocket():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    bridge = PtyBridge('bash -c "echo hello-from-shell-session; exec bash"')
    bridge.start()

    server_ready = threading.Event()

    async def runner():
        async with websockets.serve(
            lambda ws: _handler(ws, bridge), "127.0.0.1", port
        ):
            server_ready.set()
            await asyncio.Future()

    def server_thread():
        asyncio.run(runner())

    t = threading.Thread(target=server_thread, daemon=True)
    t.start()
    server_ready.wait(timeout=2.0)
    time.sleep(0.2)

    async def client():
        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
            return msg

    output = asyncio.run(client())
    assert "hello-from-shell-session" in output

    bridge.stop()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only test (uses bash)")
def test_pty_bridge_buffer_records_output():
    bridge = PtyBridge('bash -c "echo buffered-output; exit 0"')
    bridge.start()
    time.sleep(0.5)  # let the echo happen
    seq, data = bridge.read_since(0)
    assert "buffered-output" in data.decode("utf-8", errors="replace")
    bridge.stop()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only test (uses controlling PTY)")
def test_pty_bridge_child_has_controlling_terminal_for_job_control():
    bridge = PtyBridge(
        'bash -ic "echo job-control-check; jobs >/dev/null; echo job-control-ok; exit"'
    )
    bridge.start()
    time.sleep(0.8)
    _, data = bridge.read_since(0)
    bridge.stop()

    output = data.decode("utf-8", errors="replace")
    assert "job-control-ok" in output
    assert "cannot set terminal process group" not in output
    assert "no job control" not in output


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only test (uses PTY ioctl)")
def test_shell_session_resize_message_resizes_pty():
    bridge = PtyBridge('bash -c "stty size; sleep 0.5; stty size; exit 0"')
    bridge.start()

    async def resize_client():
        class FakeWs:
            async def send(self, _data):
                pass

            def __aiter__(self):
                self._messages = iter(['{"type":"resize","cols":132,"rows":43}'])
                return self

            async def __anext__(self):
                try:
                    return next(self._messages)
                except StopIteration:
                    raise StopAsyncIteration

        await _handler(FakeWs(), bridge)

    try:
        asyncio.run(resize_client())
        time.sleep(0.8)
        _, data = bridge.read_since(0)
    finally:
        bridge.stop()

    assert "43 132" in data.decode("utf-8", errors="replace")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only test (uses bash)")
def test_app_start_servers_publishes_browser_origin_websocket():
    with mock.patch.dict(
        "os.environ",
        {"A0_CLI_CMD": 'printf app-websocket-ready\\\\n; exec bash'},
        clear=True,
    ):
        bridge = app._start_servers()

    async def client():
        async with websockets.connect(
            f"ws://127.0.0.1:{app._ws_port[0]}/",
            origin="null",
        ) as ws:
            return await asyncio.wait_for(ws.recv(), timeout=5.0)

    try:
        output = asyncio.run(client())
    finally:
        bridge.stop()

    assert "app-websocket-ready" in output
