#!/usr/bin/env bash
# Install launchd job: sync-if-cursor-open.sh every 2 hours (Cursor must be running).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYNC_SCRIPT="$SCRIPT_DIR/sync-if-cursor-open.sh"
LABEL="com.raphael-batte.agent-memory-sync"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
INTERVAL="${AGENT_MEMORY_SYNC_INTERVAL:-7200}"

usage() {
  echo "Usage: $0 [--uninstall] [--interval SECONDS]"
  echo "  Default interval: 7200 (2 hours)"
  exit 0
}

UNINSTALL=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h | --help) usage ;;
    --uninstall) UNINSTALL=1; shift ;;
    --interval)
      INTERVAL="${2:?missing seconds}"
      shift 2
      ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

if [[ ! -x "$SYNC_SCRIPT" ]]; then
  chmod +x "$SYNC_SCRIPT"
fi

if [[ "$UNINSTALL" -eq 1 ]]; then
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null \
    || launchctl unload "$PLIST" 2>/dev/null \
    || true
  rm -f "$PLIST"
  echo "Uninstalled $LABEL"
  exit 0
fi

mkdir -p "$HOME/Library/LaunchAgents"
cat >"$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${SYNC_SCRIPT}</string>
  </array>
  <key>StartInterval</key>
  <integer>${INTERVAL}</integer>
  <key>RunAtLoad</key>
  <false/>
  <key>StandardOutPath</key>
  <string>${HOME}/.cursor/agent-memory/logs/cron-sync.stdout.log</string>
  <key>StandardErrorPath</key>
  <string>${HOME}/.cursor/agent-memory/logs/cron-sync.stderr.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
  </dict>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null \
  || launchctl unload "$PLIST" 2>/dev/null \
  || true
if launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null; then
  launchctl enable "gui/$(id -u)/$LABEL" 2>/dev/null || true
else
  launchctl load "$PLIST"
fi

echo "Installed periodic agent-memory sync"
echo "  Label:     $LABEL"
echo "  Script:    $SYNC_SCRIPT"
hours=$((INTERVAL / 3600))
mins=$(((INTERVAL % 3600) / 60))
if [[ "$mins" -eq 0 ]]; then
  echo "  Interval:  ${INTERVAL}s (every ${hours}h)"
else
  echo "  Interval:  ${INTERVAL}s (every ${hours}h ${mins}m)"
fi
echo "  Plist:     $PLIST"
echo "  Log:       ~/.cursor/agent-memory/logs/cron-sync.log"
echo
echo "Test now:"
echo "  bash $SYNC_SCRIPT --dry-run --force"
echo "  bash $SYNC_SCRIPT --force"
