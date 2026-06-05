# a0-ui - Agent Zero Desktop UI

A tiny cross-platform desktop wrapper that embeds the Agent Zero Web UI in a dedicated native window. It uses the OS's built-in webview engine, so there is no bundled browser and the app is only a few MB.

- Linux   -> system WebKitGTK
- Windows -> system WebView2 (Edge / Chromium, preinstalled on Win 10/11)
- macOS   -> system WKWebView (Safari engine)

The app loads http://localhost:5080 (configurable via the A0_WEBUI_URL environment variable) and adds four buttons on top of the page:

| Button      | What it does |
|-------------|---|
| Refresh     | Reloads the current tab content (Web UI, Logs, or A0 CLI) |
| Restart A0  | Runs docker restart on the container, waits for the Web UI to come back, then reloads |
| View Logs   | Switches to the Logs tab (last 150 lines of docker logs plus the 3 most recent /a0/logs/*.html) |
| A0 CLI      | Switches to the A0 CLI tab - an embedded xterm.js terminal wired to a real PTY running the a0 command |

---

## Requirements

- Docker running the Agent Zero container (default name: agent-zero)
- Python 3.10+ on the host
- The Agent Zero Web UI reachable at http://localhost:5080

---

## Installation (cross-platform)

Pick the script for your OS. Each one creates a local .venv/, installs requirements.txt, and registers the app in your application launcher / Start Menu / Finder.

### Linux

```
chmod +x install.sh
./install.sh
```

Installs to ~/.local/share/applications/a0-ui.desktop. After running, search for Agent Zero in your app menu (XFCE Whisker, GNOME Activities, etc.).

Prerequisites: python3-gi, gir1.2-webkit2-4.1, libwebkit2gtk-4.1-dev - install with your package manager if pip install pywebview complains.

### Windows

Double-click install.bat (or run it from cmd / PowerShell). It:

1. Locates py -3, python3, or python on PATH
2. Creates .venv/
3. Installs requirements
4. Creates a Start Menu shortcut: Start -> Agent Zero

No admin rights required. WebView2 runtime is preinstalled on Windows 10 and 11; on older systems Windows will prompt to install it automatically.

### macOS

Double-click install.command (Finder will ask for permission the first time). It:

1. Locates python3 (install via brew install python if missing)
2. Creates .venv/
3. Installs requirements
4. Builds a minimal Agent Zero.app bundle and optionally copies it to /Applications

After running, launch from Finder, Spotlight (Cmd+Space -> Agent Zero), or pin to the Dock.

---

## Running without installing

If you just want to try it without registering a launcher:

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt   # Linux/macOS
.venv\Scripts\pip install -r requirements.txt   # Windows
.venv/bin/python -m a0_ui                  # Linux/macOS
.venv\Scripts\python -m a0_ui              # Windows
```

---

## Configuration (environment variables)

| Variable       | Default                  | Meaning                                                 |
|----------------|--------------------------|---------------------------------------------------------|
| A0_WEBUI_URL   | http://localhost:5080    | URL the app embeds                                      |
| A0_CONTAINER   | agent-zero               | Docker container name used by Restart A0 and Logs       |
| A0_CLI_CMD     | a0                       | Command launched in the embedded CLI terminal           |

---

## Project layout

```
a0-ui/
  install.sh           Linux installer (registers .desktop file)
  install.bat          Windows installer (Start Menu shortcut)
  install.command      macOS installer (builds Agent Zero.app)
  requirements.txt
  README.md
  LICENSE
  icons/icon.svg
  a0_ui/
    __init__.py
    __main__.py
    app.py             pywebview window + WebSocket PTY server
    web/
      index.html       toolbar + tabs + xterm.js terminal
      icon.svg
```

---

## License

MIT - see LICENSE.
