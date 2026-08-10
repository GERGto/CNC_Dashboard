#!/bin/sh
set -eu

INSTALL_DIR=${INSTALL_DIR:-/opt/cnc-dashboard}
KIOSK_USER=${KIOSK_USER:-dietpi}
CNC_HOSTNAME=${CNC_HOSTNAME:-cncpi}
MEDIAMTX_VERSION=${MEDIAMTX_VERSION:-1.20.0}
SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TEMP_PATHS=""

info() {
  printf '\n[CNC Dashboard] %s\n' "$*"
}

fail() {
  printf '\n[CNC Dashboard] FEHLER: %s\n' "$*" >&2
  exit 1
}

cleanup() {
  for path in $TEMP_PATHS; do
    [ -n "$path" ] && [ -e "$path" ] && rm -rf -- "$path"
  done
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

new_temp_dir() {
  NEW_TEMP_DIR=$(mktemp -d /tmp/cnc-dashboard.XXXXXX)
  TEMP_PATHS="$TEMP_PATHS $NEW_TEMP_DIR"
}

set_config_value() {
  key=$1
  value=$2
  file=$3
  if grep -q "^[[:space:]]*${key}=" "$file"; then
    sed -i "s|^[[:space:]]*${key}=.*|${key}=${value}|" "$file"
  else
    printf '%s=%s\n' "$key" "$value" >> "$file"
  fi
}

set_boot_config_value() {
  key=$1
  value=$2
  file=$3
  if grep -q "^[[:space:]]*${key}=" "$file"; then
    sed -i "s|^[[:space:]]*${key}=.*|${key}=${value}|" "$file"
  else
    printf '\n%s=%s\n' "$key" "$value" >> "$file"
  fi
}

[ "$(id -u)" -eq 0 ] || fail "Bitte mit sudo ausführen: sudo sh ./install.sh"
[ -f /boot/dietpi/.version ] || fail "Dieses Installationsskript ist für DietPi vorgesehen."
id "$KIOSK_USER" >/dev/null 2>&1 || fail "Der DietPi-Benutzer '$KIOSK_USER' fehlt."
[ -f "$SOURCE_DIR/backend/server.py" ] || fail "Das Skript muss aus dem geklonten Repository gestartet werden."
printf '%s' "$CNC_HOSTNAME" | grep -Eq '^[a-zA-Z0-9]([a-zA-Z0-9-]{0,13}[a-zA-Z0-9])?$' || \
  fail "CNC_HOSTNAME muss ein gültiger Hostname mit höchstens 15 Zeichen sein."

info "DietPi-Paketlisten und Systemabhängigkeiten werden eingerichtet"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y \
  avahi-daemon ca-certificates curl caddy dnsmasq ffmpeg gpiod i2c-tools libcairo2 python3 python3-pip \
  python3-smbus python3-venv plymouth plymouth-themes samba smbclient x11-xserver-utils unclutter-xfixes \
  xserver-xorg-legacy

info "Stabiler Maschinenhostname wird eingerichtet"
hostnamectl set-hostname "$CNC_HOSTNAME"
if grep -q '^[[:space:]]*127\.0\.1\.1[[:space:]]' /etc/hosts; then
  sed -i "s/^[[:space:]]*127\.0\.1\.1[[:space:]].*/127.0.1.1\t${CNC_HOSTNAME}/" /etc/hosts
else
  printf '127.0.1.1\t%s\n' "$CNC_HOSTNAME" >> /etc/hosts
fi
systemctl enable --now avahi-daemon.service

info "Chromium-Kiosk wird über DietPi-Software installiert"
set_config_value AUTO_SETUP_AUTOSTART_LOGIN_USER "$KIOSK_USER" /boot/dietpi.txt
set_config_value SOFTWARE_CHROMIUM_RES_X 1024 /boot/dietpi.txt
set_config_value SOFTWARE_CHROMIUM_RES_Y 600 /boot/dietpi.txt
set_config_value SOFTWARE_CHROMIUM_AUTOSTART_URL http://127.0.0.1:8081/ /boot/dietpi.txt
/boot/dietpi/dietpi-software install 113

info "DietPi-Hardwareoptionen werden nicht-interaktiv gesetzt"
/boot/dietpi/func/dietpi-set_hardware i2c enable
/boot/dietpi/func/dietpi-set_hardware rpi-opengl vc4-kms-v3d
/boot/dietpi/func/dietpi-set_hardware bluetooth disable || true

info "Projektdateien werden nach $INSTALL_DIR installiert"
if [ "$SOURCE_DIR" != "$INSTALL_DIR" ]; then
  new_temp_dir
  persist_dir=$NEW_TEMP_DIR
  for name in settings.json tasks.json machine_stats.json; do
    if [ -f "$INSTALL_DIR/backend/$name" ]; then
      cp -p "$INSTALL_DIR/backend/$name" "$persist_dir/$name"
    fi
  done
  install -d -m 0755 "$INSTALL_DIR"
  tar -C "$SOURCE_DIR" --exclude=.git --exclude='*.lnk' -cf - . | tar -C "$INSTALL_DIR" -xf -
  for name in settings.json tasks.json machine_stats.json; do
    if [ -f "$persist_dir/$name" ]; then
      cp -p "$persist_dir/$name" "$INSTALL_DIR/backend/$name"
    fi
  done
fi
# The tar overlay above never deletes files; remove artifacts that no longer
# exist in the repository so upgrades converge on the current state.
rm -f "$INSTALL_DIR/frontend/boot.html" "$INSTALL_DIR/deploy/cnc-dashboard-browser-preload.service" \
  "$INSTALL_DIR/deploy/cnc-dashboard-initramfs-copy.sh"
chown -R "$KIOSK_USER:$KIOSK_USER" "$INSTALL_DIR"

info "Python-Laufzeitumgebung und WS2812-Treiber werden installiert"
# GPIO access is supplied by DietPi's system package (python3-libgpiod). Keep
# that hardware module visible inside the otherwise isolated application venv.
python3 -m venv --system-site-packages "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/python" -m pip install --disable-pip-version-check 'rpi-ws281x==5.0.0'

info "MediaMTX $MEDIAMTX_VERSION wird installiert und per Prüfsumme verifiziert"
case "$(uname -m)" in
  aarch64|arm64) mediamtx_arch=arm64 ;;
  armv7l|armv7) mediamtx_arch=armv7 ;;
  x86_64|amd64) mediamtx_arch=amd64 ;;
  *) fail "Nicht unterstützte MediaMTX-Architektur: $(uname -m)" ;;
esac
mediamtx_archive="mediamtx_v${MEDIAMTX_VERSION}_linux_${mediamtx_arch}.tar.gz"
mediamtx_url="https://github.com/bluenviron/mediamtx/releases/download/v${MEDIAMTX_VERSION}"
new_temp_dir
media_dir=$NEW_TEMP_DIR
curl -fsSL "$mediamtx_url/$mediamtx_archive" -o "$media_dir/$mediamtx_archive"
curl -fsSL "$mediamtx_url/checksums.sha256" -o "$media_dir/checksums.sha256"
(
  cd "$media_dir"
  checksum_line=$(grep "$mediamtx_archive\$" checksums.sha256)
  [ -n "$checksum_line" ]
  printf '%s\n' "$checksum_line" | sha256sum -c -
  tar -xzf "$mediamtx_archive" mediamtx
)
install -m 0755 "$media_dir/mediamtx" /usr/local/bin/mediamtx

info "Tailscale wird aus dem offiziellen Paket-Repository installiert"
if ! command -v tailscale >/dev/null 2>&1; then
  new_temp_dir
  tailscale_dir=$NEW_TEMP_DIR
  curl -fsSL https://tailscale.com/install.sh -o "$tailscale_dir/install-tailscale.sh"
  sh "$tailscale_dir/install-tailscale.sh"
fi
systemctl enable --now tailscaled.service

info "Lokales CNC-Ethernetnetz wird eingerichtet"
install -d -m 0755 /etc/network/interfaces.d
grep -q '^[[:space:]]*source[[:space:]].*interfaces\.d' /etc/network/interfaces || \
  printf '\nsource interfaces.d/*\n' >> /etc/network/interfaces
# Migrate the repository's former generic controller subnet to the documented DDCS V4.1 subnet.
for interfaces_file in /etc/network/interfaces /etc/network/interfaces.d/*; do
  [ -f "$interfaces_file" ] || continue
  sed -i 's/192\.168\.137\.1/192.168.2.8/g' "$interfaces_file"
done
if ! grep -Rqs '^[[:space:]]*iface[[:space:]]\+eth0[[:space:]]\+inet[[:space:]]\+static' \
  /etc/network/interfaces /etc/network/interfaces.d; then
  install -m 0644 "$INSTALL_DIR/deploy/cnc-controller-eth0" /etc/network/interfaces.d/cnc-controller
fi
install -m 0644 "$INSTALL_DIR/deploy/cnc-controller-dnsmasq.conf" /etc/dnsmasq.d/cnc-eth0.conf
dnsmasq --test
systemctl enable --now dnsmasq.service

info "Lokaler SMB-Zwischenordner wird im WLAN freigegeben"
install -d -m 0750 /etc/cnc-dashboard
if [ ! -f /etc/cnc-dashboard/controller-smb.env ]; then
  install -m 0600 "$INSTALL_DIR/deploy/controller-smb.env" /etc/cnc-dashboard/controller-smb.env
elif grep -q '^CNC_CONTROLLER_SMB_ENABLED=0$' /etc/cnc-dashboard/controller-smb.env && \
     grep -q '^CNC_CONTROLLER_SMB_HOST=$' /etc/cnc-dashboard/controller-smb.env && \
     grep -q '^CNC_CONTROLLER_SMB_SHARE=$' /etc/cnc-dashboard/controller-smb.env; then
  install -m 0600 "$INSTALL_DIR/deploy/controller-smb.env" /etc/cnc-dashboard/controller-smb.env
fi
install -d -m 0770 -o "$KIOSK_USER" -g "$KIOSK_USER" /var/lib/cnc-dashboard/programs
if [ -f /etc/samba/smb.conf ]; then
  sed -i '/^# BEGIN CNC DASHBOARD$/,/^# END CNC DASHBOARD$/d' /etc/samba/smb.conf
  printf '\n' >> /etc/samba/smb.conf
  cat "$INSTALL_DIR/deploy/samba-share.conf" >> /etc/samba/smb.conf
  samba_netbios_name=$(printf '%s' "$CNC_HOSTNAME" | tr '[:lower:]' '[:upper:]')
  sed -i "s/^[[:space:]]*netbios name = CNCPI$/    netbios name = ${samba_netbios_name}/" /etc/samba/smb.conf
else
  fail "Samba-Konfiguration /etc/samba/smb.conf fehlt"
fi
testparm -s /etc/samba/smb.conf >/dev/null
if ! pdbedit -L 2>/dev/null | grep -q "^${KIOSK_USER}:"; then
  if [ -n "${CNC_SHARE_PASSWORD:-}" ]; then
    printf '%s\n%s\n' "$CNC_SHARE_PASSWORD" "$CNC_SHARE_PASSWORD" | smbpasswd -s -a "$KIOSK_USER"
  elif [ -t 0 ]; then
    printf '\nBitte jetzt ein Passwort für die WLAN-SMB-Freigabe festlegen.\n'
    smbpasswd -a "$KIOSK_USER"
  else
    fail "Für eine unbeaufsichtigte Installation muss CNC_SHARE_PASSWORD gesetzt sein."
  fi
fi
systemctl enable --now smbd.service nmbd.service

info "Dashboard-, Proxy- und Kamera-Dienste werden eingerichtet"
install -m 0644 "$INSTALL_DIR/backend/cnc-dashboard-backend.service" /etc/systemd/system/cnc-dashboard-backend.service
install -m 0644 "$INSTALL_DIR/backend/cnc-dashboard-mediamtx.service" /etc/systemd/system/cnc-dashboard-mediamtx.service
install -m 0644 "$INSTALL_DIR/backend/cnc-dashboard-camera-publisher.service" /etc/systemd/system/cnc-dashboard-camera-publisher.service
install -m 0644 "$INSTALL_DIR/frontend/cnc-dashboard-frontend.service" /etc/systemd/system/cnc-dashboard-frontend.service
install -m 0644 "$INSTALL_DIR/frontend/Caddyfile" /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile

info "Fullscreen-Kiosk und minimierte Bootausgabe werden konfiguriert"
install -m 0755 "$INSTALL_DIR/deploy/cnc-dashboard-kiosk.sh" /usr/local/bin/cnc-dashboard-kiosk.sh
install -m 0755 "$INSTALL_DIR/deploy/cnc-dashboard-xsplash.py" /usr/local/bin/cnc-dashboard-xsplash.py
# Pre-render the boot frame as a root-window bitmap so the splash is on
# screen in the first milliseconds of the X session.
install -d -m 0755 /usr/local/share/cnc-dashboard
python3 "$INSTALL_DIR/deploy/generate-splash-xbm.py" /usr/local/share/cnc-dashboard/splash.xbm 1024 600
install -m 0755 "$INSTALL_DIR/deploy/chromium-autostart.sh" /var/lib/dietpi/dietpi-software/installed/chromium-autostart.sh
install -m 0644 "$INSTALL_DIR/deploy/cnc-dashboard-kiosk.service" /etc/systemd/system/cnc-dashboard-kiosk.service
# The former Chromium preload (dd over the ~200MB binary) competed with the
# Xorg cold start for SD-card I/O: mmc uses mq-deadline, which ignores the
# idle I/O class, and delayed the first kiosk frame by ~8 seconds.
systemctl disable --now cnc-dashboard-browser-preload.service >/dev/null 2>&1 || true
rm -f /etc/systemd/system/cnc-dashboard-browser-preload.service
install -m 0644 "$INSTALL_DIR/deploy/cnc-dashboard-background.service" /etc/systemd/system/cnc-dashboard-background.service
install -m 0644 "$INSTALL_DIR/deploy/cnc-dashboard-background.timer" /etc/systemd/system/cnc-dashboard-background.timer
install -d -m 0755 /etc/X11/xorg.conf.d
install -m 0644 "$INSTALL_DIR/deploy/20-cnc-dashboard-display.conf" /etc/X11/xorg.conf.d/20-cnc-dashboard-display.conf
# Xorg runs via the setuid wrapper with root rights and no PAM/logind session.
# A logind session would couple the kiosk start to user@1000.service, which is
# ordered after systemd-user-sessions.service and therefore network.target -
# the first kiosk frame would wait for WLAN DHCP (measured: 6-12s extra).
printf 'allowed_users=anybody\nneeds_root_rights=yes\n' > /etc/X11/Xwrapper.config
install -d -m 0755 /etc/chromium/policies/managed
printf '%s\n' '{"TranslateEnabled":false,"DefaultBrowserSettingEnabled":false,"BrowserSignin":0,"PasswordManagerEnabled":false,"PasswordLeakDetectionEnabled":false}' \
  > /etc/chromium/policies/managed/cnc-dashboard.json

# DietPi's Chromium option 11 starts only after an automatic console login. Keep
# Chromium installed/configured by DietPi, but let the early systemd unit own tty1.
/boot/dietpi/dietpi-autostart 0
systemctl mask getty@tty1.service

info "Individueller CNC-Bootscreen wird eingerichtet"
install -d -m 0755 /usr/share/plymouth/themes/cnc-dashboard
install -m 0644 "$INSTALL_DIR/deploy/plymouth/cnc-dashboard.plymouth" \
  /usr/share/plymouth/themes/cnc-dashboard/cnc-dashboard.plymouth
install -m 0644 "$INSTALL_DIR/deploy/plymouth/cnc-dashboard.script" \
  /usr/share/plymouth/themes/cnc-dashboard/cnc-dashboard.script
install -m 0644 "$INSTALL_DIR/deploy/plymouth/progress-track.png" \
  /usr/share/plymouth/themes/cnc-dashboard/progress-track.png
install -m 0644 "$INSTALL_DIR/deploy/plymouth/progress-fill.png" \
  /usr/share/plymouth/themes/cnc-dashboard/progress-fill.png
rm -f /etc/initramfs/post-update.d/cnc-dashboard-firmware-copy
plymouth-set-default-theme cnc-dashboard
# Explicit daemon settings: show the splash immediately once the DRM device
# appears (vc4 binds ~4s after kernel start; there is no initramfs).
printf '[Daemon]\nTheme=cnc-dashboard\nShowDelay=0\nDeviceTimeout=8\n' > /etc/plymouth/plymouthd.conf

# Keep firmware, KMS, Xorg and Chromium on one timing. The physical MPI7002
# EDID contains a native timing that vc4 rejects, which otherwise causes KMS to
# switch to 1920x1080 and Xorg to switch twice more during every boot.
install -d -m 0755 /usr/lib/firmware/edid
edid_source=
for candidate in /sys/class/drm/card*-HDMI-A-2/edid; do
  # sysfs attributes report a metadata size of zero even when their contents
  # are readable, so -s must not be used here.
  if [ -r "$candidate" ]; then
    edid_source=$candidate
    break
  fi
done
if [ -n "$edid_source" ]; then
  python3 "$INSTALL_DIR/deploy/generate-edid.py" \
    /usr/lib/firmware/edid/cnc-dashboard-1024x600.bin "$edid_source"
else
  python3 "$INSTALL_DIR/deploy/generate-edid.py" \
    /usr/lib/firmware/edid/cnc-dashboard-1024x600.bin
fi

boot_config=/boot/firmware/config.txt
[ -f "$boot_config" ] || boot_config=/boot/config.txt
# The machine display is connected to the Pi 4 HDMI1 socket (DRM HDMI-A-2).
# Remove the earlier HDMI0 overrides so firmware, Plymouth and X use one output.
sed -i '/^[[:space:]]*hdmi_\(force_hotplug\|group\|mode\|cvt\|drive\):0=/d' "$boot_config"
set_boot_config_value disable_splash 1 "$boot_config"
set_boot_config_value auto_initramfs 0 "$boot_config"
set_boot_config_value disable_fw_kms_setup 1 "$boot_config"
set_boot_config_value disable_overscan 1 "$boot_config"
set_boot_config_value framebuffer_width 1024 "$boot_config"
set_boot_config_value framebuffer_height 600 "$boot_config"
set_boot_config_value hdmi_blanking 0 "$boot_config"
set_boot_config_value 'hdmi_force_hotplug:1' 1 "$boot_config"
set_boot_config_value 'hdmi_group:1' 2 "$boot_config"
set_boot_config_value 'hdmi_mode:1' 87 "$boot_config"
# Give the firmware the exact detailed timing from the patched EDID (51.20MHz,
# 1024 1072 1168 1344, 600 611 621 635). One timing for firmware, kernel and
# Xorg means the panel locks its PLL once per boot. The 51.20 MHz clock is
# deliberate: at 49.00 MHz the TMDS rate was 490 Mbit/s, whose 5th harmonic
# (2.45 GHz) sits mid 2.4 GHz band - every Wi-Fi scan sheared the panel image.
sed -i '/^[[:space:]]*hdmi_cvt:1=/d' "$boot_config"
set_boot_config_value 'hdmi_timings:1' '1024 0 48 96 176 600 1 11 10 14 0 0 0 60 0 51200000 6' "$boot_config"
set_boot_config_value 'hdmi_drive:1' 2 "$boot_config"
# Pin the GPU core clock. On the Pi 4 the HDMI pixel clock is derived from the
# core clock domain, so every dynamic core transition (measured: 333 MHz idle
# <-> 500 MHz under load) briefly disturbs the output - the panel then shows a
# diagonally sheared image for several seconds. Any load spike triggered it:
# opening a dropdown, a Wi-Fi scan, or the Chromium cold start. It was also
# exactly reproducible at boot the moment initial_turbo expired.
set_boot_config_value core_freq 500 "$boot_config"
set_boot_config_value core_freq_min 500 "$boot_config"
# Keep CPU clocks at turbo through the Chromium cold start as well.
set_boot_config_value initial_turbo 30 "$boot_config"
# No HDMI audio: Chromium's audio service opens the vc4 HDMI audio device
# lazily (~30s after boot), and the newly started audio infoframes visibly
# disturb the panel signal (sheared image for ~2s). The appliance is mute.
sed -i 's|^[[:space:]]*dtoverlay=vc4-kms-v3d[[:space:]]*$|dtoverlay=vc4-kms-v3d,noaudio|' "$boot_config"
grep -q '^[[:space:]]*dtoverlay=disable-bt[[:space:]]*$' "$boot_config" || printf '%s\n' 'dtoverlay=disable-bt' >> "$boot_config"

cmdline_file=/boot/firmware/cmdline.txt
[ -f "$cmdline_file" ] || cmdline_file=/boot/cmdline.txt
cmdline_tmp=$(mktemp /tmp/cnc-dashboard-cmdline.XXXXXX)
TEMP_PATHS="$TEMP_PATHS $cmdline_tmp"
awk '
  {
    output = ""
    for (i = 1; i <= NF; i++) {
      if ($i ~ /^console=/ || $i ~ /^video=HDMI-A-[12]:/ || $i ~ /^(drm.)?edid_firmware=/ ||
          $i == "quiet" || $i == "splash" || $i == "plymouth.ignore-serial-consoles" ||
          $i ~ /^loglevel=/ || $i == "logo.nologo" || $i ~ /^fbcon=/ ||
          $i ~ /^vt.global_cursor_default=/ || $i ~ /^(rd.)?systemd.show_status=/ || $i ~ /^udev.log_level=/) {
        continue
      }
      output = output (output ? " " : "") $i
    }
    # fbcon=map:2 keeps the framebuffer console off the panel entirely: no
    # console clear over the Plymouth frame, no stray characters, and the
    # retained splash survives until Xorg takes over. Recovery access is SSH.
    print output " drm.edid_firmware=HDMI-A-2:edid/cnc-dashboard-1024x600.bin video=HDMI-A-1:d video=HDMI-A-2:1024x600@60e console=tty3 fbcon=map:2 loglevel=0 quiet splash plymouth.ignore-serial-consoles logo.nologo vt.global_cursor_default=0 systemd.show_status=false rd.systemd.show_status=false udev.log_level=3"
  }
' "$cmdline_file" > "$cmdline_tmp"
install -m 0644 "$cmdline_tmp" "$cmdline_file"

systemctl daemon-reload
# The local kiosk is the only boot-critical UI. Delaying remote/network/media
# daemons prevents SD-card and CPU contention while Xorg and Chromium perform
# their cold start.
systemctl disable caddy.service smbd.service nmbd.service tailscaled.service \
  cnc-dashboard-mediamtx.service cnc-dashboard-camera-publisher.service
systemctl enable cnc-dashboard-backend.service cnc-dashboard-frontend.service cnc-dashboard-kiosk.service \
  cnc-dashboard-background.timer
systemctl restart cnc-dashboard-backend.service cnc-dashboard-frontend.service \
  cnc-dashboard-mediamtx.service caddy.service
systemctl restart cnc-dashboard-camera-publisher.service || true
systemctl restart smbd.service nmbd.service dnsmasq.service

info "Dienste werden geprüft"
curl -fsS --retry 15 --retry-delay 1 http://127.0.0.1:8080/api/health >/dev/null
curl -fsS --retry 15 --retry-delay 1 http://127.0.0.1:8080/api/programs >/dev/null
curl -fsS --retry 15 --retry-delay 1 http://127.0.0.1:8081/ >/dev/null
systemctl --quiet is-active cnc-dashboard-backend.service
systemctl --quiet is-active cnc-dashboard-frontend.service
systemctl --quiet is-active cnc-dashboard-mediamtx.service
systemctl --quiet is-active caddy.service
systemctl --quiet is-active smbd.service
systemctl --quiet is-active dnsmasq.service
systemctl --quiet is-active avahi-daemon.service
systemctl --quiet is-enabled cnc-dashboard-kiosk.service

tailscale_state=$(tailscale status --json 2>/dev/null | grep -o '"BackendState"[[:space:]]*:[[:space:]]*"[^"]*"' | head -n 1 || true)
if printf '%s' "$tailscale_state" | grep -q 'NeedsLogin'; then
  printf '\nTailscale benötigt einmalig eine Anmeldung am Tailnet.\n'
  if [ -n "${TAILSCALE_AUTH_KEY:-}" ]; then
    new_temp_dir
    tailscale_auth_dir=$NEW_TEMP_DIR
    printf '%s' "$TAILSCALE_AUTH_KEY" > "$tailscale_auth_dir/auth-key"
    chmod 0600 "$tailscale_auth_dir/auth-key"
    tailscale up "--auth-key=file:$tailscale_auth_dir/auth-key"
  elif [ -t 0 ]; then
    printf 'Tailscale jetzt anmelden? [J/n] '
    read -r answer || answer=n
    case "$answer" in
      n|N|nein|Nein) : ;;
      *) tailscale up ;;
    esac
  else
    printf 'Nach der Installation ausführen: sudo tailscale up\n'
  fi
fi

printf '\n[CNC Dashboard] Installation erfolgreich.\n'
printf 'Bitte jetzt neu starten: sudo reboot\n'
printf 'Nach dem Neustart öffnet sich das lokale UI automatisch im Fullscreen-Kiosk.\n'
