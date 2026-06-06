"""shell_session: PTY <-> WebSocket bridge.

Exposes `serve_shell_session` so tests can drive the bridge end-to-end
without going through the full app.main() entry point.
"""
import asyncio
import os
import subprocess

from websockets.asyncio.server import serve


async def _handler(ws, command: str) -> None:
    import pty as _pty

    master_fd, slave_fd = _pty.openpty()
    proc = subprocess.Popen(
        command,
        shell=True,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        close_fds=True,
    )
    os.close(slave_fd)

    loop = asyncio.get_running_loop()

    def on_read() -> None:
        try:
            data = os.read(master_fd, 4096)
        except OSError:
            return
        if not data:
            return
        try:
            asyncio.run_coroutine_threadsafe(
                ws.send(data.decode("utf-8", errors="replace")), loop
            )
        except Exception:
            pass

    loop.add_reader(master_fd, on_read)
    try:
        async for msg in ws:
            data = (
                bytes(msg)
                if isinstance(msg, (bytes, bytearray))
                else msg.encode("utf-8", errors="replace")
            )
            try:
                os.write(master_fd, data)
            except OSError:
                break
    finally:
        try:
            loop.remove_reader(master_fd)
        except Exception:
            pass
        try:
            os.close(master_fd)
        except Exception:
            pass
        try:
            proc.terminate()
        except Exception:
            pass


async def serve_shell_session(host: str, port: int, command: str) -> None:
    """Run a WebSocket server that bridges PTY output to clients.

    Runs forever; cancel the task to stop the server.
    """
    async with serve(lambda ws: _handler(ws, command), host, port):
        await asyncio.Future()  # run until cancelled
