# SparkFun Qwiic HAT und I2C-Scan

## Rolle im System

- Der SparkFun Qwiic HAT dient als I2C-Verteiler fuer Qwiic-kompatible Module am Raspberry Pi.
- Er ist der aktuelle Einstiegspunkt fuer Sensorik, die ueber den gemeinsamen I2C-Bus in das Dashboard eingebunden wird.
- Die projektrelevanten Lastwerte werden laut Knowledge Base per I2C erfasst.

## Relevante Schnittstelle

- Bus: `I2C`
- Typischer Raspberry-Pi-Bus: `/dev/i2c-1`
- Logikpegel: `3.3 V`
- Stecksystem: `Qwiic` / `JST-SH 4-polig`
- Gemeinsame Leitungen: `3V3`, `GND`, `SDA`, `SCL`

## Dev Tool

- Skript: `backend/devtools/find_i2c_addresses.py`
- Zweck: Findet verfuegbare I2C-Busse und listet erkannte Adressen pro Bus auf.
- Aufruf aus dem Repo-Root: `python3 backend/devtools/find_i2c_addresses.py`
- Fuer den primaeren Raspberry-Pi-/Qwiic-Bus in der Regel: `python3 backend/devtools/find_i2c_addresses.py --bus 1`
- Optional fuer weitere Automatisierung: `python3 backend/devtools/find_i2c_addresses.py --json`

## Letzte Verifikation

- Datum: `2026-03-26`
- System: Raspberry Pi via `root@192.168.137.25`
- Relevanter Bus fuer den aktuellen Qwiic-HAT-Scan: `/dev/i2c-1`
- Adapter auf `/dev/i2c-1`: `bcm2835 (i2c@7e804000)`
- Gefundene Adresse auf `/dev/i2c-1`: `0x38`
- Rohscan-Hinweis: In der `30:`-Zeile wurde die Adresse `38` erkannt.
- Zusatzadapter: `/dev/i2c-20` (`fef04500.i2c`) und `/dev/i2c-21` (`fef09500.i2c`) antworteten auf sehr viele Adressen; diese Busse sind fuer die Qwiic-Inventarisierung aktuell nicht die primaere Referenz.

## Offene Punkte

- Die gefundene Adresse `0x38` einem konkreten Qwiic-Modul zuordnen
- Exakte Qwiic-Module und deren erwartete Default-Adressen erfassen
- Physische Verdrahtung und Stromversorgung des HAT dokumentieren
- Weitere Maschinen-Hardware schrittweise in `docs/hardware/` aufnehmen
