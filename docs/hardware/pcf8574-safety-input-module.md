# PCF8574 Safety- und Spindel-Inputs

## Rolle im System

- Modultyp: `PCF8574`-kompatibles 8-Kanal-Optokoppler-Eingangsmodul
- Aufgabe im Projekt: Hardware-Safety-Signale und das echte `Spindel laeuft`-Signal in das Backend einspeisen
- Aktuelle feste Betriebsadresse: `0x21`
- Aktuelle Eingangslogik im Projekt: `active-low`

## Aktuelle Belegung

- `Input 1`: mechanischer Hardware-E-Stop
- `Input 2`: mechanischer Hardware-E-Stop
- `Input 3`: `Spindel laeuft`
- `Input 4` bis `Input 8`: aktuell unbelegt

## Laufzeitverhalten

- Wenn `Input 1` oder `Input 2` aktiv wird, markiert das Backend die Maschine sofort als `E-STOP`.
- Der Hardware-E-Stop erzwingt Relaiskanal `4` am Relaisboard.
- Ein Ruecksetzen ueber Web-UI oder lokales UI ist waehrend eines aktiven Hardware-E-Stop gesperrt.
- Das lokale UI zeigt in diesem Zustand die rote Statusleiste `E-STOP`.
- Der `WS2812B`-Statusstreifen wechselt ueber die normale Maschinenstatus-Synchronisation auf rot.
- Die Spindellaufzeit wird nur hochgezaehlt, solange `Input 3` aktiv ist.

## Anschluss und Kommunikation

- Bus: `I2C`
- Zielbus auf dem Raspberry Pi: `/dev/i2c-1`
- Aktuelle Adresse im Aufbau: `0x21`
- Feldseite des Moduls: optisch getrennte 8-Kanal-Eingaenge fuer externe 3.6 V bis 24 V Signale laut Modulbezeichnung

## Backend-Anbindung

- Eingangstreiber: `backend/cnc_hardware/pcf8574_inputs.py`
- Hardware-Fassade: `backend/cnc_hardware/service.py`
- Maschinenstatus-Auswertung: `backend/cnc_backend/machine_status.py`
- API-Fehlerbehandlung fuer blockiertes E-Stop-Reset: `backend/cnc_backend/request_handler.py`
- Spindellaufzeit-Worker: `backend/cnc_backend/app.py`

Relevante Umgebungsvariablen:

- `EMERGENCY_INPUT_MODULE_ENABLED`
- `EMERGENCY_INPUT_MODULE_I2C_ADDRESS`
- `EMERGENCY_INPUT_MODULE_ESTOP_CHANNELS`
- `EMERGENCY_INPUT_MODULE_SPINDLE_RUNNING_CHANNELS`
- `HARDWARE_ESTOP_POLL_INTERVAL_SEC`

## API-Sicht

- `GET /api/hardware`
  - enthaelt das Modul unter `sensors.safetyInputs`
- `GET /api/hardware/relays`
  - spiegelt `safetyInputs` zusaetzlich im Relais-Snapshot
- `GET /api/machine/status`
  - liefert `hardwareEStopEngaged`, `hardwareEStopInputIds`, `eStopResetLocked`, `spindleRunning` und `spindleRunningInputIds`
- `POST /api/hardware/e-stop`
  - quittiert keinen aktiven Hardware-E-Stop; das Backend antwortet in diesem Fall mit `HTTP 409`

## Verifikation

- Datum: `2026-04-06`
- Zielsystem: Raspberry Pi via `ssh cncpi`
- I2C-Scan auf `/dev/i2c-1`: `0x21` ist im aktuellen Aufbau sichtbar
- Live-Backend-Snapshot:
  - `addressHex = 0x21`
  - `hardwareEStopChannelIndexes = [1, 2]`
  - `spindleRunningChannelIndexes = [3]`
  - bei inaktiven Eingaengen wurde zuletzt `rawByte = 0xff` gemeldet

## Offene Punkte

- Physische Verdrahtung der beiden mechanischen E-Stop-Kreise dokumentieren
- Rolle der freien Eingaenge `4..8` festlegen, sobald weitere Safety- oder Statussignale dazu kommen
