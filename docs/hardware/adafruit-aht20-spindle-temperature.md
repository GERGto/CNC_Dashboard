# Adafruit AHT20 Gehäusetemperatur-Sensor

## Rolle im System

- Sensor: `Adafruit AHT20`
- Aufgabe im Projekt: Misst die Gehäusetemperatur
- Zusatznutzen: Der Sensor liefert auch relative Luftfeuchtigkeit, obwohl aktuell primaer die Temperatur des Gehäuses relevant ist

## Anschluss und Adresse

- Bus: `I2C`
- Aktueller Bus auf dem Raspberry Pi: `/dev/i2c-1`
- I2C-Adresse: `0x38`
- Anschlussart: ueber den SparkFun Qwiic HAT
- I2C-Spannung im aktuellen System: `3.3 V`
- Relevante Leitungen: `3V3`, `GND`, `SDA`, `SCL`

## Verkabelung im System

- Der `SparkFun Qwiic HAT` sitzt auf dem 40-Pin-Header des Raspberry Pi und stellt den gemeinsamen `I²C`-Bus bereit.
- Der `AHT20` hängt mit `3V3`, `GND`, `SDA` und `SCL` im selben Qwiic-Daisy-Chain-Bus wie die übrigen Sensoren.
- Für dieses Modul sind im aktuellen Aufbau keine zusätzlichen Schraubklemmen oder Lastleitungen vorgesehen.
- Die Verkabelung ist damit rein logisch:
  - `Raspberry Pi -> Qwiic HAT -> Qwiic-Kabel -> AHT20`
- Relevant im System ist vor allem die physische Position:
  - der Sensor soll die Temperatur im Maschinen- bzw. Elektronikgehäuse erfassen
  - nicht direkt in einem Luftstrom des Lüfters und nicht direkt auf einem Hotspot des Pi montieren

## Hersteller-Referenzen

- Adafruit Produkt- und Pinout-Guide:
  - `https://learn.adafruit.com/adafruit-aht20`
- AHT20-Datenblatt des Chip-Herstellers ASAIR:
  - `https://www.aosong.com/userfiles/files/media/Data%20Sheet%20AHT20.pdf`

## Verifikation

- Datum: `2026-04-06`
- Aussage des Projekts: Die Adresse `0x38` ist der AHT20 fuer die Gehäusetemperatur
- I2C-Scan auf dem Pi: `0x38` wurde weiterhin auf `/dev/i2c-1` gefunden, gemeinsam mit `0x21`, `0x40`, `0x41`, `0x44` und `0x52`
- Der Sensor bleibt ueber `GET /api/hardware/enclosure-temperature` und eingebettet ueber `GET /api/hardware` verdrahtet

## Backend-Anbindung

- Python-Treiber: `backend/cnc_hardware/sensors.py`
- Hardware-Fassade: `backend/cnc_hardware/service.py`
- Laufzeit: innerhalb von `cnc-dashboard-backend.service`, kein separater eigener Hardware-Service
- HTTP-Endpunkte:
  - `GET /api/hardware`
  - `GET /api/hardware/enclosure-temperature`
  - `GET /api/hardware/spindle-temperature` als Legacy-Alias

## API-Ansteuerung

- Primaerer Endpunkt fuer die Gehäusetemperatur: `GET /api/hardware/enclosure-temperature`
- Fuer einen direkten Neu-Read ohne Cache: Query `?refresh=1` anhaengen
- Sammelendpunkt mit eingebetteter Gehäusetemperatur: `GET /api/hardware`

Typische Rueckgabefelder von `GET /api/hardware/enclosure-temperature`:

- `available`: Ob der Sensor aktuell erfolgreich gelesen werden konnte
- `status`: `ok` oder `unavailable`
- `temperatureC`: Gemessene Gehäusetemperatur in Grad Celsius
- `humidityPercent`: Relative Luftfeuchtigkeit vom AHT20
- `measuredAt`: UTC-Zeitpunkt der letzten Messung
- `error`: Fehlertext bei I2C- oder Sensorproblemen
- `bus`, `devicePath`, `addressHex`: Technische Zuordnung des Sensors auf dem I2C-Bus

## Lokale Testbefehle auf dem Pi

Direkter Test des Gehäusetemperatur-Endpunkts:

```bash
curl -fsS "http://127.0.0.1:8080/api/hardware/enclosure-temperature?refresh=1"
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

- Dauerhafte Grenzwerte und Alarmregeln fuer die Gehäusetemperatur definieren
- Physische Einbauposition am Spindelgehäuse dokumentieren
- Erwartete Temperaturbereiche im Betrieb definieren
- Spaeter Grenzwerte, Warnungen und Verlaufsspeicherung aufbauen
