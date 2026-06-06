"""Tests for terminal.command_builder."""
import sys
from unittest import mock

import pytest

from a0_ui.terminal.command_builder import build_shell_command


@pytest.mark.parametrize(
    "platform,expected",
    [
        ("linux", 'bash -c "a0; exec bash"'),
        ("darwin", 'bash -c "a0; exec bash"'),
        ("win32", 'cmd /k "a0"'),
    ],
)
def test_build_shell_command_for_default_entry(platform, expected):
    with mock.patch.object(sys, "platform", platform):
        assert build_shell_command("a0") == expected


@pytest.mark.parametrize(
    "platform,expected",
    [
        ("linux", 'bash -c "python -m a0; exec bash"'),
        ("darwin", 'bash -c "python -m a0; exec bash"'),
        ("win32", 'cmd /k "python -m a0"'),
    ],
)
def test_build_shell_command_propagates_custom_entry(platform, expected):
    with mock.patch.object(sys, "platform", platform):
        assert build_shell_command("python -m a0") == expected
