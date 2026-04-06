# Hardware API (dev)

This backend provides a simple HTTP + SSE API for Raspberry Pi hardware control
and streaming axis/spindle load values. The spindle value is currently still
mocked, while `X/Y/Z` can be backed by INA228 current sensors.

## Endpoints

- GET `/api/health`
  - `{ status: "ok", time: "<iso>" }`
- GET `/api/axes`
  - `{ timestamp, axes: { spindle, x, y, z }, axisLoadSensors }`
- GET `/api/axes/stream` (SSE)
  - `event: axes` with `{ timestamp, axes: { spindle, x, y, z }, axisLoadSensors }` every ~250 ms
  - Optional query: `?intervalMs=250`
- GET `/api/hardware`
  - `{ time, transport: { primary, i2c }, sensors: { spindleTemperature, axisLoads }, actuators: { relayBoard, statusIndicator }, machineStatus }`
  - Optional query: `?refresh=1`
- GET `/api/hardware/spindle-temperature`
  - `{ sensorId, sensorType, available, temperatureC, humidityPercent, measuredAt, ... }`
  - Optional query: `?refresh=1`
- GET `/api/hardware/axis-loads`
  - `{ sensorGroupId, available, axes: { x, y, z }, ... }`
  - Optional query: `?refresh=1`
- GET `/api/hardware/relays`
  - `{ controllerId, status, addressHex, channels, ... }`
- GET `/api/machine/status`
  - `{ reportedStatus, maintenanceDue, eStopEngaged, effectiveStatus, indicator }`
- POST `/api/machine/status`
  - Request: `{ status: "IDLE"|"RUNNING"|"ERROR", source?: "<name>" }`
  - Response: current effective machine status with LED mapping
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
- On first contact after board power-up, the backend sends an empty DUELink command and retries briefly before the real relay command.
- On backend startup, a background warmup initializes the relay board before the first frontend action.
- Optional: the backend can power-cycle the relay board on startup through a GPIO-controlled 3.3V feed.
- After a successful startup initialization, the backend can automatically switch the machine light on.
- Channel mapping:
  - `1`: machine light
  - `2`: spindle fan
  - `3`: E-Stop
  - `4`: spare

## Status Indicator

The project is now prepared for a `WS2812B` RGB strip as a machine status indicator.

- Supply: `5V`
- Data pin: `GPIO18`
- Current strip length: `76` LEDs
- Startup sequence:
  - blue expansion from the center to the outside
  - once the strip is fully blue, the machine light is switched on
  - the strip then fades from blue to white for the system check
- Shutdown sequence:
  - on frontend-triggered shutdown, the current strip image collapses quickly from the outside to the center
  - exactly when the strip turns fully off, the machine light is switched off
- Idle behavior:
  - `IDLE` uses slow moving white waves instead of static white
  - each pixel moves between `RGB 28` and `127`
  - phase offset per pixel: `0.12`
  - frame phase step: `0.012` at about `60 FPS`
- Effective color mapping after startup:
  - `white`: idle / machine on
  - `orange`: warning / maintenance due
  - `green`: job or spindle running
  - `red`: E-Stop active with repeated double pulses over a continuous red base
- Effective priority:
  - `E-Stop > maintenance due > RUNNING > IDLE`
- Backend driver:
  - `backend/cnc_hardware/neopixel.py`
- The backend keeps running on non-Pi dev systems and reports the strip as unavailable when `rpi_ws281x` is missing.

## Axis Load Sensors

The project is prepared for three `Adafruit INA228` current/power monitors.

- Bus: `/dev/i2c-1`
- Verified live:
  - `X`: `0x40`
- Backend defaults prepared for:
  - `Y`: `0x41`
  - `Z`: `0x44`
- The backend reads `currentA`, `powerW`, `busVoltageV`, `shuntVoltageMv` and `dieTemperatureC`.
- For the current frontend graph, the measured current is normalized into `loadPercent`.

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
set AXIS_LOAD_SENSOR_CACHE_TTL_SEC=0.25
set AXIS_LOAD_X_SENSOR_ENABLED=1
set AXIS_LOAD_X_SENSOR_I2C_ADDRESS=0x40
set AXIS_LOAD_X_SHUNT_RESISTANCE_OHMS=0.015
set AXIS_LOAD_X_CALIBRATION_MAX_CURRENT_A=10.0
set AXIS_LOAD_X_REFERENCE_CURRENT_A=10.0
set AXIS_LOAD_Y_SENSOR_ENABLED=1
set AXIS_LOAD_Y_SENSOR_I2C_ADDRESS=0x41
set AXIS_LOAD_Y_SHUNT_RESISTANCE_OHMS=0.015
set AXIS_LOAD_Y_CALIBRATION_MAX_CURRENT_A=10.0
set AXIS_LOAD_Y_REFERENCE_CURRENT_A=10.0
set AXIS_LOAD_Z_SENSOR_ENABLED=1
set AXIS_LOAD_Z_SENSOR_I2C_ADDRESS=0x44
set AXIS_LOAD_Z_SHUNT_RESISTANCE_OHMS=0.015
set AXIS_LOAD_Z_CALIBRATION_MAX_CURRENT_A=10.0
set AXIS_LOAD_Z_REFERENCE_CURRENT_A=10.0
set RELAY_BOARD_ENABLED=1
set RELAY_BOARD_I2C_ADDRESS=0x52
set RELAY_BOARD_DEVICE_INDEX=1
set RELAY_BOARD_RESPONSE_TIMEOUT_SEC=0.75
set RELAY_BOARD_INITIALIZATION_RETRY_WINDOW_SEC=1.5
set RELAY_BOARD_INITIALIZATION_RETRY_INTERVAL_SEC=0.05
set RELAY_BOARD_INITIALIZATION_RESPONSE_TIMEOUT_SEC=0.15
set RELAY_BOARD_STARTUP_INITIALIZATION_ENABLED=1
set RELAY_BOARD_STARTUP_INITIALIZATION_DELAY_SEC=1.0
set RELAY_BOARD_STARTUP_INITIALIZATION_ATTEMPTS=0
set RELAY_BOARD_STARTUP_INITIALIZATION_INTERVAL_SEC=1.0
set RELAY_BOARD_LIGHT_ON_AFTER_STARTUP=1
set RELAY_BOARD_POWER_CONTROL_ENABLED=0
set RELAY_BOARD_POWER_GPIO_CHIP=/dev/gpiochip0
set RELAY_BOARD_POWER_GPIO_LINE_OFFSET=17
set RELAY_BOARD_POWER_ACTIVE_HIGH=1
set RELAY_BOARD_POWER_OFF_DELAY_SEC=0.25
set RELAY_BOARD_POWER_ON_DELAY_SEC=1.0
set STATUS_INDICATOR_ENABLED=1
set STATUS_INDICATOR_LED_COUNT=76
set STATUS_INDICATOR_GPIO_PIN=18
set STATUS_INDICATOR_FREQUENCY_HZ=800000
set STATUS_INDICATOR_DMA_CHANNEL=10
set STATUS_INDICATOR_PWM_CHANNEL=0
set STATUS_INDICATOR_BRIGHTNESS=255
set STATUS_INDICATOR_INVERT=0
set STATUS_INDICATOR_STRIP_TYPE=GRB
set STATUS_INDICATOR_SYNC_INTERVAL_SEC=2.0
```

The server listens on `http://localhost:8080` by default.

## Persisted Files

- `settings.json`: UI settings (`graphWindowSec`, light/fan settings, Wi-Fi, `axisVisibility`)
- `tasks.json`: maintenance tasks (`maintenanceTasks`)
- `machine_stats.json`: machine statistics (`spindleRuntimeSec`)
