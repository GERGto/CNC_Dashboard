from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from .i2c import I2CError, LinuxI2CDevice
from .sensors import HardwareError


def iso_now_utc():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class RelayUnavailableError(HardwareError):
    pass


class RelayCommandError(HardwareError):
    pass


class DuelinkI2CEngine:
    DEFAULT_ADDRESS = 0x52
    DEFAULT_DEVICE_INDEX = 1
    FLUSH_READ_SIZE = 64
    READ_CHUNK_SIZE = 32
    POLL_INTERVAL_SEC = 0.01
    INITIALIZATION_RETRY_WINDOW_SEC = 1.5
    INITIALIZATION_RETRY_INTERVAL_SEC = 0.05
    INITIALIZATION_RESPONSE_TIMEOUT_SEC = 0.15

    def __init__(
        self,
        bus_number=1,
        address=DEFAULT_ADDRESS,
        device_index=DEFAULT_DEVICE_INDEX,
        response_timeout_sec=1.0,
        read_chunk_size=READ_CHUNK_SIZE,
        initialization_retry_window_sec=INITIALIZATION_RETRY_WINDOW_SEC,
        initialization_retry_interval_sec=INITIALIZATION_RETRY_INTERVAL_SEC,
        initialization_response_timeout_sec=INITIALIZATION_RESPONSE_TIMEOUT_SEC,
    ):
        self.bus_number = int(bus_number)
        self.address = int(address)
        self.device_index = int(device_index)
        self.response_timeout_sec = max(0.05, float(response_timeout_sec))
        self.read_chunk_size = max(1, int(read_chunk_size))
        self.initialization_retry_window_sec = max(0.0, float(initialization_retry_window_sec))
        self.initialization_retry_interval_sec = max(0.0, float(initialization_retry_interval_sec))
        self.initialization_response_timeout_sec = max(0.01, float(initialization_response_timeout_sec))
        self.device = LinuxI2CDevice(self.bus_number, self.address)
        self._lock = threading.Lock()
        self._initialized = False

    @property
    def device_path(self):
        return self.device.path

    def describe(self):
        return {
            "interface": "i2c",
            "protocol": "duelink-daisylink",
            "bus": self.bus_number,
            "devicePath": self.device_path,
            "address": self.address,
            "addressHex": f"0x{self.address:02x}",
            "deviceIndex": self.device_index,
        }

    def is_supported(self):
        return self.device.is_supported()

    def is_bus_available(self):
        return self.device.is_available()

    def execute_command(self, command, select_device=True):
        with self._lock:
            return self._execute_command_with_recovery_locked(str(command or "").strip(), select_device=select_device)

    def initialize(self):
        with self._lock:
            return self._initialize_locked()

    def _initialize_locked(self):
        self._ensure_ready()
        deadline = time.monotonic() + self.initialization_retry_window_sec

        while True:
            try:
                self._prime_interface_locked(deadline)
                if self.device_index > 0:
                    self._exchange_command_locked(f"sel({self.device_index})")
                driver_version = self._exchange_command_locked("DVer()")
                self._initialized = True
                return driver_version
            except RelayCommandError:
                self._initialized = False
                if time.monotonic() >= deadline:
                    raise
                time.sleep(self.initialization_retry_interval_sec)

    def _execute_command_with_recovery_locked(self, command, select_device=True):
        self._ensure_ready()
        if not command:
            raise RelayCommandError("Leerer Relaisbefehl ist nicht erlaubt.")

        deadline = time.monotonic() + self.initialization_retry_window_sec
        while True:
            try:
                if not self._initialized:
                    self._prime_interface_locked(deadline)
                return self._execute_command_locked(command, select_device=select_device)
            except RelayCommandError:
                self._initialized = False
                if time.monotonic() >= deadline:
                    raise
                time.sleep(self.initialization_retry_interval_sec)

    def _execute_command_locked(self, command, select_device=True):
        if select_device:
            self._exchange_command_locked(f"sel({self.device_index})")

        response = self._exchange_command_locked(command)
        self._initialized = True
        return response

    def _ensure_ready(self):
        if not self.device.is_supported():
            raise RelayUnavailableError("Linux-I2C ist in dieser Umgebung nicht verfuegbar.")
        if not self.device.is_available():
            raise RelayUnavailableError(f"I2C-Bus {self.device_path} ist nicht verfuegbar.")

    def _prime_interface_locked(self, deadline):
        last_error = None

        while True:
            try:
                self._exchange_command_locked("", response_timeout_sec=self.initialization_response_timeout_sec)
                self._initialized = True
                return
            except RelayCommandError as exc:
                last_error = exc
                if time.monotonic() >= deadline:
                    break
                time.sleep(self.initialization_retry_interval_sec)

        if last_error is None:
            last_error = RelayCommandError("Unbekannter DUELink-Initialisierungsfehler.")
        raise RelayCommandError(
            f"DUELink-Initialisierung auf {self.device_path} an Adresse 0x{self.address:02x} fehlgeschlagen: "
            f"{last_error}"
        ) from last_error

    def _exchange_command_locked(self, command, response_timeout_sec=None):
        self._write_command_locked(command)
        return self._read_response_locked(response_timeout_sec=response_timeout_sec)

    def _write_command_locked(self, command):
        try:
            try:
                self.device.read(self.FLUSH_READ_SIZE)
            except I2CError:
                # On a cold boot the board may not have buffered response bytes yet.
                # Treat the pre-write flush as best-effort so the actual command can
                # still be sent.
                pass
            self.device.write(command.encode("utf-8") + b"\n")
        except I2CError as exc:
            raise RelayCommandError(str(exc)) from exc

    def _read_response_locked(self, response_timeout_sec=None):
        timeout_sec = self.response_timeout_sec if response_timeout_sec is None else max(0.01, float(response_timeout_sec))
        deadline = time.monotonic() + timeout_sec
        response = bytearray()

        while time.monotonic() <= deadline:
            try:
                chunk = self.device.read(self.read_chunk_size)
            except I2CError as exc:
                raise RelayCommandError(str(exc)) from exc

            if chunk:
                for byte in chunk:
                    if byte != 0xFF:
                        response.append(byte)

                if self._ends_with_prompt(response):
                    payload = bytes(response[:-3]).decode("utf-8", errors="replace").strip()
                    return payload

            time.sleep(self.POLL_INTERVAL_SEC)

        raise RelayCommandError(
            f"Zeitueberschreitung beim Warten auf eine Antwort von {self.device_path} "
            f"an Adresse 0x{self.address:02x}."
        )

    @staticmethod
    def _ends_with_prompt(response):
        if len(response) < 3:
            return False
        return response[-3] == 13 and response[-2] == 10 and response[-1] in {36, 62}


class DuelinkRelayP4Controller:
    CONTROLLER_ID = "gdl-acrelayp4-c"
    DISPLAY_NAME = "4-Kanal-Relais"
    DEFAULT_ADDRESS = DuelinkI2CEngine.DEFAULT_ADDRESS
    CHANNELS = {
        "light": {
            "channel": 1,
            "label": "Maschinenlicht",
            "endpoint": "/api/hardware/light",
        },
        "fan": {
            "channel": 2,
            "label": "Spindelluefter",
            "endpoint": "/api/hardware/fan",
        },
        "eStop": {
            "channel": 3,
            "label": "E-Stop",
            "endpoint": "/api/hardware/e-stop",
        },
        "relay4": {
            "channel": 4,
            "label": "Relais 4",
            "endpoint": "/api/hardware/relay-4",
        },
    }

    def __init__(
        self,
        bus_number=1,
        address=DuelinkI2CEngine.DEFAULT_ADDRESS,
        device_index=1,
        response_timeout_sec=1.0,
        enabled=True,
        initialization_retry_window_sec=DuelinkI2CEngine.INITIALIZATION_RETRY_WINDOW_SEC,
        initialization_retry_interval_sec=DuelinkI2CEngine.INITIALIZATION_RETRY_INTERVAL_SEC,
        initialization_response_timeout_sec=DuelinkI2CEngine.INITIALIZATION_RESPONSE_TIMEOUT_SEC,
    ):
        self.enabled = bool(enabled)
        self.engine = DuelinkI2CEngine(
            bus_number=bus_number,
            address=address,
            device_index=device_index,
            response_timeout_sec=response_timeout_sec,
            initialization_retry_window_sec=initialization_retry_window_sec,
            initialization_retry_interval_sec=initialization_retry_interval_sec,
            initialization_response_timeout_sec=initialization_response_timeout_sec,
        )
        self._lock = threading.Lock()
        self._states = {channel_id: False for channel_id in self.CHANNELS}
        self._last_command_at = None
        self._last_success_at = None
        self._last_error = ""

    def get_snapshot(self):
        with self._lock:
            states = dict(self._states)
            last_command_at = self._last_command_at
            last_success_at = self._last_success_at
            last_error = self._last_error

        if not self.enabled:
            available = False
            status = "disabled"
            error = "Relaisboard ist per RELAY_BOARD_ENABLED deaktiviert."
        elif not self.engine.is_supported():
            available = False
            status = "unavailable"
            error = "Linux-I2C ist in dieser Umgebung nicht verfuegbar."
        elif not self.engine.is_bus_available():
            available = False
            status = "unavailable"
            error = f"I2C-Bus {self.engine.device_path} ist nicht verfuegbar."
        elif last_success_at:
            available = True
            status = "ok"
            error = ""
        elif last_error:
            available = False
            status = "error"
            error = last_error
        else:
            available = False
            status = "unknown"
            error = ""

        return {
            "controllerId": self.CONTROLLER_ID,
            "displayName": self.DISPLAY_NAME,
            "available": available,
            "status": status,
            "error": error,
            "lastCommandAt": last_command_at,
            "lastSuccessAt": last_success_at,
            **self.engine.describe(),
            "channels": {
                channel_id: self._build_channel_snapshot(channel_id, states[channel_id], available)
                for channel_id in self.CHANNELS
            },
        }

    def initialize(self):
        if not self.enabled:
            raise RelayUnavailableError("Relaisboard ist per RELAY_BOARD_ENABLED deaktiviert.")

        command_at = iso_now_utc()
        try:
            driver_version = self.engine.initialize()
        except HardwareError as exc:
            with self._lock:
                self._last_command_at = command_at
                self._last_error = str(exc)
            raise

        with self._lock:
            self._last_command_at = command_at
            self._last_success_at = command_at
            self._last_error = ""

        return {
            "driverVersion": driver_version,
            "relayBoard": self.get_snapshot(),
        }

    def set_output(self, output_id, enabled):
        output_id = self._normalize_output_id(output_id)
        if not self.enabled:
            raise RelayUnavailableError("Relaisboard ist per RELAY_BOARD_ENABLED deaktiviert.")
        channel_number = self.CHANNELS[output_id]["channel"]
        command = f"Set({channel_number},{1 if enabled else 0})"

        command_at = iso_now_utc()
        try:
            self.engine.execute_command(command)
        except HardwareError as exc:
            with self._lock:
                self._last_command_at = command_at
                self._last_error = str(exc)
            raise

        with self._lock:
            self._states[output_id] = bool(enabled)
            self._last_command_at = command_at
            self._last_success_at = command_at
            self._last_error = ""

        return self.get_channel_snapshot(output_id)

    def get_channel_snapshot(self, output_id):
        output_id = self._normalize_output_id(output_id)
        snapshot = self.get_snapshot()
        return dict(snapshot["channels"][output_id])

    def _normalize_output_id(self, output_id):
        key = str(output_id or "").strip()
        aliases = {
            "light": "light",
            "fan": "fan",
            "estop": "eStop",
            "e-stop": "eStop",
            "relay4": "relay4",
            "relay-4": "relay4",
            "channel4": "relay4",
            "channel-4": "relay4",
        }
        normalized = aliases.get(key)
        if normalized is None:
            raise RelayCommandError(f"Unbekannter Relaiskanal: {key or '<leer>'}")
        return normalized

    def _build_channel_snapshot(self, output_id, is_on, board_available):
        channel = self.CHANNELS[output_id]
        payload = {
            "id": output_id,
            "channel": channel["channel"],
            "label": channel["label"],
            "endpoint": channel["endpoint"],
            "on": bool(is_on),
            "available": bool(board_available),
        }
        if output_id == "eStop":
            payload["engaged"] = bool(is_on)
        return payload
