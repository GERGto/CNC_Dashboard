from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone

from .duelink_relay import DuelinkI2CEngine, DuelinkRelayP4Controller
from .gpio_power import LinuxGPIOChipLineOutput
from .sensors import AHT20Sensor, HardwareError, INA228Sensor


def iso_now_utc():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_non_negative_float_env(name, default_value):
    raw_value = str(os.getenv(name, str(default_value))).strip()
    try:
        return max(0.0, float(raw_value))
    except ValueError:
        return float(default_value)


def _read_int_env(name, default_value):
    raw_value = str(os.getenv(name, str(default_value))).strip()
    try:
        return int(raw_value, 0)
    except ValueError:
        return int(default_value)


def _read_bool_env(name, default_value):
    raw_value = str(os.getenv(name, "1" if default_value else "0")).strip().lower()
    return raw_value in {"1", "true", "yes", "on"}


def _read_str_env(name, default_value):
    raw_value = os.getenv(name)
    if raw_value is None:
        return str(default_value)
    return str(raw_value).strip()


class HardwareBackend:
    def __init__(
        self,
        primary_i2c_bus=1,
        spindle_temperature_sensor=None,
        axis_load_sensors=None,
        relay_controller=None,
        relay_power_controller=None,
        cache_ttl_sec=2.0,
        axis_load_cache_ttl_sec=0.25,
        relay_startup_initialization_enabled=True,
        relay_startup_initialization_delay_sec=1.0,
        relay_startup_initialization_attempts=0,
        relay_startup_initialization_interval_sec=1.0,
        relay_light_on_after_startup=True,
        relay_power_off_delay_sec=0.25,
        relay_power_on_delay_sec=1.0,
    ):
        self.primary_i2c_bus = int(primary_i2c_bus)
        self.spindle_temperature_sensor = spindle_temperature_sensor or AHT20Sensor(
            bus_number=self.primary_i2c_bus
        )
        self.axis_load_sensors = {
            axis: axis_load_sensors.get(axis)
            for axis in ("x", "y", "z")
        } if isinstance(axis_load_sensors, dict) else {}
        self.relay_controller = relay_controller or DuelinkRelayP4Controller(bus_number=self.primary_i2c_bus)
        self.relay_power_controller = relay_power_controller
        self.cache_ttl_sec = max(0.0, float(cache_ttl_sec))
        self.axis_load_cache_ttl_sec = max(0.0, float(axis_load_cache_ttl_sec))
        self.relay_startup_initialization_enabled = bool(relay_startup_initialization_enabled)
        self.relay_startup_initialization_delay_sec = max(0.0, float(relay_startup_initialization_delay_sec))
        self.relay_startup_initialization_attempts = max(0, int(relay_startup_initialization_attempts))
        self.relay_startup_initialization_interval_sec = max(0.0, float(relay_startup_initialization_interval_sec))
        self.relay_light_on_after_startup = bool(relay_light_on_after_startup)
        self.relay_power_off_delay_sec = max(0.0, float(relay_power_off_delay_sec))
        self.relay_power_on_delay_sec = max(0.0, float(relay_power_on_delay_sec))
        self._lock = threading.Lock()
        self._relay_operation_lock = threading.Lock()
        self._spindle_temperature_cache = None
        self._spindle_temperature_cache_until = 0.0
        self._axis_load_cache = None
        self._axis_load_cache_until = 0.0

    def get_snapshot(self, force_refresh=False):
        spindle_temperature = self.get_spindle_temperature(force_refresh=force_refresh)
        axis_loads = self.get_axis_loads(force_refresh=force_refresh)
        relay_board = self.get_relay_board()
        return {
            "time": iso_now_utc(),
            "transport": {
                "primary": "i2c",
                "i2c": {
                    "bus": self.primary_i2c_bus,
                    "devicePath": spindle_temperature["devicePath"],
                    "relayBoardAddress": relay_board["address"],
                    "relayBoardAddressHex": relay_board["addressHex"],
                },
            },
            "sensors": {
                "spindleTemperature": spindle_temperature,
                "axisLoads": axis_loads,
            },
            "actuators": {
                "relayBoard": relay_board,
            },
        }

    def get_spindle_temperature(self, force_refresh=False):
        with self._lock:
            if (
                not force_refresh
                and self._spindle_temperature_cache is not None
                and time.monotonic() < self._spindle_temperature_cache_until
            ):
                return dict(self._spindle_temperature_cache)

        reading = self._read_spindle_temperature()

        with self._lock:
            self._spindle_temperature_cache = dict(reading)
            self._spindle_temperature_cache_until = time.monotonic() + self.cache_ttl_sec

        return dict(reading)

    def _read_spindle_temperature(self):
        base_payload = {
            "sensorId": "spindle-temperature",
            "displayName": "Spindeltemperatur",
            "role": "spindleTemperature",
            "available": False,
            "status": "unavailable",
            "error": "",
            "temperatureC": None,
            "humidityPercent": None,
            "measuredAt": None,
            "cacheTtlMs": int(round(self.cache_ttl_sec * 1000)),
            **self.spindle_temperature_sensor.describe(),
        }

        try:
            measurement = self.spindle_temperature_sensor.read_measurement()
        except HardwareError as exc:
            base_payload["error"] = str(exc)
            base_payload["measuredAt"] = iso_now_utc()
            return base_payload
        except Exception as exc:  # pragma: no cover - unexpected hardware edge case
            base_payload["error"] = f"Unerwarteter Hardwarefehler: {exc}"
            base_payload["measuredAt"] = iso_now_utc()
            return base_payload

        return {
            **base_payload,
            **measurement,
            "available": True,
            "status": "ok",
            "error": "",
        }

    def get_relay_board(self):
        return self.relay_controller.get_snapshot()

    def get_axis_loads(self, force_refresh=False):
        with self._lock:
            if (
                not force_refresh
                and self._axis_load_cache is not None
                and time.monotonic() < self._axis_load_cache_until
            ):
                return dict(self._axis_load_cache)

        reading = self._read_axis_loads()

        with self._lock:
            self._axis_load_cache = dict(reading)
            self._axis_load_cache_until = time.monotonic() + self.axis_load_cache_ttl_sec

        return dict(reading)

    def _read_axis_loads(self):
        axis_payloads = {}
        any_available = False

        for axis in ("x", "y", "z"):
            sensor = self.axis_load_sensors.get(axis)
            payload = {
                "sensorId": f"axis-load-{axis}",
                "displayName": f"{axis.upper()}-Achslast",
                "role": "axisLoad",
                "axis": axis,
                "available": False,
                "status": "unavailable",
                "error": "",
                "loadPercent": None,
                "currentA": None,
                "powerW": None,
                "busVoltageV": None,
                "shuntVoltageMv": None,
                "dieTemperatureC": None,
                "measuredAt": iso_now_utc(),
                "cacheTtlMs": int(round(self.axis_load_cache_ttl_sec * 1000)),
            }

            if sensor is None:
                payload["error"] = f"INA228 fuer Achse {axis.upper()} ist nicht konfiguriert."
                axis_payloads[axis] = payload
                continue

            payload.update(sensor.describe())
            try:
                measurement = sensor.read_measurement()
            except HardwareError as exc:
                payload["error"] = str(exc)
                axis_payloads[axis] = payload
                continue
            except Exception as exc:  # pragma: no cover - unexpected hardware edge case
                payload["error"] = f"Unerwarteter Hardwarefehler: {exc}"
                axis_payloads[axis] = payload
                continue

            payload.update(measurement)
            payload["available"] = True
            payload["status"] = "ok"
            payload["error"] = ""
            axis_payloads[axis] = payload
            any_available = True

        return {
            "sensorGroupId": "axis-loads",
            "displayName": "Achslasten",
            "available": any_available,
            "status": "ok" if any_available else "unavailable",
            "cacheTtlMs": int(round(self.axis_load_cache_ttl_sec * 1000)),
            "axes": axis_payloads,
        }

    def set_relay_output(self, output_id, enabled):
        with self._relay_operation_lock:
            channel = self.relay_controller.set_output(output_id, enabled)
        return {
            "channel": channel,
            "relayBoard": self.relay_controller.get_snapshot(),
        }

    def initialize_relay_board(self):
        with self._relay_operation_lock:
            return self.relay_controller.initialize()

    def initialize_relay_board_on_startup(self):
        if not self.relay_startup_initialization_enabled:
            print("Relay startup initialization skipped: disabled.")
            return False

        if self.relay_startup_initialization_delay_sec > 0:
            time.sleep(self.relay_startup_initialization_delay_sec)

        attempt_limit = self.relay_startup_initialization_attempts if self.relay_startup_initialization_attempts > 0 else None
        attempt = 0

        while True:
            attempt += 1
            attempt_label = (
                f"{attempt}/{attempt_limit}"
                if attempt_limit is not None
                else f"{attempt}/unbegrenzt"
            )
            try:
                with self._relay_operation_lock:
                    if self.relay_power_controller is not None:
                        self.relay_power_controller.power_cycle(
                            off_delay_sec=self.relay_power_off_delay_sec,
                            on_delay_sec=self.relay_power_on_delay_sec,
                        )
                    result = self.relay_controller.initialize()
                    if self.relay_light_on_after_startup:
                        light_channel = self.relay_controller.set_output("light", True)
                        result["lightChannel"] = light_channel
                print(
                    "Relay startup initialization succeeded "
                    f"(attempt {attempt_label}, "
                    f"driver {result.get('driverVersion', '<unbekannt>')})."
                )
                if self.relay_light_on_after_startup:
                    print("Relay startup default applied: machine light on.")
                return True
            except HardwareError as exc:
                print(
                    "Relay startup initialization failed "
                    f"(attempt {attempt_label}): {exc}"
                )
                if attempt_limit is not None and attempt >= attempt_limit:
                    return False
                time.sleep(self.relay_startup_initialization_interval_sec)


def create_hardware_backend():
    primary_i2c_bus = _read_int_env("HARDWARE_PRIMARY_I2C_BUS", 1)
    spindle_sensor_address = _read_int_env("SPINDLE_TEMP_SENSOR_I2C_ADDRESS", AHT20Sensor.DEFAULT_ADDRESS)
    axis_load_cache_ttl_sec = _read_non_negative_float_env("AXIS_LOAD_SENSOR_CACHE_TTL_SEC", 0.25)
    axis_load_sensor_defaults = {
        "x": {"address": 0x40},
        "y": {"address": 0x41},
        "z": {"address": 0x44},
    }
    relay_enabled = _read_bool_env("RELAY_BOARD_ENABLED", True)
    relay_address = _read_int_env("RELAY_BOARD_I2C_ADDRESS", DuelinkRelayP4Controller.DEFAULT_ADDRESS)
    relay_device_index = _read_int_env("RELAY_BOARD_DEVICE_INDEX", 1)
    relay_response_timeout_sec = _read_non_negative_float_env("RELAY_BOARD_RESPONSE_TIMEOUT_SEC", 0.75)
    relay_initialization_retry_window_sec = _read_non_negative_float_env(
        "RELAY_BOARD_INITIALIZATION_RETRY_WINDOW_SEC",
        DuelinkI2CEngine.INITIALIZATION_RETRY_WINDOW_SEC,
    )
    relay_initialization_retry_interval_sec = _read_non_negative_float_env(
        "RELAY_BOARD_INITIALIZATION_RETRY_INTERVAL_SEC",
        DuelinkI2CEngine.INITIALIZATION_RETRY_INTERVAL_SEC,
    )
    relay_initialization_response_timeout_sec = _read_non_negative_float_env(
        "RELAY_BOARD_INITIALIZATION_RESPONSE_TIMEOUT_SEC",
        DuelinkI2CEngine.INITIALIZATION_RESPONSE_TIMEOUT_SEC,
    )
    relay_startup_initialization_enabled = _read_bool_env("RELAY_BOARD_STARTUP_INITIALIZATION_ENABLED", True)
    relay_startup_initialization_delay_sec = _read_non_negative_float_env(
        "RELAY_BOARD_STARTUP_INITIALIZATION_DELAY_SEC",
        1.0,
    )
    relay_startup_initialization_attempts = max(0, _read_int_env("RELAY_BOARD_STARTUP_INITIALIZATION_ATTEMPTS", 0))
    relay_startup_initialization_interval_sec = _read_non_negative_float_env(
        "RELAY_BOARD_STARTUP_INITIALIZATION_INTERVAL_SEC",
        1.0,
    )
    relay_light_on_after_startup = _read_bool_env("RELAY_BOARD_LIGHT_ON_AFTER_STARTUP", True)
    relay_power_control_enabled = _read_bool_env("RELAY_BOARD_POWER_CONTROL_ENABLED", False)
    relay_power_gpio_chip = _read_str_env("RELAY_BOARD_POWER_GPIO_CHIP", "/dev/gpiochip0")
    relay_power_gpio_line_offset = _read_int_env("RELAY_BOARD_POWER_GPIO_LINE_OFFSET", 17)
    relay_power_active_high = _read_bool_env("RELAY_BOARD_POWER_ACTIVE_HIGH", True)
    relay_power_off_delay_sec = _read_non_negative_float_env("RELAY_BOARD_POWER_OFF_DELAY_SEC", 0.25)
    relay_power_on_delay_sec = _read_non_negative_float_env("RELAY_BOARD_POWER_ON_DELAY_SEC", 1.0)
    cache_ttl_sec = _read_non_negative_float_env("HARDWARE_SENSOR_CACHE_TTL_SEC", 2.0)
    spindle_temperature_sensor = AHT20Sensor(
        bus_number=primary_i2c_bus,
        address=spindle_sensor_address,
    )
    axis_load_sensors = {}
    for axis, defaults in axis_load_sensor_defaults.items():
        axis_upper = axis.upper()
        sensor_enabled = _read_bool_env(f"AXIS_LOAD_{axis_upper}_SENSOR_ENABLED", True)
        sensor_address = _read_int_env(
            f"AXIS_LOAD_{axis_upper}_SENSOR_I2C_ADDRESS",
            defaults["address"],
        )
        shunt_resistance_ohms = _read_non_negative_float_env(
            f"AXIS_LOAD_{axis_upper}_SHUNT_RESISTANCE_OHMS",
            INA228Sensor.DEFAULT_SHUNT_RESISTANCE_OHMS,
        )
        calibration_max_current_a = _read_non_negative_float_env(
            f"AXIS_LOAD_{axis_upper}_CALIBRATION_MAX_CURRENT_A",
            INA228Sensor.DEFAULT_CALIBRATION_MAX_CURRENT_A,
        )
        load_reference_current_a = _read_non_negative_float_env(
            f"AXIS_LOAD_{axis_upper}_REFERENCE_CURRENT_A",
            calibration_max_current_a,
        )
        axis_load_sensors[axis] = INA228Sensor(
            bus_number=primary_i2c_bus,
            address=sensor_address,
            axis=axis,
            shunt_resistance_ohms=shunt_resistance_ohms,
            calibration_max_current_a=calibration_max_current_a,
            load_reference_current_a=load_reference_current_a,
            enabled=sensor_enabled,
        )
    relay_controller = DuelinkRelayP4Controller(
        bus_number=primary_i2c_bus,
        address=relay_address,
        device_index=relay_device_index,
        response_timeout_sec=relay_response_timeout_sec,
        enabled=relay_enabled,
        initialization_retry_window_sec=relay_initialization_retry_window_sec,
        initialization_retry_interval_sec=relay_initialization_retry_interval_sec,
        initialization_response_timeout_sec=relay_initialization_response_timeout_sec,
    )
    relay_power_controller = None
    if relay_power_control_enabled:
        relay_power_controller = LinuxGPIOChipLineOutput(
            chip_path=relay_power_gpio_chip,
            line_offset=relay_power_gpio_line_offset,
            active_high=relay_power_active_high,
        )
    return HardwareBackend(
        primary_i2c_bus=primary_i2c_bus,
        spindle_temperature_sensor=spindle_temperature_sensor,
        axis_load_sensors=axis_load_sensors,
        relay_controller=relay_controller,
        relay_power_controller=relay_power_controller,
        cache_ttl_sec=cache_ttl_sec,
        axis_load_cache_ttl_sec=axis_load_cache_ttl_sec,
        relay_startup_initialization_enabled=relay_startup_initialization_enabled,
        relay_startup_initialization_delay_sec=relay_startup_initialization_delay_sec,
        relay_startup_initialization_attempts=relay_startup_initialization_attempts,
        relay_startup_initialization_interval_sec=relay_startup_initialization_interval_sec,
        relay_light_on_after_startup=relay_light_on_after_startup,
        relay_power_off_delay_sec=relay_power_off_delay_sec,
        relay_power_on_delay_sec=relay_power_on_delay_sec,
    )
