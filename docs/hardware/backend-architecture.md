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

Die aktuelle Ausbaustufe besteht aus vier Ebenen:

1. `backend/cnc_hardware/i2c.py`
   - Linux-I2C-Zugriff ueber `/dev/i2c-*` ohne zusaetzliche Python-Abhaengigkeiten
2. `backend/cnc_hardware/sensors.py`
   - Sensortreiber fuer den `AHT20` der Spindeltemperatur und die `INA228`-Achslastsensoren
3. `backend/cnc_hardware/duelink_relay.py`
   - Aktortreiber fuer das `GHI GDL-ACRELAYP4-C` Relaisboard auf `0x52`
4. `backend/cnc_hardware/service.py`
   - Hardware-Fassade mit normalisierter Antwortstruktur und kurzem Sensor-Cache

## HTTP-Anbindung

Der bestehende HTTP-Server bindet das Hardware-Backend als Adapter ein und stellt
aktuell folgende Hardware-Endpunkte bereit:

- `GET /api/hardware`
  - Gesamtuebersicht ueber Sensoren, Aktoren und I2C-Metadaten
- `GET /api/hardware/spindle-temperature`
  - Direkter Zugriff auf den AHT20-Messwert der Spindeltemperatur
- `GET /api/hardware/axis-loads`
  - Direkter Zugriff auf die INA228-Messwerte fuer `X`, `Y` und `Z`
- `GET /api/hardware/relays`
  - Snapshot des 4-Kanal-Relaisboards
- `GET /api/axes`
  - Liefert die Frontend-Achswerte; `X/Y/Z` kommen aus den INA228-Sensoren, `Spindel` aktuell noch aus dem bestehenden Last-Mock
- `GET /api/axes/stream`
  - SSE-Stream fuer die Frontend-Achsenanzeige mit eingebetteten `axisLoadSensors`
- `POST /api/hardware/light`
  - Schaltet Relaiskanal 1 fuer das Maschinenlicht
- `POST /api/hardware/fan`
  - Schaltet Relaiskanal 2 fuer den Spindelluefter
- `POST /api/hardware/e-stop`
  - Stellt Relaiskanal 3 fuer E-Stop-Ansteuerung bereit
- `POST /api/hardware/relay-4`
  - Stellt Relaiskanal 4 als Reserve-Endpunkt bereit

## Service-Integration

Die Hardware-API laeuft nicht als eigener separater Systemdienst. Sie ist Teil
des bestehenden Backend-Dienstes `cnc-dashboard-backend.service`, der `server.py`
startet. Wenn dieser Dienst beim Booten hochkommt, stehen damit auch die
Hardware-Endpunkte automatisch zur Verfuegung.

Wichtige Betriebsdetails auf dem aktuellen Pi:

- Service-Name: `cnc-dashboard-backend.service`
- Startdatei: `/opt/cnc-dashboard/backend/server.py`
- Service-User: `dietpi`
- I2C-Zugriff: Der User `dietpi` muss Mitglied der Gruppe `i2c` sein

Nuetzliche Pruefbefehle auf dem Pi:

```bash
systemctl status cnc-dashboard-backend.service --no-pager
systemctl is-enabled cnc-dashboard-backend.service
systemctl is-active cnc-dashboard-backend.service
sudo systemctl restart cnc-dashboard-backend.service
journalctl -u cnc-dashboard-backend.service -n 80 --no-pager
id dietpi
```

## Relaisboard-Konfiguration

Das `GHI GDL-ACRELAYP4-C` ist aktuell so eingeplant:

- Bus: `/dev/i2c-1`
- Adresse: `0x52`
- Protokoll: `DUELink DaisyLink`
- Default-Geraeteindex: `1`

Konfigurierbare Umgebungsvariablen:

- `RELAY_BOARD_ENABLED`
- `RELAY_BOARD_I2C_ADDRESS`
- `RELAY_BOARD_DEVICE_INDEX`
- `RELAY_BOARD_RESPONSE_TIMEOUT_SEC`

## INA228-Konfiguration

Die Achslastsensoren sind aktuell so vorgesehen:

- Bus: `/dev/i2c-1`
- `X`: `0x40` live verifiziert
- `Y`: Backend-Default `0x41`
- `Z`: Backend-Default `0x44`

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

## Naechste Schritte

- Relaisboard auf dem Pi nach abgeschlossener Verdrahtung live verifizieren
- Weitere I2C-Sensoren und Aktoren in eigene Treiber auslagern
- Gemeinsame Hardware-Konfiguration pro Maschine einfuehren
- Health- und Diagnoseinformationen fuer Busse, Adressen und Geraetestatus erweitern
