# CNC Dashboard Knowledge Base

## Zweck des Projekts

Dieses Repository bildet die Basis fuer ein Dashboard fuer eine CNC-Fraese.
Das Dashboard laeuft auf einem Raspberry Pi 4 mit DietPi und wird lokal im Kiosk-Modus angezeigt.

Ziel ist eine zentrale Bedien- und Statusoberflaeche fuer Maschinenzustand, Wartung, Hardware-Steuerung und spaetere Remote-Funktionen.

## Aktueller Produktfokus

Die primaeren Aufgaben des Dashboards sind:

- Live-Preview der Lasten von X-, Y- und Z-Achse sowie der Spindel
- Anzeige und Verwaltung von Wartungsaufgaben
- Steuerung ausgewaehlter Hardwarekomponenten der Maschine

Die Lastwerte werden per I2C ausgelesen.

## Zielhardware und Laufzeitumgebung

### Rechenplattform

- Raspberry Pi 4
- DietPi als Betriebssystem
- Lokale Anzeige im Kiosk-Modus
- Zielauflosung des Dashboard-Displays: `1024x600`

UI-Grundsatz:

- Das gesamte lokale Dashboard-UI soll primaer fuer `1024x600` optimiert werden.
- Layout, Typografie, Abstaende, Touch-Ziele und Informationsdichte sollen sich an dieser Aufloesung orientieren.
- Andere Aufloesungen koennen spaeter unterstuetzt werden, sind aktuell aber nachrangig gegenueber einer sauberen Darstellung auf `1024x600`.

### Aktueller Zugriff

- Der aktuelle SSH-Login auf dem Entwicklungssystem erfolgt ueber `ssh cncpi`

Hinweis: Das wirkt wie ein lokal konfigurierter SSH-Alias und kann daher von der SSH-Konfiguration des jeweiligen Rechners abhaengen.

## Getesteter Systemzustand auf DietPi

### Clean Boot ohne Kernel-Logs

Auf dem Zielsystem wurde ein sauberer schwarzer Bootvorgang bis zum Login-Prompt erfolgreich getestet.
Ziel dieses Setups ist, Kernel-Logs und stoerende Firmware-Meldungen waehrend des Bootens zu unterdruecken.

#### Schritt 1: Kernel-Ausgabe auf ein unsichtbares Terminal verschieben

Datei: `/boot/firmware/cmdline.txt`

Die bestehende Zeile wird beibehalten und am Ende um die benoetigten Parameter ergaenzt.
Getestetes Beispiel:

```txt
root=PARTUUID=XXXXX-02 rootfstype=ext4 rootwait fsck.repair=yes net.ifnames=0 logo.nologo console=ttyS0,115200 console=tty3 loglevel=0 vt.global_cursor_default=0 quiet
```

Relevante Anpassungen gegenueber dem DietPi-Standard:

- `console=tty1` wurde auf `console=tty3` umgestellt, damit die Kernel-Ausgabe nicht auf dem sichtbaren Terminal erscheint.
- `loglevel=0` reduziert die Ausgabe auf kritische Kernel-Fehler.
- `vt.global_cursor_default=0` blendet den blinkenden Textcursor aus.
- `quiet` unterdrueckt weitere nicht-kritische Boot-Meldungen.
- `logo.nologo` war bereits vorhanden.

#### Schritt 2: Bluetooth deaktivieren

Datei: `/boot/firmware/config.txt`

Am Ende der Datei wurde folgender Eintrag ergaenzt:

```ini
dtoverlay=disable-bt
```

Damit verschwinden zusaetzliche Bluetooth-bezogene Firmware-Meldungen waehrend des Bootvorgangs.

#### Schritt 3: Verifikation

Nach `sudo reboot` war das erwartete Ergebnis ein sauberer schwarzer Bildschirm ohne Logs bis zum Login-Prompt.

#### Naechster geplanter Ausbauschritt

Als naechstes soll auf diesem sauberen Boot-Zustand ein eigener Custom Bootscreen aufgebaut werden.

### Chromium-Kiosk korrekt auf `1024x600`

Auf dem Zielsystem wurde der Chromium-Kiosk erfolgreich so eingerichtet, dass das Dashboard ohne schwarzen Balken und ohne abgeschnittenen rechten Rand auf dem `1024x600`-Display angezeigt wird.

Ausgangsproblem:

- Chromium lief zwar im Kiosk-Modus, die Darstellung war aber vertikal und horizontal falsch skaliert.
- Sichtbar waren ein schwarzer Balken am unteren Rand und ein abgeschnittener Bereich auf der rechten Seite.
- Ursache war, dass X/DRM nicht sauber auf der eigentlichen Panel-Aufloesung lief und zusaetzlich beide HDMI-Ausgaenge aktiv waren.

#### Schritt 1: Chromium-Zielgroesse in DietPi setzen

Datei: `/boot/dietpi.txt`

Die folgenden Werte wurden erfolgreich verwendet:

```ini
SOFTWARE_CHROMIUM_RES_X=1024
SOFTWARE_CHROMIUM_RES_Y=600
SOFTWARE_CHROMIUM_AUTOSTART_URL=http://127.0.0.1:8081/
```

Damit startet DietPi Chromium bereits mit der zur UI passenden Fenstergeometrie und direkt auf dem lokalen Frontend-Port.

#### Schritt 2: Grundlegende Display-Werte in der Firmware setzen

Datei: `/boot/firmware/config.txt`

Folgende Werte wurden verwendet:

```ini
disable_overscan=1
framebuffer_width=1024
framebuffer_height=600
```

Hinweis:

- Diese Werte allein haben das Problem noch nicht vollstaendig geloest.
- In der Praxis war entscheidend, dass die aktive Ausgabe auf den richtigen HDMI-Port gelegt und in X spaeter nochmals explizit auf `1024x600` gesetzt wurde.

#### Schritt 3: Chromium-Start um einen `xrandr`-Wrapper erweitern

Neue Datei auf dem Pi:

- `/usr/local/bin/cnc-dashboard-kiosk.sh`

Der Wrapper fuehrt vor dem eigentlichen Chromium-Start eine Display-Korrektur aus:

- Er legt einen `1024x600`-Mode fuer X an.
- Er aktiviert `HDMI-2` als primaeren Ausgang.
- Er schaltet `HDMI-1` ab.
- Danach startet er Chromium mit den von DietPi uebergebenen Kiosk-Parametern.

Verwendetes Skript:

```sh
#!/bin/sh
MODE_NAME='1024x600_60.00'

if command -v xrandr >/dev/null 2>&1; then
  i=0
  while [ "$i" -lt 5 ]; do
    if xrandr --query >/dev/null 2>&1; then
      xrandr --newmode "$MODE_NAME" 49.00 1024 1072 1168 1312 600 603 613 624 -hsync +vsync 2>/dev/null || true
      xrandr --addmode HDMI-2 "$MODE_NAME" 2>/dev/null || true
      xrandr --output HDMI-2 --primary --mode "$MODE_NAME" --output HDMI-1 --off 2>/dev/null && break
    fi
    i=$((i + 1))
    sleep 1
  done
fi

exec /usr/bin/chromium "$@"
```

#### Schritt 4: DietPi-Autostart auf den Wrapper umbiegen

Datei: `/var/lib/dietpi/dietpi-software/installed/chromium-autostart.sh`

Die Chromium-Zeile wurde so angepasst, dass nicht mehr direkt `/usr/bin/chromium`, sondern der Wrapper gestartet wird:

```sh
exec "$STARTX" /usr/local/bin/cnc-dashboard-kiosk.sh $CHROMIUM_OPTS "${URL:-https://dietpi.com/}"
```

#### Schritt 5: Kiosk-Session neu starten

Zum Uebernehmen der Aenderungen wurde erfolgreich verwendet:

```bash
sudo systemctl restart getty@tty1
```

Alternativ funktioniert auch ein kompletter Neustart des Pi.

#### Erfolgreiche Verifikation

Die funktionierende Endkonfiguration war erreicht, als folgende Bedingungen gleichzeitig erfuellt waren:

- `xrandr` meldete `current 1024 x 600`
- `HDMI-2` war `primary`
- Chromium startete mit `--window-size=1024,600`
- Das Dashboard wurde im Kiosk-Modus vollstaendig angezeigt, ohne schwarzen Balken unten und ohne abgeschnittenen rechten Rand
