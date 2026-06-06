"""Tests for diagnostics.debug_dump."""
from unittest import mock


def test_dump_writes_expected_keys_to_stderr(capsys):
    from a0_ui.diagnostics.debug_dump import dump

    fake_window = mock.MagicMock()
    fake_window.title = "Agent Zero"
    fake_window.x = 100
    fake_window.y = 200
    fake_window.width = 800
    fake_window.height = 600

    with mock.patch.dict("os.environ", {"DISPLAY": ":1", "XAUTHORITY": "/tmp/xauth"}, clear=True):
        dump(fake_window)

    captured = capsys.readouterr().err
    assert "backend" in captured
    assert "DISPLAY" in captured
    assert "XAUTHORITY" in captured
    assert "geometry" in captured
    assert "window title" in captured


def test_dump_does_not_crash_when_window_attrs_missing(capsys):
    """dump() must never raise, even if the window object is missing attrs."""
    from a0_ui.diagnostics.debug_dump import dump

    broken_window = mock.MagicMock(spec=[])

    with mock.patch.dict("os.environ", {}, clear=True):
        dump(broken_window)

    captured = capsys.readouterr().err
    assert "backend" in captured
    assert "DISPLAY" in captured
    assert "geometry" in captured
