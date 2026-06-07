"""pty_bridge: owns the PTY + subprocess + OutputBuffer; transport-agnostic.

Both the WebSocket handler (a0_ui.shell_session) and the HTTP polling
server (a0_ui.polling) attach to a single PtyBridge instance so they
share one PTY and one shell process. Subscribers receive bytes
asynchronously as they arrive; pollers query the OutputBuffer.
"""
from __future__ import annotations

import os
import signal
import threading
import struct
import fcntl
import termios
from typing import Callable

from a0_ui.pty.output_buffer import OutputBuffer


class PtyBridge:
    def __init__(self, command: str, max_buffer_bytes: int = 65536) -> None:
        self.command = command
        self.buffer = OutputBuffer(max_bytes=max_buffer_bytes)
        self._master_fd: int | None = None
        self._child_pid: int | None = None
        self._subscribers: list[Callable[[bytes], None]] = []
        self._stopped = False
        self._lock = threading.Lock()
        self._reader_thread: threading.Thread | None = None

    def start(self) -> None:
        import pty as _pty

        child_pid, master_fd = _pty.fork()
        if child_pid == 0:
            os.execlp("sh", "sh", "-c", self.command)

        self._master_fd = master_fd
        self._child_pid = child_pid
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

    def resize(self, cols: int, rows: int) -> None:
        if self._master_fd is None:
            raise RuntimeError("PtyBridge not started")
        if cols <= 0 or rows <= 0:
            return
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(self._master_fd, termios.TIOCSWINSZ, winsize)
        if self._child_pid is not None:
            try:
                os.killpg(self._child_pid, signal.SIGWINCH)
            except ProcessLookupError:
                pass

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
        if self._child_pid is not None:
            try:
                os.killpg(self._child_pid, signal.SIGTERM)
            except Exception:
                pass
            self._child_pid = None
        if self._master_fd is not None:
            try:
                os.close(self._master_fd)
            except Exception:
                pass
            self._master_fd = None


class RestartablePtyBridge:
    """Delegating bridge whose underlying PTY process can be replaced."""

    def __init__(self, command: str, max_buffer_bytes: int = 65536) -> None:
        self.command = command
        self.max_buffer_bytes = max_buffer_bytes
        self._bridge: PtyBridge | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self._bridge is not None:
                return
            self._bridge = self._new_bridge()

    def _new_bridge(self) -> PtyBridge:
        bridge = PtyBridge(self.command, max_buffer_bytes=self.max_buffer_bytes)
        bridge.start()
        return bridge

    def restart(self) -> None:
        with self._lock:
            old = self._bridge
            self._bridge = self._new_bridge()
        if old is not None:
            old.stop()

    def stop(self) -> None:
        with self._lock:
            old = self._bridge
            self._bridge = None
        if old is not None:
            old.stop()

    def _current(self) -> PtyBridge:
        bridge = self._bridge
        if bridge is None:
            raise RuntimeError("PtyBridge not started")
        return bridge

    def write(self, data: bytes) -> None:
        self._current().write(data)

    def resize(self, cols: int, rows: int) -> None:
        self._current().resize(cols, rows)

    def read_since(self, seq: int) -> tuple[int, bytes]:
        return self._current().read_since(seq)

    def subscribe(self, callback: Callable[[bytes], None]) -> None:
        self._current().subscribe(callback)

    def unsubscribe(self, callback: Callable[[bytes], None]) -> None:
        try:
            self._current().unsubscribe(callback)
        except RuntimeError:
            pass
