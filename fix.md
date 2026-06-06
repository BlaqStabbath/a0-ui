# WebSocket Fallback Fix

## Problem

Agent Zero Web UI showed:

- orange `.status-icon`
- `Degraded (polling fallback)`
- repeated notification: `WebSocket connection problems - using polling fallback`

The misleading part was that the terminal WebSocket and browser-only Chromium tests could pass while the real app still failed. The failing path was the native pywebview wrapper embedding Agent Zero inside its internal WebKit/GTK browser.

## Root Cause

The wrapper loaded its own UI as a `file://.../index.html` page and embedded Agent Zero in an iframe.

That made the embedded Agent Zero page run under a wrapper context that did not behave like a normal same-site browser tab for A0's Socket.IO/CSRF/session flow. Agent Zero's websocket handshake depends on browser cookies/session state being sent correctly during the `/socket.io/?EIO=4&transport=websocket` upgrade.

Running A0 in a normal browser did not reproduce this because the top-level browser page was already `http://127.0.0.1:<port>`. The bug only reproduced in the app wrapper.

## Key Fix

Load the wrapper itself through pywebview's local HTTP server instead of `file://`.

Before:

```python
webview.create_window(
    "Agent Zero",
    url="file://" + html_path,
    ...
)
webview.start()
```

After:

```python
wrapper_port = _free_port()
window = webview.create_window(
    "Agent Zero",
    url=html_path,
    ...
)
webview.start(
    private_mode=False,
    storage_path=storage_path,
    http_server=True,
    http_port=wrapper_port,
)
```

This makes pywebview serve the wrapper from `http://127.0.0.1:<wrapper_port>/index.html`, so the embedded A0 iframe is no longer inside a `file://` top-level page. It also enables persistent WebKit storage so cookies/local/session storage survive and can participate in A0's CSRF/session websocket handshake.

## Secondary Fix

The wrapper previously loaded remote xterm CSS/JS at startup. In native WebKit, those blocking CDN assets could prevent wrapper initialization from reaching the A0 iframe setup.

Terminal assets now lazy-load only when the Terminal tab is opened. This keeps Web UI startup independent from terminal asset loading.

## Proof

A new opt-in E2E test launches the actual pywebview app, not a normal browser:

```bash
A0_RUN_PYWEBVIEW_E2E=1 .venv/bin/python -m pytest tests/test_pywebview_app_e2e.py -q
```

The test starts a mock A0 server that:

- sets a `SameSite=Lax` session cookie
- serves an embedded A0-like page
- triggers a Socket.IO-style websocket upgrade to `/socket.io/?EIO=4&transport=websocket`
- records the upgrade headers

The passing assertion proves the real wrapper iframe sends the A0 session cookie on the websocket upgrade. That is the wrapper-specific behavior the browser-only tests could not validate.

## Verification Commands

```bash
npm test
.venv/bin/python -m pytest
A0_RUN_PYWEBVIEW_E2E=1 .venv/bin/python -m pytest tests/test_pywebview_app_e2e.py -q
```

Expected result from the final fix:

- JS suite passes
- normal Python suite passes with the native app E2E skipped by default
- opt-in native pywebview E2E passes
