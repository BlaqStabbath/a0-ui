"""diagnostics.debug_dump: print runtime diagnostics to stderr."""
import os
import sys


def _safe(getter, label: str) -> str:
    try:
        return str(getter())
    except Exception as e:
        return f"<error: {type(e).__name__}: {e}>"


def _x11_errors() -> str:
    try:
        from Xlib import X, display  # type: ignore
        d = display.Display()
        d.sync()
        return "none captured (Xlib sync ok)"
    except Exception as e:
        return f"<unavailable: {type(e).__name__}: {e}>"


def _display_info() -> str:
    import shutil
    import subprocess
    if not shutil.which("xdpyinfo"):
        return "<unavailable: xdpyinfo not on PATH>"
    try:
        r = subprocess.run(
            ["xdpyinfo"], capture_output=True, text=True, timeout=2,
        )
        return r.stdout.strip() or "<empty>"
    except Exception as e:
        return f"<error: {type(e).__name__}: {e}>"


def dump(window) -> None:
    print("[debug-dump] === a0-ui diagnostics ===", file=sys.stderr)
    print(f"[debug-dump] backend: {_safe(lambda: window.backend, 'backend')}", file=sys.stderr)
    print(f"[debug-dump] DISPLAY: {os.environ.get('DISPLAY') or 'null'}", file=sys.stderr)
    print(f"[debug-dump] XAUTHORITY: {os.environ.get('XAUTHORITY') or 'null'}", file=sys.stderr)
    print(f"[debug-dump] WAYLAND_DISPLAY: {os.environ.get('WAYLAND_DISPLAY') or 'null'}", file=sys.stderr)
    print(f"[debug-dump] window handle: {_safe(lambda: window.handle, 'handle')}", file=sys.stderr)
    print(
        f"[debug-dump] window geometry: {_safe(lambda: f'{window.x},{window.y} {window.width}x{window.height}', 'geometry')}",
        file=sys.stderr,
    )
    print(f"[debug-dump] x11 errors: {_x11_errors()}", file=sys.stderr)
    print(f"[debug-dump] display info:\n{_display_info()}", file=sys.stderr)
