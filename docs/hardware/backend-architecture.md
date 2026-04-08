# Hardware Backend Architektur

## Zielbild

Das Hardware-Backend stellt eine zentrale, erweiterbare Schicht fuer reale
Maschinenhardware bereit. Es kapselt Buszugriffe und Geraetelogik, damit weder
Frontend noch `server.py` direkt I2C-Details kennen muessen.

## Verantwortlichkeiten

- Zugriff auf Hardware-Busse wie `I2C`
- Treiberlogik pro Geraet oder Sensor
- Vereinheitlichte, frontend-taugliche Datenstruktur fuer Messwerte und Fehler
- Wiederverwendbare Python-Schnittstelle fuer das restliche Software-Backend
- Basis fuer Sensoren, Aktoren, Health-Checks und Bus-Diagnose

## Aktueller Zuschnitt

Die aktuelle Ausbaustufe besteht aus sechs Hardware-Modulen plus Backend-Koordination:

1. `backend/cnc_hardware/i2c.py`
   - Linux-I2C-Zugriff ueber `/dev/i2c-*` ohne zusaetzliche Python-Abhaengigkeiten
2. `backend/cnc_hardware/sensors.py`
   - Sensortreiber fuer den `AHT20` der Gehäusetemperatur und die `INA228`-Achslastsensoren
3. `backend/cnc_hardware/duelink_relay.py`
   - Aktortreiber fuer das `GHI GDL-ACRELAYP4-C` Relaisboard auf `0x52`
4. `backend/cnc_hardware/pcf8574_inputs.py`
   - Eingangstreiber fuer das `PCF8574`-kompatible 8-Kanal-Optokoppler-Modul auf `0x21`
5. `backend/cnc_hardware/neopixel.py`
   - Aktortreiber fuer den `WS2812B`-Status-LED-Streifen an `GPIO18`
6. `backend/cnc_hardware/service.py`
   - Hardware-Fassade mit normalisierter Antwortstruktur, kurzem Sensor-Cache und Hardware-E-Stop-Synchronisation

Zusaetzlich koordiniert `backend/cnc_backend/app.py` die laufenden Hintergrund-Worker fuer:

- Hardware-E-Stop-Polling
- RGB-Status-Synchronisation
- backend-seitiges Hochzaehlen und Persistieren der Spindellaufzeit
- Spindel-Lüfter-Automatik mit Nachkühlzeit
- Gehäuse-Lüfter-Automatik über die Gehäusetemperatur

## HTTP-Anbindung

Der bestehende HTTP-Server bindet das Hardware-Backend als Adapter ein und stellt
aktuell folgende Hardware-Endpunkte bereit:

- `GET /api/hardware`
  - Gesamtuebersicht ueber Sensoren, Aktoren, Safety-Inputs und I2C-Metadaten
- `GET /api/hardware/enclosure-temperature`
  - Direkter Zugriff auf den AHT20-Messwert der Gehäusetemperatur
- `GET /api/hardware/spindle-temperature`
  - Legacy-Alias fuer denselben Temperaturwert
- `GET /api/hardware/axis-loads`
  - Direkter Zugriff auf die INA228-Messwerte fuer `X`, `Y` und `Z`
- `GET /api/hardware/relays`
  - Snapshot des 4-Kanal-Relaisboards inklusive eingebetteter `safetyInputs`
- `GET /api/machine/status`
  - Liefert den effektiven Maschinenstatus inklusive Hardware-E-Stop-Lock, `spindleRunning` und LED-Prioritaetsentscheidung
- `POST /api/machine/status`
  - Nimmt einen gemeldeten Basisstatus wie `IDLE`, `RUNNING` oder `ERROR` entgegen
- `GET /api/axes`
  - Liefert die Frontend-Achswerte; `X/Y/Z` kommen aus den INA228-Sensoren, `Spindel` aktuell noch aus dem bestehenden Last-Mock
- `GET /api/axes/stream`
  - SSE-Stream fuer die Frontend-Achsenanzeige mit eingebetteten `axisLoadSensors`
- `GET /api/camera/status`
  - Liefert Verfuegbarkeit und Parameter der MediaMTX/WebRTC-Kamerakette fuer den Browser-Monitor
- `POST /api/hardware/light`
  - Schaltet Relaiskanal 1 fuer das Maschinenlicht
- `POST /api/hardware/fan`
  - Schaltet Relaiskanal 2 fuer den Spindelluefter
- `POST /api/hardware/enclosure-fan`
  - Schaltet Relaiskanal 3 fuer den Gehäuse-Lüfter
- `POST /api/hardware/e-stop`
  - Schaltet den manuellen E-Stop auf Relaiskanal 4; ein Hardware-E-Stop kann darueber nicht quittiert werden

## Service-Integration

Die Hardware-API laeuft weiterhin als Teil des bestehenden Backend-Dienstes
`cnc-dashboard-backend.service`, aber der Kamera-Pfad ist inzwischen in drei
separate Dienste zerlegt:

- `cnc-dashboard-backend.service`
  - stellt die Hardware- und Status-API auf `127.0.0.1:8080` bereit
- `cnc-dashboard-camera-publisher.service`
  - liest die USB-Kamera via `ffmpeg` und publisht H.264 lokal nach `rtsp://127.0.0.1:8554/camera`
- `cnc-dashboard-mediamtx.service`
  - stellt den Browser-Stream per MediaMTX/WebRTC auf `:8889` bereit

Wichtige Betriebsdetails auf dem aktuellen Pi:

- Service-Name: `cnc-dashboard-backend.service`
- Startdatei: `/opt/cnc-dashboard/backend/server.py`
- Service-User: `dietpi`
- Bind-Adresse: `127.0.0.1:8080`
- Kamera-Publisher: `ffmpeg` auf `/dev/video0`
- Video-Router: `MediaMTX`
- WebRTC-WHEP-Endpunkt: `http://<pi>:8889/camera/whep`
- I2C-Zugriff laeuft im aktuellen Deployment ueber denselben Backend-Dienst

Nuetzliche Pruefbefehle auf dem Pi:

```bash
systemctl status cnc-dashboard-backend.service --no-pager
systemctl status cnc-dashboard-camera-publisher.service --no-pager
systemctl status cnc-dashboard-mediamtx.service --no-pager
systemctl is-enabled cnc-dashboard-backend.service
systemctl is-active cnc-dashboard-backend.service
sudo systemctl restart cnc-dashboard-backend.service
journalctl -u cnc-dashboard-camera-publisher.service -n 80 --no-pager
journalctl -u cnc-dashboard-mediamtx.service -n 80 --no-pager
journalctl -u cnc-dashboard-backend.service -n 80 --no-pager
id dietpi
```

## Relaisboard-Konfiguration

Das `GHI GDL-ACRELAYP4-C` ist aktuell so eingeplant:

- Bus: `/dev/i2c-1`
- Adresse: `0x52`
- Protokoll: `DUELink DaisyLink`
- Default-Geraeteindex: `1`
- Kanalbelegung:
  - `1`: Maschinenlicht
  - `2`: Spindelluefter
  - `3`: Gehäuse-Lüfter
  - `4`: E-Stop

Konfigurierbare Umgebungsvariablen:

- `RELAY_BOARD_ENABLED`
- `RELAY_BOARD_I2C_ADDRESS`
- `RELAY_BOARD_DEVICE_INDEX`
- `RELAY_BOARD_RESPONSE_TIMEOUT_SEC`

## Safety-Input-Konfiguration

Das `PCF8574`-kompatible Optokoppler-Eingangsmodul ist aktuell fest so verdrahtet:

- Bus: `/dev/i2c-1`
- Adresse: `0x21`
- Logik: `active-low`
- `Input 1`: mechanischer Hardware-E-Stop
- `Input 2`: mechanischer Hardware-E-Stop
- `Input 3`: `Spindel laeuft`

Laufzeitverhalten:

- Sobald `Input 1` oder `Input 2` aktiv wird, markiert das Backend die Maschine sofort als `E-STOP`.
- Relaiskanal `4` wird automatisch in den E-Stop-Zustand gedrueckt.
- Ein Frontend-Reset wird geblockt, solange der mechanische Taster noch ausgeloest ist.
- Die Spindellaufzeit wird nur hochgezaehlt, solange `Input 3` aktiv ist.

Konfigurierbare Umgebungsvariablen:

- `EMERGENCY_INPUT_MODULE_ENABLED`
- `EMERGENCY_INPUT_MODULE_I2C_ADDRESS`
- `EMERGENCY_INPUT_MODULE_ESTOP_CHANNELS`
- `EMERGENCY_INPUT_MODULE_SPINDLE_RUNNING_CHANNELS`
- `HARDWARE_ESTOP_POLL_INTERVAL_SEC`

## Status-LED-Streifen-Konfiguration

Der `WS2812B`-Statusstreifen ist aktuell so vorgesehen:

- Versorgung: `5V`
- Datenleitung: `GPIO18`
- Aktuelle Laenge: `59` LEDs
- Startup-Sequenz:
  - blau expandierend von der Mitte nach aussen
  - Maschinenlicht geht an, sobald der ganze Streifen blau ist
  - danach Systemcheck-Fade von Blau auf Weiss
- `IDLE`:
  - wandernde weisse Atmungsanimation zwischen `RGB 28` und `127`
  - Phasenversatz pro Pixel: `0.12`
  - Phasenvorschub pro Frame: `0.012` bei rund `60 FPS`
- Status-Farbabbildung nach dem Startup:
  - `Weiss`: Maschine an / `IDLE`
  - `Orange`: Warnung / Wartung faellig
  - `Gruen`: Job oder Spindel laeuft
  - `Rot`: `E-Stop` aktiv

Konfigurierbare Umgebungsvariablen:

- `STATUS_INDICATOR_ENABLED`
- `STATUS_INDICATOR_LED_COUNT`
- `STATUS_INDICATOR_GPIO_PIN`
- `STATUS_INDICATOR_FREQUENCY_HZ`
- `STATUS_INDICATOR_DMA_CHANNEL`
- `STATUS_INDICATOR_PWM_CHANNEL`
- `STATUS_INDICATOR_BRIGHTNESS`
- `STATUS_INDICATOR_INVERT`
- `STATUS_INDICATOR_STRIP_TYPE`
- `STATUS_INDICATOR_SYNC_INTERVAL_SEC`

## INA228-Konfiguration

Die Achslastsensoren sind aktuell so vorgesehen:

- Bus: `/dev/i2c-1`
- `X`: `0x40` live verifiziert
- `Y`: `0x41` im aktuellen Bus-Inventar sichtbar
- `Z`: `0x44` im aktuellen Bus-Inventar sichtbar

Konfigurierbare Umgebungsvariablen:

- `AXIS_LOAD_SENSOR_CACHE_TTL_SEC`
- `AXIS_LOAD_X_SENSOR_ENABLED`
- `AXIS_LOAD_X_SENSOR_I2C_ADDRESS`
- `AXIS_LOAD_X_SHUNT_RESISTANCE_OHMS`
- `AXIS_LOAD_X_CALIBRATION_MAX_CURRENT_A`
- `AXIS_LOAD_X_REFERENCE_CURRENT_A`

Dieselbe Struktur gilt analog fuer `Y` und `Z`.

## Leitlinien

- Neue Sensoren und Aktoren bekommen eigene Treiberklassen statt Inline-Code in `server.py`
- Reale Hardwarezugriffe muessen auf Nicht-Linux-Systemen kontrolliert fehlschlagen koennen
- Antwortobjekte enthalten immer Metadaten, Status und Fehlertext, damit Frontend und Backend gleich damit arbeiten koennen
- Polling wird zentral ueber das Hardware-Backend begrenzt, um Sensoren nicht unnoetig oft auszulesen
- Auf dem Zielsystem muss der Service-User Lese-/Schreibrechte auf `/dev/i2c-*` besitzen
- Optional verfuegbare Hardware wie der WS2812B-Streifen darf das Backend im Dev-Betrieb nicht blockieren, wenn die Ziel-Library fehlt

## Naechste Schritte

- Nicht belegte Safety-Eingaenge `4..8` dokumentieren, sobald deren Rolle feststeht
- Physische Verdrahtung von Relaisboard, Safety-Modul und LED-Streifen als Einbaudokument ergaenzen
- Health- und Diagnoseinformationen fuer Busse, Adressen und Geraetestatus weiter ausbauen
