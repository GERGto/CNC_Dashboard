from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone

from .duelink_relay import DuelinkRelayP4Controller
from .sensors import AHT20Sensor, HardwareError


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


class HardwareBackend:
    def __init__(self, primary_i2c_bus=1, spindle_temperature_sensor=None, relay_controller=None, cache_ttl_sec=2.0):
        self.primary_i2c_bus = int(primary_i2c_bus)
        self.spindle_temperature_sensor = spindle_temperature_sensor or AHT20Sensor(
            bus_number=self.primary_i2c_bus
        )
        self.relay_controller = relay_controller or DuelinkRelayP4Controller(bus_number=self.primary_i2c_bus)
        self.cache_ttl_sec = max(0.0, float(cache_ttl_sec))
        self._lock = threading.Lock()
        self._spindle_temperature_cache = None
        self._spindle_temperature_cache_until = 0.0

    def get_snapshot(self, force_refresh=False):
        spindle_temperature = self.get_spindle_temperature(force_refresh=force_refresh)
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

    def set_relay_output(self, output_id, enabled):
        channel = self.relay_controller.set_output(output_id, enabled)
        return {
            "channel": channel,
            "relayBoard": self.relay_controller.get_snapshot(),
        }


def create_hardware_backend():
    primary_i2c_bus = _read_int_env("HARDWARE_PRIMARY_I2C_BUS", 1)
    spindle_sensor_address = _read_int_env("SPINDLE_TEMP_SENSOR_I2C_ADDRESS", AHT20Sensor.DEFAULT_ADDRESS)
    relay_enabled = _read_bool_env("RELAY_BOARD_ENABLED", True)
    relay_address = _read_int_env("RELAY_BOARD_I2C_ADDRESS", DuelinkRelayP4Controller.DEFAULT_ADDRESS)
    relay_device_index = _read_int_env("RELAY_BOARD_DEVICE_INDEX", 1)
    relay_response_timeout_sec = _read_non_negative_float_env("RELAY_BOARD_RESPONSE_TIMEOUT_SEC", 0.75)
    cache_ttl_sec = _read_non_negative_float_env("HARDWARE_SENSOR_CACHE_TTL_SEC", 2.0)
    spindle_temperature_sensor = AHT20Sensor(
        bus_number=primary_i2c_bus,
        address=spindle_sensor_address,
    )
    relay_controller = DuelinkRelayP4Controller(
        bus_number=primary_i2c_bus,
        address=relay_address,
        device_index=relay_device_index,
        response_timeout_sec=relay_response_timeout_sec,
        enabled=relay_enabled,
    )
    return HardwareBackend(
        primary_i2c_bus=primary_i2c_bus,
        spindle_temperature_sensor=spindle_temperature_sensor,
        relay_controller=relay_controller,
        cache_ttl_sec=cache_ttl_sec,
    )
