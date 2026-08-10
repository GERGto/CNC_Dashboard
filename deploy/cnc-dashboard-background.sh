#!/bin/sh
# Starts the services that are not needed for the local kiosk. Runs 25s after
# boot so it cannot compete with the Xorg/Chromium cold start for SD-card I/O.
set -eu

SETTINGS_PATH=${CNC_SETTINGS_PATH:-/opt/cnc-dashboard/backend/settings.json}

systemctl start caddy.service smbd.service nmbd.service

# The maintenance tunnel follows the dashboard switch instead of systemd's
# enable state: an operator who turned Tailscale off must find it off after a
# restart, and the daemon should not even run in that case.
tailscale_enabled() {
  [ -f "$SETTINGS_PATH" ] || return 1
  python3 - "$SETTINGS_PATH" <<'PY'
import json
import sys

try:
    with open(sys.argv[1], "r", encoding="utf-8") as handle:
        settings = json.load(handle)
except (OSError, ValueError):
    sys.exit(1)

sys.exit(0 if isinstance(settings, dict) and settings.get("tailscaleEnabled") else 1)
PY
}

if tailscale_enabled; then
  systemctl start tailscaled.service
else
  systemctl stop tailscaled.service 2>/dev/null || true
fi
