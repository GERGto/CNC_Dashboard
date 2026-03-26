from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from .i2c import I2CError, LinuxI2CDevice


def iso_now_utc():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class HardwareError(RuntimeError):
    pass


class SensorUnavailableError(HardwareError):
    pass


class SensorReadError(HardwareError):
    pass


def _crc8_msb(payload, polynomial=0x31, initial=0xFF):
    crc = int(initial) & 0xFF
    for byte in payload:
        crc ^= int(byte) & 0xFF
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ polynomial) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


class AHT20Sensor:
    DEFAULT_ADDRESS = 0x38
    STATUS_COMMAND = (0x71,)
    INIT_COMMAND = (0xE1, 0x28, 0x00)
    MEASURE_COMMAND = (0xAC, 0x33, 0x00)
    RESET_COMMAND = (0xBA,)
    STATUS_BUSY_MASK = 0x80
    STATUS_CALIBRATED_MASK = 0x08
    INIT_DELAY_SEC = 0.35
    MEASURE_DELAY_SEC = 0.08
    STATUS_POLL_INTERVAL_SEC = 0.01
    STATUS_POLL_TIMEOUT_SEC = 0.25
    FRAME_LENGTH = 7

    def __init__(self, bus_number=1, address=DEFAULT_ADDRESS):
        self.bus_number = int(bus_number)
        self.address = int(address)
        self.device = LinuxI2CDevice(self.bus_number, self.address)
        self._lock = threading.Lock()

    @property
    def device_path(self):
        return self.device.path

    def describe(self):
        return {
            "sensorType": "AHT20",
            "interface": "i2c",
            "bus": self.bus_number,
            "devicePath": self.device_path,
            "address": self.address,
            "addressHex": f"0x{self.address:02x}",
        }

    def read_measurement(self):
        with self._lock:
            return self._read_measurement_locked()

    def _read_measurement_locked(self):
        if not self.device.is_supported():
            raise SensorUnavailableError("Linux-I2C ist in dieser Umgebung nicht verfuegbar.")
        if not self.device.is_available():
            raise SensorUnavailableError(f"I2C-Bus {self.device_path} ist nicht verfuegbar.")

        status = self._wait_until_not_busy()
        if not status & self.STATUS_CALIBRATED_MASK:
            self.device.write(self.INIT_COMMAND)
            time.sleep(self.INIT_DELAY_SEC)
            status = self._wait_until_not_busy()
            if not status & self.STATUS_CALIBRATED_MASK:
                raise SensorReadError("AHT20 meldet sich nach der Initialisierung nicht als kalibriert.")

        self.device.write(self.MEASURE_COMMAND)
        time.sleep(self.MEASURE_DELAY_SEC)

        deadline = time.monotonic() + self.STATUS_POLL_TIMEOUT_SEC
        frame = b""
        while time.monotonic() <= deadline:
            frame = self.device.read(self.FRAME_LENGTH)
            if len(frame) != self.FRAME_LENGTH:
                raise SensorReadError(
                    f"AHT20 hat {len(frame)} statt {self.FRAME_LENGTH} Byte geliefert."
                )
            if not frame[0] & self.STATUS_BUSY_MASK:
                break
            time.sleep(self.STATUS_POLL_INTERVAL_SEC)
        else:
            raise SensorReadError("AHT20-Messung blieb zu lange im Busy-Zustand.")

        expected_crc = frame[-1]
        calculated_crc = _crc8_msb(frame[:-1])
        if calculated_crc != expected_crc:
            raise SensorReadError(
                f"AHT20-CRC ungueltig: erwartet 0x{expected_crc:02x}, berechnet 0x{calculated_crc:02x}."
            )

        humidity_raw = (frame[1] << 12) | (frame[2] << 4) | ((frame[3] & 0xF0) >> 4)
        temperature_raw = ((frame[3] & 0x0F) << 16) | (frame[4] << 8) | frame[5]
        humidity_percent = max(0.0, min(100.0, (humidity_raw * 100.0) / 1048576.0))
        temperature_c = ((temperature_raw * 200.0) / 1048576.0) - 50.0

        return {
            "measuredAt": iso_now_utc(),
            "temperatureC": round(temperature_c, 2),
            "humidityPercent": round(humidity_percent, 2),
            "statusByte": f"0x{frame[0]:02x}",
            "rawBytes": [int(byte) for byte in frame],
        }

    def _wait_until_not_busy(self):
        deadline = time.monotonic() + self.STATUS_POLL_TIMEOUT_SEC
        last_status = None
        while time.monotonic() <= deadline:
            status = self._read_status()
            last_status = status
            if not status & self.STATUS_BUSY_MASK:
                return status
            time.sleep(self.STATUS_POLL_INTERVAL_SEC)

        if last_status is None:
            raise SensorReadError("AHT20-Status konnte nicht gelesen werden.")
        raise SensorReadError(f"AHT20 blieb busy (letzter Status: 0x{last_status:02x}).")

    def _read_status(self):
        try:
            self.device.write(self.STATUS_COMMAND)
            data = self.device.read(1)
        except I2CError as exc:
            raise SensorReadError(str(exc)) from exc

        if len(data) != 1:
            raise SensorReadError(f"AHT20-Status lieferte {len(data)} statt 1 Byte.")
        return data[0]
