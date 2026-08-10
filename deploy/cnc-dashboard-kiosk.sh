#!/bin/sh
set -u

# Show the splash in the very first milliseconds of the session: the boot
# frame is pre-rendered as a 1-bit bitmap and becomes the root background
# before any other client can even load. (The Plymouth frame itself does not
# survive the glamor screen initialization, so the root must repaint it.)
if command -v xsetroot >/dev/null 2>&1; then
  if [ -f /usr/local/share/cnc-dashboard/splash.xbm ]; then
    xsetroot -bitmap /usr/local/share/cnc-dashboard/splash.xbm -fg '#000000' -bg '#ffffff' >/dev/null 2>&1 || \
      xsetroot -solid '#ffffff' >/dev/null 2>&1 || true
  else
    xsetroot -solid '#ffffff' >/dev/null 2>&1 || true
  fi
fi

# The antialiased splash window covers Chromium's blank startup surfaces
# until app.js reports the rendered dashboard.
if [ -x /usr/local/bin/cnc-dashboard-xsplash.py ]; then
  /usr/local/bin/cnc-dashboard-xsplash.py >/dev/null 2>&1 &
fi

if command -v xset >/dev/null 2>&1; then
  xset s off >/dev/null 2>&1 || true
  xset s noblank >/dev/null 2>&1 || true
  xset -dpms >/dev/null 2>&1 || true
fi

# The firmware EDID advertises 1024x600@60 as the preferred mode for kernel
# and Xorg alike, so X normally comes up correctly without any extra modeset.
# Only intervene if the mode is wrong; every xrandr modeset drops the HDMI
# signal and forces the panel to re-lock.
if command -v xrandr >/dev/null 2>&1; then
  if xrandr --query >/dev/null 2>&1 && ! xrandr --current | grep -q 'current 1024 x 600'; then
    xrandr --output HDMI-2 --primary --mode 1024x600 2>/dev/null || true
    xrandr --output HDMI-1 --off 2>/dev/null || true
  fi
fi

if command -v unclutter >/dev/null 2>&1; then
  pkill -x unclutter >/dev/null 2>&1 || true
  unclutter --timeout 0 --hide-on-touch --start-hidden --fork >/dev/null 2>&1 || true
fi

# Chromium loads the dashboard directly (no intermediate boot page), so both
# the frontend server and the backend API must answer before it starts. The
# splash keeps covering the screen during this wait.
if command -v curl >/dev/null 2>&1; then
  attempt=0
  while [ "$attempt" -lt 300 ]; do
    if curl -fsS --max-time 1 http://127.0.0.1:8081/index.html >/dev/null 2>&1 && \
       curl -fsS --max-time 1 http://127.0.0.1:8080/api/health >/dev/null 2>&1; then
      break
    fi
    attempt=$((attempt + 1))
    sleep 0.1
  done
fi

# Keep the appliance browser separate from former DietPi desktop sessions. Chromium
# stores the hostname in its singleton lock; after renaming DietPi to cncpi, a stale
# lock would otherwise make every kiosk start exit immediately.
PROFILE_DIR="${XDG_CONFIG_HOME:-${HOME:-/home/dietpi}/.config}/chromium-cnc-dashboard"
mkdir -p "$PROFILE_DIR"
if ! pgrep -u "$(id -u)" -x chromium >/dev/null 2>&1; then
  rm -f "$PROFILE_DIR/SingletonCookie" "$PROFILE_DIR/SingletonLock" "$PROFILE_DIR/SingletonSocket"
fi

# --disable-audio-output: the appliance has no speakers, and Chromium's lazy
# audio-device probe would otherwise start HDMI audio infoframes mid-session,
# which visibly disturbs the panel signal.
# The three backgrounding flags are load-bearing: the native boot splash fully
# occludes Chromium during startup, and an occluded Chromium freezes rAF and
# throttles timers - exactly the ticks that produce the "CNC Dashboard bereit"
# title the splash is waiting for.
exec /usr/bin/chromium \
  --user-data-dir="$PROFILE_DIR" \
  --disable-audio-output \
  --disable-backgrounding-occluded-windows \
  --disable-renderer-backgrounding \
  --disable-background-timer-throttling \
  --lang=de-DE \
  --no-first-run \
  --no-default-browser-check \
  --noerrdialogs \
  --disable-save-password-bubble \
  --disable-crash-reporter \
  --disable-background-networking \
  --disable-breakpad \
  --disable-component-update \
  --disable-default-apps \
  --disable-extensions \
  --disable-session-crashed-bubble \
  --disable-sync \
  --metrics-recording-only \
  --password-store=basic \
  --disable-features=Translate,TouchpadOverscrollHistoryNavigation,OptimizationHints,MediaRouter \
  --disable-pinch \
  --overscroll-history-navigation=0 \
  "$@"
