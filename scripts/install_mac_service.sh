#!/bin/bash
# Installs Signality as a background service on this Mac (launchd).
# It starts when you log in, and restarts itself if it ever crashes.
# Undo with: scripts/uninstall_mac_service.sh
set -euo pipefail

LABEL="com.signality.agent"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LAUNCHD_LOG="$HOME/Library/Logs/signality-launchd.log"   # startup errors land here

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"

cat > "$PLIST" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>              <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$ROOT/.venv/bin/python</string>
        <string>-m</string>
        <string>signality.agent</string>
    </array>
    <key>WorkingDirectory</key>   <string>$ROOT</string>
    <key>RunAtLoad</key>          <true/>
    <key>KeepAlive</key>          <true/>
    <key>ThrottleInterval</key>   <integer>60</integer>
    <key>StandardOutPath</key>    <string>/dev/null</string>
    <key>StandardErrorPath</key>  <string>$LAUNCHD_LOG</string>
</dict>
</plist>
PLIST

# Restart cleanly if it was already installed.
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"

echo "Signality is now running in the background."
echo "  Activity log:  $ROOT/data/signality.log"
echo "  Startup errors: $LAUNCHD_LOG"
