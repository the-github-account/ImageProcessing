#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$PROJECT_DIR/venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3)"
fi
AUTOSTART_DIR="$HOME/.config/autostart"
mkdir -p "$AUTOSTART_DIR"
DESKTOP_FILE="$AUTOSTART_DIR/tapo-live-viewer.desktop"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Tapo Live Camera Viewer
Comment=Show the live camera stream from the Tapo background service
Exec=$PYTHON $PROJECT_DIR/live_viewer.py
Terminal=false
X-GNOME-Autostart-enabled=true
EOF
chmod 644 "$DESKTOP_FILE"
echo "Installed desktop autostart: $DESKTOP_FILE"
echo "The viewer will open after your next Ubuntu desktop login."
echo "The Tapo daemon must be running and ENABLE_LIVE_DISPLAY must be 1 in main.py."
