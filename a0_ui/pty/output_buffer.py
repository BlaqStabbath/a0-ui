"""pty.output_buffer: bounded ring buffer of PTY output with monotonic seq numbers."""


class OutputBuffer:
    """Append-only byte buffer with a max-byte cap and per-byte sequence numbers.

    Sequence numbers are monotonic across the lifetime of the buffer; they
    are NOT reset when the buffer truncates. drain_since(seq) returns
    (current_seq, bytes) — if seq is older than what we still have, it
    returns (oldest_seq, all_current_bytes) so the client can reset.
    """

    def __init__(self, max_bytes: int = 65536) -> None:
        self.max_bytes = max_bytes
        self._buf = bytearray()
        self._oldest_seq = 0
        self.next_seq = 0

    def append(self, data: bytes) -> int:
        """Append data, return the sequence number of the first byte appended."""
        start = self.next_seq
        self._buf.extend(data)
        self.next_seq += len(data)
        if len(self._buf) > self.max_bytes:
            overflow = len(self._buf) - self.max_bytes
            del self._buf[:overflow]
            self._oldest_seq += overflow
        return start

    def drain_since(self, since: int) -> tuple[int, bytes]:
        """Return (current_seq, bytes) where bytes are those with seq > since.

        If `since` is older than the oldest byte we still have, returns
        (oldest_seq, all_current_bytes) so the caller can reset.
        """
        if since < self._oldest_seq:
            return self._oldest_seq, bytes(self._buf)
        offset = since - self._oldest_seq
        return self.next_seq, bytes(self._buf[offset:])
