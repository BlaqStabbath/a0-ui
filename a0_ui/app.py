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
import webbrowser
import webview
from webview import settings as webview_settings

from a0_ui.polling import serve_polling
from a0_ui.pty_bridge import PtyBridge
from a0_ui.runtime.config import load_config
from a0_ui.shell_session import serve_shell_session
from a0_ui.terminal.command_builder import build_shell_command

WINDOW_W, WINDOW_H = 1200, 800

_ws_port = [0]
_http_port = [0]
_wrapper_port = [0]


def get_status() -> dict:
    config = load_config()
    return {
        "webui_url": config.webui_url,
        "container": config.container,
        "entry_cmd": config.entry_cmd,
        "ws_port": _ws_port[0],
        "http_port": _http_port[0],
        "wrapper_port": _wrapper_port[0],
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


def open_webui() -> dict:
    url = load_config().webui_url
    return {"ok": webbrowser.open(url)}


def _webview_storage_path() -> str:
    data_home = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(data_home, "a0-ui", "webview")


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _start_servers() -> PtyBridge:
    config = load_config()
    command = build_shell_command(config.entry_cmd)
    bridge = PtyBridge(command)
    bridge.start()

    ws_port = _free_port()
    http_port = _free_port()
    _ws_port[0] = ws_port
    _http_port[0] = http_port

    def run_ws():
        asyncio.run(serve_shell_session(bridge, "127.0.0.1", ws_port))

    def run_http():
        serve_polling(bridge, "127.0.0.1", http_port)

    threading.Thread(target=run_ws, daemon=True).start()
    threading.Thread(target=run_http, daemon=True).start()
    time.sleep(0.3)
    return bridge


class Api:
    def get_status(self):
        return get_status()

    def get_logs(self):
        return get_logs()

    def restart_a0(self):
        return restart_a0()

    def open_webui(self):
        return open_webui()


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="a0-ui")
    p.add_argument("--debug", action="store_true", help="Print diagnostic info to stderr")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    config = load_config()
    debug_enabled = args.debug or config.debug
    webview_settings["ALLOW_FILE_URLS"] = True

    if debug_enabled:
        from a0_ui.diagnostics.debug_dump import dump

        class _WindowStub:
            backend = "pre-create"

        dump(_WindowStub())

    _start_servers()
    api = Api()
    html_path = os.path.join(os.path.dirname(__file__), "web", "index.html")
    wrapper_port = _free_port()
    _wrapper_port[0] = wrapper_port
    window = webview.create_window(
        "Agent Zero",
        url=html_path,
        width=WINDOW_W,
        height=WINDOW_H,
        js_api=api,
        confirm_close=False,
    )

    if debug_enabled:
        from a0_ui.diagnostics.debug_dump import dump

        dump(window)

    storage_path = _webview_storage_path()
    os.makedirs(storage_path, exist_ok=True)
    webview.start(
        private_mode=False,
        storage_path=storage_path,
        http_server=True,
        http_port=wrapper_port,
    )


if __name__ == "__main__":
    main()
