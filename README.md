# CNC Dashboard

Lokales Maschinen-Dashboard für DietPi mit Hardware-Backend, Kamera-Streaming,
Fullscreen-Touch-Kiosk und optionalem Tailscale-Wartungszugang.

## Installation auf DietPi

Git installieren und dieses Repository klonen beziehungsweise aktualisieren. Diese
beiden Schritte werden bewusst nicht durch den Installer übernommen. Anschließend
im Repository ausführen:

```sh
sudo sh ./install.sh
```

Der Installer richtet alle weiteren Komponenten ein:

- Chromium als früher systemd-Kiosk auf dem Benutzer `dietpi`, ohne sichtbaren Konsolenlogin
- Backend, Frontend, Caddy, Kamera-Publisher und MediaMTX als Systemdienste
- I²C, GPIO-/WS2812-Abhängigkeiten und die bekannte 1024×600-Displaykonfiguration
- einen eigenen Plymouth- und HTML-Bootscreen bis zur Übernahme des Fullscreen-Kiosks
- Tailscale für die über das lokale UI schaltbare Remote-Wartung
- ein separates Ethernetnetz für den DDCS V4.1 (`Pi: 192.168.2.8`, `DDCS: 192.168.2.5`)
- den persistenten Programmordner `/var/lib/cnc-dashboard/programs`
- eine authentifizierte WLAN-Samba-Freigabe `cnc-programs`
- den vorbereiteten SMB1-Transfer zur DDCS-Freigabe `cncdisk`

Der Paket- und DietPi-Teil läuft ohne Rückfragen. Bei einem interaktiven Aufruf fragt
der Installer einmal nach dem Samba-Passwort und bietet die Tailscale-Anmeldung an.
Für eine vollständig unbeaufsichtigte Installation müssen die Geheimnisse als
Umgebungsvariablen übergeben werden:

```sh
sudo CNC_SHARE_PASSWORD='sicheres-passwort' \
  TAILSCALE_AUTH_KEY='tskey-auth-...' \
  sh ./install.sh
```

Der Tailscale-Schlüssel wird nur über eine temporäre, ausschließlich für root lesbare
Datei an `tailscale up` gegeben. Ohne Auth-Key kann die Anmeldung im interaktiven
Installer durchgeführt oder später über SSH nachgeholt werden:

```sh
sudo tailscale up
```

Danach das System neu starten:

```sh
sudo reboot
```

## CNC-Programmdateien und Samba

Uploads aus der Remote-Monitoransicht werden dauerhaft unter
`/var/lib/cnc-dashboard/programs` gespeichert. Derselbe Ordner ist im WLAN als
`cnc-programs` freigegeben. Der Installer setzt dafür den stabilen Hostnamen
`cncpi`, sodass ein Wechsel der per DHCP vergebenen WLAN-IP keine Anpassung am
Windows-PC erfordert:

```text
\\cncpi\cnc-programs
```

Die Anmeldung erfolgt mit dem Benutzer `dietpi` und dem während der Installation
gesetzten Samba-Passwort. Bei einer nicht-interaktiven Installation kann es vorab
übergeben werden:

```text
Benutzer: dietpi
Passwort: marcusbierusmaschienus
```

```sh
sudo CNC_SHARE_PASSWORD='marcusbierusmaschienus' sh ./install.sh
```

Zusätzlich veröffentlicht Avahi den DNS-Namen `cncpi.local`. Falls die kurze
Windows-Namensauflösung in einem Netz deaktiviert ist, funktioniert daher in der
Regel auch `\\cncpi.local\cnc-programs`. Ein abweichender Maschinenname mit maximal
15 Zeichen kann beim Installerlauf mit `CNC_HOSTNAME=<name>` gesetzt werden. Das
Frontend übernimmt den tatsächlich konfigurierten Hostnamen automatisch in die
Windows-Anleitung.

Zusätzlich heißt derselbe Ordner am Controller-Ethernet `share`. Diese anonyme
Legacy-Freigabe ist auf `192.168.2.5` beschränkt und wird für die DDCS-Funktion
„Net Disk“ benötigt. Für den Zugriff aus dem WLAN bleibt ausschließlich die
passwortgeschützte Freigabe `cnc-programs` vorgesehen.

## DDCS V4.1 einrichten

Am DDCS unter **Parameters → System settings** folgende Werte setzen:

```text
#325 "Disable network functionality": No
#326 "Obtain IP address automatically": No
#327 Lokale IP-Adresse: 192.168.2.5
#328 Netzmaske: 255.255.255.0
#329 Router-IP: 192.168.2.8
#330 Shared host IP: 192.168.2.8
```

Danach den DDCS neu starten. Seine lokale Platte ist für den Pi als
`\\192.168.2.5\cncdisk` erreichbar. Im DDCS-Dateimanager zeigt **Net Disk** die
Pi-Freigabe `share`. Das Backend überträgt neue Uploads automatisch in `cncdisk`.

Die vorinstallierte Controller-Konfiguration liegt unter
`/etc/cnc-dashboard/controller-smb.env`:

```ini
CNC_CONTROLLER_SMB_ENABLED=1
CNC_CONTROLLER_SMB_HOST=192.168.2.5
CNC_CONTROLLER_SMB_SHARE=cncdisk
CNC_CONTROLLER_SMB_USERNAME=
CNC_CONTROLLER_SMB_PASSWORD=
CNC_CONTROLLER_SMB_REMOTE_DIRECTORY=
CNC_CONTROLLER_SMB_PROTOCOL=NT1
```

Anschließend das Backend neu starten:

```sh
sudo systemctl restart cnc-dashboard-backend.service
```

Falls die IP oder Firmware des Controllers abweicht, können diese Werte angepasst
und das Backend anschließend neu gestartet werden.

Der Installer ist wiederholbar. Vorhandene `settings.json`, `tasks.json` und
`machine_stats.json` unter `/opt/cnc-dashboard/backend` bleiben bei einem erneuten
Durchlauf erhalten.

## Zielpfade

- Anwendung: `/opt/cnc-dashboard`
- lokales UI: `http://127.0.0.1:8081/`
- Remote-Monitor im LAN oder Tailnet: `http://<IP-des-Geräts>/`
- Backend-API: `http://127.0.0.1:8080/`

Die Displayparameter können vor dem Aufruf bei Bedarf über eine angepasste Version
der Dateien unter `deploy/` geändert werden. MediaMTX ist standardmäßig auf die auf
dem Referenzsystem geprüfte Version `1.20.0` festgelegt. Eine andere Version kann
bei Bedarf über die Umgebungsvariable `MEDIAMTX_VERSION` gesetzt werden.
