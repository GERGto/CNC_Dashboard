# WS2812B Status-LED-Streifen

## Rolle im System

- Modultyp: `WS2812B` RGB-LED-Streifen
- Aufgabe im Projekt: visueller Maschinenstatus direkt an der Maschine
- Aktueller Ausbau:
  - Versorgung: `5V`
  - Datensignal: `GPIO18` am Raspberry Pi
  - Aktuelle Laenge: `76` LEDs

## Startup-Sequenz

Beim Hochfahren laeuft eine feste Initialisierungssequenz:

1. Ein blaues Lauflicht expandiert von der Mitte nach aussen.
2. Wenn der komplette Streifen blau ist, wird das Maschinenlicht eingeschaltet.
3. Danach faeden die blauen LEDs im Systemcheck auf Weiss.
4. Im `IDLE` blendet der Streifen weich von Voll-Weiss in die langsame Idle-Welle ueber.
5. Anschliessend laeuft der finale Maschinenstatus dauerhaft weiter.

## Shutdown-Sequenz

Beim Herunterfahren ueber das Frontend laeuft eine schnelle Abschaltsequenz:

1. Das aktuell sichtbare Bild des Streifens zieht sich von aussen zur Mitte zusammen.
2. Sobald der Streifen komplett ausgeht, wird im selben Moment das Maschinenlicht ausgeschaltet.
3. Erst danach setzt das Backend den eigentlichen System-Shutdown fort.

Kritische Ausnahme:

- Wenn waehrend des Startvorgangs `E-Stop` aktiv wird, unterbricht der Treiber die Boot-Animation sofort und schaltet direkt auf `Rot`.

## Statusabbildung

Nach dem Startup zeigt der Streifen den Maschinenstatus mit einer festen Prioritaet:

1. `Rot`
   - `E-Stop` aktiv
   - Grundzustand bleibt rot, darueber laufen fortlaufende Doppel-Pulse
2. `Orange`
   - Warnung oder Wartung faellig
3. `Gruen`
   - Job laeuft oder Spindel laeuft
4. `Weiss`
   - `IDLE` als ruhiger Atmungszustand

Aktuelle Backend-Prioritaet:

- `E-Stop > Wartung faellig > RUNNING > IDLE`

Damit bleibt die Warnung sichtbar, auch wenn die Maschine zwar laeuft, aber bereits Wartung faellig ist.

## Idle-Animation

Im Zustand `IDLE` nutzt der Streifen kein statisches Weiss, sondern langsame wandernde Wellen mit auf `50%` begrenzter Maximalhelligkeit:

- jede LED pulsiert zwischen `RGB(28,28,28)` und `RGB(127,127,127)`
- die Maximalhelligkeit bleibt damit bei `RGB 127`, also etwa `50%`
- pro Pixel wird ein Phasenversatz von `0.12` verwendet
- die Welle verschiebt sich pro Frame mit `t += 0.012`
- Zielbild ist ein ruhiges, klar sichtbares Wellenbild entlang des gesamten 76-LED-Streifens bei rund `60 FPS`

## Anschluss

- Versorgung des Streifens: `5V`
- Dateneingang des Streifens: `GPIO18`
- Empfohlener gemeinsamer Bezug: gemeinsame `GND` zwischen Pi und Strip
- Der Backend-Treiber ist auf den fuer `WS2812B` typischen Farbkanalaufbau `GRB` vorbereitet

## Backend-Anbindung

- Python-Treiber: `backend/cnc_hardware/neopixel.py`
- Hardware-Fassade: `backend/cnc_hardware/service.py`
- Maschinenstatus-Logik: `backend/cnc_backend/machine_status.py`
- HTTP-Endpunkte:
  - `GET /api/hardware`
    - enthaelt `actuators.statusIndicator`
    - enthaelt zusaetzlich `machineStatus`
  - `GET /api/machine/status`
    - liefert den effektiven Maschinenstatus und die daraus abgeleitete LED-Farbe
  - `POST /api/machine/status`
    - nimmt einen gemeldeten Basisstatus wie `IDLE`, `RUNNING` oder `ERROR` entgegen

## Laufzeitverhalten

- Das Backend synchronisiert den LED-Streifen zyklisch mit dem effektiven Maschinenstatus.
- Beim Backend-Start wird zuerst die Boot-Sequenz des Streifens gestartet.
- Das Maschinenlicht wird absichtlich erst dann eingeschaltet, wenn der Streifen vollstaendig blau erreicht hat.
- `E-Stop` wird direkt aus dem Relaisboard-Snapshot uebernommen.
- Im `E-Stop`-Zustand rendert der Treiber ein permanentes rotes Warnbild mit wiederholten Doppel-Pulsen.
- `Wartung faellig` wird aus den gespeicherten Wartungsaufgaben und der Spindellaufzeit abgeleitet.
- `RUNNING` kann von anderen Backend- oder Frontend-Komponenten ueber `POST /api/machine/status` gemeldet werden.
- Wenn die NeoPixel-Library auf einem Nicht-Pi- oder Dev-System fehlt, bleibt das Backend lauffaehig und meldet den Streifen als `unavailable`.

## Umgebungsvariablen

- `STATUS_INDICATOR_ENABLED` (Default: `true`)
- `STATUS_INDICATOR_LED_COUNT` (Default: `76`)
- `STATUS_INDICATOR_GPIO_PIN` (Default: `18`)
- `STATUS_INDICATOR_FREQUENCY_HZ` (Default: `800000`)
- `STATUS_INDICATOR_DMA_CHANNEL` (Default: `10`)
- `STATUS_INDICATOR_PWM_CHANNEL` (Default: `0`)
- `STATUS_INDICATOR_BRIGHTNESS` (Default: `255`)
- `STATUS_INDICATOR_INVERT` (Default: `false`)
- `STATUS_INDICATOR_STRIP_TYPE` (Default: `GRB`)
- `STATUS_INDICATOR_SYNC_INTERVAL_SEC` (Default: `2.0`)

## Offene Punkte

- Live-Verifikation des Streifens auf dem Pi nach Installation von `rpi_ws281x`
- Spaeteres Power- und Einspeisekonzept dokumentieren, wenn der Streifen deutlich laenger wird
