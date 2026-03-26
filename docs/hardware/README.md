# Hardware Dokumentation

Dieses Verzeichnis ist der Startpunkt fuer die technische Hardware-Dokumentation des CNC Dashboards.
Hier sollen kuenftig alle verbauten oder angebundenen Komponenten mit ihren Schnittstellen, Besonderheiten und Tests dokumentiert werden.

## Ziel

- Komponenten, HATs, Sensoren, Aktoren und Adapter zentral erfassen
- Pins, Busse, Versorgung, Default-Adressen und Einbauhinweise dokumentieren
- Dev-Tools, Scan-Ergebnisse und Inbetriebnahme-Schritte versioniert ablegen

## Pflege-Regeln

- Pro Hardware-Baustein oder Bus-Gruppe eine eigene Markdown-Datei anlegen
- Messergebnisse und Scans immer mit Datum, System und Werkzeug festhalten
- Unbekannte oder noch nicht verifizierte Informationen explizit als `Offen` markieren
- Diese Sammlung bei jeder neuen Hardware erweitern, statt Wissen nur in Commits oder Chat-Verlaeufen zu lassen

## Aktueller Stand

- [SparkFun Qwiic HAT und I2C-Scan](./sparkfun-qwiic-hat.md)

## Vorlage fuer neue Komponenten

- Bezeichnung und Rolle im System
- Anschluss, Versorgung und relevante Pegel
- Verwendete Pins, Ports oder Busse
- Bekannte Default-Adressen oder Kommunikationsparameter
- Relevante Software-Komponenten oder Skripte
- Inbetriebnahme, Test oder Fehlersuche
- Letzte Verifikation
- Offene Punkte
