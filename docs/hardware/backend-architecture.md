# Hardware Backend Architektur

## Zielbild

Das Hardware-Backend soll eine zentrale, erweiterbare Schicht fuer reale Maschinenhardware bereitstellen.
Es kapselt Buszugriffe und Geraetelogik, damit weder Frontend noch `server.py` direkt I2C-Details kennen muessen.

## Verantwortlichkeiten

- Zugriff auf Hardware-Busse wie `I2C`
- Treiberlogik pro Geraet oder Sensor
- Vereinheitlichte, frontend-taugliche Datenstruktur fuer Messwerte und Fehler
- Wiederverwendbare Python-Schnittstelle fuer das restliche Software-Backend
- Spaeere Basis fuer Aktoren, Polling, Health-Checks und Bus-Diagnose

## Erster Zuschnitt

Die erste Ausbaustufe besteht aus drei Ebenen:

1. `backend/cnc_hardware/i2c.py`
   Linux-I2C-Zugriff ueber `/dev/i2c-*` ohne zusaetzliche Python-Abhaengigkeiten.
2. `backend/cnc_hardware/sensors.py`
   Geraetetreiber, aktuell fuer den `AHT20` Spindeltemperatur-Sensor.
3. `backend/cnc_hardware/service.py`
   Hardware-Fassade mit normalisierter Antwortstruktur und kurzem Messwert-Cache.

## HTTP-Anbindung

Der bestehende HTTP-Server bindet das Hardware-Backend als Adapter ein und stellt zunaechst zwei Endpunkte bereit:

- `GET /api/hardware`
  Gesamtuebersicht ueber den Hardware-Status und bekannte Sensoren
- `GET /api/hardware/spindle-temperature`
  Direkter Zugriff auf den AHT20-Messwert der Spindeltemperatur

## Leitlinien

- Neue Sensoren bekommen eigene Treiberklassen statt Inline-Code in `server.py`
- Reale Hardwarezugriffe muessen auf Nicht-Linux-Systemen kontrolliert fehlschlagen koennen
- Antwortobjekte enthalten immer Metadaten, Status und Fehlertext, damit Frontend und Backend gleich damit arbeiten koennen
- Polling wird zentral ueber das Hardware-Backend begrenzt, um Sensoren nicht unnoetig oft auszulesen
- Auf dem Zielsystem muss der Service-User Lese-/Schreibrechte auf `/dev/i2c-*` besitzen; auf dem aktuellen Pi wurde `dietpi` dazu der Gruppe `i2c` hinzugefuegt

## Naechste Schritte

- Weitere I2C-Sensoren und Aktoren in eigene Treiber auslagern
- Gemeinsame Hardware-Konfiguration pro Maschine einfuehren
- Langlaufende Polling-/Streaming-Pfade fuer Live-Daten ergaenzen
- Health- und Diagnoseinformationen fuer Busse, Adressen und Geraetestatus erweitern
