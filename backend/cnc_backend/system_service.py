from __future__ import annotations

import math
import os
import shlex
import subprocess
import threading
import time

from .command_utils import format_command_failure, is_posix_root, run_command
from .common import iso_now_utc


def mock_axes_load(t_ms):
    def base(index):
        value = (math.sin(t_ms / 700.0 + index) * 40.0 + 50.0)
        return round(value, 1)

    return {
        "spindle": base(0),
        "x": base(1),
        "y": base(2),
        "z": base(3),
    }


def _clamp_percent(value):
    try:
        return max(0.0, min(100.0, float(value)))
    except (ValueError, TypeError):
        return 0.0


class SystemInfoService:
    def __init__(self, config, hardware_backend, backend_app=None):
        self.config = config
        self.hardware_backend = hardware_backend
        self.backend_app = backend_app
        self._cpu_usage_lock = threading.Lock()
        self._cpu_usage_previous_sample = self._read_cpu_stat_sample()

    def build_snapshot(self):
        spindle_runtime_sec = 0
        axis_runtime_sec = {
            "x": 0,
            "y": 0,
            "z": 0,
        }
        if self.backend_app is not None and hasattr(self.backend_app, "get_spindle_runtime_sec"):
            try:
                spindle_runtime_sec = max(0, int(self.backend_app.get_spindle_runtime_sec() or 0))
            except (ValueError, TypeError):
                spindle_runtime_sec = 0
        if self.backend_app is not None and hasattr(self.backend_app, "get_axis_runtime_snapshot"):
            try:
                axis_runtime_snapshot = self.backend_app.get_axis_runtime_snapshot()
                if isinstance(axis_runtime_snapshot, dict):
                    axis_runtime_sec = {
                        axis: max(0, int(axis_runtime_snapshot.get(axis, 0) or 0))
                        for axis in ("x", "y", "z")
                    }
            except (ValueError, TypeError):
                axis_runtime_sec = {
                    "x": 0,
                    "y": 0,
                    "z": 0,
                }

        enclosure = self.hardware_backend.get_enclosure_temperature(force_refresh=False)
        enclosure_temp_c = enclosure.get("temperatureC") if isinstance(enclosure, dict) else None
        enclosure_available = bool(isinstance(enclosure, dict) and enclosure.get("available"))

        cpu_temp_c = self._read_cpu_temperature_c()
        cpu_usage_percent = self._read_cpu_used_percent()
        ram_used_percent = self._read_memory_used_percent()
        storage_used_percent = self._read_storage_used_percent()
        software_version, version_source = self._read_software_version()

        return {
            "time": iso_now_utc(),
            "spindleRuntimeSec": spindle_runtime_sec,
            "spindleRuntimeHours": round(spindle_runtime_sec / 3600.0, 1),
            "axisRuntimeSec": axis_runtime_sec,
            "axisRuntimeHours": {
                axis: round(axis_runtime_sec[axis] / 3600.0, 1)
                for axis in ("x", "y", "z")
            },
            "enclosureTemperatureC": enclosure_temp_c if enclosure_available else None,
            "enclosureTemperatureAvailable": enclosure_available,
            "cpuTemperatureC": cpu_temp_c,
            "cpuTemperatureAvailable": cpu_temp_c is not None,
            "cpuUsagePercent": cpu_usage_percent,
            "cpuUsageAvailable": cpu_usage_percent is not None,
            "ramUsedPercent": ram_used_percent,
            "ramAvailable": ram_used_percent is not None,
            "storageUsedPercent": storage_used_percent,
            "storageAvailable": storage_used_percent is not None,
            "softwareVersion": software_version,
            "softwareVersionSource": version_source,
            "bars": {
                "enclosureTemperaturePercent": self._temperature_to_percent(enclosure_temp_c, 20.0, 55.0),
                "cpuTemperaturePercent": self._temperature_to_percent(cpu_temp_c, 35.0, 85.0),
                "cpuUsagePercent": _clamp_percent(cpu_usage_percent) if cpu_usage_percent is not None else None,
                "ramUsedPercent": _clamp_percent(ram_used_percent) if ram_used_percent is not None else None,
                "storageUsedPercent": _clamp_percent(storage_used_percent) if storage_used_percent is not None else None,
            },
        }

    @staticmethod
    def _temperature_to_percent(value, min_c, max_c):
        try:
            current = float(value)
        except (ValueError, TypeError):
            return None
        if max_c <= min_c:
            return None
        return round(_clamp_percent(((current - min_c) / (max_c - min_c)) * 100.0), 1)

    def _read_cpu_temperature_c(self):
        for path in (
            "/sys/class/thermal/thermal_zone0/temp",
            "/sys/devices/virtual/thermal/thermal_zone0/temp",
        ):
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    raw = handle.read().strip()
                value = float(raw)
                if value > 1000.0:
                    value = value / 1000.0
                return round(value, 1)
            except (FileNotFoundError, OSError, ValueError):
                continue

        result = run_command(["vcgencmd", "measure_temp"], timeout=2)
        if result and result.returncode == 0:
            output = str(result.stdout or "").strip()
            if "=" in output:
                candidate = output.split("=", 1)[1].replace("'C", "").strip()
                try:
                    return round(float(candidate), 1)
                except ValueError:
                    return None
        return None

    def _read_cpu_stat_sample(self):
        try:
            with open("/proc/stat", "r", encoding="utf-8") as handle:
                first_line = handle.readline().strip()
        except OSError:
            return None

        if not first_line.startswith("cpu "):
            return None

        parts = first_line.split()
        try:
            values = [int(value) for value in parts[1:]]
        except ValueError:
            return None
        if len(values) < 4:
            return None

        idle_ticks = values[3]
        if len(values) > 4:
            idle_ticks += values[4]
        total_ticks = sum(values)
        if total_ticks <= 0:
            return None
        return total_ticks, idle_ticks

    def _read_cpu_used_percent(self):
        current_sample = self._read_cpu_stat_sample()
        if current_sample is None:
            return None

        with self._cpu_usage_lock:
            previous_sample = self._cpu_usage_previous_sample
            self._cpu_usage_previous_sample = current_sample

        if previous_sample is None:
            return None

        total_delta = current_sample[0] - previous_sample[0]
        idle_delta = current_sample[1] - previous_sample[1]
        if total_delta <= 0:
            return None

        used_percent = ((float(total_delta) - float(idle_delta)) / float(total_delta)) * 100.0
        return round(_clamp_percent(used_percent), 1)

    def _read_memory_used_percent(self):
        meminfo = {}
        try:
            with open("/proc/meminfo", "r", encoding="utf-8") as handle:
                for line in handle:
                    if ":" not in line:
                        continue
                    key, value = line.split(":", 1)
                    number = value.strip().split(" ", 1)[0]
                    meminfo[key.strip()] = int(number)
        except (FileNotFoundError, OSError, ValueError):
            return None

        total_kb = meminfo.get("MemTotal")
        available_kb = meminfo.get("MemAvailable")
        if not total_kb or available_kb is None or total_kb <= 0:
            return None

        used_percent = ((float(total_kb) - float(available_kb)) / float(total_kb)) * 100.0
        return round(_clamp_percent(used_percent), 1)

    def _read_storage_used_percent(self):
        try:
            stats = os.statvfs(self.config.backend_root or "/")
            total_bytes = stats.f_blocks * stats.f_frsize
            available_bytes = stats.f_bavail * stats.f_frsize
            if total_bytes <= 0:
                return None
            used_percent = ((float(total_bytes) - float(available_bytes)) / float(total_bytes)) * 100.0
            return round(_clamp_percent(used_percent), 1)
        except (AttributeError, OSError, ValueError):
            return None

    def _read_software_version(self):
        explicit_version = str(os.getenv("SOFTWARE_VERSION", "")).strip()
        if explicit_version:
            return explicit_version, "env"

        repo_root = os.path.dirname(self.config.backend_root)
        for command in (
            ["git", "-C", repo_root, "describe", "--always", "--dirty", "--tags"],
            ["git", "-C", repo_root, "rev-parse", "--short", "HEAD"],
        ):
            result = run_command(command, timeout=3)
            if result and result.returncode == 0:
                version = str(result.stdout or "").strip()
                if version:
                    return version, "git"

        version_file = os.path.join(repo_root, "VERSION")
        try:
            with open(version_file, "r", encoding="utf-8") as handle:
                version = handle.read().strip()
            if version:
                return version, "file"
        except OSError:
            pass

        return "unbekannt", "fallback"


class ShutdownService:
    def __init__(self, config, hardware_backend=None):
        self.config = config
        self.hardware_backend = hardware_backend

    def build_shutdown_commands(self):
        if self.config.shutdown_command:
            try:
                return [shlex.split(self.config.shutdown_command)]
            except ValueError:
                return []

        if os.name != "posix":
            return []

        prefix = []
        if hasattr(os, "geteuid") and os.geteuid() != 0:
            prefix = ["sudo", "-n"]

        commands = []
        for command in (
            ["/usr/bin/systemctl", "poweroff"],
            ["/usr/sbin/shutdown", "-h", "now"],
            ["/usr/sbin/poweroff"],
        ):
            if os.path.exists(command[0]):
                commands.append(prefix + command)
        return commands

    def blackout_display_for_shutdown(self):
        if os.name != "posix":
            return False

        display_env = {"DISPLAY": self.config.kiosk_display}
        if self.config.kiosk_xauthority:
            display_env["XAUTHORITY"] = self.config.kiosk_xauthority

        xset_result = None
        if self.config.kiosk_display:
            run_command(["xset", "-display", self.config.kiosk_display, "+dpms"], timeout=2, env=display_env)
            xset_result = run_command(
                ["xset", "-display", self.config.kiosk_display, "dpms", "force", "off"],
                timeout=2,
                env=display_env,
            )
            if xset_result and xset_result.returncode == 0:
                return True

        if is_posix_root():
            vcgencmd_result = run_command(["vcgencmd", "display_power", "0"], timeout=2)
            if vcgencmd_result and vcgencmd_result.returncode == 0:
                return True

        detail = format_command_failure(xset_result, "Display blackout command failed")
        print(detail, flush=True)
        return False

    def execute_shutdown_request(self):
        self.prepare_hardware_for_shutdown()
        self.blackout_display_for_shutdown()

        if self.config.shutdown_delay_sec > 0:
            time.sleep(self.config.shutdown_delay_sec)

        commands = self.build_shutdown_commands()
        failures = []

        for command in commands:
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=10,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                failures.append(f"{command}: {exc}")
                continue

            if result.returncode == 0:
                return

            stderr = (result.stderr or "").strip()
            stdout = (result.stdout or "").strip()
            detail = stderr or stdout or f"exit code {result.returncode}"
            failures.append(f"{command}: {detail}")

        print("Failed to execute system shutdown request:", " | ".join(failures), flush=True)

    def prepare_hardware_for_shutdown(self):
        if self.hardware_backend is None:
            return

        try:
            result = self.hardware_backend.prepare_outputs_for_shutdown()
            if isinstance(result, dict):
                print(
                    "Hardware shutdown sequence finished "
                    f"(statusIndicatorStarted={result.get('statusIndicatorStarted')}, "
                    f"statusIndicatorCompleted={result.get('statusIndicatorCompleted')}).",
                    flush=True,
                )
        except Exception as exc:  # pragma: no cover - shutdown should still proceed
            print(f"Hardware shutdown sequence failed: {exc}", flush=True)

    def request_system_shutdown(self):
        if not self.config.enable_real_shutdown:
            return False, "Real shutdown is disabled"

        commands = self.build_shutdown_commands()
        if not commands:
            return False, "No shutdown command is available"

        worker = threading.Thread(target=self.execute_shutdown_request, daemon=True)
        worker.start()
        return True, "Shutdown scheduled"
