import http.server
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
from pathlib import Path

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


@pytest.mark.skipif(
    os.environ.get("A0_RUN_PYWEBVIEW_E2E") != "1",
    reason="set A0_RUN_PYWEBVIEW_E2E=1 to launch the real pywebview app",
)
def test_pywebview_wrapper_restart_reloads_webui_and_reconnects_terminal():
    """Launch the real pywebview wrapper and drive Restart through the DOM.

    This test keeps the actual app wrapper, pywebview JS bridge, iframe load,
    terminal WebSocket, and restart button code in the path. It substitutes only
    external dependencies: Docker is a fake executable, and A0 Web UI is a local
    HTTP server.
    """

    observed = {"page_requests": []}

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            observed["page_requests"].append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<!doctype html><html><body>A0 ready</body></html>")

    class Server(http.server.ThreadingHTTPServer):
        daemon_threads = True

    server = Server(("127.0.0.1", 0), Handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    with tempfile.TemporaryDirectory(prefix="a0-ui-real-wrapper-e2e-") as tmp:
        tmp_path = Path(tmp)
        result_path = tmp_path / "result.json"
        docker_log_path = tmp_path / "docker.log"
        restarted_path = tmp_path / "restarted"
        cli_start_path = tmp_path / "cli-start-count"
        cli_script = tmp_path / "cli-start.sh"
        cli_script.write_text(
            "#!/bin/sh\n"
            f"count=$(($(cat {cli_start_path} 2>/dev/null || echo 0)+1))\n"
            f"echo $count > {cli_start_path}\n"
            "echo wrapper-cli-start-$count\n"
            "exec bash\n"
        )
        cli_script.chmod(0o755)
        fake_bin = tmp_path / "bin"
        fake_bin.mkdir()
        fake_docker = fake_bin / "docker"
        fake_docker.write_text(
            textwrap.dedent(
                f"""\
                #!/bin/sh
                echo "$@" >> {docker_log_path}
                case "$1" in
                  restart)
                    touch {restarted_path}
                    exit 0
                    ;;
                  inspect)
                    if [ -f {restarted_path} ]; then echo true; else echo false; fi
                    exit 0
                    ;;
                  logs)
                    echo fake docker logs
                    exit 0
                    ;;
                  exec)
                    exit 0
                    ;;
                esac
                exit 1
                """
            )
        )
        fake_docker.chmod(0o755)

        probe = textwrap.dedent(
            f"""
            import json
            import threading
            import time
            import traceback
            import webview
            from a0_ui import app

            result_path = {str(result_path)!r}
            original_start = app.webview.start

            def wait_for(window, expression, timeout=15):
                deadline = time.monotonic() + timeout
                last = None
                while time.monotonic() < deadline:
                    try:
                        last = window.evaluate_js(expression)
                        if last:
                            return last
                    except Exception as error:
                        last = repr(error)
                    time.sleep(0.1)
                raise AssertionError(f"timed out waiting for {{expression}}; last={{last!r}}")

            def e2e_probe():
                threading.Thread(target=run_probe, daemon=True).start()

            def run_probe():
                window = webview.windows[0]
                try:
                    wait_for(window, "document.getElementById('btn-restart')")
                    wait_for(window, "!!(window.pywebview && window.pywebview.api)")
                    wait_for(window, "document.getElementById('webui').src.indexOf('127.0.0.1') !== -1")
                    window.evaluate_js(\"\"\"
                      (() => {{
                        const OriginalWebSocket = WebSocket;
                        window.__a0E2EWsCreated = 0;
                        window.WebSocket = function(...args) {{
                          window.__a0E2EWsCreated += 1;
                          return new OriginalWebSocket(...args);
                        }};
                        window.WebSocket.prototype = OriginalWebSocket.prototype;
                        for (const key of ['CONNECTING', 'OPEN', 'CLOSING', 'CLOSED']) {{
                          window.WebSocket[key] = OriginalWebSocket[key];
                        }}
                      }})()
                    \"\"\")
                    window.evaluate_js("document.querySelector('[data-pane=cli-pane]').click()")
                    wait_for(window, "window.__a0E2EWsCreated >= 1")
                    window.evaluate_js("document.getElementById('btn-restart').click()")
                    state = wait_for(window, \"\"\"
                      (() => {{
                        const status = document.getElementById('status').textContent;
                        const toast = document.getElementById('toast').textContent;
                        const toastVisible = document.getElementById('toast').classList.contains('visible');
                        const activePane = document.querySelector('.pane.active').id;
                        const webuiSrc = document.getElementById('webui').src;
                        const wsCreated = window.__a0E2EWsCreated || 0;
                        if (toast === 'Container is up. Reloading Web UI.' && toastVisible && wsCreated >= 2) {{
                          return {{status, toast, toastVisible, activePane, webuiSrc, wsCreated}};
                        }}
                        return null;
                      }})()
                    \"\"\", timeout=20)
                    with open(result_path, 'w') as result_file:
                        json.dump({{'ok': True, 'state': state}}, result_file)
                except Exception:
                    with open(result_path, 'w') as result_file:
                        json.dump({{'ok': False, 'error': traceback.format_exc()}}, result_file)
                finally:
                    window.destroy()

            def patched_start(*args, **kwargs):
                kwargs['func'] = e2e_probe
                return original_start(*args, **kwargs)

            app.webview.start = patched_start
            app.main()
            """
        )

        env = os.environ.copy()
        env.update(
            {
                "A0_CONTAINER": "agent-zero-e2e",
                "A0_WEBUI_URL": f"http://127.0.0.1:{server.server_port}",
                "A0_CLI_CMD": f"sh {cli_script}",
                "PATH": f"{fake_bin}{os.pathsep}{env.get('PATH', '')}",
                "PYWEBVIEW_GUI": "gtk",
                "XDG_DATA_HOME": str(tmp_path / "xdg-data"),
            }
        )

        proc = subprocess.Popen(
            [sys.executable, "-c", probe],
            cwd=os.getcwd(),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        try:
            stdout, stderr = proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate(timeout=5)
            raise AssertionError(f"a0-ui restart e2e timed out\nstdout:\n{stdout}\nstderr:\n{stderr}")
        finally:
            server.server_close()

        assert proc.returncode == 0, f"a0-ui exited with {proc.returncode}\nstdout:\n{stdout}\nstderr:\n{stderr}"
        assert result_path.exists(), f"probe did not write result\nstdout:\n{stdout}\nstderr:\n{stderr}"
        result = json.loads(result_path.read_text())
        assert result["ok"], result.get("error")
        assert result["state"]["status"] == (
            f"Container: agent-zero-e2e | WebUI: http://127.0.0.1:{server.server_port} | Shell: sh {cli_script}"
        )
        assert result["state"]["toast"] == "Container is up. Reloading Web UI."
        assert result["state"]["toastVisible"] is True
        assert result["state"]["activePane"] == "webui-pane"
        assert result["state"]["webuiSrc"] == f"http://127.0.0.1:{server.server_port}/"
        assert result["state"]["wsCreated"] >= 2
        assert restarted_path.exists()
        docker_log = docker_log_path.read_text()
        assert "restart agent-zero-e2e" in docker_log
        assert "inspect -f {{.State.Running}} agent-zero-e2e" in docker_log
        assert cli_start_path.read_text().strip() == "2"
        assert len(observed["page_requests"]) >= 2
