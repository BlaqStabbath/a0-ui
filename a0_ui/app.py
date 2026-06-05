"""a0-ui: cross-platform desktop wrapper for the Agent Zero Web UI."""
import os, threading, subprocess, asyncio, time, socket, shutil
import webview
from websockets.asyncio.server import serve

WEBUI_URL = os.environ.get("A0_WEBUI_URL", "http://localhost:5080")
CONTAINER_NAME = os.environ.get("A0_CONTAINER", "agent-zero")
CLI_CMD = os.environ.get("A0_CLI_CMD", "a0")
WINDOW_W, WINDOW_H = 1200, 800

_ws_port = [0]

def get_status():
    return {"webui_url": WEBUI_URL, "container": CONTAINER_NAME, "cli_cmd": CLI_CMD, "ws_port": _ws_port[0]}

def get_logs() -> str:
    out = ""
    if not shutil.which("docker"):
        return "docker not found on PATH"
    try:
        r = subprocess.run(["docker", "logs", "--tail", "150", CONTAINER_NAME], capture_output=True, text=True, timeout=5)
        out += "=== docker logs (last 150) ===\n" + (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        out += f"docker logs error: {e}\n"
    try:
        r = subprocess.run(["docker", "exec", CONTAINER_NAME, "ls", "-t", "/a0/logs"], capture_output=True, text=True, timeout=5)
        files = [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip().endswith(".html")][:3]
        for fn in files:
            r2 = subprocess.run(["docker", "exec", CONTAINER_NAME, "tail", "-n", "40", f"/a0/logs/{fn}"], capture_output=True, text=True, timeout=5)
            out += f"\n=== {fn} (last 40) ===\n" + (r2.stdout or "")
    except Exception as e:
        out += f"\nlog file read error: {e}\n"
    return out

def restart_a0():
    if not shutil.which("docker"):
        return {"ok": False, "error": "docker not found on PATH"}
    def run():
        subprocess.run(["docker", "restart", CONTAINER_NAME], capture_output=True, text=True, timeout=60)
    threading.Thread(target=run, daemon=True).start()
    return {"ok": True}

async def _pty_handler(ws):
    import pty as _pty
    master_fd, slave_fd = _pty.openpty()
    proc = subprocess.Popen(CLI_CMD, shell=True, stdin=slave_fd, stdout=slave_fd, stderr=slave_fd, close_fds=True)
    os.close(slave_fd)
    loop = asyncio.get_running_loop()
    def on_read():
        try:
            data = os.read(master_fd, 4096)
        except OSError:
            return
        if not data:
            return
        try:
            asyncio.run_coroutine_threadsafe(ws.send(data.decode("utf-8", errors="replace")), loop)
        except Exception:
            pass
    loop.add_reader(master_fd, on_read)
    try:
        async for msg in ws:
            data = bytes(msg) if isinstance(msg, (bytes, bytearray)) else msg.encode("utf-8", errors="replace")
            try:
                os.write(master_fd, data)
            except OSError:
                break
    finally:
        try: loop.remove_reader(master_fd)
        except Exception: pass
        try: os.close(master_fd)
        except Exception: pass
        try: proc.terminate()
        except Exception: pass

def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p

def _start_ws():
    port = _free_port()
    _ws_port[0] = port
    async def serve_forever():
        async with serve(_pty_handler, "127.0.0.1", port):
            await asyncio.Future()
    threading.Thread(target=lambda: asyncio.run(serve_forever()), daemon=True).start()
    time.sleep(0.3)

class Api:
    def get_status(self): return get_status()
    def get_logs(self): return get_logs()
    def restart_a0(self): return restart_a0()

def main():
    _start_ws()
    api = Api()
    html_path = os.path.join(os.path.dirname(__file__), "web", "index.html")
    webview.create_window("Agent Zero", url="file://" + html_path, width=WINDOW_W, height=WINDOW_H, js_api=api, confirm_close=False)
    webview.start()

if __name__ == "__main__":
    main()
