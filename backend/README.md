# Hardware API (dev)

This backend provides a simple HTTP + SSE API for Raspberry Pi hardware control
and streaming axis/spindle load values. For development it serves mock values.

## Endpoints

- GET `/api/health`
  - `{ status: "ok", time: "<iso>" }`
- GET `/api/axes`
  - `{ timestamp, axes: { spindle,x,y,z } }`
- GET `/api/axes/stream` (SSE)
  - `event: axes` with `{ timestamp, axes: { spindle,x,y,z } }` every ~250ms
  - Optional query: `?intervalMs=250`
- GET `/api/hardware`
  - `{ time, transport: { primary, i2c }, sensors: { spindleTemperature } }`
  - Optional query: `?refresh=1`
- GET `/api/hardware/spindle-temperature`
  - `{ sensorId, sensorType, available, temperatureC, humidityPercent, measuredAt, ... }`
  - Optional query: `?refresh=1`
- GET `/api/settings`
  - `{ graphWindowSec, lightBrightness, fanSpeed, fanAuto, wifiSsid, wifiPassword, wifiAutoConnect, wifiConnected, axisVisibility, spindleRuntimeSec, maintenanceTasks }`
- POST `/api/settings`
  - `{ graphWindowSec, lightBrightness, fanSpeed, fanAuto, wifiSsid, wifiPassword, wifiAutoConnect, wifiConnected, axisVisibility, spindleRuntimeSec, maintenanceTasks }`
- GET `/api/maintenance/tasks`
  - `{ tasks: [{ id, title, intervalType, intervalValue, effortMin, description, lastCompletedAt, spindleRuntimeSecAtCompletion }] }`
  - `intervalType`: `runtimeHours` | `calendarMonths` | `none`
  - `intervalValue`: Zahl oder `"-"` (`"-"` bzw. `intervalType: "none"` bedeutet: keine automatische Fälligkeit)
- GET `/api/wifi/networks`
  - `{ networks: [ "<ssid1>", "<ssid2>", ... ] }`
- POST `/api/wifi/connect`
  - Request: `{ ssid, password, autoConnect }`
  - Response: `{ ok, connected, ssid, autoConnect }`
- POST `/api/wifi/disconnect`
  - Response: `{ ok, connected, ssid, autoConnect }`
- POST `/api/maintenance/tasks/<taskId>/complete`
  - Markiert Aufgabe als erledigt (mit aktuellem Datum und aktueller Spindellaufzeit)
- POST `/api/shutdown`
  - When configured for a real device shutdown: `{ ok: true, message: "Shutdown scheduled" }`
  - Otherwise: `{ ok: false, message: "Real shutdown is disabled" }`

## Run

```
python server.py
```

Optional:

```
set PORT=8080
set AXES_INTERVAL_MS=250
set ENABLE_REAL_SHUTDOWN=1
set SHUTDOWN_COMMAND=sudo -n /usr/bin/systemctl poweroff
set SHUTDOWN_DELAY_SEC=1.0
set HARDWARE_PRIMARY_I2C_BUS=1
set SPINDLE_TEMP_SENSOR_I2C_ADDRESS=0x38
set HARDWARE_SENSOR_CACHE_TTL_SEC=2.0
```

The server listens on `http://localhost:8080` by default.

## Persistenzdateien

- `settings.json`: UI-Einstellungen (`graphWindowSec`, Licht/Lüfter, WLAN, `axisVisibility`)
- `tasks.json`: Wartungsaufgaben (`maintenanceTasks`)
- `machine_stats.json`: Maschinenstatistiken (`spindleRuntimeSec`)
