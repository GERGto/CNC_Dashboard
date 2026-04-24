# Pololu 5411 Spindellast-Sensor

## Rolle im System

- Modultyp: `Pololu 5411`
- Produktbezeichnung: `ACS37800KMACTR-030B3-I²C Power Monitor Carrier with Attached Terminal Block`
- Sensorfamilie im Projekt: einzelnes Modul für die primäre `Spindellast`
- Aufgabe im Projekt: reale Strom-/Leistungsaufnahme der Spindel erfassen und daraus den Lastwert für Dashboard und RGB-Status ableiten
- Messbereich des eingesetzten Bausteins:
  - Strom: `±30 A`
  - Kommunikation: `I²C`

## Funktionsprinzip

- Das Modul basiert auf dem `Allegro ACS37800`.
- Der Sensor misst berührungslos über einen integrierten Halleffekt-Stromsensor.
- Im Projekt werden aktuell diese Werte genutzt:
  - `currentA`
  - `powerW`
  - `busVoltageV`
- Daraus wird im Backend ein normierter `loadPercent` für die Spindel berechnet.
- Für die sichtbare Dashboard-Anzeige wird dieser Rohwert zusätzlich über eine konfigurierbare Kalibrierung in `calibratedLoadPercent` überführt.

## Anschluss und Adresse

- Bus: `I²C`
- Aktueller Bus auf dem Raspberry Pi: `/dev/i2c-1`
- Aktuelle Live-Adresse im Aufbau: `0x60`
- Laut Pololu ist `0x60` die Standardadresse des Moduls
- Anschlussart im aktuellen Aufbau:
  - `SDA`
  - `SCL`
  - `3V3`
  - `GND`
  - Lastpfad über die Schraubklemmen des Moduls

## Verkabelung im System

- Die Logikseite des `Pololu 5411` hängt am gemeinsamen `Qwiic`-Daisy-Chain-Bus des Raspberry Pi.
- Der vorgesehene Buspfad ist:
  - `Raspberry Pi -> SparkFun Qwiic HAT -> Qwiic-Daisy-Chain -> Pololu 5411`
- Über `Qwiic` werden nur `3V3`, `GND`, `SDA` und `SCL` geführt.
- Die eigentliche Messverdrahtung läuft separat über die Schraubklemmen des Moduls.
- Für das System ist vorgesehen:
  - die zu messende Spindelzuleitung in Serie durch den Strompfad des Boards zu führen
  - positive Messrichtung gemäß Pololu-Markierung von `IP+` nach `IP-`
  - die Spannungsreferenzseite gemäß Pololu-Schaltbild an die überwachte Spindelversorgung anzubinden
- Praktisch bedeutet das:
  - `Qwiic` ist nur die Logik-/Busseite
  - die Spindel-Leistungsverdrahtung bleibt vollständig auf der Klemmen- und Strompfadseite des Boards
- Die exakte endgültige Zuordnung der Spindel-Versorgungsleitung an `IP+`, `IP-` und die Spannungsreferenz sollte zusätzlich noch im Schaltschrank dokumentiert werden.

## Einsatz im Projekt

- Die Spindellast in beiden Dashboards kommt nicht mehr aus einem Dummy-Pfad.
- `GET /api/axes` und `GET /api/axes/stream` liefern die Spindel jetzt aus dem echten `ACS37800`.
- Die `RUNNING`-Animation des RGB-Strips nutzt denselben kalibrierten Spindellastwert.
- Im lokalen Dashboard kann die Prozentkalibrierung der Spindel per Long-Press auf einer Spindel-Kachel angepasst werden.

## Backend-Anbindung

- Python-Treiber: `backend/cnc_hardware/sensors.py`
  - Klasse: `ACS37800Sensor`
- Hardware-Fassade: `backend/cnc_hardware/service.py`
- App-Kalibrierung und Weitergabe an Dashboard/RGB-Strip: `backend/cnc_backend/app.py`
- HTTP-Endpunkt:
  - `GET /api/hardware/spindle-load`

## API-Ansteuerung

- Direkter Sensor-Endpunkt: `GET /api/hardware/spindle-load`
- Sammelendpunkt mit eingebettetem Sensor: `GET /api/hardware`
  - unter `sensors.spindleLoad`
- Dashboard- und Stream-Pfad:
  - `GET /api/axes`
  - `GET /api/axes/stream`

Typische Rückgabefelder von `GET /api/hardware/spindle-load`:

- `available`
- `currentA`
- `powerW`
- `reactivePowerW`
- `busVoltageV`
- `loadPercent`
- `calibratedLoadPercent`
- `addressHex`
- `measuredAt`
- `error`

## Umgebungsvariablen

- `SPINDLE_LOAD_SENSOR_ENABLED`
- `SPINDLE_LOAD_SENSOR_I2C_ADDRESS`
- `SPINDLE_LOAD_SENSOR_RSENSE_KOHM`
- `SPINDLE_LOAD_SENSOR_REFERENCE_CURRENT_A`
- `AXIS_LOAD_SENSOR_CACHE_TTL_SEC`

## Lokale Testbefehle auf dem Pi

I²C-Scan:

```bash
i2cdetect -y 1
```

Direkter Sensor-Endpunkt:

```bash
curl -fsS "http://127.0.0.1:8080/api/hardware/spindle-load?refresh=1"
```

Gesamtübersicht des Hardware-Backends:

```bash
curl -fsS "http://127.0.0.1:8080/api/hardware?refresh=1"
```

Dashboard-/Stream-Payload prüfen:

```bash
curl -fsS "http://127.0.0.1:8080/api/axes"
```

## Verifikation

- Datum: `2026-04-24`
- Zielsystem: `ssh cncpi`
- I²C-Scan auf dem Pi:
  - `0x60` ist auf `/dev/i2c-1` sichtbar
- Live-Backend-Endpunkt:
  - `sensorType = ACS37800`
  - `addressHex = 0x60`
  - `role = spindleLoad`
  - `axis = spindle`
- Die Spindel wird in `GET /api/axes` seitdem nicht mehr aus dem Mock gespeist.

## Referenzen

- Pololu Produktseite: `https://www.pololu.com/product/5411`
- Pololu Bibliotheksdoku: `https://pololu.github.io/acs37800-arduino/`
- Allegro Produktseite:
  - `https://www.allegromicro.com/en/products/sense/current-sensor-ics/integrated-current-sensors/acs37800`
- Allegro Datenblatt:
  - `https://www.allegromicro.com/-/media/files/datasheets/acs37800-datasheet.pdf`

## Offene Punkte

- Reale Verdrahtung des Lastpfads an den Schraubklemmen im Schaltschrank noch separat fotografisch dokumentieren
- Prüfen, ob `SPINDLE_LOAD_SENSOR_REFERENCE_CURRENT_A = 30.0` dauerhaft gut zur Maschine passt oder nach Kalibrierfahrt enger gesetzt werden sollte
- Optional: zusätzlich Rohwerte in `A` oder `W` sichtbar im lokalen oder Remote-Dashboard einblenden
