#!/usr/bin/env bash
# a0-ui macOS installer / updater
# Double-clickable. Creates .venv, installs deps, builds Agent Zero.app bundle.
# Re-running upgrades pip packages and rebuilds the .app.

set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

# 1. Detect first install vs update
if [ -x "$HERE/.venv/bin/python" ]; then
    MODE="update"
else
    MODE="first-install"
fi

echo "=== a0-ui $MODE ==="
echo "Project directory: $HERE"
echo

if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 not found."
    echo
    echo "Install Python 3.10+ with one of:"
    echo "  1. Homebrew:  brew install python"
    echo "  2. Xcode CLT: xcode-select --install"
    echo "  3. python.org: https://www.python.org/downloads/macos/"
    echo
    read -p "Press Enter to close..."
    exit 1
fi

PY=python3
echo "Using Python: $($PY --version 2>&1)"

if [ "$MODE" = "first-install" ]; then
    if [ ! -x ".venv/bin/python" ]; then
        echo "Creating virtual environment..."
        $PY -m venv .venv
    fi
fi

echo "Installing dependencies..."
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

APP_DIR="$HERE/Agent Zero.app"
LAUNCHER_SCRIPT="$APP_DIR/Contents/MacOS/AgentZeroLauncher"

# 2. Validate the previously-registered .app (if any)
if [ -f "$LAUNCHER_SCRIPT" ]; then
    old_here=$(grep '^cd ' "$LAUNCHER_SCRIPT" | head -1 | sed -E 's/^cd "(.+)"$/\1/')
    if [ -n "$old_here" ] && [ ! -d "$old_here" ]; then
        echo
        echo "WARNING: previous install pointed at $old_here which no longer exists."
        echo "         this install registers: $HERE"
    fi
fi

# 3. Rebuild the .app bundle
echo "Creating $APP_DIR..."
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

cat > "$APP_DIR/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>Agent Zero</string>
    <key>CFBundleDisplayName</key><string>Agent Zero</string>
    <key>CFBundleIdentifier</key><string>ai.agentzero.ui</string>
    <key>CFBundleVersion</key><string>0.1.0</string>
    <key>CFBundleShortVersionString</key><string>0.1.0</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleExecutable</key><string>AgentZeroLauncher</string>
    <key>LSUIElement</key><false/>
    <key>NSHighResolutionCapable</key><true/>
    <key>CFBundleIconFile</key><string>icon</string>
</dict>
</plist>
PLIST

cat > "$APP_DIR/Contents/MacOS/AgentZeroLauncher" <<LAUNCHER
#!/usr/bin/env bash
cd "$HERE"
exec "$HERE/.venv/bin/python" -m a0_ui
LAUNCHER

chmod +x "$APP_DIR/Contents/MacOS/AgentZeroLauncher"

if [ -f "$HERE/icons/icon.svg" ]; then
    cp "$HERE/icons/icon.svg" "$APP_DIR/Contents/Resources/icon.svg"
fi

read -p "Copy Agent Zero.app to /Applications? (y/N) " ans
if [[ "$ans" =~ ^[Yy]$ ]]; then
    if [ -w "/Applications" ] || sudo -n true 2>/dev/null; then
        rm -rf "/Applications/Agent Zero.app" 2>/dev/null || sudo rm -rf "/Applications/Agent Zero.app"
        cp -R "$APP_DIR" "/Applications/" || sudo cp -R "$APP_DIR" "/Applications/"
        echo "Installed: /Applications/Agent Zero.app"
    else
        echo "Skipped: no write access to /Applications."
        echo "You can drag '$APP_DIR' to /Applications manually."
    fi
else
    echo "Skipped. You can run the app from: $APP_DIR"
fi

echo
echo "=== Installation complete ==="
echo "Launch Agent Zero from Finder (double-click Agent Zero.app) or run:"
echo "  $HERE/.venv/bin/python -m a0_ui"
read -p "Press Enter to close..."
