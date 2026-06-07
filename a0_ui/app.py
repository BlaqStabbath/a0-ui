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
import urllib.request
from collections import deque
from webview import settings as webview_settings

from a0_ui.polling import serve_polling
from a0_ui.pty_bridge import RestartablePtyBridge
from a0_ui.runtime.config import load_config
from a0_ui.shell_session import serve_shell_session
from a0_ui.terminal.command_builder import build_shell_command

WINDOW_W, WINDOW_H = 1200, 800

_ws_port = [0]
_http_port = [0]
_wrapper_port = [0]
_terminal_bridge: list[RestartablePtyBridge | None] = [None]
_wrapper_events = deque(maxlen=300)
_wrapper_events_lock = threading.Lock()


def _record_event(message: str) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with _wrapper_events_lock:
        _wrapper_events.append(f"[{timestamp}] {message}")


def _format_wrapper_events() -> str:
    with _wrapper_events_lock:
        events = list(_wrapper_events)
    if not events:
        return "=== wrapper events ===\n(no wrapper events recorded)\n"
    return "=== wrapper events ===\n" + "\n".join(events) + "\n"


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
    out = _format_wrapper_events()
    if not shutil.which("docker"):
        return out + "\n=== docker logs ===\ndocker not found on PATH\n"
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
        _record_event("docker restart requested but docker was not found on PATH")
        return {"ok": False, "error": "docker not found on PATH"}
    container = load_config().container
    _record_event(f"docker restart requested for container {container}")

    def run():
        try:
            r = subprocess.run(
                ["docker", "restart", container],
                capture_output=True, text=True, timeout=60,
            )
            if r.returncode == 0:
                _record_event(f"docker restart completed for container {container}")
            else:
                error = (r.stderr or r.stdout or f"exit {r.returncode}").strip()
                _record_event(f"docker restart failed for container {container}: {error}")
        except Exception as e:
            _record_event(f"docker restart raised for container {container}: {e}")

    threading.Thread(target=run, daemon=True).start()
    return {"ok": True}


def restart_cli() -> dict:
    bridge = _terminal_bridge[0]
    if bridge is None:
        _record_event("A0 CLI restart requested but terminal bridge is not started")
        return {"ok": False, "error": "terminal bridge not started"}
    try:
        _record_event("A0 CLI restart requested")
        bridge.restart()
    except Exception as e:
        _record_event(f"A0 CLI restart failed: {e}")
        return {"ok": False, "error": str(e)}
    _record_event("A0 CLI restart completed")
    return {"ok": True}


def check_a0_ready() -> dict:
    """Return readiness from the wrapper backend, not browser fetch/CORS."""
    if not shutil.which("docker"):
        _record_event("readiness check failed: docker not found on PATH")
        return {"ok": False, "running": False, "webui_ready": False, "error": "docker not found on PATH"}
    config = load_config()
    try:
        r = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", config.container],
            capture_output=True, text=True, timeout=5,
        )
    except Exception as e:
        _record_event(f"readiness check failed while inspecting container {config.container}: {e}")
        return {"ok": False, "running": False, "webui_ready": False, "error": str(e)}

    running = r.returncode == 0 and (r.stdout or "").strip().lower() == "true"
    if not running:
        _record_event(f"readiness check: container {config.container} is not running")
        return {
            "ok": False,
            "running": False,
            "webui_ready": False,
            "error": (r.stderr or r.stdout or "container is not running").strip(),
        }

    try:
        req = urllib.request.Request(config.webui_url, method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            webui_ready = resp.status < 500
    except Exception as e:
        _record_event(f"readiness check: container {config.container} running, Web UI not ready: {e}")
        return {"ok": False, "running": True, "webui_ready": False, "error": str(e)}

    if webui_ready:
        _record_event(f"readiness check passed for container {config.container} and Web UI {config.webui_url}")
    else:
        _record_event(f"readiness check: Web UI {config.webui_url} returned server error")
    return {"ok": webui_ready, "running": True, "webui_ready": webui_ready}


def open_webui() -> dict:
    url = load_config().webui_url
    ok = webbrowser.open(url)
    _record_event(f"open browser requested for Web UI {url}: {'ok' if ok else 'failed'}")
    return {"ok": ok}


def _webview_storage_path() -> str:
    data_home = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(data_home, "a0-ui", "webview")


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _start_servers() -> RestartablePtyBridge:
    config = load_config()
    command = build_shell_command(config.entry_cmd)
    _record_event(f"starting A0 CLI bridge with command: {config.entry_cmd}")
    bridge = RestartablePtyBridge(command)
    bridge.start()
    _terminal_bridge[0] = bridge

    ws_port = _free_port()
    http_port = _free_port()
    _ws_port[0] = ws_port
    _http_port[0] = http_port
    _record_event(f"terminal servers allocated: ws_port={ws_port}, http_port={http_port}")

    def run_ws():
        asyncio.run(serve_shell_session(bridge, "127.0.0.1", ws_port))

    def run_http():
        serve_polling(bridge, "127.0.0.1", http_port)

    threading.Thread(target=run_ws, daemon=True).start()
    threading.Thread(target=run_http, daemon=True).start()
    _record_event("terminal WebSocket and polling servers started")
    time.sleep(0.3)
    return bridge


class Api:
    def get_status(self):
        return get_status()

    def get_logs(self):
        return get_logs()

    def restart_a0(self):
        return restart_a0()

    def restart_cli(self):
        return restart_cli()

    def check_a0_ready(self):
        return check_a0_ready()

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
    _record_event("a0-ui wrapper starting")
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
    _record_event(f"pywebview starting with wrapper_port={wrapper_port}, storage_path={storage_path}")
    webview.start(
        private_mode=False,
        storage_path=storage_path,
        http_server=True,
        http_port=wrapper_port,
    )


if __name__ == "__main__":
    main()
