# Adafruit INA228 Achslast-Sensoren

## Rolle im System

- Modultyp: `Adafruit INA228 I2C Power Monitor` (Adafruit Produkt `5832`)
- Sensorfamilie im Projekt: drei baugleiche Module fuer `X`, `Y` und `Z`
- Aufgabe im Projekt: reale Strom-/Leistungsaufnahme der Achsen erfassen
- Messbereich laut eingesetztem Breakout:
  - Spannung `0-85 V`
  - Strom `bis 10 A`
- Darstellung im Dashboard:
  - rohe Messwerte als `currentA`, `powerW`, `busVoltageV`, `shuntVoltageMv`, `dieTemperatureC`
  - daraus abgeleiteter `loadPercent` fuer die bestehende Achslast-Anzeige im Frontend

## Funktionsprinzip

- Der `INA228` ist ein praeziser I2C-Leistungsmonitor fuer Strom, Spannung und Leistung.
- Auf dem Adafruit-Breakout ist bereits ein `15 mOhm` Shunt-Widerstand verbaut.
- Das Modul misst:
  - `VBUS`: Busspannung
  - `VSHUNT`: Spannungsabfall ueber dem Shunt
  - `CURRENT`: berechneter Strom
  - `POWER`: berechnete Leistung
  - `DIETEMP`: interne Chiptemperatur
- Das Dashboard verwendet die gemessene Achs-Stromaufnahme fuer einen normierten `loadPercent`:
  - Formel: `abs(currentA) / referenceCurrentA * 100`
  - die Referenzstroeme sind pro Achse per Umgebungsvariable anpassbar

## Anschluss und Adresse

- Bus: `I2C`
- Aktueller Bus auf dem Raspberry Pi: `/dev/i2c-1`
- Anschlussart: ueber `Qwiic / STEMMA QT`
- I2C-Spannung im aktuellen System: `3.3 V`
- Relevante Leitungen: `3V3`, `GND`, `SDA`, `SCL`

Aktuell verifiziert:

- `X`-Achse: `0x40`

Fuer die weitere Kette im Projekt vorgesehen:

- `Y`-Achse: Backend-Default `0x41` (noch nicht live verifiziert)
- `Z`-Achse: Backend-Default `0x44` (noch nicht live verifiziert)

Hinweis:

- Das Adafruit-Board besitzt zwei Address-Jumper `A0` und `A1`.
- Dadurch koennen mehrere INA228-Boards am selben I2C-Bus betrieben werden.
- Fuer `Y` und `Z` sind die Adressen im Backend konfigurierbar, falls die reale Verdrahtung davon abweicht.

## Verifikation

- Datum: `2026-03-29`
- Zielsystem: `root@192.168.178.61`
- I2C-Scan auf dem Pi:
  - `0x38` = `AHT20`
  - `0x40` = `INA228` fuer die `X`-Achse
  - `0x52` = `GHI GDL-ACRELAYP4-C`
- Direkter Registerzugriff auf `0x40` war erfolgreich
- Die Adressen `0x41`, `0x44` und `0x45` haben im aktuellen Live-Setup noch nicht geantwortet

## Backend-Anbindung

- Python-Treiber: `backend/cnc_hardware/sensors.py`
  - Klasse: `INA228Sensor`
- Hardware-Fassade: `backend/cnc_hardware/service.py`
- Laufzeit: innerhalb von `cnc-dashboard-backend.service`
- HTTP-Endpunkte:
  - `GET /api/hardware`
  - `GET /api/hardware/axis-loads`
  - `GET /api/axes`
  - `GET /api/axes/stream`

## API-Ansteuerung

- Primaerer Hardware-Endpunkt fuer die Sensorgruppe: `GET /api/hardware/axis-loads`
- Sammelendpunkt mit eingebetteten Achslasten: `GET /api/hardware`
- Live-Frontend-Stream: `GET /api/axes/stream`

Typische Rueckgabefelder von `GET /api/hardware/axis-loads`:

- `available`: Ob mindestens ein INA228 erfolgreich gelesen werden konnte
- `axes.x|y|z.available`: Status pro Achse
- `axes.<axis>.loadPercent`: normierter Lastwert fuer das Dashboard
- `axes.<axis>.currentA`: gemessener Strom
- `axes.<axis>.powerW`: gemessene Leistung
- `axes.<axis>.busVoltageV`: gemessene Busspannung
- `axes.<axis>.shuntVoltageMv`: Spannungsabfall am Shunt
- `axes.<axis>.dieTemperatureC`: interne Sensor-Temperatur
- `axes.<axis>.error`: Fehlertext bei fehlender Antwort oder I2C-Problemen

## Umgebungsvariablen

Pro Achse koennen diese Werte gesetzt werden:

- `AXIS_LOAD_X_SENSOR_ENABLED`
- `AXIS_LOAD_X_SENSOR_I2C_ADDRESS`
- `AXIS_LOAD_X_SHUNT_RESISTANCE_OHMS`
- `AXIS_LOAD_X_CALIBRATION_MAX_CURRENT_A`
- `AXIS_LOAD_X_REFERENCE_CURRENT_A`

Dieselbe Struktur gilt analog fuer `Y` und `Z`.

Zusatz:

- `AXIS_LOAD_SENSOR_CACHE_TTL_SEC`

## Lokale Testbefehle auf dem Pi

I2C-Scan:

```bash
i2cdetect -y 1
```

Direkter Hardware-Endpunkt:

```bash
curl -fsS "http://127.0.0.1:8080/api/hardware/axis-loads?refresh=1"
```

Gesamtuebersicht des Hardware-Backends:

```bash
curl -fsS "http://127.0.0.1:8080/api/hardware?refresh=1"
```

Achs-Stream pruefen:

```bash
curl -N "http://127.0.0.1:8080/api/axes/stream?intervalMs=250"
```

## Offene Punkte

- Reale Verdrahtung und Adressen fuer `Y` und `Z` live verifizieren
- Referenzstroeme pro Achse kalibrieren, damit `loadPercent` zur Maschine passt
- Falls gewuenscht: zusaetzlich reale `A` oder `W` direkt im Frontend-Card-Text anzeigen
