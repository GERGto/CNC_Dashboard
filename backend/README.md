# Hardware API (dev)

This backend provides a simple HTTP + SSE API for Raspberry Pi hardware control
and streaming axis/spindle load values. For development it serves mock values.

## Endpoints

- GET `/api/health`
  - `{ status: "ok", time: "<iso>" }`
- GET `/api/axes`
  - `{ timestamp, axes: { spindle, x, y, z } }`
- GET `/api/axes/stream` (SSE)
  - `event: axes` with `{ timestamp, axes: { spindle, x, y, z } }` every ~250 ms
  - Optional query: `?intervalMs=250`
- GET `/api/hardware`
  - `{ time, transport: { primary, i2c }, sensors: { spindleTemperature }, actuators: { relayBoard } }`
  - Optional query: `?refresh=1`
- GET `/api/hardware/spindle-temperature`
  - `{ sensorId, sensorType, available, temperatureC, humidityPercent, measuredAt, ... }`
  - Optional query: `?refresh=1`
- GET `/api/hardware/relays`
  - `{ controllerId, status, addressHex, channels, ... }`
- POST `/api/hardware/light`
  - Request: `{ on: true|false }`
  - Response: `{ ok, channel, relayBoard }`
- POST `/api/hardware/fan`
  - Request: `{ on: true|false }`
  - Response: `{ ok, channel, relayBoard }`
- POST `/api/hardware/e-stop`
  - Request: `{ engaged: true|false }` or `{ on: true|false }`
  - Response: `{ ok, channel, relayBoard }`
- POST `/api/hardware/relay-4`
  - Request: `{ on: true|false }`
  - Response: `{ ok, channel, relayBoard }`
- GET `/api/settings`
  - `{ graphWindowSec, lightBrightness, fanSpeed, fanAuto, wifiSsid, wifiPassword, wifiAutoConnect, wifiConnected, axisVisibility, spindleRuntimeSec, maintenanceTasks }`
- POST `/api/settings`
  - `{ graphWindowSec, lightBrightness, fanSpeed, fanAuto, wifiSsid, wifiPassword, wifiAutoConnect, wifiConnected, axisVisibility, spindleRuntimeSec, maintenanceTasks }`
- GET `/api/maintenance/tasks`
  - `{ tasks: [{ id, title, intervalType, intervalValue, effortMin, description, lastCompletedAt, spindleRuntimeSecAtCompletion }] }`
  - `intervalType`: `runtimeHours` | `calendarMonths` | `none`
  - `intervalValue`: number or `"-"` (`intervalType: "none"` means no automatic due date)
- GET `/api/wifi/networks`
  - `{ networks: [ "<ssid1>", "<ssid2>", ... ] }`
- POST `/api/wifi/connect`
  - Request: `{ ssid, password, autoConnect }`
  - Response: `{ ok, connected, ssid, autoConnect }`
- POST `/api/wifi/disconnect`
  - Response: `{ ok, connected, ssid, autoConnect }`
- POST `/api/maintenance/tasks/<taskId>/complete`
  - Marks a task as completed using the current timestamp and spindle runtime
- POST `/api/shutdown`
  - When configured for a real device shutdown: `{ ok: true, message: "Shutdown scheduled" }`
  - Otherwise: `{ ok: false, message: "Real shutdown is disabled" }`

## Relay Board

The project is prepared for a `GHI GDL-ACRELAYP4-C` 4-channel relay board.

- Official I2C address: `0x52` (`82` decimal)
- Protocol: `DUELink DaisyLink` over I2C
- Default device index: `1`
- Channel mapping:
  - `1`: machine light
  - `2`: spindle fan
  - `3`: E-Stop
  - `4`: spare

## Run

```bash
python server.py
```

Optional environment variables:

```bash
set PORT=8080
set AXES_INTERVAL_MS=250
set ENABLE_REAL_SHUTDOWN=1
set SHUTDOWN_COMMAND=sudo -n /usr/bin/systemctl poweroff
set SHUTDOWN_DELAY_SEC=1.0
set HARDWARE_PRIMARY_I2C_BUS=1
set SPINDLE_TEMP_SENSOR_I2C_ADDRESS=0x38
set HARDWARE_SENSOR_CACHE_TTL_SEC=2.0
set RELAY_BOARD_ENABLED=1
set RELAY_BOARD_I2C_ADDRESS=0x52
set RELAY_BOARD_DEVICE_INDEX=1
set RELAY_BOARD_RESPONSE_TIMEOUT_SEC=0.75
```

The server listens on `http://localhost:8080` by default.

## Persisted Files

- `settings.json`: UI settings (`graphWindowSec`, light/fan settings, Wi-Fi, `axisVisibility`)
- `tasks.json`: maintenance tasks (`maintenanceTasks`)
- `machine_stats.json`: machine statistics (`spindleRuntimeSec`)
