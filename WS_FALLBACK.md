# WebSocket → Polling Fallback in Agent Zero: Technical Root-Cause Analysis

> Handoff document for coding agent. Compiled 2026-06-06 against `agent0ai/agent-zero` main branch (commit 143ff8, last index 2026-06-03).
>
> **Scope:** every documented technical/security reason the webui's WebSocket transport fails to establish or remain healthy, causing fallback to HTTP polling. Includes file/line references, code excerpts, diagnostic steps, and patch points.

---

## TL;DR

Agent Zero's UI is **deliberately designed** to fall back from WebSocket to HTTP polling. The fallback is triggered at **two layers**:

1. **Engine.IO client protocol fallback** (built into `socket.io-client` v4.8.1) — when the WebSocket transport fails to connect, it automatically retries with HTTP long-polling
2. **Application-level `DEGRADED` mode** (`webui/components/sync/sync-store.js`) — when the WebSocket connects but the `state_request` handshake times out (>2s), the UI switches to polling `/api/poll` every 250 ms

The "technical security reasons" all map to **what causes the WebSocket transport to fail in the first place**. They are: Origin/CORS validation, CSRF token requirements, SameSite cookie policy, missing WebSocket upgrade headers on reverse proxies, namespace mismatches, and HTTPS/wss vs ws mixed-content rules.

---

## 1. The Architecture (What Exists)

| Layer | Component | File |
|---|---|---|
| WS server | `python-socketio` `AsyncServer(async_mode="asgi")` | `helpers/ui_server.py:82-87` |
| Origin gate | `cors_allowed_origins=lambda o,e: validate_ws_origin(e)[0]` | `helpers/ui_server.py:85`, `helpers/ws.py:62-148` |
| ASGI mount | `ASGIApp(socketio, other_asgi_app=starlette_app)` | `helpers/ui_server.py:189-190` |
| Flask under root | `WSGIMiddleware(webapp)` inside `Mount("/", app=wsgi_app)` | `helpers/ui_server.py:170-184` |
| HTTP server | `uvicorn` with `ws="wsproto"` | `run_ui.py` → `helpers/server_startup.py:238-333` |
| Client connect | `io("/ws", { transports: ["websocket","polling"], withCredentials:true, auth:{csrf_token} })` | `webui/js/websocket.js:618-632` |
| Sync state machine | `HEALTHY / HANDSHAKE_PENDING / DEGRADED / DISCONNECTED` | `webui/components/sync/sync-store.js:13-16` |
| Polling endpoint | `GET/POST /api/poll` → `build_snapshot()` | `api/poll.py`, `helpers/state_snapshot.py` |
| Docker entry | `EXPOSE 22 80 9000-9009`; supervisord runs `run_ui` | `docker/run/Dockerfile`, `docker/run/fs/etc/supervisor/conf.d/supervisord.conf` |

This is **not** raw WebSocket — it's Socket.IO over Engine.IO. The protocol explicitly uses HTTP long-polling as the universal fallback. The choice `transports: ["websocket","polling"]` (note the order) is **deliberately WebSocket-first**, which is the inverse of the default `["polling","websocket"]` — this inversion is the source of the visible fallback behavior.

Sources:
- https://socket.io/docs/v4/client-options/#transports
- https://socket.io/docs/v4/how-it-works/#upgrade-mechanism
- https://github.com/socketio/engine.io-protocol

---

## 2. The Two Polling Mechanisms (Don't Confuse Them)

There are **two distinct polling loops**, both of which appear when the WebSocket "fails":

### A. Engine.IO transport polling (`socket.io-client` built-in)
- Activates automatically at the protocol level when the WebSocket transport fails to upgrade
- The path is `/socket.io/?EIO=4&transport=polling&...`
- Returns Engine.IO frames, not application snapshots
- No visible UI symptom besides slower real-time updates
- **This is what happens when the WebSocket handshake itself is rejected**

### B. Application-level `/api/poll` polling (`webui/index.js:418-441`)
- Activates when `syncStore.mode === "DEGRADED"` (triggered by `state_request` timeout, see `sync-store.js:397-419`)
- The cadence is **250 ms** in `DEGRADED` mode
- Triggers the user-facing toast: **"WebSocket connection problems — using polling fallback"** (`sync-store.js:103-115`)
- Returns application snapshots (logs, notifications, contexts, tasks)
- **This is what the user sees** as the visible fallback

Both loops can run simultaneously. Agent Zero is designed to always try the WebSocket first; failing that, it operates "degraded but functional" using `/api/poll` indefinitely.

---

## 3. Exact Trigger Conditions for the Fallback

### Trigger 1: `connect_error` on the WebSocket transport
`webui/js/websocket.js:678-686`:
```js
this.socket.on("connect_error", (error) => {
  this.debugLog("socket connect_error", error);
  this.invokeErrorCallbacks(error);
  if (!this._csrfInvalidatedForConnectError) { ... }
  this._scheduleConnectErrorRetry("connect_error");
});
```
When this fires, engine.io-client has already started its built-in polling transport internally.

### Trigger 2: `state_request` timeout (2 s)
`webui/components/sync/sync-store.js:397-419`:
```js
response = await stateSocket.request("state_request", payload, { timeoutMs: 2000 });
// If the socket is connected but the request failed/timed out, treat as degraded (poll fallback).
this._setMode(
  stateSocket.isConnected() ? SYNC_MODES.DEGRADED : SYNC_MODES.DISCONNECTED,
  "state_request failed",
);
```
The handshake request `state_request` to namespace `/state_sync` (or `/webui`) is sent **after** the WebSocket is "connected" but it expects an application-level acknowledgement. A 2-second timeout = the WS connects but the app-level RTT is too slow or the request never reaches the handler.

### Trigger 3: Handshake response with `ok !== true`
`sync-store.js:410-419` — if the server returns an error code (e.g., `NO_HANDLERS`, `INVALID_FILTER`, `UNKNOWN_NAMESPACE`), the mode is forced to `DEGRADED` regardless of WS connection state.

---

## 4. The Technical Security Reasons the WebSocket Fails

These are the actual root causes, ordered by frequency in the project's issue tracker and PR #863 commit history.

### 4.1 Origin / CORS validation failure (most common)
**File:** `helpers/ws.py:62-148` (`validate_ws_origin`)

The server enforces a custom Origin check on the Socket.IO handshake:
```python
cors_allowed_origins=lambda _origin, environ: validate_ws_origin(environ)[0]
```

`validate_ws_origin()`:
- Reads `HTTP_ORIGIN` or `HTTP_REFERER` header
- Compares `(scheme, host, port)` against the request's `Host` AND `X-Forwarded-Host`
- Considers `X-Forwarded-Proto` for scheme
- Returns `False` for `origin_host_mismatch` or `origin_port_mismatch`

**Failure scenarios:**
- Browser opens webui at `https://a0.example.com` but the proxy strips/forwards to the container as `http://a0.example.com:80` (default port) — port `443` ≠ port `80` → reject
- Reverse proxy doesn't forward `X-Forwarded-Host` and `X-Forwarded-Proto` — Host header is the container's internal name/port, but Origin is the public hostname → reject
- WebSocket opened from a different host (e.g. `http://localhost:50001` connecting to a remote A0) → `origin_host_mismatch`
- Reverse proxy rewrites Host header but not Origin → mismatch

**Why the engine.io-client falls back:** Per the Socket.IO docs: "the validity of your CORS configuration will only be checked if the WebSocket connection fails to be established." Source: https://socket.io/docs/v4/client-options/#transports

### 4.2 CSRF token missing or invalid on WebSocket upgrade
**Files:** `helpers/ws.py` (`requires_csrf = True` for all WsHandlers), `api/csrf_token.py`, `webui/js/websocket.js:625-632`

The Socket.IO `auth` callback is:
```js
auth: (cb) => {
  const handlers = [...this._handlers];
  getCsrfToken()
    .then((token) => cb({ csrf_token: token, handlers }))
    .catch((error) => {
      console.error("[websocket] failed to fetch CSRF token for connect", error);
      cb({ handlers });
    });
},
```

**Failure scenarios:**
- The `/api/csrf_token` GET fails due to `ALLOWED_ORIGINS` mismatch (`api/csrf_token.py:50-60`) — when login is not required, the request's Origin must match `*://localhost`, `*://127.0.0.1`, `*://0.0.0.0`, or the auto-saved first-visit origin
- CSRF token is session-bound (Flask session), but the WebSocket upgrade is a different request — session cookie must be sent
- The Flask session cookie name is `session_<runtime_id>` (`helpers/ui_server.py:69`), which rotates on every restart — old tabs lose the session
- The CSRF cookie is `SameSite=Strict` by Flask default, which browsers **drop on cross-site WebSocket upgrades** (issue #1373 fix #4: changed to `Lax`)

### 4.3 SameSite cookie policy drops the session
The default Flask session cookie is `SameSite=Lax` in modern versions, but historically was `Strict`. The browser blocks cookies on:
- Cross-origin WebSocket upgrades when `SameSite=None` is required but `Secure` is missing
- WebSocket upgrades where the page is `https://` but the WS is `ws://` (different "site")
- Some corporate browsers/extensions strip cookies on upgrade requests

Fix documented in issue #1373 comment: "Changed `SameSite=Strict` to `SameSite=Lax` in both `run_ui.py` and `api.js`"

### 4.4 Namespace mismatch (client requests a non-existent namespace)
**Files:** `helpers/ws_manager.py`, `extensions/python/webui_ws_connect/_10_state_sync.py`, `webui/components/sync/sync-store.js`

Issue #1373 root cause: the frontend `sync-store.js` line 8 was connecting to `getNamespacedClient("/state_sync")` but the server only registered `/webui` (from `ws_webui.py` class name resolution). The connect succeeded but `state_request` returned `UNKNOWN_NAMESPACE`/`NO_HANDLERS`, triggering `DEGRADED` mode.

Discovery is automatic from `api/ws_*.py` files — only namespaces corresponding to those files exist. Adding a new `ws_*.py` file registers a new namespace.

### 4.5 Missing WebSocket upgrade headers on reverse proxies
The container's own nginx (`docker/run/fs/etc/nginx/nginx.conf`) does **not** proxy the `/socket.io/` path. It listens on `127.0.0.1:31735` and serves static files only. The actual uvicorn process is reached via container port `80`.

If the user puts a reverse proxy in front (nginx, Caddy, Traefik, Cloudflare Tunnel, etc.), the proxy MUST forward:
- `Upgrade: websocket` header
- `Connection: upgrade` header
- Pass the original `Host`, `Origin`, `X-Forwarded-For`, `X-Forwarded-Proto`, `X-Forwarded-Host`

Without `Upgrade`/`Connection`, the proxy returns HTTP 200 (or 400) instead of 101, and the browser rejects the WebSocket. The engine.io-client then falls back to polling.

Documented in issues #815, #1587, and #1658.

### 4.6 Mixed-content blocking (HTTPS page → ws://)
Issue #1580, #1587: when the page is served over HTTPS (via Cloudflare, nginx, Caddy), browsers block:
- `new WebSocket("ws://...")` — "An insecure WebSocket connection may not be initiated from a page loaded over HTTPS"
- The engine.io-client's polling fallback uses HTTPS, but if the client was constructed with `io("http://...")` instead of `io("https://...")`, even polling fails with mixed content

The browser console will show: `SecurityError: Failed to construct 'WebSocket': An insecure WebSocket connection may not be initiated from a page loaded over HTTPS.`

### 4.7 API endpoint prefix mismatch
Issue #1373 fix #2: the frontend was calling `/settings_get`, `/projects`, `/csrf_token` (no prefix) but the backend registers them under `/api/...`. When `/api/csrf_token` fails, the next step (WebSocket connect with CSRF) fails too.

### 4.8 uvicorn `ws="wsproto"` vs `websockets` library
`run_ui.py` calls `run_uvicorn_with_retries(..., ws="wsproto")`. This selects the `wsproto` WebSocket implementation over the `websockets` library. wsproto has had edge-case bugs with:
- Subprotocol negotiation
- Large frames (>64KB) — relevant for state snapshots
- Backpressure handling

Some deployments report the WS works locally but fails through Cloudflare/Traefik with wsproto specifically.

### 4.9 Reverse-proxy session affinity (sticky sessions)
Per python-socketio docs (https://python-socketio.readthedocs.io/en/latest/server.html): "**The clients must connect directly over WebSocket. The long-polling transport is incompatible with the way Gunicorn load balances requests among workers. To disable long-polling in the server, add transports=['websocket'] in the server constructor. Clients will have a similar option to initiate the connection with WebSocket.**" And: "**If the long-polling transport is used, then there are two additional requirements that must be met: Each Socket.IO process must be able to handle multiple requests concurrently... The load balancer must be configured to always forward requests from a given client to the same worker.**"

If the deployment uses multiple workers (e.g., uvicorn `--workers > 1`) behind a round-robin proxy, the `state_request` may land on a different worker than the `connect`, and since there's no shared message queue configured, the response never arrives → 2s timeout → `DEGRADED`.

### 4.10 `withCredentials=true` requires `Access-Control-Allow-Credentials: true`
From socket.io client options docs: "**You cannot use origin: * when setting withCredentials to true. This will trigger the following error: Cross-Origin Request Blocked**". Agent Zero uses `withCredentials: true` and the custom origin validator does support wildcards, but if the response from the polling endpoint is missing `Access-Control-Allow-Credentials: true`, the browser rejects the response.

### 4.11 `extraHeaders` ignored on browser WebSocket
From the socket.io client options: "**In a browser environment, the extraHeaders option will be ignored if you only enable the WebSocket transport, since the WebSocket API in the browser does not allow providing custom headers.**" — this means any custom auth that depends on headers (not cookies) will only work in polling mode, not WebSocket. If the server requires a header, the WS upgrade is rejected.

### 4.12 Session-bound state on restart
`SESSION_COOKIE_NAME = "session_" + runtime.get_runtime_id()` (`helpers/ui_server.py:69`). The `runtime_id` is generated fresh on every A0 process restart. So:
- A long-lived browser tab with a WebSocket connection loses its session on restart
- The CSRF token in `session["csrf_token"]` is invalidated
- The next `state_request` returns unauthorized → `DEGRADED`
- A new tab can connect fine; an old tab cannot

The connect() method at `webui/js/websocket.js:393-401` tries to refresh the CSRF token first, but the session itself may be gone.

### 4.13 Server-side OOM / crash mid-connect
Issue #1658: the `run_ui` process crashes with exit status 247 (OOMKilled) during long LLM streams. During the 2-3 second restart, the WebSocket is dropped. After restart, the session cookie name changes (new `runtime_id`), and even though the page reconnects, the session is gone.

### 4.14 Alpine component loading chain (frontend bug masquerading as WS failure)
Issue #1373: the `sync-status.html` Alpine component is the entry point that calls `$store.sync.init()`. If the component doesn't load (e.g., Alpine doesn't see the template because of a server-side rendering glitch), `init()` never runs, no WebSocket is ever opened, the UI just sits in `DISCONNECTED` state and the polling safety net (`webui/index.js:673-674`) kicks in after 2 seconds. The user sees polling, no apparent WS error.

### 4.15 Service Worker caching old JS
Issue #1373 fix #5: `webui/sw.js` (service worker) was caching old JavaScript with bugs. After a fix is pushed, browsers keep running the old buggy code → infinite fallback loop. Disable the service worker or version-bust the cache.

---

## 5. Engine.IO Client Fallback Mechanism (The Underlying "Why")

The fallback is built into the protocol. The official socket.io docs explain (https://socket.io/docs/v4/how-it-works/):

> "While WebSocket is clearly the best way to establish a bidirectional communication, **experience has shown that it is not always possible to establish a WebSocket connection, due to corporate proxies, personal firewall, antivirus software**... From the user perspective, an unsuccessful WebSocket connection can translate in up to 10 seconds of waiting for the realtime application to begin exchanging data. This perceptively hurts user experience. To summarize, Engine.IO focuses on reliability and user experience first, marginal potential UX improvements and increased server performance second."

The Engine.IO client behavior with `transports: ["websocket", "polling"]`:
1. Try WebSocket first (`GET /socket.io/?EIO=4&transport=websocket`)
2. If that fails (no 101 Switching Protocols), fall back to polling
3. If polling succeeds, the client **stays on polling** for the duration of the session
4. With `tryAllTransports: true` (v4.8.0+, default false), it would test both — Agent Zero does NOT set this

The client will only log the fallback; there's no UI signal at this layer. The user only sees the application-level `/api/poll` polling.

---

## 6. File-Level Patch Points (For the Coding Agent)

To fix the fallback in a specific deployment, the most likely interventions, with the exact files to touch:

| Root cause | File(s) to modify | Notes |
|---|---|---|
| Origin check rejects reverse-proxied host | `helpers/ws.py:62-148` | Improve `validate_ws_origin()` to check `X-Forwarded-Host` AND `X-Forwarded-Port` more thoroughly |
| ALLOWED_ORIGINS too restrictive | `api/csrf_token.py`, `.env` | Add the public origin to `ALLOWED_ORIGINS` env var |
| SameSite cookies | Flask session config in `helpers/ui_server.py` | Set `SESSION_COOKIE_SAMESITE="Lax"` (or `"None"`) |
| Namespace mismatch | `webui/components/sync/sync-store.js:8` and `api/ws_*.py` | Make sure `getNamespacedClient("/<name>")` matches a registered `WsHandler` class |
| Reverse proxy missing WS upgrade | External nginx/Caddy/Traefik config | Add `proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade";` |
| HTTPS/WSS mixed content | Frontend config | Construct `io()` with `https://` and `wss://` URLs; set `X-Forwarded-Proto: https` |
| wsproto quirks | `run_ui.py` | Change `ws="wsproto"` to `ws="websockets"` (or remove to use uvicorn's default) |
| Sticky session needed | Proxy config OR uvicorn single-worker | Use one worker, or configure cookie-based session affinity |
| OOM crashes | Docker `--memory` flag, supervisord | Increase container memory limit, add `--limit-request-line` to uvicorn |
| Service worker caching | `webui/sw.js` or `webui/index.html` | Disable service worker registration in dev |
| API prefix mismatch | `webui/js/api.js` | Auto-prepend `/api/` if not present |
| Alpine component load | `webui/index.html`, `webui/components/sync/sync-status.html` | Verify component is mounted |

---

## 7. Diagnostic Procedure (For the Coding Agent)

To identify which root cause is in play on a specific deployment, follow this exact procedure:

1. **Open browser DevTools → Network → WS filter** on the failing webui
   - Look for `wss://.../socket.io/?EIO=4&transport=websocket`
   - Status 101 = success
   - Status 400/403/404 = upgrade rejected → check headers in response
   - Connection closed immediately = origin/CSRF/CSRF cookie issue
2. **Check the Network → XHR filter** for `/socket.io/?...transport=polling`
   - If this appears, Engine.IO has fallen back — that's the protocol-level fallback
3. **Check the Network → Fetch/XHR** for `/api/poll`
   - If this appears at 250ms intervals, the application has gone `DEGRADED`
4. **Browser console** for:
   - `WebSocket connection to 'wss://...' failed`
   - `SecurityError: Failed to construct 'WebSocket'`
   - `Cross-Origin Request Blocked`
   - `WebSocket connection problems - using polling fallback` (this is the toast from `sync-store.js:104`)
5. **In the container, check `/var/log/supervisor/run_ui.log`** (stdout) for:
   - `invalid request: ... UNKNOWN_NAMESPACE`
   - `NO_HANDLERS`
   - `HANDLER_ERROR`
   - `origin_host_mismatch`, `origin_port_mismatch`, `missing_origin`
6. **Set `A0_WS_DEBUG=1`** in container env to enable verbose `ws_debug()` output (`helpers/ws.py:32-37`)

---

## 8. Authoritative Source URLs

### Agent Zero source (commit 143ff8, main branch)
- WebSocket base: https://github.com/agent0ai/agent-zero/blob/main/helpers/ws.py
- WebSocket manager: https://github.com/agent0ai/agent-zero/blob/main/helpers/ws_manager.py
- Server runtime: https://github.com/agent0ai/agent-zero/blob/main/helpers/ui_server.py
- Startup / uvicorn config: https://github.com/agent0ai/agent-zero/blob/main/helpers/server_startup.py
- WebSocket handlers: https://github.com/agent0ai/agent-zero/tree/main/api/ws_*.py
- CSRF endpoint: https://github.com/agent0ai/agent-zero/blob/main/api/csrf_token.py
- Polling endpoint: https://github.com/agent0ai/agent-zero/blob/main/api/poll.py
- State snapshot: https://github.com/agent0ai/agent-zero/blob/main/helpers/state_snapshot.py
- Client transport config: https://github.com/agent0ai/agent-zero/blob/main/webui/js/websocket.js (line 622)
- Sync state machine: https://github.com/agent0ai/agent-zero/blob/main/webui/components/sync/sync-store.js
- Polling loop: https://github.com/agent0ai/agent-zero/blob/main/webui/index.js (line 418-441, 652-780)
- Container nginx: https://github.com/agent0ai/agent-zero/blob/main/docker/run/fs/etc/nginx/nginx.conf
- Container supervisord: https://github.com/agent0ai/agent-zero/blob/main/docker/run/fs/etc/supervisor/conf.d/supervisord.conf
- Developer docs: https://github.com/agent0ai/agent-zero/blob/main/docs/developer/websockets.md
- Tunnel proxy: https://github.com/agent0ai/agent-zero/blob/main/api/tunnel_proxy.py

### Agent Zero issues (the canonical record of fixes)
- #863 "WebSocket Infrastructure + Replace /poll with websocket" — https://github.com/agent0ai/agent-zero/issues/863 (the design history, contains all the prior fixes as commit messages)
- #1373 "WebSocket fails to connect in v1.3 due to Alpine component system not loading sync-status component" — https://github.com/agent0ai/agent-zero/issues/1373 (the most complete catalog of root causes: namespace mismatch, API prefix, CSRF, SameSite, SW caching)
- #898 "Massive polling slows system down" — https://github.com/agent0ai/agent-zero/issues/898 (the issue that motivated the whole redesign)
- #815 "Update v0.9.7: No longer compatible with reverse proxy?" — https://github.com/agent0ai/agent-zero/issues/815
- #1580 "Collabora CODE WebSocket SecurityError when webui served over HTTPS" — https://github.com/agent0ai/agent-zero/issues/1580 (mixed content, ssl.termination)
- #1587 "Collabora CODE reader fails over HTTPS (Custom Cloudflare Tunnel)" — https://github.com/agent0ai/agent-zero/issues/1587
- #1658 "Intermittent tunnel disconnects caused by run_ui crashing with Exit Status 247" — https://github.com/agent0ai/agent-zero/issues/1658 (OOMKilled mid-stream)

### Protocol/library documentation
- Socket.IO v4 client options (`transports`, `withCredentials`, `extraHeaders`, `upgrade`): https://socket.io/docs/v4/client-options/
- Socket.IO v4 how it works (Engine.IO transport upgrade mechanism, the WHY of polling fallback): https://socket.io/docs/v4/how-it-works/
- Engine.IO protocol specification: https://github.com/socketio/engine.io-protocol
- python-socketio server documentation (CORS, async modes, load balancer requirements): https://python-socketio.readthedocs.io/en/latest/server.html
- python-socketio issue #1357 "Server cannot emit to client - after getting stuck in websocket upgrade loop": https://github.com/miguelgrinberg/python-socketio/issues/1357
- RFC 6455 (WebSocket protocol, Origin security considerations): https://datatracker.ietf.org/doc/html/rfc6455
- MDN WebSocket API: https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API
- MDN Mixed content (WebSocket from HTTPS): https://developer.mozilla.org/en-US/docs/Web/Security/Mixed_content

### Reverse proxy WebSocket upgrade requirements
- nginx WebSocket proxying: http://nginx.org/en/docs/http/websocket.html
- Caddy WebSocket reverse proxy: https://caddyserver.com/docs/caddyfile/directives/reverse_proxy#websocket
- Traefik WebSocket: https://doc.traefik.io/traefik/middlewares/http/websocket/
- Cloudflare Tunnel WebSocket support: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/ tunnels/

---

## 9. Recommended Fix Strategy (For the Coding Agent)

The fix depends on which of the 15 root causes applies. Quick triage:

| Symptom | Most likely cause | Fix |
|---|---|---|
| WebSocket connects (101) but goes to `/api/poll` in 2s | Origin check fails silently OR namespace mismatch | Add Origin to `ALLOWED_ORIGINS`; check namespace matches `api/ws_*.py` |
| WebSocket doesn't appear in DevTools at all | CORS or preflight rejection; session cookie dropped | Set SameSite=Lax, ensure `withCredentials` flow, check `Access-Control-Allow-Credentials: true` |
| 400/403 on `GET /socket.io/?...transport=websocket` | `validate_ws_origin()` returns False | Check Host, X-Forwarded-Host, X-Forwarded-Proto, Origin headers at the container |
| 404 on `/socket.io/...` | Reverse proxy not forwarding `/socket.io/` to backend | Add `location /socket.io/ { proxy_pass http://backend; proxy_http_version 1.1; proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade"; }` |
| `SecurityError: Mixed Content` in console | HTTPS page connecting to `ws://` | Configure backend URL to use `wss://`; set `X-Forwarded-Proto: https` at reverse proxy |
| WebSocket connects then drops after 30-60s | Reverse proxy idle timeout (default 60s) | Set `proxy_read_timeout 3600s` (nginx), increase Cloudflare Tunnel timeout |
| "Disconnected" status with no `/api/poll` activity | Alpine component didn't load | Check `webui/components/sync/sync-status.html` is included and `x-create` fires |
| Intermittent drops every few minutes | run_ui OOMKilled | Increase container memory; check `docker inspect` for `OOMKilled: true` |
| Long-lived tab stops working after restart | Session cookie name includes `runtime_id`, rotates on restart | The coding agent should add a `/api/csrf_token` re-fetch path on `connect_error` (already exists at `webui/js/websocket.js:393-401`) and instruct users to refresh |

---

## 10. Engine.IO v4 Protocol Reference

For the coding agent's understanding of how transport fallback actually works at the protocol level:

**Handshake** (server → client):
```json
{
  "sid": "FSDjX-WRwSA4zTZMALqx",
  "upgrades": ["websocket"],
  "pingInterval": 25000,
  "pingTimeout": 20000,
  "maxPayload": 1000000
}
```

**Polling transport request:**
```
GET /socket.io/?EIO=4&transport=polling&t=<timestamp>
```

**WebSocket transport request:**
```
GET /socket.io/?EIO=4&transport=websocket
```

The WebSocket request must upgrade from HTTP — i.e., the response must be `101 Switching Protocols`. Any non-101 response (200, 400, 403, 404, 502) causes the client to fall back to polling.

**Critical headers required for upgrade:**
- Request: `Connection: Upgrade`, `Upgrade: websocket`, `Sec-WebSocket-Version: 13`, `Sec-WebSocket-Key: <base64>`
- Response: `101 Switching Protocols`, `Upgrade: websocket`, `Connection: Upgrade`, `Sec-WebSocket-Accept: <hash>`

**Cookie behavior:** WebSocket API in browsers does NOT allow setting custom headers, but DOES send cookies for the origin's domain. The agent zero `withCredentials: true` ensures cookies are included, but SameSite policy governs whether the browser sends them on a cross-origin upgrade.

**`Sec-WebSocket-Protocol` subprotocols:** Agent Zero doesn't use subprotocols, but if the client and server disagree, the upgrade is rejected. The socket.io-client sends no subprotocol by default.

---

## 11. Glossary

- **EIO** — Engine.IO protocol version marker. Agent Zero uses EIO=4 (current).
- **sid** — Session ID assigned by server in handshake, used in all subsequent requests.
- **polling** — HTTP long-polling transport (also called "long-polling" or just "polling"). Not the same as Agent Zero's application-level `/api/poll`.
- **namespace** — Socket.IO multiplexing channel (e.g., `/webui`, `/hello`, `/dev_websocket_test`). Discovered from `api/ws_*.py` files.
- **DEGRADED** — Application-level state meaning "WebSocket is up but handshake failed; falling back to /api/poll".
- **DISCONNECTED** — Application-level state meaning "WebSocket is down; no polling, just reconnect attempts".
- **HEALTHY** — Application-level state meaning "WebSocket is up and handshake completed".
- **HANDSHAKE_PENDING** — Application-level state meaning "WebSocket is up; waiting for `state_request` response".
- **transport** — A specific Engine.IO connection method (`websocket`, `polling`, or `webtransport`).
- **upgrade** — In the Engine.IO protocol, the transition from `polling` to `websocket`. Different from HTTP Upgrade headers, but related.

---

## 12. Cross-References to a0-ui Project

The local `/home/blaq/DEV/SRC/a0-ui` project is a separate Python application (uses `BaseHTTPRequestHandler` / `ThreadingHTTPServer` for an embedded terminal via `/pty/output` and `/pty/input`). It does NOT use Socket.IO. The local `a0_ui/polling.py` file is the polling implementation for the local PTY bridge, not the Agent Zero webui.

If the coding agent is tasked with making `a0-ui` work alongside Agent Zero (e.g., embedded terminal panel that talks to the running A0 container), the relevant cross-cutting concerns are:
- Both projects use HTTP polling as a fallback for unreliable transports (different transports though: A0 uses Engine.IO, a0-ui uses raw HTTP)
- The local `a0-ui` would need a Socket.IO client if it needs to subscribe to A0 state events (`/api/ws_webui` events)
- CORS for the embedded terminal would need to allow the A0 webui's origin

---

*End of handbook. Compiled 2026-06-06. All URLs valid as of that date; verify against current `main` branch before relying on line numbers.*
