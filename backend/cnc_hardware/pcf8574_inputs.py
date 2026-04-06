from __future__ import annotations

import copy
import threading
from datetime import datetime, timezone

from .i2c import I2CError, LinuxI2CDevice
from .sensors import HardwareError


def iso_now_utc():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class InputModuleUnavailableError(HardwareError):
    pass


class InputModuleReadError(HardwareError):
    pass


class PCF8574InputModule:
    CONTROLLER_ID = "pcf8574-inputs"
    DISPLAY_NAME = "8-Kanal-Optokoppler-Eingaenge"
    DEFAULT_ADDRESS = 0x21
    DEFAULT_ESTOP_CHANNELS = (1, 2)
    DEFAULT_SPINDLE_RUNNING_CHANNELS = (3,)
    PORT_WIDTH = 8
    INPUT_CONFIG_BYTE = 0xFF

    def __init__(
        self,
        bus_number=1,
        address=DEFAULT_ADDRESS,
        enabled=True,
        active_low=True,
        hardware_estop_channels=None,
        spindle_running_channels=None,
    ):
        self.bus_number = int(bus_number)
        self.address = int(address)
        self.enabled = bool(enabled)
        self.active_low = bool(active_low)
        self.hardware_estop_channels = self._normalize_channel_list(
            hardware_estop_channels if hardware_estop_channels is not None else self.DEFAULT_ESTOP_CHANNELS
        )
        self.spindle_running_channels = self._normalize_channel_list(
            spindle_running_channels if spindle_running_channels is not None else self.DEFAULT_SPINDLE_RUNNING_CHANNELS
        )
        self.device = LinuxI2CDevice(self.bus_number, self.address)
        self._lock = threading.Lock()
        self._last_snapshot = self._build_snapshot_base(
            available=False,
            status="disabled" if not self.enabled else "unknown",
            error="Eingangsmodul ist deaktiviert." if not self.enabled else "",
        )

    @property
    def device_path(self):
        return self.device.path

    def describe(self):
        return {
            "controllerId": self.CONTROLLER_ID,
            "displayName": self.DISPLAY_NAME,
            "interface": "i2c",
            "bus": self.bus_number,
            "devicePath": self.device_path,
            "address": self.address,
            "addressHex": f"0x{self.address:02x}",
            "activeLow": self.active_low,
            "hardwareEStopChannelIndexes": list(self.hardware_estop_channels),
            "hardwareEStopInputIds": [self._channel_id(index) for index in self.hardware_estop_channels],
            "spindleRunningChannelIndexes": list(self.spindle_running_channels),
            "spindleRunningInputIds": [self._channel_id(index) for index in self.spindle_running_channels],
        }

    def get_snapshot(self):
        with self._lock:
            return copy.deepcopy(self._last_snapshot)

    def read_snapshot(self):
        with self._lock:
            snapshot = self._read_snapshot_locked()
            self._last_snapshot = copy.deepcopy(snapshot)
            return copy.deepcopy(snapshot)

    def _read_snapshot_locked(self):
        if not self.enabled:
            return self._build_snapshot_base(
                available=False,
                status="disabled",
                error="Eingangsmodul ist deaktiviert.",
            )
        if not self.device.is_supported():
            return self._build_snapshot_base(
                available=False,
                status="unavailable",
                error="Linux-I2C ist in dieser Umgebung nicht verfuegbar.",
            )
        if not self.device.is_available():
            return self._build_snapshot_base(
                available=False,
                status="unavailable",
                error=f"I2C-Bus {self.device_path} ist nicht verfuegbar.",
            )

        measured_at = iso_now_utc()
        try:
            self.device.write((self.INPUT_CONFIG_BYTE,))
            raw_port = self.device.read(1)
        except I2CError as exc:
            return self._build_snapshot_base(
                available=False,
                status="error",
                error=str(exc),
                measured_at=measured_at,
            )

        if not raw_port:
            return self._build_snapshot_base(
                available=False,
                status="error",
                error="PCF8574 lieferte kein Datenbyte.",
                measured_at=measured_at,
            )

        raw_value = int(raw_port[0]) & 0xFF
        channels = {}
        triggered_inputs = []
        spindle_running_input_ids = []

        for index in range(1, self.PORT_WIDTH + 1):
            bit_high = bool(raw_value & (1 << (index - 1)))
            active = (not bit_high) if self.active_low else bit_high
            channel_id = self._channel_id(index)
            channels[channel_id] = {
                "id": channel_id,
                "index": index,
                "label": f"Input {index}",
                "active": active,
                "activeLow": self.active_low,
                "rawHigh": bit_high,
                "isHardwareEStop": index in self.hardware_estop_channels,
                "isSpindleRunning": index in self.spindle_running_channels,
            }
            if active and index in self.hardware_estop_channels:
                triggered_inputs.append(channel_id)
            if active and index in self.spindle_running_channels:
                spindle_running_input_ids.append(channel_id)

        return {
            **self._build_snapshot_base(
                available=True,
                status="ok",
                error="",
                measured_at=measured_at,
            ),
            "rawByte": raw_value,
            "rawByteHex": f"0x{raw_value:02x}",
            "channels": channels,
            "triggeredInputIds": triggered_inputs,
            "hardwareEStopEngaged": bool(triggered_inputs),
            "spindleRunningInputIds": spindle_running_input_ids,
            "spindleRunning": bool(spindle_running_input_ids),
        }

    def _build_snapshot_base(self, available, status, error, measured_at=None):
        measured_at_value = str(measured_at or iso_now_utc())
        base_snapshot = {
            **self.describe(),
            "available": bool(available),
            "status": str(status or "unknown"),
            "error": str(error or ""),
            "measuredAt": measured_at_value,
            "rawByte": None,
            "rawByteHex": "",
            "channels": {
                self._channel_id(index): {
                    "id": self._channel_id(index),
                    "index": index,
                    "label": f"Input {index}",
                    "active": False,
                    "activeLow": self.active_low,
                    "rawHigh": None,
                    "isHardwareEStop": index in self.hardware_estop_channels,
                    "isSpindleRunning": index in self.spindle_running_channels,
                }
                for index in range(1, self.PORT_WIDTH + 1)
            },
            "triggeredInputIds": [],
            "hardwareEStopEngaged": False,
            "spindleRunningInputIds": [],
            "spindleRunning": False,
        }
        return base_snapshot

    @staticmethod
    def _channel_id(index):
        return f"input{int(index)}"

    @staticmethod
    def _normalize_channel_list(values):
        normalized = []
        for raw_value in values if isinstance(values, (list, tuple, set)) else []:
            try:
                channel = int(raw_value)
            except (TypeError, ValueError):
                continue
            if 1 <= channel <= 8 and channel not in normalized:
                normalized.append(channel)
        return tuple(normalized) if normalized else tuple(PCF8574InputModule.DEFAULT_ESTOP_CHANNELS)
