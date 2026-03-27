# GHI GDL-ACRELAYP4-C 4-Kanal-Relais

## Rolle im System

- Modul: `GHI Electronics GDL-ACRELAYP4-C`
- Aufgabe im Projekt: Schaltet Maschinenlicht, Spindelluefter und weitere Lasten ueber ein 4-Kanal-Relais
- Aktuelle Kanalbelegung im CNC-Dashboard:
  - `K1`: Maschinenlicht
  - `K2`: Spindelluefter
  - `K3`: E-Stop
  - `K4`: frei / Reserve

## Anschluss und Kommunikation

- Bus: `I2C`
- Zielbus auf dem Raspberry Pi: `/dev/i2c-1`
- Offizielle I2C-Adresse des Boards: `0x52` (`82` dezimal)
- Protokoll: `DUELink DaisyLink` ueber ASCII-Kommandos per I2C
- Aktueller Geraeteindex laut Herstellerbeispiel: `1`

Vom Hersteller bestaetigte Kommandostruktur:

- Geraet waehlen: `sel(1)`
- Relais schalten: `Set(<kanal>, <0|1>)`
- Treiberversion lesen: `DVer()`
- Initialisierungs-Trigger nach Power-up: leeres Kommando / leere Zeile

## Hersteller-Referenzen

- Offizielle Treiberdatei: `gdl-acrelayp4-c.txt`
  - enthaelt `fn Set(i, v)` fuer die Kanaele `1..4`
- Offizielles DUELink-Beispiel: `gdl-acrelayp4-c.ubp`
  - verwendet `due_select_device 1`
  - verwendet `sensors:i2cWrite 82` und `sensors:i2cRead 82`

## Verifikation

- Datum: `2026-03-26`
- Zielsystem: Raspberry Pi mit DietPi via `root@192.168.137.116`
- Ergebnis der Herstellerrecherche: Das Board spricht auf `0x52`
- Ergebnis des Pi-Scans:
  - `i2c-1` ist der primaere Linux-I2C-Bus
  - auf `i2c-1` wurde beim Scan nur `0x38` (AHT20) gesehen
  - das Relaisboard war beim Linux-Scan auf `i2c-1` noch nicht sichtbar

Wichtiger Hinweis:

- Die Software ist auf `0x52` und den DUELink-Befehlssatz vorbereitet.
- Wenn das Board physisch noch nicht korrekt antwortet, liefern die Relais-Endpunkte einen Hardware-Fehler zurueck, bis Verdrahtung, Versorgung oder Bus-Anbindung passen.

## Backend-Anbindung

- Python-Treiber: `backend/cnc_hardware/duelink_relay.py`
- Hardware-Fassade: `backend/cnc_hardware/service.py`
- HTTP-Anbindung: `backend/cnc_backend/request_handler.py`
- Laufzeit: innerhalb von `cnc-dashboard-backend.service`

Konfigurierbare Umgebungsvariablen:

- `RELAY_BOARD_ENABLED` (Default: `true`)
- `RELAY_BOARD_I2C_ADDRESS` (Default: `0x52`)
- `RELAY_BOARD_DEVICE_INDEX` (Default: `1`)
- `RELAY_BOARD_RESPONSE_TIMEOUT_SEC` (Default: `0.75`)
- `RELAY_BOARD_INITIALIZATION_RETRY_WINDOW_SEC` (Default: `1.5`)
- `RELAY_BOARD_INITIALIZATION_RETRY_INTERVAL_SEC` (Default: `0.05`)
- `RELAY_BOARD_INITIALIZATION_RESPONSE_TIMEOUT_SEC` (Default: `0.15`)
- `RELAY_BOARD_STARTUP_INITIALIZATION_ENABLED` (Default: `true`)
- `RELAY_BOARD_STARTUP_INITIALIZATION_DELAY_SEC` (Default: `1.0`)
- `RELAY_BOARD_STARTUP_INITIALIZATION_ATTEMPTS` (Default: `0`, bedeutet unbegrenzt bis Erfolg)
- `RELAY_BOARD_STARTUP_INITIALIZATION_INTERVAL_SEC` (Default: `1.0`)
- `RELAY_BOARD_LIGHT_ON_AFTER_STARTUP` (Default: `true`)
- `RELAY_BOARD_POWER_CONTROL_ENABLED` (Default: `false`)
- `RELAY_BOARD_POWER_GPIO_CHIP` (Default: `/dev/gpiochip0`)
- `RELAY_BOARD_POWER_GPIO_LINE_OFFSET` (Default: `17`)
- `RELAY_BOARD_POWER_ACTIVE_HIGH` (Default: `true`)
- `RELAY_BOARD_POWER_OFF_DELAY_SEC` (Default: `0.25`)
- `RELAY_BOARD_POWER_ON_DELAY_SEC` (Default: `1.0`)

Initialisierung im Backend:

- Beim Start des Backend-Dienstes laeuft automatisch ein Relais-Warmup im Hintergrund.
- Optional kann dieser Warmup die 3.3V-Logikversorgung des Relaisboards vor jedem Init-Versuch ueber einen GPIO-Ausgang power-cyclen.
- Dieser Warmup versucht das Board nach einem kurzen Delay mehrfach zu initialisieren, noch bevor das Frontend den ersten Schaltbefehl sendet.
- Nach erfolgreicher Initialisierung kann das Backend standardmaessig das Maschinenlicht auf Kanal 1 direkt einschalten.
- Vor dem ersten echten Relaiskommando sendet das Backend ein leeres DUELink-Kommando.
- Wenn das Board nach dem Anstecken noch nicht sauber enumeriert ist, wird diese Initialisierung fuer ein kurzes Zeitfenster wiederholt.
- Erst danach wird `sel(1)` und der eigentliche `Set(...)`-Befehl ausgefuehrt.

## API-Endpunkte

- `GET /api/hardware`
  - enthaelt `actuators.relayBoard`
- `GET /api/hardware/relays`
  - liefert den aktuellen Snapshot des Relaisboards
- `POST /api/hardware/light`
  - Request: `{ "on": true|false }`
- `POST /api/hardware/fan`
  - Request: `{ "on": true|false }`
- `POST /api/hardware/e-stop`
  - Request: `{ "engaged": true|false }` oder `{ "on": true|false }`
- `POST /api/hardware/relay-4`
  - Request: `{ "on": true|false }`

## Frontend-Anbindung

- Das Haupt-Frontend schaltet das Maschinenlicht ueber `/api/hardware/light`
- Das Haupt-Frontend schaltet den Spindelluefter ueber `/api/hardware/fan`
- Der aktuelle Relaisstatus wird ueber den Hardware-Snapshot wieder in die iFrames gespiegelt

## Offene Punkte

- Physische Verdrahtung am Pi und am Relaisboard abschliessend dokumentieren
- Rueckmeldung des echten Board-Status nach erster erfolgreicher Schaltung auf dem Pi verifizieren
- Sicherheitskonzept fuer `E-Stop` fachlich bewerten, bevor dieser Kanal produktiv verwendet wird
