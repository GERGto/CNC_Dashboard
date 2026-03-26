# Adafruit AHT20 Spindeltemperatur-Sensor

## Rolle im System

- Sensor: `Adafruit AHT20`
- Aufgabe im Projekt: Misst die Spindeltemperatur
- Zusatznutzen: Der Sensor liefert auch relative Luftfeuchtigkeit, obwohl aktuell primaer die Temperatur der Spindel relevant ist

## Anschluss und Adresse

- Bus: `I2C`
- Aktueller Bus auf dem Raspberry Pi: `/dev/i2c-1`
- I2C-Adresse: `0x38`
- Anschlussart: ueber den SparkFun Qwiic HAT
- I2C-Spannung im aktuellen System: `3.3 V`
- Relevante Leitungen: `3V3`, `GND`, `SDA`, `SCL`

## Verifikation

- Datum: `2026-03-26`
- Aussage des Projekts: Die Adresse `0x38` ist der AHT20 fuer die Spindeltemperatur
- I2C-Scan auf dem Pi: `0x38` wurde auf `/dev/i2c-1` gefunden
- Live-Backend-Test auf `root@192.168.137.116`: `GET /api/hardware/spindle-temperature` liefert Temperatur- und Luftfeuchtewerte vom Sensor

## Backend-Anbindung

- Python-Treiber: `backend/cnc_hardware/sensors.py`
- Hardware-Fassade: `backend/cnc_hardware/service.py`
- Laufzeit: innerhalb von `cnc-dashboard-backend.service`, kein separater eigener Hardware-Service
- HTTP-Endpunkte:
  - `GET /api/hardware`
  - `GET /api/hardware/spindle-temperature`

## API-Ansteuerung

- Primaerer Endpunkt fuer die Spindeltemperatur: `GET /api/hardware/spindle-temperature`
- Fuer einen direkten Neu-Read ohne Cache: Query `?refresh=1` anhaengen
- Sammelendpunkt mit eingebetteter Spindeltemperatur: `GET /api/hardware`

Typische Rueckgabefelder von `GET /api/hardware/spindle-temperature`:

- `available`: Ob der Sensor aktuell erfolgreich gelesen werden konnte
- `status`: `ok` oder `unavailable`
- `temperatureC`: Gemessene Spindeltemperatur in Grad Celsius
- `humidityPercent`: Relative Luftfeuchtigkeit vom AHT20
- `measuredAt`: UTC-Zeitpunkt der letzten Messung
- `error`: Fehlertext bei I2C- oder Sensorproblemen
- `bus`, `devicePath`, `addressHex`: Technische Zuordnung des Sensors auf dem I2C-Bus

## Lokale Testbefehle auf dem Pi

Direkter Test des Spindeltemperatur-Endpunkts:

```bash
curl -fsS "http://127.0.0.1:8080/api/hardware/spindle-temperature?refresh=1"
```

Gesamtuebersicht des Hardware-Backends:

```bash
curl -fsS "http://127.0.0.1:8080/api/hardware?refresh=1"
```

Backend-Service pruefen:

```bash
systemctl status cnc-dashboard-backend.service --no-pager
```

Pruefen, ob der Service beim Start aktiviert ist:

```bash
systemctl is-enabled cnc-dashboard-backend.service
```

Pruefen, ob der laufende Service I2C-Zugriff haben sollte:

```bash
id dietpi
```

## Offene Punkte

- Dauerhafte Grenzwerte und Alarmregeln fuer die Spindeltemperatur definieren
- Physische Einbauposition am Spindelgehaeuse dokumentieren
- Erwartete Temperaturbereiche im Betrieb definieren
- Spaeter Grenzwerte, Warnungen und Verlaufsspeicherung aufbauen
