"""shell_session: WebSocket transport for a PtyBridge.

Subscribes to bridge output and forwards it to the WebSocket client.
Receives WebSocket messages and writes them to the bridge (PTY input).
"""
from __future__ import annotations

import asyncio

from websockets.asyncio.server import serve

from a0_ui.pty_bridge import PtyBridge


async def _handler(ws, bridge: PtyBridge) -> None:
    loop = asyncio.get_running_loop()

    # Replay buffered output first so a freshly-connected client sees the
    # current terminal state (prompt, prior output, etc.). Then subscribe
    # to new bytes for streaming.
    _, buffered = bridge.read_since(0)
    if buffered:
        try:
            await ws.send(buffered.decode("utf-8", errors="replace"))
        except Exception:
            return

    def on_data(data: bytes) -> None:
        try:
            asyncio.run_coroutine_threadsafe(
                ws.send(data.decode("utf-8", errors="replace")), loop
            )
        except Exception:
            pass

    bridge.subscribe(on_data)
    try:
        async for msg in ws:
            data = (
                bytes(msg)
                if isinstance(msg, (bytes, bytearray))
                else msg.encode("utf-8", errors="replace")
            )
            try:
                bridge.write(data)
            except Exception:
                break
    finally:
        bridge.unsubscribe(on_data)


async def serve_shell_session(bridge: PtyBridge, host: str, port: int) -> None:
    """Run a WebSocket server attached to `bridge`. Cancel the task to stop."""
    async with serve(lambda ws: _handler(ws, bridge), host, port):
        await asyncio.Future()  # run until cancelled
