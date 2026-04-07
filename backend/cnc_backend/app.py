from __future__ import annotations

import threading
import time

from cnc_hardware import create_hardware_backend

from .camera_service import CameraService
from .common import iso_now_utc
from .config import load_app_config
from .machine_status import MachineStatusService
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
    SPINDLE_RUNTIME_POLL_INTERVAL_SEC = 0.25
    SPINDLE_RUNTIME_PERSIST_INTERVAL_SEC = 5.0
    SPINDLE_RUNTIME_DELTA_CLAMP_SEC = 5.0

    def __init__(
        self,
        config,
        store,
        wifi_service,
        shutdown_service,
        hardware_backend,
        machine_status_service,
        camera_service,
    ):
        self.config = config
        self.store = store
        self.wifi_service = wifi_service
        self.shutdown_service = shutdown_service
        self.hardware_backend = hardware_backend
        self.machine_status_service = machine_status_service
        self.camera_service = camera_service
        self._spindle_runtime_lock = threading.Lock()
        self._spindle_runtime_sec = None
        self._spindle_runtime_last_sample_monotonic = None
        self._spindle_runtime_last_persist_monotonic = 0.0
        self._spindle_runtime_last_running = False

    def ensure_storage(self):
        self.store.ensure_split_storage()
        self._load_spindle_runtime_state()

    def start_background_tasks(self):
        threading.Thread(target=self.wifi_service.autoconnect_wifi_on_startup, daemon=True).start()
        threading.Thread(target=self.hardware_backend.initialize_outputs_on_startup, daemon=True).start()
        threading.Thread(target=self._hardware_estop_worker, daemon=True).start()
        threading.Thread(target=self._spindle_runtime_worker, daemon=True).start()
        threading.Thread(target=self._status_indicator_worker, daemon=True).start()
        self.camera_service.start_background_tasks()

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
        snapshot = self.hardware_backend.get_snapshot(force_refresh=force_refresh)
        snapshot["machineStatus"] = self.get_machine_status()
        return snapshot

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

    def get_camera_status(self, ensure_active=False):
        return self.camera_service.get_status(ensure_active=ensure_active)

    def set_relay_output(self, output_id, enabled):
        result = self.hardware_backend.set_relay_output(output_id, enabled)
        self.sync_status_indicator()
        return result

    def get_machine_status(self):
        self.hardware_backend.sync_hardware_estop(force_refresh=False)
        maintenance_tasks = self.store.load_maintenance_tasks()
        relay_board = self.hardware_backend.get_relay_board()
        return self.machine_status_service.build_snapshot(
            self.get_spindle_runtime_sec(),
            maintenance_tasks,
            relay_board,
        )

    def report_machine_status(self, status, source="api"):
        self.machine_status_service.update_reported_status(status, source=source)
        self.sync_status_indicator()
        return self.get_machine_status()

    def sync_status_indicator(self):
        machine_status = self.get_machine_status()
        indicator = machine_status.get("indicator", {}) if isinstance(machine_status, dict) else {}
        state = str(indicator.get("state", "idle")).strip() or "idle"
        reason = str(indicator.get("reason", "")).strip()
        self.hardware_backend.set_status_indicator_state(state, reason=reason, source="machine-status")
        return machine_status

    def get_settings(self):
        legacy = self.store.load_legacy_settings()
        ui_settings = self.wifi_service.merge_wifi_runtime_settings(self.store.load_ui_settings())
        machine_stats = {"spindleRuntimeSec": self.get_spindle_runtime_sec()}
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
            self.set_spindle_runtime_sec(payload.get("spindleRuntimeSec"), persist=True)

        if "maintenanceTasks" in payload:
            self.store.save_maintenance_tasks(payload.get("maintenanceTasks"))

        saved = self.get_settings()
        if any(key in payload for key in ("wifiSsid", "wifiPassword", "wifiAutoConnect")):
            ok, message = self.wifi_service.apply_saved_wifi_configuration(self.store.load_ui_settings())
            saved = self.get_settings()
            if not ok:
                return saved, message
        if "spindleRuntimeSec" in payload or "maintenanceTasks" in payload:
            self.sync_status_indicator()
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

    def get_spindle_runtime_sec(self):
        with self._spindle_runtime_lock:
            if self._spindle_runtime_sec is None:
                self._load_spindle_runtime_state_locked()
            return max(0, int(self._spindle_runtime_sec or 0))

    def set_spindle_runtime_sec(self, value, persist=False):
        normalized = max(0, int(value or 0))
        with self._spindle_runtime_lock:
            if self._spindle_runtime_sec is None:
                self._load_spindle_runtime_state_locked()
            self._spindle_runtime_sec = float(normalized)
            self._spindle_runtime_last_sample_monotonic = time.monotonic()
        if persist:
            self._persist_spindle_runtime(force=True)
        return normalized

    def _load_spindle_runtime_state(self):
        with self._spindle_runtime_lock:
            self._load_spindle_runtime_state_locked()

    def _load_spindle_runtime_state_locked(self):
        machine_stats = self.store.load_machine_stats()
        self._spindle_runtime_sec = float(max(0, int(machine_stats.get("spindleRuntimeSec", 0) or 0)))
        self._spindle_runtime_last_sample_monotonic = time.monotonic()
        self._spindle_runtime_last_persist_monotonic = self._spindle_runtime_last_sample_monotonic

    def _persist_spindle_runtime(self, force=False):
        runtime_to_save = None
        now = time.monotonic()
        with self._spindle_runtime_lock:
            if self._spindle_runtime_sec is None:
                self._load_spindle_runtime_state_locked()
            if not force and (now - self._spindle_runtime_last_persist_monotonic) < self.SPINDLE_RUNTIME_PERSIST_INTERVAL_SEC:
                return max(0, int(self._spindle_runtime_sec or 0))
            runtime_to_save = max(0, int(self._spindle_runtime_sec or 0))
            self._spindle_runtime_last_persist_monotonic = now

        self.store.save_machine_stats({"spindleRuntimeSec": runtime_to_save})
        return runtime_to_save

    def _status_indicator_worker(self):
        interval_sec = max(0.25, float(self.config.status_indicator_sync_interval_sec))
        while True:
            try:
                self.sync_status_indicator()
            except Exception as exc:  # pragma: no cover - background safety net
                print(f"Status indicator sync failed: {exc}", flush=True)
            time.sleep(interval_sec)

    def _hardware_estop_worker(self):
        interval_sec = max(0.05, float(self.config.hardware_estop_poll_interval_sec))
        while True:
            try:
                result = self.hardware_backend.sync_hardware_estop(force_refresh=True)
                if result.get("stateChanged") or result.get("relayChanged"):
                    self.sync_status_indicator()
                elif result.get("relayError"):
                    print(f"Hardware E-Stop relay sync failed: {result['relayError']}", flush=True)
            except Exception as exc:  # pragma: no cover - background safety net
                print(f"Hardware E-Stop monitor failed: {exc}", flush=True)
            time.sleep(interval_sec)

    def _spindle_runtime_worker(self):
        interval_sec = self.SPINDLE_RUNTIME_POLL_INTERVAL_SEC
        while True:
            try:
                spindle_running_info = self.hardware_backend.get_spindle_running(force_refresh=False)
                spindle_running = bool(spindle_running_info.get("spindleRunning", False))
                now = time.monotonic()
                persist_required = False
                status_sync_required = False

                with self._spindle_runtime_lock:
                    if self._spindle_runtime_sec is None:
                        self._load_spindle_runtime_state_locked()

                    previous_running = bool(self._spindle_runtime_last_running)
                    last_sample = self._spindle_runtime_last_sample_monotonic
                    delta_sec = now - last_sample if last_sample is not None else 0.0
                    self._spindle_runtime_last_sample_monotonic = now

                    if spindle_running and 0.0 < delta_sec <= self.SPINDLE_RUNTIME_DELTA_CLAMP_SEC:
                        self._spindle_runtime_sec += delta_sec

                    if spindle_running != previous_running:
                        status_sync_required = True

                    if spindle_running:
                        persist_required = (now - self._spindle_runtime_last_persist_monotonic) >= self.SPINDLE_RUNTIME_PERSIST_INTERVAL_SEC
                    elif previous_running:
                        persist_required = True

                    self._spindle_runtime_last_running = spindle_running

                if persist_required:
                    self._persist_spindle_runtime(force=True)
                if status_sync_required:
                    self.sync_status_indicator()
            except Exception as exc:  # pragma: no cover - background safety net
                print(f"Spindle runtime worker failed: {exc}", flush=True)
            time.sleep(interval_sec)


def create_backend_app():
    config = load_app_config()
    store = SettingsStore(config)
    wifi_service = WiFiService(config, store)
    hardware_backend = create_hardware_backend()
    shutdown_service = ShutdownService(config, hardware_backend=hardware_backend)
    machine_status_service = MachineStatusService()
    camera_service = CameraService(config)
    return BackendApp(
        config=config,
        store=store,
        wifi_service=wifi_service,
        shutdown_service=shutdown_service,
        hardware_backend=hardware_backend,
        machine_status_service=machine_status_service,
        camera_service=camera_service,
    )
