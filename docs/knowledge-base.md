# CNC Dashboard Knowledge Base

## Zweck des Projekts

Dieses Repository bildet die Basis fuer ein Dashboard fuer eine CNC-Fraese.
Das Dashboard laeuft auf einem Raspberry Pi 4 mit DietPi und wird lokal im Kiosk-Modus angezeigt.

Ziel ist eine zentrale Bedien- und Statusoberflaeche fuer Maschinenzustand, Wartung, Hardware-Steuerung und spaetere Remote-Funktionen.

## Schreibweise

- In UI-Texten, Benutzertexten und Dokumentation verwenden wir echte deutsche Umlaute wie `ä`, `ö`, `ü` und `ß`.
- Umschriften wie `ae`, `oe`, `ue` oder `ss` nutzen wir nur dort, wo technische Bezeichner ASCII bleiben muessen, zum Beispiel in IDs, Rollen, API-Feldern, Dateipfaden oder Legacy-Endpunkten.

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

Warmlauf-Logik:

- `Spindelwarmlauf` ist eine besondere Form von `Wartung faellig` und wird im UI-Banner explizit als `Warmlauf faellig` gezeigt
- Ein gueltiger Warmlauf bleibt `2 Stunden` ab dem letzten gueltigen Warmlauf bzw. der letzten Spindelaktivitaet erhalten; Backend-Neustarts setzen diesen Zustand nicht zurueck
- Nach `5 Minuten` echtem Spindellauf ueber den Optokoppler-Eingang `Spindel laeuft` wird der Warmlauf automatisch als erledigt markiert
- Wenn die Spindel nach bereits gueltigem Warmlauf erneut laeuft, wird der `2-Stunden`-Zeitraum beim Ende des Laufes wieder aufgefrischt
- Der RGB-Strip fadet nach dem Booten sauber in `IDLE` oder in den Warnzustand, falls Warmlauf bzw. Wartung faellig ist

Wartungs-UI:

- Auf der lokalen Wartungsseite kann per Wischgeste links/rechts zwischen den Tabellen-Seiten geblaettert werden
- In der Aufgaben-Anleitung kann ebenfalls per Wischgeste links/rechts zwischen den einzelnen Schritten gewechselt werden
- Anleitungsschritte mit Bild nutzen eine breitere Bilddarstellung; Text und Bild duerfen nebeneinander stehen, um den Bildplatz auf `1024x600` besser zu nutzen

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

### Aktuelle UI-Erreichbarkeit

- Oeffentlich im Heimnetz ist nur der Browser-Monitor unter `http://192.168.178.61/` freigegeben.
- Diese oeffentliche Seite wird ueber `Caddy` auf Port `80` ausgeliefert und zeigt nur `monitor.html` plus die fuer den Monitor benoetigten Assets und API-Routen.
- Das lokale Maschinen-UI fuer Bedienung und Kiosk bleibt auf `http://127.0.0.1:8081/`.
- Das Backend bleibt auf `http://127.0.0.1:8080/` gebunden und ist aus dem Heimnetz nicht direkt erreichbar.

### Lokale Seite „Systemkonfiguration“

Die lokale Seite `frontend/pages/system.html` ist die kompakte Systemübersicht des Maschinen-Dashboards auf dem Pi.

Aktueller Aufbau:

- ein festes, nicht scrollendes Drei-Kachel-Layout für `Systemdaten`, `NETZWERK` und `Remote-Dashboard`
- das Design ist bewusst kantig und orientiert sich an den schwarzen Konturen und rechteckigen Kacheln des restlichen lokalen Systems
- es gibt keine zusätzliche Seitenüberschrift oder erklärende Hero-Fläche auf dieser Seite
- innerhalb der Seite bleiben nur die drei Hauptkacheln `Systemdaten`, `NETZWERK` und `Remote-Dashboard`; innere Unterboxen werden vermieden
- die Kacheln nutzen direkt ihre Haupttitel; kleine Oberüberschriften wie `Maschine`, `Netzwerk` oder `Zugriff` werden nicht zusätzlich gezeigt

Inhalt der Kacheln:

- `Systemdaten`: drei kompakte Gruppen statt vieler Einzelboxen
- Laufzeiten: oben als flacher Vollbreiten-Block mit Spindellaufzeit sowie Achsenlaufzeiten für `X`, `Y` und `Z`
- unterhalb der Laufzeiten folgt ein einzelner Vollbreiten-Block mit Gehäusetemperatur, CPU-Temperatur, CPU-Auslastung, RAM-Auslastung, Speicher-Auslastung und Softwareversion untereinander
- für Gehäusetemperatur, CPU-Temperatur, CPU-Auslastung, RAM und Speicher werden einfache Balkenanzeigen verwendet
- unnötige Beschreibungstexte innerhalb der Kacheln werden vermieden, um die Höhe für `1024x600` klein zu halten
- `NETZWERK`: zuerst WLAN-Verbindungsstatus, SSID und IP-Adresse mit dem Button zum WLAN-Modal; darunter der per SMB-Port geprüfte DDCS-V4.1-Verbindungsstatus und die gemeinsame DDCS-/Windows-Anleitung
- `Remote-Dashboard`: QR-Code und Zieladresse ohne separate Status-Unterkachel

Datenquellen der Seite:

- `GET /api/system/status` für Hostname, Spindellaufzeit, X/Y/Z-Laufzeiten, Gehäusetemperatur, CPU-Temperatur, CPU-Auslastung, RAM-Auslastung, Speicher-Auslastung und Softwareversion
- `GET /api/wifi/status` für Live-Status wie `wifiConnected`, `wifiSsid`, `wifiIpAddress` und `wifiIssue`
- `GET /api/programs` prueft fuer den DDCS-Status die SMB-Ports `445` und `139`
  von `192.168.2.5`; `verbunden` bedeutet damit, dass der konfigurierte
  Controller-SMB-Dienst tatsaechlich erreichbar ist
- die Softwareversion nutzt bevorzugt `SOFTWARE_VERSION`, danach Git-Metadaten und ohne `.git` als Fallback die Datei `VERSION` im Repo-Root

Interaktion:

- der Button `WLAN konfigurieren` öffnet weiterhin das vorhandene WLAN-Modal des Parent-Dashboards
- die Seite hört zusätzlich auf `postMessage`-Events vom Parent, insbesondere `init`, `spindleRuntime`, `wifi`, `pageShown` und `openWifiConfig`
- die Systemdaten werden zusätzlich in einem kurzen Intervall nachgeladen, damit CPU-, RAM-, Speicher- und Laufzeitwerte aktuell bleiben

Remote-Dashboard:

- der QR-Code wird clientseitig über `frontend/assets/vendor/qrcode.min.js` erzeugt
- als Ziel wird aktuell `http://<wifiIpAddress>` verwendet
- ohne aktives WLAN oder ohne vergebene IP zeigt die Karte einen kompakten Platzhalterzustand

### Kamera-Live-Stream via MediaMTX/WebRTC

Der Kamera-Live-Stream laeuft nicht mehr als MJPEG aus dem Backend, sondern als
eigene MediaMTX/WebRTC-Kette.

Aktuelles Zielbild:

- `ffmpeg` liest die USB-Kamera auf `/dev/video0`
- `ffmpeg` publisht H.264 lokal nach `rtsp://127.0.0.1:8554/camera`
- `MediaMTX` stellt daraus WebRTC/WHEP auf `http://192.168.178.61:8889/camera/whep` bereit
- das Frontend fragt beim Backend nur `GET /api/camera/status` ab und verbindet sich danach direkt mit MediaMTX

Aktive Dateien im Repository:

- `backend/camera-stream.env`
- `backend/camera-publisher.sh`
- `backend/mediamtx.yml`
- `backend/cnc-dashboard-camera-publisher.service`
- `backend/cnc-dashboard-mediamtx.service`

Aktive Dienste auf dem Pi:

- `cnc-dashboard-backend.service`
- `cnc-dashboard-camera-publisher.service`
- `cnc-dashboard-mediamtx.service`
- `caddy.service`

Wichtige Ports:

- `127.0.0.1:8080` fuer das Backend
- `127.0.0.1:8554` fuer lokales RTSP-Ingest nach MediaMTX
- `:8889` fuer MediaMTX-WebRTC/WHEP im Heimnetz

Schnelle Verifikation:

- `curl -s http://127.0.0.1:8080/api/camera/status`
- `curl -i -X OPTIONS http://127.0.0.1:8889/camera/whep`
- `systemctl status cnc-dashboard-camera-publisher.service --no-pager`
- `systemctl status cnc-dashboard-mediamtx.service --no-pager`

### Ethernet fuer DDCS V4.1 als lokales Netz

Der Raspberry Pi wurde so umgestellt, dass `eth0` nicht mehr per DHCP im Heimnetz sucht, sondern ein eigenes lokales Netz fuer den CNC-Controller bereitstellt.

Zielbild:

- `wlan0`: Verbindung ins Heimnetz und Zugriff auf das lokale Web-UI
- `eth0`: separates Punkt-zu-Punkt-/Lokalsegment fuer den CNC-Controller
- Dateifluss: Upload ins Web-UI, persistente Zwischenablage auf dem Pi und SMB-Weitergabe an den DDCS V4.1

Aktive Konfiguration auf dem Pi:

- Statische IP des Pi auf `eth0`: `192.168.2.8/24`
- Statische Soll-IP des DDCS V4.1: `192.168.2.5/24`
- DHCP-Server auf `eth0` via `dnsmasq`
- DHCP-Fallbackbereich: `192.168.2.100` bis `192.168.2.150`
- Gateway-Option per DHCP: `192.168.2.8`
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
dhcp-range=192.168.2.100,192.168.2.150,255.255.255.0,12h
dhcp-option=option:router,192.168.2.8
dhcp-leasefile=/var/lib/misc/dnsmasq.eth0.leases
```

Verifikation:

- `ip -4 addr show eth0` zeigt `192.168.2.8/24`
- `systemctl status dnsmasq --no-pager` zeigt einen laufenden Dienst
- `journalctl -u dnsmasq -n 20 --no-pager` bestaetigt, dass DHCP exklusiv auf `eth0` gebunden ist

Nutzen fuer den Bootvorgang:

- Vor der Umstellung wartete `eth0` beim Booten auf DHCP und blockierte dadurch den Kiosk-Start deutlich.
- Mit der statischen `eth0`-Konfiguration sollte dieser Blocker beim naechsten Neustart entfallen oder stark reduziert sein.

### CNC-Programmablage und SMB-Weitergabe

Die Programmdatei-Pipeline ist fuer den DDCS V4.1 vorbereitet:

- erlaubte Formate: `.gcode`, `.nc`, `.tap`, `.ngc`
- persistenter Zwischenordner: `/var/lib/cnc-dashboard/programs`
- Upload, Liste, Download und Loeschen ueber die Backend-API
- derselbe Ordner wird vom Pi authentifiziert als Samba-Freigabe `cnc-programs` angeboten
- stabiler Windows-Pfad unabhaengig von DHCP: `\\cncpi\cnc-programs`
- Namensaufloesung ueber Samba/NetBIOS (`CNCPI`) und Avahi/mDNS (`cncpi.local`)
- Windows-Anmeldung: Benutzer `dietpi`, Passwort `marcusbierusmaschienus`
- fuer den DDCS wird derselbe Ordner als `share` anonym bereitgestellt; der Zugriff ist auf `192.168.2.5` begrenzt
- manuell ueber Samba abgelegte Programmdateien werden vom Backend automatisch erkannt
- ein Hintergrund-Worker uebertraegt wartende Dateien per SMB1 an `//192.168.2.5/cncdisk`
- Controller-Kennwort wird ueber die Prozessumgebung an `smbclient` gegeben und erscheint nicht in dessen Argumentliste
- vor dem finalen Zielnamen wird eine temporaere SMB-Datei vollstaendig hochgeladen

Am DDCS werden die Parameter #325 (`Disable network functionality: No`), #326 (kein DHCP), #327
(`192.168.2.5`), #328 (`255.255.255.0`), #329 (`192.168.2.8`) und #330
(`192.168.2.8`) gesetzt. Die Controller-Konfiguration liegt root-lesbar unter
`/etc/cnc-dashboard/controller-smb.env`.

Fuer diesen Dateifluss ist kein IP-Forwarding zwischen `wlan0` und `eth0` erforderlich:
Der Pi ist auf beiden Netzen selbst Endpunkt und arbeitet als kontrolliertes
Anwendungs-Gateway. Layer-3-Forwarding oder NAT wird daher weiterhin nicht aktiviert.

## Aktuell bekannte I2C-Hardware

Letzter bekannter Live-Scan auf `/dev/i2c-1`:

- `0x21`
- `0x38`
- `0x40`
- `0x41`
- `0x44`
- `0x52`
- `0x60`

- `Adafruit AHT20` fuer die Gehäusetemperatur auf `0x38`
- `Adafruit INA228` fuer die `X`-Achslast auf `0x40`
- `Pololu 5411` / `ACS37800` fuer die Spindellast auf `0x60`
- `GHI GDL-ACRELAYP4-C` 4-Kanal-Relais auf `0x52` (`82` dezimal)
- `PCF8574`-kompatibles 8-Kanal-Optokoppler-Eingangsmodul auf `0x21`
  - Produkt: `PCF8574 I2C 8 Kanal Optokoppler Eingang Input Modul 3,6-24V`
  - Auf dem Pi per erneutem `i2cdetect -y 1` nach dem Umstecken der Adressjumper auf Bus `1` verifiziert
  - Feste Betriebsadresse im aktuellen Aufbau: `0x21`
  - Die Adresse `0x21` liegt im offiziellen `PCF8574`-Bereich `0x20` bis `0x27` und nicht im `PCF8574A`-Bereich `0x38` bis `0x3F`
  - Daraus folgt: Der aktuell aktive Adressdecoder des Moduls verhaelt sich im Live-Betrieb wie ein `PCF8574`, nicht wie ein `PCF8574A`
  - Die Eingangslogik wird im Projekt aktiv als `active-low` ausgewertet
- `Input 1` und `Input 2` sind fest fuer mechanische Hardware-E-Stops reserviert
- `Input 3` ist fest als `Spindel laeuft` verdrahtet
- Sobald `Input 1` oder `Input 2` aktiv wird, loest das Backend sofort einen System-E-Stop aus
- Dieser Hardware-E-Stop kann nicht im Frontend quittiert werden; er bleibt aktiv, bis der mechanische Taster real geloest wurde
- Die Spindellaufzeit wird nur hochgezaehlt, solange `Input 3` aktiv ist, und wird im Backend nach `machine_stats.json` persistiert
- Die Achsenlaufzeiten fuer `X`, `Y` und `Z` werden separat gezaehlt, sobald die kalibrierte Achslast der jeweiligen Achse ueber `5 %` liegt
- Backend-Starts werden ebenfalls nach `machine_stats.json` als `backendStartCount` gezaehlt; ein Start des Backend-Prozesses reicht dafuer jeweils einmal aus
- Die allgemeine Maschinenlaufzeit wird als `machineOnTimeSec` ueber die aktive Backend-Laufzeit mitgezaehlt
- Spindelstarts werden als `spindleStartCount` auf der Flanke `Spindel laeuft: aus -> an` gezaehlt
- Die Spindellast kommt im Dashboard und fuer die RGB-Strip-Running-Animation aus dem `ACS37800` auf `0x60`, nicht mehr aus dem Dummy-Pfad
- Die Prozentanzeige der Spindellast nutzt dieselbe Kalibrierlogik wie die Achslasten und kann im lokalen Dashboard per Long-Press auf einer Spindel-Kachel angepasst werden
- E-Stop-Ausloesungen werden ebenfalls nach `machine_stats.json` persistiert: als Gesamtzaehler `eStopCount` sowie getrennt nach `manualEStopCount` und `hardwareEStopCount`

Geplante/Backend-vorbereitete Erweiterung fuer Achslasten:

- `Y`-Achse: `INA228` auf `0x41`
- `Z`-Achse: `INA228` auf `0x44`

Aktuelle Relaisbelegung im Dashboard:

- Kanal 1: Maschinenlicht
- Kanal 2: Spindel-Lüfter
- Kanal 3: Gehäuse-Lüfter
- Kanal 4: E-Stop

Aktuelle Lüfterlogik:

- Der Spindel-Lüfter auf Kanal `2` startet automatisch, sobald das Hardware-Signal `Spindel läuft` aktiv ist.
- Nach dem Abschalten der Spindel läuft der Spindel-Lüfter um die konfigurierte Nachkühlzeit weiter.
- Der Gehäuse-Lüfter auf Kanal `3` kann manuell geschaltet werden und optional automatisch über die Gehäusetemperatur geregelt werden.
- Die Einschalt-Schwelle des Gehäuse-Lüfters ist im lokalen Dashboard einstellbar und wird persistent in den Settings gespeichert.

Aktuelle E-Stop-Logik:

- Frontend-E-Stop nutzt Relaiskanal `4`
- Hardware-E-Stop kommt zusaetzlich ueber das PCF8574-Eingangsmodul auf `Input 1` und `Input 2`
- Spindel-Running kommt ueber dasselbe Eingangsmodul auf `Input 3`
- Der effektive Maschinen-Not-Halt ist aktiv, sobald Relaiskanal `4` aktiv ist oder einer der Hardware-E-Stop-Eingaenge ausloest
- Bei aktivem Hardware-E-Stop wird Relaiskanal `4` automatisch gesetzt und ein Frontend-Reset mit Konfliktfehler abgewiesen
- Bei aktivem Hardware-E-Stop zeigt das lokale UI die rote Statusleiste `E-STOP`, und der WS2812B-Statusstreifen wechselt auf rot
- Die Spindellaufzeit kommt nicht mehr aus der Lastkurve, sondern nur noch aus dem echten Hardware-Signal auf `Input 3`

## Aktuell bekannte GPIO-/LED-Hardware

- `WS2812B` RGB-LED-Streifen fuer den Maschinenstatus
  - Versorgung: `5V`
  - Datensignal: `GPIO18`
  - Aktuelle Laenge: `59` LEDs
  - Die LED-Bootsequenz startet unabhaengig von der Relaisboard-Erkennung. Ein
    fehlendes oder noch nicht initialisiertes Relaisboard darf den Streifen nicht
    im ausgeschalteten Zustand halten.
  - Startup-Sequenz: blau von der Mitte nach aussen, danach Systemcheck auf Weiss
  - Idle-Sequenz: langsame wandernde weisse Wellen zwischen `RGB 28` und `127`, gedeckelt auf `50%` Maximalhelligkeit
  - Warn-Sequenz: langsames Pulsieren in tieferem Orange mit leichtem Rotanteil

## Getesteter Systemzustand auf DietPi

### Eigener Bootscreen und frueher Kiosk-Start

Eine Messung des bisherigen Live-Systems zeigte `1,497 s` Kernelzeit und `16,970 s`
Userspace bis `graphical.target`. Der groesste einzelne Blocker war
`ifup@wlan0.service` mit `11,264 s`. Der lokale Backend- und Frontend-Dienst war
dagegen bereits nach rund `4,6 s` gestartet. Der fruehere DietPi-Autostart wartete
auf den automatischen Login: `getty@tty1` startete erst nach rund `16,5 s`, X nach
rund `19 s` und Chromium nochmals spaeter.

Der Installer verwendet deshalb DietPis Chromium-Paket und Displaykonfiguration,
stellt `dietpi-autostart` aber auf den konfliktfreien manuellen Modus `0`. Ein eigener
`cnc-dashboard-kiosk.service` startet X und Chromium parallel zum WLAN-Aufbau und
besitzt `tty1` direkt. `getty@tty1` ist fuer den Appliance-Betrieb maskiert; die
Wartung bleibt ueber SSH moeglich. `TimeoutStopSec=10` verhindert, dass ein nicht
rechtzeitig beendeter Chromium-Prozess einen Neustart bis zum systemd-Standardtimeout
verzoegert. Die Plymouth-Uebergabe folgt dem Display-Manager-Muster: Der Kiosk
wartet kurz, bis Plymouth tatsaechlich gezeichnet hat (`--has-active-vt`), und ruft
dann `plymouth deactivate` auf. Das gibt VT und DRM-Master frei, laesst den
Framebuffer-Inhalt aber stehen, so dass Xorg mit `-background none` nahtlos
uebernimmt. Ein hartes `plymouth quit` an dieser Stelle waere falsch: Der Daemon
verschiebt sein Ende dann auf `plymouth-quit.service`, das ueber
`systemd-user-sessions.service` an `network.target` haengt - Xorg blockierte am
gehaltenen VT, bis DHCP fertig war (gemessen: Bildschirmstart erst bei Sekunde 17).
Den finalen Daemon-Exit erledigt weiterhin `plymouth-quit.service`; zu diesem
Zeitpunkt besitzt Xorg laengst das Display, der Quit ist reine Aufraeumarbeit.
Die X-Sitzung wird explizit auf Display `:0` gestartet. Damit wechselt sie bei einem
schnellen Dienstneustart nicht unbemerkt auf `:1`, und Backend-Aktionen wie das
Abdunkeln beim Herunterfahren treffen immer die laufende Kiosk-Sitzung.
Der Dienst ruft `xinit` und Xorg direkt auf. Der allgemeine `startx`-Wrapper wird
nicht benoetigt; er kostete beim gemessenen Kaltstart rund acht Sekunden fuer
Session- und Xauthority-Vorbereitung. Xorg lauscht nicht auf TCP und laeuft auf dem
exklusiv vom Kiosk belegten `tty1`.
Die Unit verwendet bewusst kein `PAMName=` mehr: `pam_systemd` blockiert die
Session-Erstellung, bis `session-N.scope` startet, dieser wartet auf
`user@1000.service`, der wiederum ueber `systemd-user-sessions.service` nach
`network.target` geordnet ist. Das erste Kiosk-Bild wartete dadurch auf WLAN-DHCP
(gemessen: Xorg-Start erst bei Sekunde 12-18 statt 6). Stattdessen laeuft Xorg
ueber den setuid-Wrapper aus `xserver-xorg-legacy`
(`/etc/X11/Xwrapper.config`: `allowed_users=anybody`, `needs_root_rights=yes`)
mit Root-Rechten direkt auf VT und DRM. Ohne logind-Session gibt es auch keine
Seat-ACLs auf den GPU-Geraeten; Chromium erhaelt `/dev/dri/renderD128` deshalb
ueber `SupplementaryGroups=render video` in der Unit.
Der Kiosk besitzt außerdem keine Ordering-Abhaengigkeit zu
`systemd-user-sessions.service`: Diese zog auf DietPi indirekt `network.target` und
damit den langsamen `ifup@wlan0.service` in den kritischen Startpfad. X und Chromium
koennen als Systemdienst bereits nach `local-fs.target` parallel zum WLAN starten.
Der Kiosk erhaelt waehrend des Starts die hoechste CPU-/I/O-Gewichtung. Der
fruehere `cnc-dashboard-browser-preload.service` (Chromium-Binary per `dd` in
den Dateicache lesen) wurde wieder entfernt: Die SD-Karte nutzt den
`mq-deadline`-Scheduler, der die `idle`-I/O-Klasse ignoriert. Der Preload
konkurrierte dadurch mit dem Xorg-Kaltstart um die SD-Bandbreite und
verzoegerte das erste Kiosk-Bild um rund acht Sekunden. Caddy, Samba und Tailscale sind fuer
das lokale UI nicht erforderlich und werden deshalb erst bei Sekunde 25 durch
`cnc-dashboard-background.timer` gestartet. Remote-UI und Freigabe stehen damit
kurz nach dem lokalen Bedienbild bereit, konkurrieren aber nicht mehr mit dessen
Kaltstart. MediaMTX und der Kamera-Publisher bleiben deaktiviert, bis das Backend
sie fuer einen tatsaechlichen Kameraabruf bedarfsgesteuert startet.

#### Schritt 1: Kernel-Ausgabe auf ein unsichtbares Terminal verschieben

Datei: `/boot/firmware/cmdline.txt`

Die bestehende Zeile wird beibehalten und am Ende um die benoetigten Parameter ergaenzt:

```txt
root=PARTUUID=XXXXX-02 rootfstype=ext4 rootwait fsck.repair=yes net.ifnames=0 drm.edid_firmware=HDMI-A-2:edid/cnc-dashboard-1024x600.bin video=HDMI-A-1:d video=HDMI-A-2:1024x600@60e console=tty3 fbcon=map:2 loglevel=0 quiet splash plymouth.ignore-serial-consoles logo.nologo vt.global_cursor_default=0 systemd.show_status=false rd.systemd.show_status=false udev.log_level=3
```

Relevante Anpassungen gegenueber dem DietPi-Standard:

- `console=tty1` wurde auf `console=tty3` umgestellt, damit die Kernel-Ausgabe nicht auf dem sichtbaren Terminal erscheint.
- `fbcon=map:2` haelt die Framebuffer-Konsole komplett vom Panel fern: kein Konsolen-Clear ueber dem Plymouth-Frame, keine Streuzeichen, und der zurueckbehaltene Splash (`--retain-splash`) bleibt bis zur Xorg-Uebernahme stehen. Wartungszugriff erfolgt ueber SSH.
- `loglevel=0` reduziert die Ausgabe auf kritische Kernel-Fehler.
- `vt.global_cursor_default=0` blendet den blinkenden Textcursor aus.
- `quiet` unterdrueckt weitere nicht-kritische Boot-Meldungen.
- `logo.nologo` war bereits vorhanden.
- `splash plymouth.ignore-serial-consoles` aktiviert den grafischen CNC-Bootscreen.
- `systemd.show_status=false` unterdrueckt die normalen systemd-Statuszeilen.

Das Dashboard benoetigt fuer das feste Pi-System kein Initramfs. Der Installer setzt
`auto_initramfs=0`, sodass der Kernel das Root-Dateisystem direkt startet und Plymouth
anschliessend sehr frueh aus dem Root-System uebernimmt. Das vermeidet das Laden und
Entpacken des rund 22 MB grossen bisherigen Initramfs. `disable_fw_kms_setup=1` verhindert
zugleich, dass die Firmware konkurrierende EDID-Modi an den Kernel anhaengt. HDMI-A-1
wird deaktiviert und der angeschlossene HDMI-A-2-Ausgang durchgaengig auf 1024x600
gezwungen.

Das MPI7002 meldet 1024x600 zwar als bevorzugte Aufloesung, sein originales
Sync-Timing wird vom Raspberry-Pi-`vc4`-KMS-Treiber jedoch verworfen. In der Folge
wechselte der Boot mehrfach von 1024x600 ueber 1920x1080 und 1152x864 zurueck auf
1024x600. Der Installer kopiert deshalb die echte Monitor-EDID, ersetzt nur den
ersten detaillierten Timing-Block durch das bereits bewaehrte vc4-kompatible Timing
und installiert sie unter `/usr/lib/firmware/edid/cnc-dashboard-1024x600.bin`.
CEA-Erweiterung, Monitoridentitaet und die uebrigen Modi bleiben erhalten. Eine
Xorg-Konfiguration markiert denselben Modus zusaetzlich als bevorzugt; `xrandr`
bleibt nur noch als Rueckfallebene bestehen.

#### Schritt 2: Bluetooth deaktivieren

Datei: `/boot/firmware/config.txt`

Am Ende der Datei wurde folgender Eintrag ergaenzt:

```ini
dtoverlay=disable-bt
```

Damit verschwinden zusaetzliche Bluetooth-bezogene Firmware-Meldungen waehrend des Bootvorgangs.

#### Uebergabe an den Kiosk

- Plymouth zeigt frueh den weissen CNC-Dashboard-Bootscreen (mit pulsierendem
  Balken; beim Herunterfahren lautet der Text "SYSTEM WIRD BEENDET").
- Der Kiosk-Dienst wartet, bis Plymouth tatsaechlich gezeichnet hat, beendet es
  mit `--retain-splash` und wartet auf den echten Daemon-Exit (siehe oben).
- In den ersten Millisekunden der X-Session setzt `xsetroot -bitmap` den beim
  Install vorgerenderten Splash (`generate-splash-xbm.py`) als Root-Hintergrund.
- Der native X11/Cairo-Splash (`cnc-dashboard-xsplash.py`) liegt mit animiertem
  Balken ueber Chromiums leeren Startflaechen und zeichnet sich bei Expose-Events
  selbst neu. Er verschwindet erst, wenn app.js das fertig gerenderte Dashboard
  ueber den Fenstertitel "CNC Dashboard bereit" meldet - direkt auf das fertige
  Bedienbild, ohne Browser-Weissbild.
- Chromium laedt `/` direkt; eine separate Boot-Seite gibt es nicht mehr. Das
  Kiosk-Skript wartet vor dem Chromium-Start, bis Frontend (`:8081`) und
  Backend-Health (`:8080/api/health`) antworten; solange deckt der Splash ab.
  Die Chromium-Flags gegen Occlusion-Backgrounding sind dabei zwingend: ein
  vollstaendig verdecktes Chromium friert sonst rAF ein und das "bereit"-Signal
  entstuende nie.
- Der Kiosk ist nicht von `network-online.target` abhaengig. Der langsame WLAN-Aufbau
  darf parallel weiterlaufen.

Kiosk-Session neu starten:

```bash
sudo systemctl restart cnc-dashboard-kiosk.service
```

### Displaytiming: 51,20 MHz wegen 2,4-GHz-WLAN-Interferenz

Das Panel lief zunaechst mit einem 49,00-MHz-Timing (1312x624 Totals). Dabei
betraegt die TMDS-Datenrate 490 Mbit/s pro Lane; deren 5. Harmonische liegt bei
exakt 2,45 GHz - mitten im 2,4-GHz-WLAN-Band. Folge: Jede aktive WLAN-Phase
(Scan im WLAN-Dialog, Association beim Boot, periodische Hintergrund-Scans)
stoerte den HDMI-Link, und der Panel-Receiver verlor fuer Sekunden den
H-Sync - sichtbar als diagonal verzerrtes ("warped") Bild. Nachweis: Waehrend
der Verzerrung waren x11grab-Frames sauber und `hvs_underrun` blieb 0; die
Stoerung passiert also hinter dem Framebuffer auf dem Kabelweg.

Aktuelles Timing ueberall (Firmware `hdmi_timings:1`, EDID-DTD aus
`generate-edid.py`, Xorg-Modeline): `51.20 MHz, 1024 1072 1168 1344,
600 611 621 635, -HSync +VSync` (59,99 Hz). Die 5. Harmonische liegt damit bei
2,56 GHz, ausserhalb des WLAN-Bands. Bei einer kuenftigen Timing-Aenderung
darauf achten, dass `Pixeltakt x 10 x n` fuer kleine `n` nicht in
2,401-2,484 GHz faellt.

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
sudo systemctl restart cnc-dashboard-kiosk.service
```

Alternativ funktioniert auch ein kompletter Neustart des Pi.

#### Erfolgreiche Verifikation

Die funktionierende Endkonfiguration war erreicht, als folgende Bedingungen gleichzeitig erfuellt waren:

- `xrandr` meldete `current 1024 x 600`
- `HDMI-2` war `primary`
- Chromium fordert ohne Window-Manager eine Aussenflaeche von `1025x601` an; X schneidet
  sie auf 1024x600 zu, sodass der Chromium-Content exakt 1024x600 statt 1023x599 misst
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
sudo systemctl restart cnc-dashboard-kiosk.service
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
sudo systemctl restart cnc-dashboard-kiosk.service
```

#### Erfolgreiche Verifikation

Die funktionierende Endkonfiguration war erreicht, als folgende Bedingungen gleichzeitig erfuellt waren:

- der laufende Chromium-Prozess enthaelt `--lang=de-DE --disable-features=Translate`
- in den Chromium-Preferences steht `selected_languages=de-DE,de`
- in den Chromium-Preferences steht `translate.enabled=false`
- das Translate-Badge wird im Kiosk nicht mehr angezeigt

### Pinch-Zoom im Chromium-Kiosk deaktivieren

Auf dem lokalen Maschinen-UI soll keine Zwei-Finger-Zoom-Geste moeglich sein.

Umgesetzt wurde eine Kombination aus Frontend-Viewport und Chromium-Startflag:

- `frontend/index.html`, `frontend/pages/home.html`, `frontend/pages/maintenance.html`, `frontend/pages/system.html` und `frontend/monitor.html` setzen `maximum-scale=1` und `user-scalable=no`.
- Der Kiosk-Wrapper `/usr/local/bin/cnc-dashboard-kiosk.sh` startet Chromium mit `--disable-pinch`.

Aktuelle Chromium-Startzeile:

```sh
exec /usr/bin/chromium --lang=de-DE --disable-features=Translate --disable-pinch "$@"
```
