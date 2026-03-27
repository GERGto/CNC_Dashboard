from __future__ import annotations

import os
import threading
import time

try:
    import gpiod
    from gpiod.line import Direction, Value
except ImportError:  # pragma: no cover - Windows development environment
    gpiod = None
    Direction = None
    Value = None

from .sensors import HardwareError


class GPIOPowerError(HardwareError):
    pass


class LinuxGPIOChipLineOutput:
    def __init__(
        self,
        chip_path="/dev/gpiochip0",
        line_offset=17,
        active_high=True,
        consumer_label="cnc-dashboard-relay-power",
    ):
        self.chip_path = str(chip_path)
        self.line_offset = int(line_offset)
        self.active_high = bool(active_high)
        self.consumer_label = str(consumer_label)
        self._lock = threading.Lock()
        self._request = None
        self._enabled = False

    def is_supported(self):
        return os.name == "posix" and gpiod is not None and Direction is not None and Value is not None

    def is_available(self):
        return self.is_supported() and os.path.exists(self.chip_path)

    def describe(self):
        return {
            "interface": "gpiochip",
            "chipPath": self.chip_path,
            "lineOffset": self.line_offset,
            "activeHigh": self.active_high,
            "consumerLabel": self.consumer_label,
            "enabled": bool(self._enabled),
        }

    def set_enabled(self, enabled):
        with self._lock:
            self._ensure_requested_locked(initial_enabled=enabled)
            self._request.set_value(self.line_offset, self._physical_value(enabled))
            self._enabled = bool(enabled)

    def power_cycle(self, off_delay_sec=0.25, on_delay_sec=1.0):
        self.set_enabled(False)
        if off_delay_sec > 0:
            time.sleep(max(0.0, float(off_delay_sec)))
        self.set_enabled(True)
        if on_delay_sec > 0:
            time.sleep(max(0.0, float(on_delay_sec)))

    def close(self):
        with self._lock:
            if self._request is not None:
                self._request.release()
                self._request = None

    def _ensure_requested_locked(self, initial_enabled):
        if self._request is not None:
            return
        if not self.is_supported():
            raise GPIOPowerError("GPIO-Steuerung ueber libgpiod ist in dieser Umgebung nicht verfuegbar.")
        if not self.is_available():
            raise GPIOPowerError(f"GPIO-Chip ist nicht verfuegbar: {self.chip_path}")

        try:
            settings = gpiod.LineSettings(
                direction=Direction.OUTPUT,
                output_value=self._physical_value(initial_enabled),
            )
            self._request = gpiod.request_lines(
                self.chip_path,
                consumer=self.consumer_label,
                config={self.line_offset: settings},
            )
            self._enabled = bool(initial_enabled)
        except OSError as exc:
            raise GPIOPowerError(
                f"GPIO-Zugriff auf {self.chip_path} fuer Line {self.line_offset} fehlgeschlagen: {exc}"
            ) from exc

    def _physical_value(self, enabled):
        logical_enabled = bool(enabled)
        active = logical_enabled == self.active_high
        return Value.ACTIVE if active else Value.INACTIVE

    def __del__(self):  # pragma: no cover - best effort cleanup only
        try:
            self.close()
        except Exception:
            pass
