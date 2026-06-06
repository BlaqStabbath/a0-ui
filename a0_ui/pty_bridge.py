"""pty_bridge: owns the PTY + subprocess + OutputBuffer; transport-agnostic.

Both the WebSocket handler (a0_ui.shell_session) and the HTTP polling
server (a0_ui.polling) attach to a single PtyBridge instance so they
share one PTY and one shell process. Subscribers receive bytes
asynchronously as they arrive; pollers query the OutputBuffer.
"""
from __future__ import annotations

import os
import subprocess
import threading
from typing import Callable

from a0_ui.pty.output_buffer import OutputBuffer


class PtyBridge:
    def __init__(self, command: str, max_buffer_bytes: int = 65536) -> None:
        self.command = command
        self.buffer = OutputBuffer(max_bytes=max_buffer_bytes)
        self._master_fd: int | None = None
        self._proc: subprocess.Popen | None = None
        self._subscribers: list[Callable[[bytes], None]] = []
        self._stopped = False
        self._lock = threading.Lock()
        self._reader_thread: threading.Thread | None = None

    def start(self) -> None:
        import pty as _pty

        master_fd, slave_fd = _pty.openpty()
        self._master_fd = master_fd
        self._proc = subprocess.Popen(
            self.command,
            shell=True,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            close_fds=True,
        )
        os.close(slave_fd)
        self._reader_thread = threading.Thread(target=self._reader, daemon=True)
        self._reader_thread.start()

    def _reader(self) -> None:
        while not self._stopped:
            try:
                data = os.read(self._master_fd, 4096)
            except OSError:
                break
            if not data:
                break
            self.buffer.append(data)
            with self._lock:
                subs = list(self._subscribers)
            for sub in subs:
                try:
                    sub(data)
                except Exception:
                    pass

    def write(self, data: bytes) -> None:
        if self._master_fd is None:
            raise RuntimeError("PtyBridge not started")
        os.write(self._master_fd, data)

    def read_since(self, seq: int) -> tuple[int, bytes]:
        return self.buffer.drain_since(seq)

    def subscribe(self, callback: Callable[[bytes], None]) -> None:
        with self._lock:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[bytes], None]) -> None:
        with self._lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

    def stop(self) -> None:
        self._stopped = True
        if self._proc is not None:
            try:
                self._proc.terminate()
            except Exception:
                pass
        if self._master_fd is not None:
            try:
                os.close(self._master_fd)
            except Exception:
                pass
            self._master_fd = None
