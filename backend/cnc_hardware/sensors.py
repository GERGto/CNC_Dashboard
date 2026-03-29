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


def _sign_extend(value, bits):
    sign_bit = 1 << (int(bits) - 1)
    full_scale = 1 << int(bits)
    value = int(value)
    return value - full_scale if value & sign_bit else value


class INA228Sensor:
    DEFAULT_ADDRESS = 0x40
    DEFAULT_SHUNT_RESISTANCE_OHMS = 0.015
    DEFAULT_CALIBRATION_MAX_CURRENT_A = 10.0
    DEFAULT_LOAD_REFERENCE_CURRENT_A = 10.0

    REG_CONFIG = 0x00
    REG_ADCCFG = 0x01
    REG_SHUNTCAL = 0x02
    REG_VSHUNT = 0x04
    REG_VBUS = 0x05
    REG_DIETEMP = 0x06
    REG_CURRENT = 0x07
    REG_POWER = 0x08
    REG_MANUFACTURER_ID = 0x3E
    REG_DEVICE_ID = 0x3F

    MODE_CONTINUOUS = 0x0F
    ADC_RANGE_HIGH = 0x00
    AVG_COUNT_16 = 0x02
    CONV_TIME_150_US = 0x02
    CONV_TIME_280_US = 0x03

    EXPECTED_MANUFACTURER_ID = 0x5449
    EXPECTED_DEVICE_ID = 0x228

    CURRENT_LSB_DIVISOR = 1 << 19
    SHUNT_CAL_SCALE = 13107.2 * 1000000.0
    BUS_VOLTAGE_LSB_V = 195.3125e-6
    SHUNT_VOLTAGE_LSB_RANGE0_V = 312.5e-9
    SHUNT_VOLTAGE_LSB_RANGE1_V = 78.125e-9
    DIE_TEMPERATURE_LSB_C = 7.8125e-3
    POWER_LSB_MULTIPLIER = 3.2
    CONFIGURE_SETTLE_SEC = 0.002

    def __init__(
        self,
        bus_number=1,
        address=DEFAULT_ADDRESS,
        axis="x",
        shunt_resistance_ohms=DEFAULT_SHUNT_RESISTANCE_OHMS,
        calibration_max_current_a=DEFAULT_CALIBRATION_MAX_CURRENT_A,
        load_reference_current_a=DEFAULT_LOAD_REFERENCE_CURRENT_A,
        enabled=True,
    ):
        self.bus_number = int(bus_number)
        self.address = int(address)
        self.axis = str(axis or "").strip().lower() or "x"
        self.enabled = bool(enabled)
        self.device = LinuxI2CDevice(self.bus_number, self.address)
        self.shunt_resistance_ohms = max(1e-9, float(shunt_resistance_ohms))
        self.calibration_max_current_a = max(1e-6, float(calibration_max_current_a))
        self.load_reference_current_a = max(1e-6, float(load_reference_current_a))
        self._lock = threading.Lock()
        self._configured = False
        self._current_lsb = self.calibration_max_current_a / self.CURRENT_LSB_DIVISOR
        self._adc_range = self.ADC_RANGE_HIGH

    @property
    def device_path(self):
        return self.device.path

    def describe(self):
        return {
            "sensorType": "INA228",
            "interface": "i2c",
            "bus": self.bus_number,
            "devicePath": self.device_path,
            "address": self.address,
            "addressHex": f"0x{self.address:02x}",
            "axis": self.axis,
            "shuntResistanceOhms": round(self.shunt_resistance_ohms, 6),
            "calibrationMaxCurrentA": round(self.calibration_max_current_a, 3),
            "loadReferenceCurrentA": round(self.load_reference_current_a, 3),
        }

    def read_measurement(self):
        with self._lock:
            return self._read_measurement_locked()

    def _read_measurement_locked(self):
        if not self.enabled:
            raise SensorUnavailableError(f"INA228 fuer Achse {self.axis.upper()} ist deaktiviert.")
        if not self.device.is_supported():
            raise SensorUnavailableError("Linux-I2C ist in dieser Umgebung nicht verfuegbar.")
        if not self.device.is_available():
            raise SensorUnavailableError(f"I2C-Bus {self.device_path} ist nicht verfuegbar.")

        self._ensure_configured_locked()

        raw_bus_voltage = self._read_u24(self.REG_VBUS)
        raw_shunt_voltage = self._read_s24(self.REG_VSHUNT)
        raw_current = self._read_s24(self.REG_CURRENT)
        raw_power = self._read_u24(self.REG_POWER)
        raw_die_temperature = self._read_s16(self.REG_DIETEMP)

        bus_voltage_v = (raw_bus_voltage >> 4) * self.BUS_VOLTAGE_LSB_V
        shunt_lsb_v = (
            self.SHUNT_VOLTAGE_LSB_RANGE1_V
            if self._adc_range
            else self.SHUNT_VOLTAGE_LSB_RANGE0_V
        )
        shunt_voltage_v = (raw_shunt_voltage / 16.0) * shunt_lsb_v
        current_a = (raw_current / 16.0) * self._current_lsb
        power_w = raw_power * self.POWER_LSB_MULTIPLIER * self._current_lsb
        die_temperature_c = raw_die_temperature * self.DIE_TEMPERATURE_LSB_C
        load_percent = min(
            100.0,
            max(0.0, (abs(current_a) / self.load_reference_current_a) * 100.0),
        )

        return {
            "measuredAt": iso_now_utc(),
            "loadPercent": round(load_percent, 2),
            "currentA": round(current_a, 4),
            "powerW": round(power_w, 4),
            "busVoltageV": round(bus_voltage_v, 4),
            "shuntVoltageMv": round(shunt_voltage_v * 1000.0, 4),
            "dieTemperatureC": round(die_temperature_c, 3),
        }

    def _ensure_configured_locked(self):
        if self._configured:
            return

        try:
            manufacturer_id = self._read_u16(self.REG_MANUFACTURER_ID)
            device_id_raw = self._read_u16(self.REG_DEVICE_ID)
        except I2CError as exc:
            raise SensorReadError(str(exc)) from exc

        device_id = (device_id_raw >> 4) & 0x0FFF
        if manufacturer_id != self.EXPECTED_MANUFACTURER_ID:
            raise SensorReadError(
                f"INA228 Hersteller-ID ungueltig: 0x{manufacturer_id:04x}."
            )
        if device_id != self.EXPECTED_DEVICE_ID:
            raise SensorReadError(
                f"INA228 Device-ID ungueltig: 0x{device_id:03x}."
            )

        adc_config = (
            (self.MODE_CONTINUOUS << 12)
            | (self.CONV_TIME_150_US << 9)
            | (self.CONV_TIME_280_US << 6)
            | (self.CONV_TIME_150_US << 3)
            | self.AVG_COUNT_16
        )
        calibration_value = int(
            self.SHUNT_CAL_SCALE
            * self.shunt_resistance_ohms
            * self._current_lsb
        )

        try:
            self._write_u16(self.REG_CONFIG, self._adc_range << 4)
            self._write_u16(self.REG_ADCCFG, adc_config)
            self._write_u16(self.REG_SHUNTCAL, calibration_value)
        except I2CError as exc:
            raise SensorReadError(str(exc)) from exc

        time.sleep(self.CONFIGURE_SETTLE_SEC)
        self._configured = True

    def _write_u16(self, register, value):
        self.device.transfer(
            write_bytes=(
                int(register) & 0xFF,
                (int(value) >> 8) & 0xFF,
                int(value) & 0xFF,
            )
        )

    def _read_u16(self, register):
        data = self.device.transfer(write_bytes=(int(register) & 0xFF,), read_length=2)
        if len(data) != 2:
            raise I2CError(f"INA228-Register 0x{int(register):02x} lieferte {len(data)} statt 2 Byte.")
        return (data[0] << 8) | data[1]

    def _read_s16(self, register):
        return _sign_extend(self._read_u16(register), 16)

    def _read_u24(self, register):
        data = self.device.transfer(write_bytes=(int(register) & 0xFF,), read_length=3)
        if len(data) != 3:
            raise I2CError(f"INA228-Register 0x{int(register):02x} lieferte {len(data)} statt 3 Byte.")
        return (data[0] << 16) | (data[1] << 8) | data[2]

    def _read_s24(self, register):
        return _sign_extend(self._read_u24(register), 24)
