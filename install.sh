#!/usr/bin/env bash
# a0-ui Linux installer / updater
# - First run: creates .venv with --system-site-packages, installs requirements,
#   registers a .desktop file in ~/.local/share/applications/.
# - Re-run: skips venv creation, runs pip install -r requirements.txt (upgrades),
#   rewrites the .desktop (picks up a new project path if the user moved it),
#   warns if the previously-registered path no longer exists.

set -e
APPS="$HOME/.local/share/applications"
DESKTOP="$APPS/a0-ui.desktop"
mkdir -p "$APPS"
HERE="$(cd "$(dirname "$0")" && pwd)"

# 1. Detect first install vs update
if [ -x "$HERE/.venv/bin/python" ]; then
    MODE="update"
    echo "=== a0-ui update ==="
    echo "Project: $HERE"
    echo
else
    MODE="first-install"
    echo "=== a0-ui first install ==="
    echo "Project: $HERE"
    echo
fi

# 2. Check Python
if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 not found. Install Python 3.10+ with your package manager."
    exit 1
fi
PY=python3
echo "Using Python: $($PY --version 2>&1)"

# 3. Create venv if missing
if [ "$MODE" = "first-install" ]; then
    echo "Creating virtual environment..."
    $PY -m venv --system-site-packages .venv
fi

# 4. Install/upgrade requirements
echo "Installing dependencies..."
"$HERE/.venv/bin/python" -m pip install --upgrade pip
"$HERE/.venv/bin/python" -m pip install -r requirements.txt

# 5. Validate the previously-registered launcher path (if any)
if [ -f "$DESKTOP" ]; then
    old_exec=$(grep '^Exec=' "$DESKTOP" | head -1 | sed -E 's/^Exec="([^"]+)".*/\1/')
    if [ -n "$old_exec" ]; then
        # old_exec is <project>/.venv/bin/python; project is 3 levels up
        old_project=$(dirname "$(dirname "$(dirname "$old_exec")")")
        if [ -n "$old_project" ] && [ ! -d "$old_project" ]; then
            echo
            echo "WARNING: previous install pointed at $old_project which no longer exists."
            echo "         this install registers: $HERE"
        fi
    fi
fi

# 6. Write the .desktop file
cat > "$DESKTOP" <<LAUNCH
[Desktop Entry]
Type=Application
Name=Agent Zero
Comment=Agent Zero desktop UI
Exec="$HERE/.venv/bin/python" -m a0_ui
Path=$HERE
Icon=$HERE/icons/icon.svg
Terminal=false
Categories=Development;Utility;
StartupNotify=true
LAUNCH
chmod +x "$DESKTOP"
update-desktop-database "$APPS" 2>/dev/null || true

echo
echo "Installed: $DESKTOP"
echo "Launch Agent Zero from your application menu, or run:"
echo "  $HERE/.venv/bin/python -m a0_ui"
