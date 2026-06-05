#!/usr/bin/env bash
set -e
APPS="$HOME/.local/share/applications"
mkdir -p "$APPS"
HERE="$(cd "$(dirname "$0")" && pwd)"
cat > "$APPS/a0-ui.desktop" <<LAUNCH
[Desktop Entry]
Type=Application
Name=Agent Zero
Comment=Agent Zero desktop UI
Exec="$HERE/.venv/bin/python" -m a0_ui
Icon=$HERE/icons/icon.svg
Terminal=false
Categories=Development;Utility;
StartupNotify=true
LAUNCH
chmod +x "$APPS/a0-ui.desktop"
update-desktop-database "$APPS" 2>/dev/null || true
echo "Installed: $APPS/a0-ui.desktop"
