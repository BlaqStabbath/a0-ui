# a0-ui Project Handoff & TODO

> Comprehensive state dump for the a0-ui project. Pick up from here.

---

## Project at a Glance

| Key | Value |
|---|---|
| Name | a0-ui (Agent Zero Desktop UI) |
| Purpose | Cross-platform desktop wrapper that embeds Agent Zero Web UI as a dedicated native window |
| Stack | Python 3 + pywebview (native webview per OS) + xterm.js + WebSocket PTY |
| Web UI URL | http://localhost:5080 (was wrongly told as 50001 initially) |
| Host path | /home/blaq/DEV/SRC/a0-ui |
| Container path (scaffold source) | /a0/usr/workdir/a0-ui |
| GitHub | git@github.com:BlaqStabbath/a0-ui.git |
| Current branch | dev (main is protected from AI agent pushes) |
| License | MIT (all code original) |
| User | blaq (BlaqStabbath on GitHub) |

---

## Completed Work (in `dev` branch, pushed)

- [x] **Initial scaffold (commit `0d17eec`)** — 11 files: README.md, LICENSE, .gitignore, requirements.txt, install.sh, a0_ui/__init__.py, a0_ui/__main__.py, a0_ui/app.py, a0_ui/web/index.html, a0_ui/web/icon.svg, icons/icon.svg
- [x] **SyntaxError fix (commit `7ef046b`)** — `a0_ui/app.py` line 19 had an unterminated string literal `"docker not found on PATH` (missing closing quote). Fixed via `git checkout HEAD --`
- [x] **Cross-platform installers (commit `a729584`)** — added `install.bat` (Windows Start Menu shortcut via PowerShell) and `install.command` (macOS Agent Zero.app bundle), updated README with full cross-platform install docs. `install.sh` registers a .desktop file in `~/.local/share/applications/`
- [x] **CLI enlargement (commit `5b13fd0`)** — `a0_ui/web/index.html` fontSize 13→20, added monospace `fontFamily`, added `lineHeight: 1.2`, removed `#cli-pane` padding (4px→0), `.xterm` fills 100% width/height, `.xterm-screen` set to height:100%
- [x] **Linux venv fix** — recreated with `--system-site-packages` so `gi` (PyGObject) is importable. Installed system packages: `python3-gi, gir1.2-webkit2-4.1, libwebkit2gtk-4.1-dev, pkg-config`

---

## Completed in Container This Session (NOT yet pushed to `dev`)

The user asked: **"why not just embed shell/powershell in tab"** instead of the custom `a0` CLI. The system shell change was applied to the container files but the README rewrite and push were not completed before the user said **stop**.

- [x] **`a0_ui/app.py` patch 1/2** — added `import sys`, added `_default_shell()` function (returns `$SHELL` on Linux/macOS, `%COMSPEC%` on Windows), changed `CLI_CMD` to `SHELL_CMD` with platform-detecting default, updated `get_status()` to return `shell_cmd` key
- [x] **`a0_ui/app.py` patch 2/2** — the `subprocess.Popen(...)` call now uses `SHELL_CMD` instead of `CLI_CMD`
- [x] **`a0_ui/web/index.html` patch 1/3** — toolbar button text `"A0 CLI"` → `"Terminal"`
- [x] **`a0_ui/web/index.html` patch 2/3** — tab label `<div class="tab" data-pane="cli-pane">A0 CLI</div>` → `Terminal`
- [x] **`a0_ui/web/index.html` patch 3/3** — status text `' | CLI: '` → `' | Shell: '` and `status.cli_cmd` → `status.shell_cmd`

---

## NOT Completed (left as TODO)

### Immediate (this session's incomplete work)
- [ ] **Rewrite `a0_ui/../README.md`** to reflect the system shell change. Should document:
  - Tab is now `Terminal`, not `A0 CLI`
  - Default command is `$SHELL` (Linux/macOS) or `%COMSPEC%` (Windows), not `a0`
  - User can still run `a0` from the terminal, or set `A0_CLI_CMD=a0` to launch it directly
  - Architecture section should mention the `_default_shell()` function and `sys.platform` detection
  - The README rewrite was attempted via `code_execution_tool` (python triple-quoted string) but the tool call was REJECTED for JSON misformat. Needs to be retried with a smaller payload or written directly via `code_execution_remote` heredoc

### Copy + commit + push (for the system shell change)
- [ ] **Copy modified files from container to host**:
  ```bash
  docker cp agent-zero:/a0/usr/workdir/a0-ui/a0_ui/app.py      /home/blaq/DEV/SRC/a0-ui/a0_ui/app.py
  docker cp agent-zero:/a0/usr/workdir/a0-ui/a0_ui/web/index.html /home/blaq/DEV/SRC/a0-ui/a0_ui/web/index.html
  docker cp agent-zero:/a0/usr/workdir/a0-ui/README.md          /home/blaq/DEV/SRC/a0-ui/README.md   # after rewrite
  ```
- [ ] **Commit and push to `dev` branch** (with message like `Embed system shell in Terminal tab by default`):
  ```bash
  cd /home/blaq/DEV/SRC/a0-ui
  git add -A
  git commit -m "Embed system shell in Terminal tab by default"
  git push -u origin dev
  ```
- [ ] **User merges `dev` → `main` via GitHub PR** (AI agents blocked from main; user must do the merge in the GitHub UI at https://github.com/BlaqStabbath/a0-ui/pull/new/dev)

---

## Known Bugs / Broken Things

### App window does not appear (CRITICAL — unblocked all manual testing)
- [ ] **Fix the GTK window display issue**. The `a0_ui` process starts, runs in event loop (state `S<l`), and the log only shows a non-fatal QT fallback warning (`PyQt5.QtWebChannel` / `PyQt5.QtWebKitWidgets` not found). No `Agent Zero` window appears on `xdotool search` on either `DISPLAY=:120` or `DISPLAY=:1`.
- [ ] **Investigate XAUTHORITY / DISPLAY mismatch**. The in-container display is `:120` (per `desktop_state` extras) but the user's actual desktop is on `:1` (xdotool finds KWin, Discord, etc. on `:1`). The app is being launched from a non-graphical session/container.
- [ ] **Consider installing PyQt5 as a fallback** (so the QT backend works even if GTK can't connect to the X server): `pip install pyqt5 pyqtwebengine`
- [ ] **Consider adding explicit `DISPLAY=...` and `XAUTHORITY=...` to the launch script** in `install.sh`

### install.sh does not set up the venv (KNOWN, tracked in memories)
- [ ] **Make `install.sh` a true one-shot installer**:
  1. Create venv: `python3 -m venv --system-site-packages .venv`
  2. Install requirements: `./.venv/bin/pip install -r requirements.txt`
  3. Register the `.desktop` file

---

## Architecture Reference (for whoever picks this up)

```
a0-ui/
├── a0_ui/
│   ├── __init__.py
│   ├── __main__.py        # python -m a0_ui entry point
│   ├── app.py             # pywebview + JS API + WebSocket PTY server (UPDATED for system shell)
│   └── web/
│       ├── index.html     # toolbar, tabs (Web UI / Logs / Terminal), xterm.js (UPDATED: Terminal labels)
│       └── icon.svg
├── icons/
│   └── icon.svg
├── install.sh             # Linux: venv + deps + .desktop file (NEEDS FIX: should create venv)
├── install.bat            # Windows: venv + deps + Start Menu shortcut
├── install.command        # macOS: venv + Agent Zero.app bundle
├── requirements.txt       # pywebview>=5.0, websockets>=12.0, pywinpty>=2.0;sys_platform=='win32'
├── LICENSE                # MIT
├── README.md              # (NEEDS REWRITE for system shell)
├── .gitignore
└── todo.md                # this file
```

### Key app.py API surface
- `get_status()` → returns `{webui_url, container, shell_cmd, ws_port}` (UPDATED: was `cli_cmd`)
- `get_logs()` → returns `docker logs --tail 150` + 3 most recent `/a0/logs/*.html`
- `restart_a0()` → runs `docker restart <container>` in daemon thread, returns `{ok: True}`
- `_pty_handler(ws)` → opens `pty.openpty()`, spawns `SHELL_CMD`, bridges PTY to WebSocket (UPDATED: was `CLI_CMD`)
- `_default_shell()` → returns `$SHELL` on Linux/macOS, `%COMSPEC%` on Windows (NEW)

### Config (env vars)
- `A0_WEBUI_URL` (default `http://localhost:5080`)
- `A0_CONTAINER` (default `agent-zero`)
- `A0_CLI_CMD` (now defaults to `_default_shell()` — was hardcoded to `a0`)

---

## Git Workflow Rules (CRITICAL)

1. **NEVER push to `main`** — branch protection blocks AI agents with: *"AI agents are not allowed to make any pushes to this branch"*
2. **Always push to `dev`** — it's unprotected, the user merges via PR at https://github.com/BlaqStabbath/a0-ui/pull/new/dev
3. **The user** does the `dev` → `main` merge in the GitHub UI

---

## What's Been Tried (and outcomes)

| Attempt | Outcome |
|---|---|
| Push to `main` directly | ❌ Blocked by branch protection |
| Push to `dev` | ✅ Works |
| Run app on host with DISPLAY=:120 | ❌ Process runs, no window appears |
| Run app on host with DISPLAY=:1 | ❌ Process runs, no window appears |
| `pip install pyqt5` to fix QT backend | Not tried — should be tried |
| Hard refresh browser at localhost:5080 | (Web UI issue, not a0-ui) |
| Run app on host without DISPLAY var | Same — process runs, no window |
| `pkill -9 -f a0_ui && nohup ./venv/bin/python -m a0_ui` | Process starts, no window |

---

## Next Steps (in order)

1. **Retry the README.md rewrite** — try a smaller payload, or write directly via `code_execution_remote` heredoc
2. **Copy all 3 modified files from container to host** (`docker cp` for app.py, index.html, README.md)
3. **Commit and push to `dev`** with message `Embed system shell in Terminal tab by default`
4. **Tell user to merge `dev` → `main` via GitHub PR**
5. **Fix the app window display issue** — investigate DISPLAY/XAUTHORITY, or install PyQt5 as fallback
6. **Fix install.sh** to create the venv and install requirements (so it's a true one-shot installer)
7. **Merge to main and test** the app end-to-end on the user's actual desktop display

---

## Environment Notes

- **Container**: agent-zero running on host, port 5080:80 mapped
- **Web UI**: http://localhost:5080 (NOT 50001 — I told the user wrong earlier)
- **Container display**: :120 (per desktop_state extras), but user's actual desktop is on :1
- **Brave browser** is installed on the host (found in `/home/blaq/.cache/BraveSoftware`)
- **Node.js v24.15.0** and **Bun** are installed on the host
- **XFCE** is the desktop environment
- **Remote file structure** in the [EXTRAS] is truncated at the limit, but shows the standard Linux user dir layout

---

## Conversation Summary (this session)

1. User reported Web UI showed "Proxy key is incorrect" (port was actually 5080, not 50001)
2. We added a custom "minimax" provider to model_providers.yaml and onboarding-providers.js — this BROKE the Web UI
3. User said: revert the modifications
4. We reverted via `git checkout HEAD --` on both files
5. User said: create `dev` branch and push it (workaround for AI agent main protection)
6. We pushed to dev successfully
7. User asked for the cross-platform app `a0-ui`
8. We generated the full project in /a0/usr/workdir/a0-ui, copied to host, pushed to dev
9. User wanted: install.sh to also be cross-platform (Windows + macOS installers)
10. We added install.bat, install.command, updated README, pushed to dev (commit a729584)
11. User said: `make CLI bigger`
12. We enlarged xterm.js font from 13 to 20, monospace, full pane — pushed to dev (commit 5b13fd0)
13. User said: `why not just embedd shell/powepowershell in tab`
14. We started the system shell change: app.py and index.html patches all applied in container, README rewrite attempted but tool call rejected for misformat
15. User said: `stop` and asked to dump everything into todo.md
16. **This file is the handoff.**
