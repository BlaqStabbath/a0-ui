"""a0-ui: cross-platform desktop wrapper for the Agent Zero Web UI."""
import argparse
import os
import threading
import subprocess
import asyncio
import time
import socket
import shutil
import sys
import webview
from websockets.asyncio.server import serve

from a0_ui.runtime.config import load_config
from a0_ui.shell_session import serve_shell_session
from a0_ui.terminal.command_builder import build_shell_command

WINDOW_W, WINDOW_H = 1200, 800

_ws_port = [0]


def get_status() -> dict:
    config = load_config()
    return {
        "webui_url": config.webui_url,
        "container": config.container,
        "entry_cmd": config.entry_cmd,
        "ws_port": _ws_port[0],
        "platform": config.platform,
    }


def get_logs() -> str:
    out = ""
    if not shutil.which("docker"):
        return "docker not found on PATH"
    container = load_config().container
    try:
        r = subprocess.run(
            ["docker", "logs", "--tail", "150", container],
            capture_output=True, text=True, timeout=5,
        )
        out += "=== docker logs (last 150) ===\n" + (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        out += f"docker logs error: {e}\n"
    try:
        r = subprocess.run(
            ["docker", "exec", container, "ls", "-t", "/a0/logs"],
            capture_output=True, text=True, timeout=5,
        )
        files = [
            ln.strip() for ln in (r.stdout or "").splitlines()
            if ln.strip().endswith(".html")
        ][:3]
        for fn in files:
            r2 = subprocess.run(
                ["docker", "exec", container, "tail", "-n", "40", f"/a0/logs/{fn}"],
                capture_output=True, text=True, timeout=5,
            )
            out += f"\n=== {fn} (last 40) ===\n" + (r2.stdout or "")
    except Exception as e:
        out += f"\nlog file read error: {e}\n"
    return out


def restart_a0() -> dict:
    if not shutil.which("docker"):
        return {"ok": False, "error": "docker not found on PATH"}
    container = load_config().container

    def run():
        subprocess.run(
            ["docker", "restart", container],
            capture_output=True, text=True, timeout=60,
        )

    threading.Thread(target=run, daemon=True).start()
    return {"ok": True}


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _start_ws() -> None:
    port = _free_port()
    _ws_port[0] = port
    config = load_config()
    command = build_shell_command(config.entry_cmd)

    def runner():
        asyncio.run(serve_shell_session("127.0.0.1", port, command))

    threading.Thread(target=runner, daemon=True).start()
    time.sleep(0.3)


class Api:
    def get_status(self):
        return get_status()

    def get_logs(self):
        return get_logs()

    def restart_a0(self):
        return restart_a0()


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="a0-ui")
    p.add_argument("--debug", action="store_true", help="Print diagnostic info to stderr")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    config = load_config()
    # CLI flag wins over env var. Env var is already in config.debug; override
    # if --debug was passed.
    debug_enabled = args.debug or config.debug

    if debug_enabled:
        from a0_ui.diagnostics.debug_dump import dump

        class _WindowStub:
            backend = "pre-create"

        dump(_WindowStub())

    _start_ws()
    api = Api()
    html_path = os.path.join(os.path.dirname(__file__), "web", "index.html")
    window = webview.create_window(
        "Agent Zero",
        url="file://" + html_path,
        width=WINDOW_W,
        height=WINDOW_H,
        js_api=api,
        confirm_close=False,
    )

    if debug_enabled:
        # Re-dump with the real window once it exists (geometry is available
        # only after the window is created).
        from a0_ui.diagnostics.debug_dump import dump

        dump(window)

    webview.start()


if __name__ == "__main__":
    main()
