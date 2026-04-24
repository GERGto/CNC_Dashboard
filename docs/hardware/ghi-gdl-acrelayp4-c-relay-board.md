# GHI GDL-ACRELAYP4-C 4-Kanal-Relais

## Rolle im System

- Modul: `GHI Electronics GDL-ACRELAYP4-C`
- Aufgabe im Projekt: Schaltet Maschinenlicht, Spindelluefter und weitere Lasten ueber ein 4-Kanal-Relais
- Aktuelle Kanalbelegung im CNC-Dashboard:
  - `K1`: Maschinenlicht
  - `K2`: Spindelluefter
  - `K3`: Gehäuse-Lüfter
  - `K4`: E-Stop

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
- Offizielle DUELink-Produktseite:
  - `https://www.ghielectronics.com/duelink/`

## Verkabelung im System

- Die Logikseite des Relaisboards hängt am gemeinsamen `I²C`-/`DaisyLink`-Bus des Raspberry Pi.
- Der vorgesehene Buspfad ist:
  - `Raspberry Pi -> SparkFun Qwiic HAT -> I²C/DaisyLink-Bus -> GDL-ACRELAYP4-C`
- Über diese Busseite laufen nur Kommunikation und Logikversorgung, nicht die geschalteten Lasten.
- Die eigentliche Feldverdrahtung erfolgt an den Relais-Schraubklemmen.
- Im System ist vorgesehen, die Arbeitskontakte je Kanal über `COM` und `NO` zu nutzen, damit die Lasten im stromlosen Grundzustand aus bleiben.
- Aktuelle Funktionszuordnung der Schraubklemmen:
  - `K1`: Maschinenlicht
  - `K2`: Spindel-Lüfter
  - `K3`: Gehäuse-Lüfter
  - `K4`: E-Stop-Kreis
- Das bedeutet praktisch:
  - Versorgungs- oder Freigabeleitung der jeweiligen Last auf `COM`
  - geschalteter Abgang zur Last auf `NO`
  - `NC` bleibt im aktuellen Aufbau ungenutzt, solange kein inverses Schaltverhalten gewünscht ist

## Verifikation

- Datum: `2026-04-06`
- Zielsystem: Raspberry Pi mit DietPi via `ssh cncpi`
- Ergebnis der Herstellerrecherche: Das Board spricht auf `0x52`
- Ergebnis des Pi-Scans:
  - `i2c-1` ist der primaere Linux-I2C-Bus
  - auf `i2c-1` wurden zuletzt `0x21`, `0x38`, `0x40`, `0x41`, `0x44` und `0x52` gesehen
  - `0x52` ist damit im aktuellen Maschinenaufbau live sichtbar

Wichtiger Hinweis:

- Die Software ist auf `0x52` und den DUELink-Befehlssatz vorbereitet.
- Kanal `4` wird zusaetzlich vom Backend automatisch gesetzt, wenn ein Hardware-E-Stop ueber das PCF8574-Eingangsmodul ausloest.

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
- `POST /api/hardware/enclosure-fan`
  - Request: `{ "on": true|false }`
- `POST /api/hardware/e-stop`
  - Request: `{ "engaged": true|false }` oder `{ "on": true|false }`

## Frontend-Anbindung

- Das Haupt-Frontend schaltet das Maschinenlicht ueber `/api/hardware/light`
- Das Haupt-Frontend schaltet den Spindelluefter ueber `/api/hardware/fan`
- Das Haupt-Frontend schaltet den Gehäuse-Lüfter ueber `/api/hardware/enclosure-fan`
- Der Web-Monitor nutzt fuer den manuellen Not-Halt `/api/hardware/e-stop`
- Bei aktivem mechanischem Hardware-E-Stop sperrt das Backend das Ruecksetzen von `K4`, bis der reale Taster geloest wurde
- Der aktuelle Relaisstatus wird ueber den Hardware-Snapshot wieder in die UIs gespiegelt

## Offene Punkte

- Physische Verdrahtung am Pi und am Relaisboard abschliessend dokumentieren
- Rueckmeldung des echten Board-Status nach erster erfolgreicher Schaltung auf dem Pi verifizieren
- Physische Verdrahtung des Gehäuse-Lüfters auf `K3` bei Gelegenheit mit Foto dokumentieren
