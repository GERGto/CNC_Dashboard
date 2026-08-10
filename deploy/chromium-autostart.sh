#!/bin/sh

RES_X=$(sed -n '/^[[:blank:]]*SOFTWARE_CHROMIUM_RES_X=/{s/^[^=]*=//p;q}' /boot/dietpi.txt)
RES_Y=$(sed -n '/^[[:blank:]]*SOFTWARE_CHROMIUM_RES_Y=/{s/^[^=]*=//p;q}' /boot/dietpi.txt)
URL=$(sed -n '/^[[:blank:]]*SOFTWARE_CHROMIUM_AUTOSTART_URL=/{s/^[^=]*=//p;q}' /boot/dietpi.txt)

case "$RES_X" in ''|*[!0-9]*) RES_X=1024 ;; esac
case "$RES_Y" in ''|*[!0-9]*) RES_Y=600 ;; esac
# Chromium without a window manager creates its kiosk surface one pixel smaller
# than the requested outer size. The extra pixel is clipped by the X root window
# and gives the page an exact 1024x600 content viewport.
WINDOW_X=$((RES_X + 1))
WINDOW_Y=$((RES_Y + 1))

# -background none keeps the framebuffer content (the retained Plymouth
# frame) as the X root instead of clearing to black during server startup.
# /usr/bin/Xorg routes through the setuid Xorg.wrap (xserver-xorg-legacy),
# which grants VT/DRM access without a PAM/logind session.
exec /usr/bin/xinit /usr/local/bin/cnc-dashboard-kiosk.sh \
  --kiosk \
  --window-size="${WINDOW_X},${WINDOW_Y}" \
  --window-position=0,0 \
  "${URL:-http://127.0.0.1:8081/}" \
  -- /usr/bin/Xorg :0 vt1 -keeptty -nolisten tcp -ac -background none
