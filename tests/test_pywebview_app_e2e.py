import http.server
import os
import subprocess
import sys
import threading
import time

import pytest


@pytest.mark.skipif(
    os.environ.get("A0_RUN_PYWEBVIEW_E2E") != "1",
    reason="set A0_RUN_PYWEBVIEW_E2E=1 to launch the real pywebview app",
)
def test_pywebview_wrapper_embeds_a0_same_site_and_sends_session_cookie_on_socketio_upgrade():
    """Launch the actual app wrapper; do not substitute a normal browser.

    The mocked A0 page sets a SameSite=Lax session cookie, then opens a
    Socket.IO-style websocket. WebKitGTK must send that cookie on the upgrade.
    If the wrapper is loaded as file://, this is the class of behavior that
    breaks A0's CSRF/session websocket handshake inside the iframe.
    """

    observed = {
        "page_requests": [],
        "poll_requests": [],
        "upgrade_requests": [],
    }

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            if self.path.startswith("/socket.io/") and self.headers.get("Upgrade", "").lower() == "websocket":
                observed["upgrade_requests"].append(dict(self.headers))
                self.send_response(403)
                self.end_headers()
                return

            if self.path.startswith("/api/poll"):
                observed["poll_requests"].append(dict(self.headers))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"ok":true}')
                return

            observed["page_requests"].append(dict(self.headers))
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Set-Cookie", "a0_session=e2e; Path=/; SameSite=Lax")
            self.end_headers()
            self.wfile.write(
                b"""<!doctype html>
<html>
<body>
  <div class="status-icon" title="Healthy (websocket)" aria-label="Healthy (websocket)"></div>
  <script>
    window.__a0AppWrapperProbe = {
      origin: location.origin,
      referrer: document.referrer,
      cookie: document.cookie,
    };
    new WebSocket("ws://" + location.host + "/socket.io/?EIO=4&transport=websocket");
    fetch("/api/poll").catch(() => {});
  </script>
</body>
</html>"""
            )

    class Server(http.server.ThreadingHTTPServer):
        daemon_threads = True

    server = Server(("127.0.0.1", 0), Handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    env = os.environ.copy()
    env.update(
        {
            "A0_WEBUI_URL": f"http://127.0.0.1:{server.server_port}",
            "A0_CLI_CMD": "true",
            "PYWEBVIEW_GUI": "gtk",
            "XDG_DATA_HOME": "/tmp/a0-ui-pywebview-e2e",
        }
    )

    proc = subprocess.Popen(
        [sys.executable, "-m", "a0_ui"],
        cwd=os.getcwd(),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline and not observed["upgrade_requests"]:
            if proc.poll() is not None:
                stdout, stderr = proc.communicate(timeout=2)
                raise AssertionError(f"a0-ui exited early\nstdout:\n{stdout}\nstderr:\n{stderr}")
            time.sleep(0.1)

        if not observed["page_requests"] or not observed["upgrade_requests"]:
            proc.terminate()
            try:
                stdout, stderr = proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate(timeout=5)
            raise AssertionError(
                "embedded A0 iframe did not complete the websocket probe\n"
                f"page_requests={observed['page_requests']!r}\n"
                f"poll_requests={observed['poll_requests']!r}\n"
                f"upgrade_requests={observed['upgrade_requests']!r}\n"
                f"stdout:\n{stdout}\nstderr:\n{stderr}"
            )

        upgrade = observed["upgrade_requests"][-1]
        assert upgrade.get("Origin") == f"http://127.0.0.1:{server.server_port}"
        assert "a0_session=e2e" in upgrade.get("Cookie", "")
        assert observed["poll_requests"], "probe did not perform fallback /api/poll request"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        server.server_close()
