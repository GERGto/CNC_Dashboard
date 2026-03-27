#!/usr/bin/env python3
"""
Standalone test tool for the GHI DUELink Relay P4 (GDL-ACRELAYP4-C).

The script talks directly to a DUELink board over I2C or, optionally, over a
USB/UART serial console. It does not depend on the dashboard backend service.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import time


BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from cnc_hardware.i2c import I2CError, LinuxI2CDevice

try:
    import serial as pyserial  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    pyserial = None


PROMPT_SUFFIXES = (b"\r\n>", b"\r\n$")


class ToolError(RuntimeError):
    pass


def ends_with_prompt(buffer):
    return any(buffer.endswith(suffix) for suffix in PROMPT_SUFFIXES)


class DuelinkI2CTransport:
    def __init__(
        self,
        bus_number=1,
        address=0x52,
        device_index=1,
        read_chunk_size=32,
        flush_length=64,
        timeout_sec=1.5,
        poll_interval_sec=0.01,
        flush_before_write=True,
        initialization_retry_window_sec=1.5,
        initialization_retry_interval_sec=0.05,
        initialization_response_timeout_sec=0.15,
    ):
        self.bus_number = int(bus_number)
        self.address = int(address)
        self.device_index = int(device_index)
        self.read_chunk_size = max(1, int(read_chunk_size))
        self.flush_length = max(1, int(flush_length))
        self.timeout_sec = max(0.05, float(timeout_sec))
        self.poll_interval_sec = max(0.001, float(poll_interval_sec))
        self.flush_before_write = bool(flush_before_write)
        self.initialization_retry_window_sec = max(0.0, float(initialization_retry_window_sec))
        self.initialization_retry_interval_sec = max(0.0, float(initialization_retry_interval_sec))
        self.initialization_response_timeout_sec = max(0.01, float(initialization_response_timeout_sec))
        self.device = LinuxI2CDevice(self.bus_number, self.address)
        self._initialized = False

    def describe(self):
        return f"I2C bus={self.bus_number} address=0x{self.address:02x} deviceIndex={self.device_index}"

    def ensure_ready(self):
        if not self.device.is_supported():
            raise ToolError("Linux-I2C ist auf diesem System nicht verfuegbar.")
        if not self.device.is_available():
            raise ToolError(f"I2C-Bus nicht gefunden: {self.device.path}")

    def flush(self):
        try:
            return self.device.read(self.flush_length)
        except I2CError:
            return b""

    def write_line(self, command):
        payload = (command or "").encode("ascii", errors="ignore") + b"\n"
        try:
            self.device.write(payload)
        except I2CError as exc:
            raise ToolError(str(exc)) from exc

    def read_until_prompt(self, timeout_sec=None):
        effective_timeout_sec = self.timeout_sec if timeout_sec is None else max(0.01, float(timeout_sec))
        deadline = time.monotonic() + effective_timeout_sec
        response = bytearray()

        while time.monotonic() <= deadline:
            try:
                chunk = self.device.read(self.read_chunk_size)
            except I2CError as exc:
                raise ToolError(str(exc)) from exc

            if chunk:
                response.extend(byte for byte in chunk if byte != 0xFF)
                if ends_with_prompt(response):
                    return bytes(response[:-3]).decode("ascii", errors="replace").strip()

            time.sleep(self.poll_interval_sec)

        raise ToolError(
            f"Zeitueberschreitung beim Warten auf eine Antwort von {self.device.path} "
            f"an Adresse 0x{self.address:02x}."
        )

    def exchange(self, command, response_timeout_sec=None):
        self.ensure_ready()
        if self.flush_before_write:
            self.flush()
        self.write_line(command)
        return self.read_until_prompt(timeout_sec=response_timeout_sec)

    def prime_interface(self, deadline):
        last_error = None

        while True:
            try:
                self.exchange("", response_timeout_sec=self.initialization_response_timeout_sec)
                self._initialized = True
                return
            except ToolError as exc:
                last_error = exc
                if time.monotonic() >= deadline:
                    break
                time.sleep(self.initialization_retry_interval_sec)

        if last_error is None:
            last_error = ToolError("Unbekannter DUELink-Initialisierungsfehler.")
        raise ToolError(
            f"DUELink-Initialisierung auf {self.device.path} an Adresse 0x{self.address:02x} fehlgeschlagen: "
            f"{last_error}"
        ) from last_error

    def run_command(self, command, select_device=True):
        deadline = time.monotonic() + self.initialization_retry_window_sec

        while True:
            try:
                if not self._initialized:
                    self.prime_interface(deadline)
                if select_device and self.device_index > 0:
                    self.exchange(f"sel({self.device_index})")
                response = self.exchange(command)
                self._initialized = True
                return response
            except ToolError:
                self._initialized = False
                if time.monotonic() >= deadline:
                    raise
                time.sleep(self.initialization_retry_interval_sec)

    def reset_initialization(self):
        self._initialized = False


class DuelinkSerialTransport:
    def __init__(
        self,
        port,
        baudrate=115200,
        device_index=1,
        timeout_sec=1.5,
        write_timeout_sec=0.5,
        initialization_retry_window_sec=1.5,
        initialization_retry_interval_sec=0.05,
        initialization_response_timeout_sec=0.15,
    ):
        if pyserial is None:
            raise ToolError(
                "pyserial ist nicht installiert. Fuer den seriellen Modus bitte `python3 -m pip install pyserial`."
            )
        self.port = str(port)
        self.baudrate = int(baudrate)
        self.device_index = int(device_index)
        self.timeout_sec = max(0.05, float(timeout_sec))
        self.write_timeout_sec = max(0.05, float(write_timeout_sec))
        self.initialization_retry_window_sec = max(0.0, float(initialization_retry_window_sec))
        self.initialization_retry_interval_sec = max(0.0, float(initialization_retry_interval_sec))
        self.initialization_response_timeout_sec = max(0.01, float(initialization_response_timeout_sec))
        self.serial = pyserial.Serial(
            self.port,
            self.baudrate,
            timeout=0.05,
            write_timeout=self.write_timeout_sec,
        )
        self._initialized = False

    def describe(self):
        return f"Serial port={self.port} baud={self.baudrate} deviceIndex={self.device_index}"

    def ensure_ready(self):
        if not self.serial.is_open:
            raise ToolError(f"Serieller Port ist nicht offen: {self.port}")

    def close(self):
        if self.serial.is_open:
            self.serial.close()

    def flush(self):
        self.serial.reset_input_buffer()

    def write_line(self, command):
        payload = (command or "").encode("ascii", errors="ignore") + b"\n"
        self.serial.write(payload)
        self.serial.flush()

    def read_until_prompt(self, timeout_sec=None):
        effective_timeout_sec = self.timeout_sec if timeout_sec is None else max(0.01, float(timeout_sec))
        deadline = time.monotonic() + effective_timeout_sec
        response = bytearray()

        while time.monotonic() <= deadline:
            waiting = self.serial.in_waiting or 1
            chunk = self.serial.read(waiting)
            if chunk:
                response.extend(chunk)
                if ends_with_prompt(response):
                    return bytes(response[:-3]).decode("ascii", errors="replace").strip()
            time.sleep(0.01)

        raise ToolError(f"Zeitueberschreitung beim Warten auf eine Antwort von {self.port}.")

    def stop_script(self):
        self.serial.write(b"\x1b")
        self.serial.flush()
        time.sleep(0.1)

    def exchange(self, command, response_timeout_sec=None):
        self.ensure_ready()
        self.flush()
        self.write_line(command)
        return self.read_until_prompt(timeout_sec=response_timeout_sec)

    def prime_interface(self, deadline):
        last_error = None

        while True:
            try:
                self.exchange("", response_timeout_sec=self.initialization_response_timeout_sec)
                self._initialized = True
                return
            except ToolError as exc:
                last_error = exc
                if time.monotonic() >= deadline:
                    break
                time.sleep(self.initialization_retry_interval_sec)

        if last_error is None:
            last_error = ToolError("Unbekannter DUELink-Initialisierungsfehler.")
        raise ToolError(f"DUELink-Initialisierung auf {self.port} fehlgeschlagen: {last_error}") from last_error

    def run_command(self, command, select_device=True):
        deadline = time.monotonic() + self.initialization_retry_window_sec

        while True:
            try:
                if not self._initialized:
                    self.prime_interface(deadline)
                if select_device and self.device_index > 0:
                    self.exchange(f"sel({self.device_index})")
                response = self.exchange(command)
                self._initialized = True
                return response
            except ToolError:
                self._initialized = False
                if time.monotonic() >= deadline:
                    raise
                time.sleep(self.initialization_retry_interval_sec)

    def reset_initialization(self):
        self._initialized = False


def parse_channel_list(raw_value):
    channels = []
    for token in str(raw_value or "").split(","):
        token = token.strip()
        if not token:
            continue
        value = int(token)
        if value < 1 or value > 4:
            raise argparse.ArgumentTypeError("Kanaele muessen zwischen 1 und 4 liegen.")
        channels.append(value)
    if not channels:
        raise argparse.ArgumentTypeError("Mindestens ein Kanal ist erforderlich.")
    return channels


def build_transport(args):
    if args.transport == "i2c":
        return DuelinkI2CTransport(
            bus_number=args.bus,
            address=args.address,
            device_index=args.device_index,
            read_chunk_size=args.read_chunk_size,
            flush_length=args.flush_length,
            timeout_sec=args.timeout,
            poll_interval_sec=args.poll_interval,
            flush_before_write=not args.no_flush_before_write,
            initialization_retry_window_sec=args.initialization_retry_window,
            initialization_retry_interval_sec=args.initialization_retry_interval,
            initialization_response_timeout_sec=args.initialization_response_timeout,
        )

    return DuelinkSerialTransport(
        port=args.port,
        baudrate=args.baudrate,
        device_index=args.device_index,
        timeout_sec=args.timeout,
        initialization_retry_window_sec=args.initialization_retry_window,
        initialization_retry_interval_sec=args.initialization_retry_interval,
        initialization_response_timeout_sec=args.initialization_response_timeout,
    )


def maybe_stop_script(transport, args):
    if args.transport == "serial" and args.stop_first:
        transport.stop_script()
    reset_initialization = getattr(transport, "reset_initialization", None)
    if callable(reset_initialization):
        reset_initialization()


def cmd_probe(transport, args):
    maybe_stop_script(transport, args)
    driver_version = transport.run_command("DVer()", select_device=not args.no_select)
    print("DVer():", driver_version or "<leer>")


def cmd_raw(transport, args):
    maybe_stop_script(transport, args)
    response = transport.run_command(args.command, select_device=not args.no_select)
    print(f"Command: {args.command}")
    print("Response:", response or "<leer>")


def cmd_set(transport, args):
    maybe_stop_script(transport, args)
    value = 1 if args.state == "on" else 0
    command = f"Set({args.channel},{value})"
    response = transport.run_command(command, select_device=not args.no_select)
    print(f"Command: {command}")
    print("Response:", response or "<leer>")


def cmd_cycle(transport, args):
    maybe_stop_script(transport, args)

    for iteration in range(args.repeat):
        print(f"Durchlauf {iteration + 1}/{args.repeat}")
        for channel in args.channels:
            on_command = f"Set({channel},1)"
            off_command = f"Set({channel},0)"

            on_response = transport.run_command(on_command, select_device=not args.no_select)
            print(f"  {on_command} -> {on_response or '<leer>'}")
            time.sleep(args.on_ms / 1000.0)

            off_response = transport.run_command(off_command, select_device=not args.no_select)
            print(f"  {off_command} -> {off_response or '<leer>'}")
            time.sleep(args.off_ms / 1000.0)


def cmd_monitor(transport, args):
    maybe_stop_script(transport, args)

    for attempt in range(args.attempts):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        prefix = f"[{timestamp}] Versuch {attempt + 1}/{args.attempts}"
        try:
            response = transport.run_command(args.command, select_device=not args.no_select)
            print(f"{prefix}: OK -> {response or '<leer>'}")
            if args.stop_on_success:
                return
        except ToolError as exc:
            print(f"{prefix}: FEHLER -> {exc}")

        if attempt + 1 < args.attempts:
            time.sleep(args.interval_sec)


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Direktes Diagnose- und Testtool fuer das DUELink Relay P4. "
            "Wichtig: Das Relaisboard benoetigt zusaetzlich 5V am Barrel-Jack."
        )
    )
    parser.add_argument("--transport", choices=("i2c", "serial"), default="i2c")
    parser.add_argument("--device-index", type=int, default=1, help="DUELink sel(<index>) vor dem Kommando senden.")
    parser.add_argument("--timeout", type=float, default=1.5, help="Antwort-Timeout in Sekunden.")
    parser.add_argument("--no-select", action="store_true", help="Kein sel(<index>) vor dem Kommando senden.")
    parser.add_argument(
        "--initialization-retry-window",
        type=float,
        default=1.5,
        help="Gesamtfenster fuer leere Initialisierungs-Kommandos und Retry nach Power-up in Sekunden.",
    )
    parser.add_argument(
        "--initialization-retry-interval",
        type=float,
        default=0.05,
        help="Pause zwischen Initialisierungs-/Retry-Versuchen in Sekunden.",
    )
    parser.add_argument(
        "--initialization-response-timeout",
        type=float,
        default=0.15,
        help="Antwort-Timeout des leeren Initialisierungs-Kommandos in Sekunden.",
    )

    i2c_group = parser.add_argument_group("I2C")
    i2c_group.add_argument("--bus", type=int, default=1, help="I2C-Busnummer, Standard: 1")
    i2c_group.add_argument(
        "--address",
        type=lambda value: int(str(value), 0),
        default=0x52,
        help="DUELink-I2C-Adresse, Standard: 0x52",
    )
    i2c_group.add_argument("--read-chunk-size", type=int, default=32, help="Anzahl gelesener Bytes pro Poll.")
    i2c_group.add_argument("--flush-length", type=int, default=64, help="Best-effort-Flush vor dem Schreiben.")
    i2c_group.add_argument(
        "--poll-interval",
        type=float,
        default=0.01,
        help="Pause zwischen I2C-Lesepolls in Sekunden.",
    )
    i2c_group.add_argument(
        "--no-flush-before-write",
        action="store_true",
        help="Keinen Vorab-Flush des I2C-Empfangspuffers versuchen.",
    )

    serial_group = parser.add_argument_group("Serial")
    serial_group.add_argument("--port", default="/dev/ttyACM0", help="Serieller Port fuer USB/UART.")
    serial_group.add_argument("--baudrate", type=int, default=115200, help="Serielle Baudrate.")
    serial_group.add_argument(
        "--stop-first",
        action="store_true",
        help="Vor dem Test ESC an die DUELink-Engine senden, um ein laufendes Skript zu stoppen.",
    )

    subparsers = parser.add_subparsers(dest="action", required=True)

    probe_parser = subparsers.add_parser("probe", help="Mit DVer() pruefen, ob das Board antwortet.")
    probe_parser.set_defaults(handler=cmd_probe)

    raw_parser = subparsers.add_parser("raw", help="Beliebiges DUELink-Kommando senden.")
    raw_parser.add_argument("command", help='Beispiel: "DVer()" oder "Set(1,1)"')
    raw_parser.set_defaults(handler=cmd_raw)

    set_parser = subparsers.add_parser("set", help="Ein Relais direkt setzen.")
    set_parser.add_argument("channel", type=int, choices=(1, 2, 3, 4))
    set_parser.add_argument("state", choices=("on", "off"))
    set_parser.set_defaults(handler=cmd_set)

    cycle_parser = subparsers.add_parser("cycle", help="Mehrere Kanaele zyklisch an/aus schalten.")
    cycle_parser.add_argument(
        "--channels",
        type=parse_channel_list,
        default=[1, 2, 3, 4],
        help="Kommagetrennte Kanalliste, z. B. 1,2,4",
    )
    cycle_parser.add_argument("--repeat", type=int, default=1, help="Anzahl Durchlaeufe.")
    cycle_parser.add_argument("--on-ms", type=int, default=500, help="Einschaltdauer pro Kanal in Millisekunden.")
    cycle_parser.add_argument("--off-ms", type=int, default=250, help="Ausschaltdauer pro Kanal in Millisekunden.")
    cycle_parser.set_defaults(handler=cmd_cycle)

    monitor_parser = subparsers.add_parser(
        "monitor",
        help="Kommandos wiederholt senden, um das Board waehrend eines Power-Cycles zu beobachten.",
    )
    monitor_parser.add_argument(
        "--command",
        default="DVer()",
        help='DUELink-Kommando fuer die Wiederholungspruefung, Standard: "DVer()"',
    )
    monitor_parser.add_argument("--attempts", type=int, default=30, help="Anzahl Versuche.")
    monitor_parser.add_argument(
        "--interval-sec",
        type=float,
        default=1.0,
        help="Pause zwischen den Versuchen in Sekunden.",
    )
    monitor_parser.add_argument(
        "--stop-on-success",
        action="store_true",
        help="Nach dem ersten erfolgreichen Antwortpaket beenden.",
    )
    monitor_parser.set_defaults(handler=cmd_monitor)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        transport = build_transport(args)
    except ToolError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2

    print(f"Transport: {transport.describe()}")

    try:
        args.handler(transport, args)
    except ToolError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    finally:
        close = getattr(transport, "close", None)
        if callable(close):
            close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
