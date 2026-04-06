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
- Anzeige des Maschinenstatus ueber einen externen RGB-LED-Streifen

Die Lastwerte werden per I2C ausgelesen.

Der Maschinenstatus soll zusaetzlich physisch an der Maschine sichtbar sein:

- `Blau`: Startup-Sequenz von der Mitte nach aussen
- `Weiss`: `IDLE` mit sanftem wanderndem Atmen
- `Orange`: Warnung oder Wartung faellig
- `Gruen`: Job laeuft oder Spindel laeuft
- `Rot`: `E-Stop` aktiv

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
- Die aktuell bekannte direkte IP des Raspberry Pi ist `192.168.178.61`

Hinweis: Das wirkt wie ein lokal konfigurierter SSH-Alias und kann daher von der SSH-Konfiguration des jeweiligen Rechners abhaengen.

### Ethernet fuer CNC-Controller als lokales Netz

Der Raspberry Pi wurde so umgestellt, dass `eth0` nicht mehr per DHCP im Heimnetz sucht, sondern ein eigenes lokales Netz fuer den CNC-Controller bereitstellt.

Zielbild:

- `wlan0`: Verbindung ins Heimnetz und Zugriff auf das lokale Web-UI
- `eth0`: separates Punkt-zu-Punkt-/Lokalsegment fuer den CNC-Controller
- Dateifluss spaeter: Upload ins Web-UI auf dem Pi und Weitergabe vom Pi an das CNC-Board

Aktive Konfiguration auf dem Pi:

- Statische IP des Pi auf `eth0`: `192.168.137.1/24`
- DHCP-Server auf `eth0` via `dnsmasq`
- DHCP-Bereich fuer den CNC-Controller: `192.168.137.100` bis `192.168.137.150`
- Gateway-Option per DHCP: `192.168.137.1`
- DNS ist in `dnsmasq` bewusst deaktiviert (`port=0`), da fuer den lokalen SMB-Dateitransfer zunaechst nur DHCP benoetigt wird

Geaenderte Dateien auf dem Pi:

- `/etc/network/interfaces`
- `/etc/dnsmasq.d/cnc-eth0.conf`

Verwendete `dnsmasq`-Konfiguration:

```ini
port=0
interface=eth0
bind-interfaces
dhcp-authoritative
dhcp-range=192.168.137.100,192.168.137.150,255.255.255.0,12h
dhcp-option=option:router,192.168.137.1
dhcp-leasefile=/var/lib/misc/dnsmasq.eth0.leases
```

Verifikation:

- `ip -4 addr show eth0` zeigt `192.168.137.1/24`
- `systemctl status dnsmasq --no-pager` zeigt einen laufenden Dienst
- `journalctl -u dnsmasq -n 20 --no-pager` bestaetigt, dass DHCP exklusiv auf `eth0` gebunden ist

Nutzen fuer den Bootvorgang:

- Vor der Umstellung wartete `eth0` beim Booten auf DHCP und blockierte dadurch den Kiosk-Start deutlich.
- Mit der statischen `eth0`-Konfiguration sollte dieser Blocker beim naechsten Neustart entfallen oder stark reduziert sein.

## Aktuell bekannte I2C-Hardware

- `Adafruit AHT20` fuer die Spindeltemperatur auf `0x38`
- `Adafruit INA228` fuer die `X`-Achslast auf `0x40`
- `GHI GDL-ACRELAYP4-C` 4-Kanal-Relais auf `0x52` (`82` dezimal)
- `PCF8574`-kompatibles 8-Kanal-Optokoppler-Eingangsmodul auf `0x21`
  - Produkt: `PCF8574 I2C 8 Kanal Optokoppler Eingang Input Modul 3,6-24V`
  - Auf dem Pi per erneutem `i2cdetect -y 1` nach dem Umstecken der Adressjumper auf Bus `1` verifiziert
  - Feste Betriebsadresse im aktuellen Aufbau: `0x21`
  - Die Adresse `0x21` liegt im offiziellen `PCF8574`-Bereich `0x20` bis `0x27` und nicht im `PCF8574A`-Bereich `0x38` bis `0x3F`
  - Daraus folgt: Der aktuell aktive Adressdecoder des Moduls verhaelt sich im Live-Betrieb wie ein `PCF8574`, nicht wie ein `PCF8574A`
  - `Input 1` und `Input 2` sind fest fuer mechanische Hardware-E-Stops reserviert
  - `Input 3` ist fest als `Spindel laeuft` verdrahtet
  - Sobald `Input 1` oder `Input 2` aktiv wird, loest das Backend sofort einen System-E-Stop aus
  - Dieser Hardware-E-Stop kann nicht im Frontend quittiert werden; er bleibt aktiv, bis der mechanische Taster real geloest wurde
  - Die Spindellaufzeit wird nur hochgezaehlt, solange `Input 3` aktiv ist

Geplante/Backend-vorbereitete Erweiterung fuer Achslasten:

- `Y`-Achse: `INA228` auf `0x41`
- `Z`-Achse: `INA228` auf `0x44`

Aktuelle Relaisbelegung im Dashboard:

- Kanal 1: Maschinenlicht
- Kanal 2: Spindelluefter
- Kanal 3: Reserve
- Kanal 4: E-Stop

Aktuelle E-Stop-Logik:

- Frontend-E-Stop nutzt Relaiskanal `4`
- Hardware-E-Stop kommt zusaetzlich ueber das PCF8574-Eingangsmodul auf `Input 1` und `Input 2`
- Spindel-Running kommt ueber dasselbe Eingangsmodul auf `Input 3`
- Der effektive Maschinen-Not-Halt ist aktiv, sobald Relaiskanal `4` aktiv ist oder einer der Hardware-E-Stop-Eingaenge ausloest
- Bei aktivem Hardware-E-Stop zeigt das lokale UI die rote Statusleiste `E-STOP`, und der WS2812B-Statusstreifen wechselt auf rot
- Die Spindellaufzeit kommt nicht mehr aus der Lastkurve, sondern nur noch aus dem echten Hardware-Signal auf `Input 3`

## Aktuell bekannte GPIO-/LED-Hardware

- `WS2812B` RGB-LED-Streifen fuer den Maschinenstatus
  - Versorgung: `5V`
  - Datensignal: `GPIO18`
  - Aktuelle Laenge: `59` LEDs
  - Startup-Sequenz: blau von der Mitte nach aussen, danach Systemcheck auf Weiss
  - Idle-Sequenz: langsame wandernde weisse Wellen zwischen `RGB 28` und `127`, gedeckelt auf `50%` Maximalhelligkeit

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

### Mauszeiger im Touch-Kiosk ausblenden

Auf dem Zielsystem wurde der Mauszeiger im Chromium-Kiosk erfolgreich ausgeblendet, ohne die Touch-Bedienung zu blockieren.

Ausgangsproblem:

- Im Kiosk war trotz Touch-Bedienung weiterhin ein sichtbarer Mauszeiger vorhanden.
- Eine reine Frontend-Loesung mit `cursor: none` wurde vom Pi zwar ausgeliefert, der sichtbare Zeiger kam jedoch weiterhin aus X/Chromium.
- Die erste Variante mit `unclutter classic` und `-grab` war fuer diesen Anwendungsfall ungeeignet, weil waehrend der Finger auf dem Display war weiterhin ein Zeiger sichtbar sein konnte und Touch-Klicks gestoert wurden.

#### Erfolgreiche Loesung

Die stabile Loesung bestand darin, auf dem Pi die XFixes-basierte Variante von `unclutter` zu verwenden.

Installierter Helfer:

```bash
sudo apt-get install -y unclutter-xfixes
```

Hinweis:

- Danach zeigt `/usr/bin/unclutter` per `update-alternatives` auf `/usr/bin/unclutter-xfixes`.

#### Kiosk-Wrapper erweitern

Datei: `/usr/local/bin/cnc-dashboard-kiosk.sh`

Vor dem Chromium-Start wurde der folgende Block erfolgreich eingefuegt:

```sh
if command -v unclutter >/dev/null 2>&1; then
  pkill -x unclutter >/dev/null 2>&1 || true
  unclutter --timeout 0 --hide-on-touch --start-hidden --fork >/dev/null 2>&1 || true
fi
```

Der vollstaendige Wrapper lautet damit:

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

if command -v unclutter >/dev/null 2>&1; then
  pkill -x unclutter >/dev/null 2>&1 || true
  unclutter --timeout 0 --hide-on-touch --start-hidden --fork >/dev/null 2>&1 || true
fi

exec /usr/bin/chromium "$@"
```

#### Kiosk-Session neu starten

```bash
sudo systemctl restart getty@tty1
```

#### Erfolgreiche Verifikation

Die funktionierende Endkonfiguration war erreicht, als folgende Bedingungen gleichzeitig erfuellt waren:

- `pgrep -af unclutter` zeigte einen laufenden Prozess mit `--hide-on-touch --start-hidden`
- Chromium startete weiterhin normal im Kiosk-Modus
- Der Mauszeiger war nicht mehr sichtbar
- Touch-Klicks funktionierten weiterhin normal

### Google-Translate-Badge in Chromium ausblenden

Auf dem Zielsystem wurde das links oben eingeblendete Google-Translate-Badge im Chromium-Kiosk erfolgreich deaktiviert.

Ausgangsproblem:

- Im Kiosk erschien links oben ein Uebersetzungs-Hinweis beziehungsweise Translate-Badge.
- Ursache war, dass Chromium mit englischer Browsersprache (`en-US`) lief, waehrend das Dashboard deutsch ist.

#### Erfolgreiche Loesung

Die stabile Loesung bestand aus zwei Teilen:

- Chromium beim Start explizit auf Deutsch setzen
- die integrierte Translate-Funktion im Profil deaktivieren

#### Schritt 1: Chromium-Startflags erweitern

Datei: `/usr/local/bin/cnc-dashboard-kiosk.sh`

Die Chromium-Startzeile wurde erfolgreich auf folgende Form angepasst:

```sh
exec /usr/bin/chromium --lang=de-DE --disable-features=Translate "$@"
```

Damit startet Chromium im Kiosk-Modus direkt mit deutscher UI-Sprache und ohne aktive Translate-Funktion.

#### Schritt 2: Chromium-Profil auf Deutsch und Translate aus setzen

Datei: `/home/dietpi/.config/chromium/Default/Preferences`

Die folgenden Werte wurden erfolgreich gesetzt:

```json
"intl": {
  "selected_languages": "de-DE,de"
},
"translate": {
  "enabled": false
}
```

#### Schritt 3: Kiosk-Session neu starten

```bash
sudo systemctl restart getty@tty1
```

#### Erfolgreiche Verifikation

Die funktionierende Endkonfiguration war erreicht, als folgende Bedingungen gleichzeitig erfuellt waren:

- der laufende Chromium-Prozess enthaelt `--lang=de-DE --disable-features=Translate`
- in den Chromium-Preferences steht `selected_languages=de-DE,de`
- in den Chromium-Preferences steht `translate.enabled=false`
- das Translate-Badge wird im Kiosk nicht mehr angezeigt
