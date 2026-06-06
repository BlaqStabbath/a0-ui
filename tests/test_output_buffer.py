"""Tests for pty.output_buffer."""
import pytest

from a0_ui.pty.output_buffer import OutputBuffer


def test_empty_buffer_returns_zero_seq_and_no_bytes():
    buf = OutputBuffer()
    seq, data = buf.drain_since(0)
    assert seq == 0
    assert data == b""


def test_append_returns_starting_seq_and_increments_next_seq():
    buf = OutputBuffer()
    s = buf.append(b"hello")
    assert s == 0
    assert buf.next_seq == 5


def test_drain_since_returns_bytes_after_seq():
    buf = OutputBuffer()
    buf.append(b"hello world")
    seq, data = buf.drain_since(6)
    assert seq == 11
    assert data == b"world"


def test_drain_since_with_seq_in_middle():
    buf = OutputBuffer()
    buf.append(b"abcdef")
    seq, data = buf.drain_since(2)
    assert seq == 6
    assert data == b"cdef"


def test_buffer_truncates_old_bytes_when_over_cap():
    buf = OutputBuffer(max_bytes=8)
    buf.append(b"0123456789")  # 10 bytes
    # buffer should hold only the last 8 bytes: "23456789"
    # next_seq should still be 10 (we tracked all 10)
    assert buf.next_seq == 10
    # drain from seq 0 → buffer doesn't go back that far
    seq, data = buf.drain_since(0)
    assert seq == 2  # oldest byte in buffer is at seq 2
    assert data == b"23456789"


def test_drain_since_too_old_returns_current_window():
    buf = OutputBuffer(max_bytes=4)
    buf.append(b"abcdefgh")  # 8 bytes total
    seq, data = buf.drain_since(0)
    assert seq == 4  # we only have the last 4
    assert data == b"efgh"
