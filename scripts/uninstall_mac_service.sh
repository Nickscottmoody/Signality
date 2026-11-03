#!/bin/bash
# Stops Signality's background service and removes it from login.
set -uo pipefail

LABEL="com.signality.agent"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null && echo "Stopped." || echo "It wasn't running."
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist" && echo "Removed from login."
