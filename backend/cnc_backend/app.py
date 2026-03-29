from __future__ import annotations

import threading
import time

from cnc_hardware import create_hardware_backend

from .common import iso_now_utc
from .config import load_app_config
from .settings_store import SettingsStore
from .system_service import ShutdownService, mock_axes_load
from .wifi_service import WiFiService


def _calibrate_axis_load_percent(current_a, calibration):
    calibration_data = calibration if isinstance(calibration, dict) else {}
    try:
        min_a = float(calibration_data.get("minA", 0.0))
    except (ValueError, TypeError):
        min_a = 0.0
    try:
        max_a = float(calibration_data.get("maxA", 10.0))
    except (ValueError, TypeError):
        max_a = 10.0

    min_a = max(0.0, min(10.0, min_a))
    max_a = max(0.0, min(10.0, max_a))
    if max_a <= min_a:
        return 100.0 if abs(float(current_a or 0.0)) >= max_a else 0.0

    return max(0.0, min(100.0, ((abs(float(current_a or 0.0)) - min_a) / (max_a - min_a)) * 100.0))


class BackendApp:
    def __init__(self, config, store, wifi_service, shutdown_service, hardware_backend):
        self.config = config
        self.store = store
        self.wifi_service = wifi_service
        self.shutdown_service = shutdown_service
        self.hardware_backend = hardware_backend

    def ensure_storage(self):
        self.store.ensure_split_storage()

    def start_background_tasks(self):
        threading.Thread(target=self.wifi_service.autoconnect_wifi_on_startup, daemon=True).start()
        threading.Thread(target=self.hardware_backend.initialize_relay_board_on_startup, daemon=True).start()

    def get_health(self):
        return {"status": "ok", "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    def get_axes(self, timestamp_ms=None):
        timestamp = int(timestamp_ms if timestamp_ms is not None else time.time() * 1000)
        axes = mock_axes_load(timestamp)
        axis_loads = self.get_axis_loads()
        axis_sensor_payloads = axis_loads.get("axes", {}) if isinstance(axis_loads, dict) else {}

        for axis in ("x", "y", "z"):
            sensor_payload = axis_sensor_payloads.get(axis, {})
            if sensor_payload.get("available") and sensor_payload.get("calibratedLoadPercent") is not None:
                axes[axis] = float(sensor_payload.get("calibratedLoadPercent"))
            else:
                axes[axis] = 0.0

        return {
            "timestamp": timestamp,
            "axes": axes,
            "axisLoadSensors": axis_sensor_payloads,
        }

    def get_hardware_snapshot(self, force_refresh=False):
        return self.hardware_backend.get_snapshot(force_refresh=force_refresh)

    def get_spindle_temperature(self, force_refresh=False):
        return self.hardware_backend.get_spindle_temperature(force_refresh=force_refresh)

    def get_axis_loads(self, force_refresh=False):
        axis_loads = self.hardware_backend.get_axis_loads(force_refresh=force_refresh)
        if not isinstance(axis_loads, dict):
            return axis_loads

        calibration = self.store.load_ui_settings().get("axisLoadCalibration", {})
        axes = axis_loads.get("axes")
        if not isinstance(axes, dict):
            return axis_loads

        for axis in ("x", "y", "z"):
            payload = axes.get(axis)
            if not isinstance(payload, dict):
                continue
            axis_calibration = calibration.get(axis, {"minA": 0.0, "maxA": 10.0})
            payload["calibration"] = axis_calibration
            if payload.get("available") and payload.get("currentA") is not None:
                payload["calibratedLoadPercent"] = round(
                    _calibrate_axis_load_percent(payload.get("currentA"), axis_calibration),
                    2,
                )
            else:
                payload["calibratedLoadPercent"] = None
        return axis_loads

    def get_relay_board(self):
        return self.hardware_backend.get_relay_board()

    def set_relay_output(self, output_id, enabled):
        return self.hardware_backend.set_relay_output(output_id, enabled)

    def get_settings(self):
        legacy = self.store.load_legacy_settings()
        ui_settings = self.wifi_service.merge_wifi_runtime_settings(self.store.load_ui_settings())
        machine_stats = self.store.load_machine_stats(legacy)
        maintenance_tasks = self.store.load_maintenance_tasks(legacy)
        return {
            **ui_settings,
            **machine_stats,
            "maintenanceTasks": maintenance_tasks,
        }

    def get_wifi_status(self):
        saved = self.store.load_ui_settings()
        runtime = self.wifi_service.get_wifi_runtime_status(saved)
        return {
            "wifiAvailable": bool(runtime.get("available", False)),
            "wifiInterface": str(runtime.get("interface", "")).strip(),
            "wifiConnected": bool(runtime.get("connected", False)),
            "wifiSsid": str(runtime.get("ssid", "")).strip() or str(saved.get("wifiSsid", "")).strip(),
            "wifiIpAddress": str(runtime.get("ipAddress", "")).strip(),
            "wifiState": str(runtime.get("state", "")).strip(),
            "wifiIssueCode": str(runtime.get("issueCode", "")).strip(),
            "wifiIssue": str(runtime.get("issue", "")).strip(),
            "wifiAutoConnect": bool(saved.get("wifiAutoConnect", False)),
        }

    def save_settings(self, patch):
        payload = patch if isinstance(patch, dict) else {}

        ui_keys = {
            "graphWindowSec",
            "lightBrightness",
            "fanSpeed",
            "fanAuto",
            "wifiSsid",
            "wifiPassword",
            "wifiAutoConnect",
            "axisVisibility",
            "axisLoadCalibration",
        }
        ui_patch = {key: payload[key] for key in ui_keys if key in payload}
        if ui_patch:
            self.store.save_ui_settings(ui_patch)

        if "spindleRuntimeSec" in payload:
            self.store.save_machine_stats({"spindleRuntimeSec": payload.get("spindleRuntimeSec")})

        if "maintenanceTasks" in payload:
            self.store.save_maintenance_tasks(payload.get("maintenanceTasks"))

        saved = self.get_settings()
        if any(key in payload for key in ("wifiSsid", "wifiPassword", "wifiAutoConnect")):
            ok, message = self.wifi_service.apply_saved_wifi_configuration(self.store.load_ui_settings())
            saved = self.get_settings()
            if not ok:
                return saved, message
        return saved, ""

    def get_maintenance_tasks(self):
        return self.get_settings().get("maintenanceTasks", [])

    def complete_maintenance_task(self, task_id):
        task_id = str(task_id or "").strip()
        if not task_id:
            return None

        settings = self.get_settings()
        tasks = settings.get("maintenanceTasks", [])
        spindle_runtime_sec = max(0, int(settings.get("spindleRuntimeSec", 0) or 0))
        now_iso = iso_now_utc()

        updated_task = None
        for task in tasks:
            if str(task.get("id", "")).strip() != task_id:
                continue
            task["lastCompletedAt"] = now_iso
            task["spindleRuntimeSecAtCompletion"] = spindle_runtime_sec
            updated_task = task
            break

        if updated_task is None:
            return None

        self.save_settings({"maintenanceTasks": tasks})
        return updated_task

    def request_system_shutdown(self):
        return self.shutdown_service.request_system_shutdown()

    def connect_wifi(self, ssid, password, auto_connect):
        self.store.save_ui_settings(
            {
                "wifiSsid": ssid,
                "wifiPassword": password,
                "wifiAutoConnect": auto_connect,
            }
        )
        return self.wifi_service.connect_wifi()

    def disconnect_wifi(self):
        return self.wifi_service.disconnect_wifi()

    def scan_wifi_networks(self):
        return self.wifi_service.scan_wifi_networks()

    def get_wifi_autoconnect(self):
        return bool(self.store.load_ui_settings().get("wifiAutoConnect", False))


def create_backend_app():
    config = load_app_config()
    store = SettingsStore(config)
    wifi_service = WiFiService(config, store)
    shutdown_service = ShutdownService(config)
    hardware_backend = create_hardware_backend()
    return BackendApp(
        config=config,
        store=store,
        wifi_service=wifi_service,
        shutdown_service=shutdown_service,
        hardware_backend=hardware_backend,
    )
