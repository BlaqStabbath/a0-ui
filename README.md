# a0-ui

Cross-platform desktop app that embeds the Agent Zero Web UI (http://localhost:5080) as a dedicated window.

## Features
- **Web UI tab** - iframe to the Agent Zero Web UI, no browser chrome
- **Refresh** button - reloads the active tab
- **Restart A0** button - runs `docker restart agent-zero`, polls until ready, auto-reloads Web UI
- **View Logs** tab - tails `docker logs` and Agent Zero log files
- **A0 CLI** tab - embedded xterm.js terminal running the `a0` command in a real PTY
- Standard window title bar with min/max/close
- Cross-platform: Linux, Windows, macOS

## Stack
Python + pywebview (system webview: WebKitGTK / WebView2 / WKWebView). No bundled browser. ~5MB.

## Install
```bash
git clone <your-repo-url> a0-ui
cd a0-ui
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run
```bash
python -m a0_ui
```

## Desktop launcher (Linux only)
```bash
./install.sh
```

## Configuration (env vars)
- `A0_WEBUI_URL` (default `http://localhost:5080`)
- `A0_CONTAINER` (default `agent-zero`)
- `A0_CLI_CMD` (default `a0`)

## Requirements
- Python 3.10+
- Docker (the `agent-zero` container must exist)
- Linux: `webkit2gtk-4.1` + `gtk3` (preinstalled on most desktops)
- Windows: WebView2 (preinstalled on Win 10/11)
- macOS: nothing extra
