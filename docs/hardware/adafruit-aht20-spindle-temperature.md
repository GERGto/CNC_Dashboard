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
- Logik-/Versorgungshinweis laut Breakout-Dokumentation: `2.7V` bis `5.5V`, I2C-Logik ueber `SDA` und `SCL`

## Verifikation

- Datum: `2026-03-26`
- Aussage des Projekts: Die Adresse `0x38` ist der AHT20 fuer die Spindeltemperatur
- I2C-Scan auf dem Pi: `0x38` wurde auf `/dev/i2c-1` gefunden
- Live-Backend-Test auf `root@192.168.137.25`: `GET /api/hardware/spindle-temperature` liefert Temperatur- und Luftfeuchtewerte vom Sensor

## Backend-Anbindung

- Python-Treiber: `backend/cnc_hardware/sensors.py`
- Hardware-Fassade: `backend/cnc_hardware/service.py`
- HTTP-Endpunkte:
  - `GET /api/hardware`
  - `GET /api/hardware/spindle-temperature`

## Offene Punkte

- Dauerhafte Grenzwerte und Alarmregeln fuer die Spindeltemperatur definieren
- Physische Einbauposition am Spindelgehaeuse dokumentieren
- Erwartete Temperaturbereiche im Betrieb definieren
- Spaeter Grenzwerte, Warnungen und Verlaufsspeicherung aufbauen
