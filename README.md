# a0-ui - Agent Zero Desktop UI

A tiny cross-platform desktop wrapper that embeds the Agent Zero Web UI in a dedicated native window. It uses the OS's built-in webview engine, so there is no bundled browser and the app is only a few MB.

- Linux   -> system WebKitGTK
- Windows -> system WebView2 (Edge / Chromium, preinstalled on Win 10/11)
- macOS   -> system WKWebView (Safari engine)

The app loads http://localhost:5080 (configurable via `A0_WEBUI_URL`) and provides three tabs:

| Tab      | What it does |
|----------|---|
| Web UI   | Embeds the Agent Zero Web UI in an iframe |
| Logs     | Shows `docker logs --tail 150` plus the 3 most recent `/a0/logs/*.html` |
| Terminal | An embedded xterm.js terminal wired to a real PTY running your system shell with `a0` as the entry command |

The Terminal tab is also useful as a generic shell for debugging the container (`docker ps`, `journalctl`, etc.) — when `a0` exits, the terminal stays open as a plain shell.

---

## Requirements

- Docker running the Agent Zero container (default name: `agent-zero`)
- Python 3.10+ on the host
- The Agent Zero Web UI reachable at `http://localhost:5080`

---

## Installation (cross-platform)

Pick the script for your OS. Each one creates a local `.venv/`, installs `requirements.txt`, and registers the app in your application launcher / Start Menu / Finder.

### Linux

```
chmod +x install.sh
./install.sh
```

Installs to `~/.local/share/applications/a0-ui.desktop`. After running, search for Agent Zero in your app menu (XFCE Whisker, GNOME Activities, etc.).

Prerequisites: `python3-gi`, `gir1.2-webkit2-4.1`, `libwebkit2gtk-4.1-dev` — install with your package manager if `pip install pywebview` complains.

### Windows

Double-click `install.bat` (or run it from `cmd` / PowerShell). It:

1. Locates `py -3`, `python3`, or `python` on PATH
2. Creates `.venv/`
3. Installs requirements
4. Creates a Start Menu shortcut: Start -> Agent Zero

No admin rights required. WebView2 runtime is preinstalled on Windows 10 and 11; on older systems Windows will prompt to install it automatically.

### macOS

Double-click `install.command` (Finder will ask for permission the first time). It:

1. Locates `python3` (install via `brew install python` if missing)
2. Creates `.venv/`
3. Installs requirements
4. Builds a minimal `Agent Zero.app` bundle and optionally copies it to `/Applications`

After running, launch from Finder, Spotlight (Cmd+Space -> Agent Zero), or pin to the Dock.

---

## Running without installing

If you just want to try it without registering a launcher:

```
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt   # Linux/macOS
.venv\Scripts\pip install -r requirements.txt   # Windows
.venv/bin/pip install -r requirements-dev.txt  # for running tests
.venv/bin/python -m a0_ui                  # Linux/macOS
.venv\Scripts\python -m a0_ui              # Windows
```

---

## Debug mode

If the app starts but no window appears (or anything else looks off), enable debug mode to dump runtime diagnostics to stderr:

```
./.venv/bin/python -m a0_ui --debug        # via CLI flag
A0_DEBUG=1 ./.venv/bin/python -m a0_ui     # via env var
```

The dump includes the pywebview backend, `DISPLAY` / `XAUTHORITY` / `WAYLAND_DISPLAY` values, the window handle, geometry, and (on X11) any captured X11 errors. The CLI flag takes precedence when both are set.

---

## Configuration (environment variables)

| Variable       | Default                  | Meaning                                                 |
|----------------|--------------------------|---------------------------------------------------------|
| `A0_WEBUI_URL` | `http://localhost:5080`  | URL the app embeds                                      |
| `A0_CONTAINER` | `agent-zero`             | Docker container name used by Restart a0 and Logs       |
| `A0_CLI_CMD`   | `a0`                     | Entry command launched in the embedded Terminal. The host shell (`bash` on Linux/macOS, `cmd.exe` on Windows) is preserved. |
| `A0_DEBUG`     | unset                    | Set to `1` to enable diagnostic dump to stderr. CLI flag `--debug` also enables it and takes precedence. |

---

## Project layout

```
a0-ui/
  install.sh           Linux installer (registers .desktop file)
  install.bat          Windows installer (Start Menu shortcut)
  install.command      macOS installer (builds Agent Zero.app)
  requirements.txt
  requirements-dev.txt pytest (for running tests)
  pytest.ini
  conftest.py
  README.md
  LICENSE
  icons/icon.svg
  a0_ui/
    __init__.py
    __main__.py
    app.py             pywebview window + CLI entry + WS server wiring
    runtime/
      config.py        load_config() -> Config (frozen dataclass)
    terminal/
      command_builder.py  build_shell_command(entry_cmd) -> str
    shell_session.py   PTY <-> WebSocket bridge
    diagnostics/
      debug_dump.py    dump(window) -> None; writes diagnostics to stderr
    web/
      index.html       tabs + xterm.js terminal
      icon.svg
  tests/
    test_terminal_command_builder.py
    test_runtime_config.py
    test_shell_session.py
    test_debug_dump.py
```

---

## Running tests

```
./.venv/bin/pytest
```

---

## License

MIT — see `LICENSE`.
