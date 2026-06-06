"""terminal.command_builder: build platform-appropriate shell commands."""
import sys


def build_shell_command(entry_cmd: str) -> str:
    if sys.platform == "win32":
        return f'cmd /k "{entry_cmd}"'
    return f'bash -c "{entry_cmd}; exec bash"'
