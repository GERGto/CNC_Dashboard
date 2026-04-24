from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

from cnc_hardware import create_hardware_backend

from .camera_service import CameraService
from .common import iso_now_utc
from .config import load_app_config
from .machine_status import MachineStatusService
from .settings_store import SettingsStore
from .system_service import ShutdownService, SystemInfoService, mock_axes_load
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

    min_a = max(0.0, min_a)
    max_a = max(0.0, max_a)
    if max_a <= min_a:
        return 100.0 if abs(float(current_a or 0.0)) >= max_a else 0.0

    return max(0.0, min(100.0, ((abs(float(current_a or 0.0)) - min_a) / (max_a - min_a)) * 100.0))


class BackendApp:
    SPINDLE_RUNTIME_POLL_INTERVAL_SEC = 0.25
    SPINDLE_RUNTIME_PERSIST_INTERVAL_SEC = 5.0
    SPINDLE_RUNTIME_DELTA_CLAMP_SEC = 5.0
    AXIS_RUNTIME_MOVING_THRESHOLD_PERCENT = 5.0
    FAN_CONTROL_POLL_INTERVAL_SEC = 0.5
    STATUS_INDICATOR_RUNNING_REFRESH_INTERVAL_SEC = 0.25
    ENCLOSURE_FAN_HYSTERESIS_C = 1.0
    AUTOMATED_FAN_OUTPUTS = frozenset({"fan", "enclosureFan"})
    WARMUP_TASK_ID = "spindle-warmup"
    WARMUP_AUTO_COMPLETE_RUNNING_SEC = 5.0 * 60.0
    WARMUP_VALIDITY_SEC = 2 * 3600

    def __init__(
        self,
        config,
        store,
        wifi_service,
        shutdown_service,
        system_info_service,
        hardware_backend,
        machine_status_service,
        camera_service,
    ):
        self.config = config
        self.store = store
        self.wifi_service = wifi_service
        self.shutdown_service = shutdown_service
        self.system_info_service = system_info_service
        self.hardware_backend = hardware_backend
        self.machine_status_service = machine_status_service
        self.camera_service = camera_service
        if self.system_info_service is not None:
            self.system_info_service.backend_app = self
        self._spindle_runtime_lock = threading.Lock()
        self._fan_control_lock = threading.Lock()
        self._machine_on_time_sec = None
        self._spindle_runtime_sec = None
        self._axis_runtime_sec = None
        self._backend_start_count = None
        self._spindle_start_count = None
        self._estop_count = None
        self._manual_estop_count = None
        self._hardware_estop_count = None
        self._spindle_runtime_last_sample_monotonic = None
        self._spindle_runtime_last_persist_monotonic = 0.0
        self._spindle_runtime_last_running = False
        self._spindle_warmup_running_sec = 0.0
        self._spindle_warmup_run_qualified = False
        self._spindle_warmup_refresh_on_stop = False
        self._axis_runtime_last_moving = {
            axis: False
            for axis in ("x", "y", "z")
        }
        self._last_spindle_running_observed = None
        self._last_hardware_estop_engaged = None
        self._backend_start_recorded = False
        self._spindle_fan_last_running = False
        self._spindle_fan_last_stop_monotonic = None
        self._fan_manual_overrides = {
            output_id: {
                "active": False,
                "manualOn": False,
                "lastAutoDesiredOn": None,
            }
            for output_id in self.AUTOMATED_FAN_OUTPUTS
        }

    def ensure_storage(self):
        self.store.ensure_split_storage()
        self._load_spindle_runtime_state()
        self._record_backend_startup()
        self._apply_status_indicator_preferences()

    def start_background_tasks(self):
        threading.Thread(target=self.wifi_service.autoconnect_wifi_on_startup, daemon=True).start()
        threading.Thread(target=self.hardware_backend.initialize_outputs_on_startup, daemon=True).start()
        threading.Thread(target=self._hardware_estop_worker, daemon=True).start()
        threading.Thread(target=self._spindle_runtime_worker, daemon=True).start()
        threading.Thread(target=self._fan_control_worker, daemon=True).start()
        threading.Thread(target=self._status_indicator_worker, daemon=True).start()
        self.camera_service.start_background_tasks()

    def get_health(self):
        return {"status": "ok", "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    def get_axes(self, timestamp_ms=None):
        timestamp = int(timestamp_ms if timestamp_ms is not None else time.time() * 1000)
        axes = mock_axes_load(timestamp)
        axis_loads = self.get_axis_loads()
        spindle_load = self.get_spindle_load()
        axis_sensor_payloads = axis_loads.get("axes", {}) if isinstance(axis_loads, dict) else {}

        for axis in ("x", "y", "z"):
            sensor_payload = axis_sensor_payloads.get(axis, {})
            if sensor_payload.get("available") and sensor_payload.get("calibratedLoadPercent") is not None:
                axes[axis] = float(sensor_payload.get("calibratedLoadPercent"))
            else:
                axes[axis] = 0.0

        if spindle_load.get("available") and spindle_load.get("calibratedLoadPercent") is not None:
            axes["spindle"] = float(spindle_load.get("calibratedLoadPercent"))
        else:
            axes["spindle"] = 0.0

        return {
            "timestamp": timestamp,
            "axes": axes,
            "axisLoadSensors": {
                **axis_sensor_payloads,
                "spindle": spindle_load,
            },
        }

    def get_hardware_snapshot(self, force_refresh=False):
        snapshot = self.hardware_backend.get_snapshot(force_refresh=force_refresh)
        snapshot["machineStatus"] = self.get_machine_status()
        return snapshot

    def get_enclosure_temperature(self, force_refresh=False):
        return self.hardware_backend.get_enclosure_temperature(force_refresh=force_refresh)

    def get_spindle_temperature(self, force_refresh=False):
        return self.get_enclosure_temperature(force_refresh=force_refresh)

    def get_axis_loads(self, force_refresh=False):
        axis_loads = self.hardware_backend.get_axis_loads(force_refresh=force_refresh)
        if not isinstance(axis_loads, dict):
            return axis_loads

        calibration_defaults = self.store.default_ui_settings().get("axisLoadCalibration", {})
        calibration = self.store.load_ui_settings().get("axisLoadCalibration", {})
        axes = axis_loads.get("axes")
        if not isinstance(axes, dict):
            return axis_loads

        for axis in ("x", "y", "z"):
            payload = axes.get(axis)
            if not isinstance(payload, dict):
                continue
            axis_calibration = calibration.get(axis, calibration_defaults.get(axis, {"minA": 0.0, "maxA": 10.0}))
            payload["calibration"] = axis_calibration
            if payload.get("available") and payload.get("currentA") is not None:
                payload["calibratedLoadPercent"] = round(
                    _calibrate_axis_load_percent(payload.get("currentA"), axis_calibration),
                    2,
                )
            else:
                payload["calibratedLoadPercent"] = None
        return axis_loads

    def get_spindle_load(self, force_refresh=False):
        spindle_load = self.hardware_backend.get_spindle_load(force_refresh=force_refresh)
        if not isinstance(spindle_load, dict):
            return spindle_load

        calibration_defaults = self.store.default_ui_settings().get("axisLoadCalibration", {})
        calibration = self.store.load_ui_settings().get("axisLoadCalibration", {})
        spindle_calibration = calibration.get(
            "spindle",
            calibration_defaults.get("spindle", {"minA": 0.0, "maxA": 30.0}),
        )
        spindle_load["calibration"] = spindle_calibration
        if spindle_load.get("available") and spindle_load.get("currentA") is not None:
            spindle_load["calibratedLoadPercent"] = round(
                _calibrate_axis_load_percent(spindle_load.get("currentA"), spindle_calibration),
                2,
            )
        else:
            spindle_load["calibratedLoadPercent"] = None
        return spindle_load

    def get_relay_board(self):
        return self.hardware_backend.get_relay_board()

    def get_camera_status(self, ensure_active=False):
        return self.camera_service.get_status(ensure_active=ensure_active)

    def set_relay_output(self, output_id, enabled, source="manual"):
        normalized_output_id = self._normalize_automated_fan_output_id(output_id)
        manual_auto_desired_on = None
        previous_estop_engaged = None
        if source != "automation":
            manual_auto_desired_on = self._get_manual_override_auto_desired_on(normalized_output_id)
        if str(output_id or "").strip().lower() in {"estop", "e-stop", "e_stop", "relay4", "relay-4"}:
            previous_estop_engaged = self._is_estop_engaged(self.hardware_backend.get_relay_board())

        result = self.hardware_backend.set_relay_output(output_id, enabled)

        if source != "automation":
            self._update_manual_fan_override(normalized_output_id, enabled, manual_auto_desired_on)
        if previous_estop_engaged is not None:
            current_estop_engaged = self._is_estop_engaged(result.get("relayBoard"))
            if bool(enabled) and current_estop_engaged and not previous_estop_engaged:
                self._record_estop_activation("manual")
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
            backend_start_count=self.get_backend_start_count(),
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
        self.hardware_backend.set_status_indicator_running_load_percent(
            self._get_status_indicator_running_load_percent(machine_status)
        )
        return machine_status

    def get_settings(self):
        legacy = self.store.load_legacy_settings()
        ui_settings = self.wifi_service.merge_wifi_runtime_settings(self.store.load_ui_settings())
        machine_stats = {
            "spindleRuntimeSec": self.get_spindle_runtime_sec(),
            "backendStartCount": self.get_backend_start_count(),
        }
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

    def get_system_status(self):
        return self.system_info_service.build_snapshot()

    def save_settings(self, patch):
        payload = patch if isinstance(patch, dict) else {}
        saved_ui_settings = None

        ui_keys = {
            "graphWindowSec",
            "rgbStripBrightness",
            "spindleFanAftercoolSeconds",
            "enclosureFanThresholdC",
            "enclosureFanAuto",
            "wifiSsid",
            "wifiPassword",
            "wifiAutoConnect",
            "axisVisibility",
            "axisLoadCalibration",
        }
        ui_patch = {key: payload[key] for key in ui_keys if key in payload}
        if ui_patch:
            saved_ui_settings = self.store.save_ui_settings(ui_patch)
            if "rgbStripBrightness" in ui_patch:
                self._apply_status_indicator_preferences(saved_ui_settings)
            if any(
                key in ui_patch
                for key in ("spindleFanAftercoolSeconds", "enclosureFanThresholdC", "enclosureFanAuto")
            ):
                try:
                    self._sync_spindle_fan_automation(saved_ui_settings)
                    self._sync_enclosure_fan_automation(saved_ui_settings)
                except Exception as exc:  # pragma: no cover - hardware may not be ready during settings save
                    print(f"Immediate fan settings sync failed: {exc}", flush=True)

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
        return self._complete_maintenance_task(task_id)

    def _complete_maintenance_task(
        self,
        task_id,
        *,
        completed_at=None,
        spindle_runtime_sec=None,
        backend_start_count=None,
    ):
        task_id = str(task_id or "").strip()
        if not task_id:
            return None

        settings = self.get_settings()
        tasks = settings.get("maintenanceTasks", [])
        completion_runtime_sec = (
            max(0, int(spindle_runtime_sec or 0))
            if spindle_runtime_sec is not None
            else max(0, int(settings.get("spindleRuntimeSec", 0) or 0))
        )
        completion_backend_start_count = (
            max(0, int(backend_start_count or 0))
            if backend_start_count is not None
            else max(0, int(settings.get("backendStartCount", 0) or 0))
        )
        now_iso = str(completed_at or iso_now_utc())

        updated_task = None
        for task in tasks:
            if str(task.get("id", "")).strip() != task_id:
                continue
            task["lastCompletedAt"] = now_iso
            task["spindleRuntimeSecAtCompletion"] = completion_runtime_sec
            task["backendStartCountAtCompletion"] = completion_backend_start_count
            updated_task = task
            break

        if updated_task is None:
            return None

        self.save_settings({"maintenanceTasks": tasks})
        return updated_task

    def _mark_warmup_completed(self, spindle_runtime_sec=None):
        current_runtime_sec = (
            self.get_spindle_runtime_sec()
            if spindle_runtime_sec is None
            else max(0, int(spindle_runtime_sec or 0))
        )
        return self._complete_maintenance_task(
            self.WARMUP_TASK_ID,
            spindle_runtime_sec=current_runtime_sec,
            backend_start_count=self.get_backend_start_count(),
        )

    def _is_warmup_currently_valid(self):
        warmup_task = None
        for task in self.store.load_maintenance_tasks():
            if str(task.get("id", "")).strip() == self.WARMUP_TASK_ID:
                warmup_task = task
                break

        if not isinstance(warmup_task, dict):
            return False

        completed_at = str(warmup_task.get("lastCompletedAt", "") or "").strip()
        if not completed_at:
            return False

        try:
            completed_dt = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
        except ValueError:
            return False

        current_dt = datetime.now(completed_dt.tzinfo or timezone.utc)
        if completed_dt.tzinfo is None and current_dt.tzinfo is not None:
            current_dt = current_dt.replace(tzinfo=None)

        return current_dt < (completed_dt + timedelta(seconds=self.WARMUP_VALIDITY_SEC))

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

    def get_axis_runtime_snapshot(self):
        with self._spindle_runtime_lock:
            if self._axis_runtime_sec is None:
                self._load_spindle_runtime_state_locked()
            return {
                axis: max(0, int((self._axis_runtime_sec or {}).get(axis, 0) or 0))
                for axis in ("x", "y", "z")
            }

    def get_backend_start_count(self):
        with self._spindle_runtime_lock:
            if self._backend_start_count is None:
                self._load_spindle_runtime_state_locked()
            return max(0, int(self._backend_start_count or 0))

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
        self._machine_on_time_sec = float(max(0, int(machine_stats.get("machineOnTimeSec", 0) or 0)))
        self._spindle_runtime_sec = float(max(0, int(machine_stats.get("spindleRuntimeSec", 0) or 0)))
        axis_runtime_sec = machine_stats.get("axisRuntimeSec", {})
        self._axis_runtime_sec = {
            axis: float(max(0, int(axis_runtime_sec.get(axis, 0) or 0)))
            for axis in ("x", "y", "z")
        }
        self._backend_start_count = max(0, int(machine_stats.get("backendStartCount", 0) or 0))
        self._spindle_start_count = max(0, int(machine_stats.get("spindleStartCount", 0) or 0))
        self._estop_count = max(0, int(machine_stats.get("eStopCount", 0) or 0))
        self._manual_estop_count = max(0, int(machine_stats.get("manualEStopCount", 0) or 0))
        self._hardware_estop_count = max(0, int(machine_stats.get("hardwareEStopCount", 0) or 0))
        self._spindle_runtime_last_sample_monotonic = time.monotonic()
        self._spindle_runtime_last_persist_monotonic = self._spindle_runtime_last_sample_monotonic
        self._spindle_runtime_last_running = False
        self._spindle_warmup_running_sec = 0.0
        self._spindle_warmup_run_qualified = False
        self._spindle_warmup_refresh_on_stop = False
        self._axis_runtime_last_moving = {
            axis: False
            for axis in ("x", "y", "z")
        }
        self._last_spindle_running_observed = None
        self._last_hardware_estop_engaged = None

    def _persist_spindle_runtime(self, force=False):
        machine_stats_to_save = None
        now = time.monotonic()
        with self._spindle_runtime_lock:
            if self._spindle_runtime_sec is None:
                self._load_spindle_runtime_state_locked()
            if not force and (now - self._spindle_runtime_last_persist_monotonic) < self.SPINDLE_RUNTIME_PERSIST_INTERVAL_SEC:
                return {
                    "machineOnTimeSec": max(0, int(self._machine_on_time_sec or 0)),
                    "spindleRuntimeSec": max(0, int(self._spindle_runtime_sec or 0)),
                    "axisRuntimeSec": {
                        axis: max(0, int((self._axis_runtime_sec or {}).get(axis, 0) or 0))
                        for axis in ("x", "y", "z")
                    },
                    "backendStartCount": max(0, int(self._backend_start_count or 0)),
                    "spindleStartCount": max(0, int(self._spindle_start_count or 0)),
                    "eStopCount": max(0, int(self._estop_count or 0)),
                    "manualEStopCount": max(0, int(self._manual_estop_count or 0)),
                    "hardwareEStopCount": max(0, int(self._hardware_estop_count or 0)),
                }
            machine_stats_to_save = {
                "machineOnTimeSec": max(0, int(self._machine_on_time_sec or 0)),
                "spindleRuntimeSec": max(0, int(self._spindle_runtime_sec or 0)),
                "axisRuntimeSec": {
                    axis: max(0, int((self._axis_runtime_sec or {}).get(axis, 0) or 0))
                        for axis in ("x", "y", "z")
                },
                "backendStartCount": max(0, int(self._backend_start_count or 0)),
                "spindleStartCount": max(0, int(self._spindle_start_count or 0)),
                "eStopCount": max(0, int(self._estop_count or 0)),
                "manualEStopCount": max(0, int(self._manual_estop_count or 0)),
                "hardwareEStopCount": max(0, int(self._hardware_estop_count or 0)),
            }
            self._spindle_runtime_last_persist_monotonic = now

        self.store.save_machine_stats(machine_stats_to_save)
        return machine_stats_to_save

    def _record_backend_startup(self):
        with self._spindle_runtime_lock:
            if self._spindle_runtime_sec is None:
                self._load_spindle_runtime_state_locked()
            if self._backend_start_recorded:
                return max(0, int(self._backend_start_count or 0))
            self._backend_start_count = max(0, int(self._backend_start_count or 0)) + 1
            self._backend_start_recorded = True
        self._persist_spindle_runtime(force=True)
        return max(0, int(self._backend_start_count or 0))

    @staticmethod
    def _is_estop_engaged(relay_board):
        channels = relay_board.get("channels", {}) if isinstance(relay_board, dict) else {}
        estop = channels.get("eStop", {}) if isinstance(channels, dict) else {}
        return bool(
            estop.get("engaged", estop.get("on", False))
            or estop.get("hardwareInputEngaged", False)
        )

    def _record_estop_activation(self, source):
        source_key = str(source or "").strip().lower()
        with self._spindle_runtime_lock:
            if self._spindle_runtime_sec is None:
                self._load_spindle_runtime_state_locked()
            self._estop_count = max(0, int(self._estop_count or 0)) + 1
            if source_key == "hardware":
                self._hardware_estop_count = max(0, int(self._hardware_estop_count or 0)) + 1
            else:
                self._manual_estop_count = max(0, int(self._manual_estop_count or 0)) + 1
        self._persist_spindle_runtime(force=True)

    def _observe_hardware_estop_state(self, engaged):
        engaged = bool(engaged)
        should_count = False
        with self._spindle_runtime_lock:
            if self._spindle_runtime_sec is None:
                self._load_spindle_runtime_state_locked()
            if self._last_hardware_estop_engaged is None:
                self._last_hardware_estop_engaged = engaged
                return
            should_count = engaged and not self._last_hardware_estop_engaged
            self._last_hardware_estop_engaged = engaged
        if should_count:
            self._record_estop_activation("hardware")

    def _apply_status_indicator_preferences(self, ui_settings=None):
        settings = ui_settings if isinstance(ui_settings, dict) else self.store.load_ui_settings()
        brightness_percent = settings.get("rgbStripBrightness", 75)
        self.hardware_backend.set_status_indicator_dynamic_brightness(brightness_percent)

    def _status_indicator_worker(self):
        default_interval_sec = max(0.25, float(self.config.status_indicator_sync_interval_sec))
        while True:
            interval_sec = default_interval_sec
            try:
                machine_status = self.sync_status_indicator()
                indicator = machine_status.get("indicator", {}) if isinstance(machine_status, dict) else {}
                if str(indicator.get("state", "")).strip() == "running":
                    interval_sec = min(
                        default_interval_sec,
                        self.STATUS_INDICATOR_RUNNING_REFRESH_INTERVAL_SEC,
                    )
            except Exception as exc:  # pragma: no cover - background safety net
                print(f"Status indicator sync failed: {exc}", flush=True)
            time.sleep(interval_sec)

    def _get_status_indicator_running_load_percent(self, machine_status=None):
        status_snapshot = machine_status if isinstance(machine_status, dict) else self.get_machine_status()
        indicator = status_snapshot.get("indicator", {}) if isinstance(status_snapshot, dict) else {}
        if str(indicator.get("state", "")).strip() != "running":
            return 0.0

        try:
            spindle_load = self.get_spindle_load(force_refresh=False)
            return max(
                0.0,
                min(100.0, float(spindle_load.get("calibratedLoadPercent", 0.0) or 0.0)),
            )
        except (ValueError, TypeError):
            return 0.0

    def _fan_control_worker(self):
        while True:
            try:
                settings = self.store.load_ui_settings()
                self._sync_spindle_fan_automation(settings)
                self._sync_enclosure_fan_automation(settings)
            except Exception as exc:  # pragma: no cover - background safety net
                print(f"Fan control worker failed: {exc}", flush=True)
            time.sleep(self.FAN_CONTROL_POLL_INTERVAL_SEC)

    def _sync_spindle_fan_automation(self, settings=None):
        desired_on = self._get_spindle_fan_automation_desired_on(settings)
        desired_on = self._resolve_manual_fan_override("fan", desired_on)
        relay_board = self.hardware_backend.get_relay_board()
        current_on = self._get_relay_channel_state(relay_board, "fan")

        if current_on == desired_on:
            return
        self.set_relay_output("fan", desired_on, source="automation")

    def _get_spindle_fan_automation_desired_on(self, settings=None):
        ui_settings = settings if isinstance(settings, dict) else self.store.load_ui_settings()
        aftercool_seconds = max(0, int(ui_settings.get("spindleFanAftercoolSeconds", 0) or 0))
        spindle_running_info = self.hardware_backend.get_spindle_running(force_refresh=False)
        spindle_running = bool(spindle_running_info.get("spindleRunning", False))
        now = time.monotonic()

        with self._fan_control_lock:
            previous_running = bool(self._spindle_fan_last_running)
            if spindle_running:
                self._spindle_fan_last_stop_monotonic = None
            elif previous_running:
                self._spindle_fan_last_stop_monotonic = now

            stop_monotonic = self._spindle_fan_last_stop_monotonic
            self._spindle_fan_last_running = spindle_running

        aftercool_active = (
            stop_monotonic is not None
            and aftercool_seconds > 0
            and (now - stop_monotonic) < aftercool_seconds
        )
        return spindle_running or aftercool_active

    def _sync_enclosure_fan_automation(self, settings=None):
        desired_on = self._get_enclosure_fan_automation_desired_on(settings)
        if desired_on is None:
            return

        desired_on = self._resolve_manual_fan_override("enclosureFan", desired_on)
        relay_board = self.hardware_backend.get_relay_board()
        current_on = self._get_relay_channel_state(relay_board, "enclosureFan")

        if current_on == desired_on:
            return
        self.set_relay_output("enclosureFan", desired_on, source="automation")

    def _get_enclosure_fan_automation_desired_on(self, settings=None, relay_board=None):
        ui_settings = settings if isinstance(settings, dict) else self.store.load_ui_settings()
        if not bool(ui_settings.get("enclosureFanAuto", False)):
            return None

        relay_board = relay_board if isinstance(relay_board, dict) else self.hardware_backend.get_relay_board()
        current_on = self._get_relay_channel_state(relay_board, "enclosureFan")
        temperature_payload = self.hardware_backend.get_enclosure_temperature(force_refresh=False)
        if not bool(temperature_payload.get("available")):
            return None

        temperature_c = temperature_payload.get("temperatureC")
        if temperature_c is None:
            return None

        threshold_c = float(ui_settings.get("enclosureFanThresholdC", 40) or 40)
        threshold_to_switch_on = threshold_c
        threshold_to_switch_off = threshold_c - self.ENCLOSURE_FAN_HYSTERESIS_C
        return float(temperature_c) >= (threshold_to_switch_off if current_on else threshold_to_switch_on)

    def _get_manual_override_auto_desired_on(self, output_id):
        if output_id == "fan":
            return self._get_spindle_fan_automation_desired_on()
        if output_id == "enclosureFan":
            relay_board = self.hardware_backend.get_relay_board()
            return self._get_enclosure_fan_automation_desired_on(relay_board=relay_board)
        return None

    def _update_manual_fan_override(self, output_id, manual_on, auto_desired_on):
        if output_id not in self.AUTOMATED_FAN_OUTPUTS:
            return

        manual_on = bool(manual_on)
        allow_conflicting_override = False
        if auto_desired_on is not None:
            auto_desired_on = bool(auto_desired_on)
            if output_id == "enclosureFan":
                allow_conflicting_override = manual_on != auto_desired_on
            elif output_id == "fan":
                allow_conflicting_override = manual_on and not auto_desired_on

        with self._fan_control_lock:
            state = self._fan_manual_overrides[output_id]
            state["manualOn"] = manual_on
            state["lastAutoDesiredOn"] = auto_desired_on
            state["active"] = bool(allow_conflicting_override)

    def _resolve_manual_fan_override(self, output_id, auto_desired_on):
        if output_id not in self.AUTOMATED_FAN_OUTPUTS:
            return bool(auto_desired_on)

        auto_desired_on = bool(auto_desired_on)
        with self._fan_control_lock:
            state = self._fan_manual_overrides[output_id]
            last_auto_desired_on = state.get("lastAutoDesiredOn")

            if not state.get("active", False):
                state["lastAutoDesiredOn"] = auto_desired_on
                return auto_desired_on

            if last_auto_desired_on is None:
                state["lastAutoDesiredOn"] = auto_desired_on
                return bool(state.get("manualOn", False))

            manual_on = bool(state.get("manualOn", False))
            auto_changed = auto_desired_on != bool(last_auto_desired_on)
            state["lastAutoDesiredOn"] = auto_desired_on

            if auto_changed and auto_desired_on != manual_on:
                state["active"] = False
                return auto_desired_on

            return manual_on

    @staticmethod
    def _normalize_automated_fan_output_id(output_id):
        key = str(output_id or "").strip().lower()
        aliases = {
            "fan": "fan",
            "spindlefan": "fan",
            "spindle-fan": "fan",
            "enclosurefan": "enclosureFan",
            "enclosure-fan": "enclosureFan",
            "relay3": "enclosureFan",
            "relay-3": "enclosureFan",
        }
        return aliases.get(key, str(output_id or "").strip())

    @staticmethod
    def _get_relay_channel_state(relay_board, channel_id):
        channels = relay_board.get("channels", {}) if isinstance(relay_board, dict) else {}
        if not isinstance(channels, dict):
            return False

        if channel_id == "enclosureFan":
            channel = channels.get("enclosureFan") or channels.get("relay3") or {}
        else:
            channel = channels.get(channel_id, {})

        return bool(channel.get("on", False))

    def _hardware_estop_worker(self):
        interval_sec = max(0.05, float(self.config.hardware_estop_poll_interval_sec))
        while True:
            try:
                result = self.hardware_backend.sync_hardware_estop(force_refresh=True)
                self._observe_hardware_estop_state(result.get("hardwareEStopEngaged", False))
                if result.get("stateChanged") or result.get("relayChanged"):
                    self.sync_status_indicator()
                elif result.get("relayError"):
                    print(f"Hardware E-Stop relay sync failed: {result['relayError']}", flush=True)
            except Exception as exc:  # pragma: no cover - background safety net
                print(f"Hardware E-Stop monitor failed: {exc}", flush=True)
            time.sleep(interval_sec)

    def _get_axis_movement_states(self):
        axis_loads = self.get_axis_loads(force_refresh=False)
        axes = axis_loads.get("axes", {}) if isinstance(axis_loads, dict) else {}
        movement_states = {}
        for axis in ("x", "y", "z"):
            payload = axes.get(axis, {}) if isinstance(axes, dict) else {}
            try:
                calibrated_load_percent = float(payload.get("calibratedLoadPercent"))
            except (ValueError, TypeError):
                calibrated_load_percent = 0.0
            movement_states[axis] = bool(payload.get("available")) and (
                calibrated_load_percent > self.AXIS_RUNTIME_MOVING_THRESHOLD_PERCENT
            )
        return movement_states

    def _spindle_runtime_worker(self):
        interval_sec = self.SPINDLE_RUNTIME_POLL_INTERVAL_SEC
        while True:
            try:
                spindle_running_info = self.hardware_backend.get_spindle_running(force_refresh=False)
                spindle_running = bool(spindle_running_info.get("spindleRunning", False))
                axis_moving = self._get_axis_movement_states()
                now = time.monotonic()
                persist_required = False
                status_sync_required = False
                warmup_completed_required = False
                warmup_refresh_on_stop = False
                current_runtime_sec = 0

                with self._spindle_runtime_lock:
                    if self._spindle_runtime_sec is None:
                        self._load_spindle_runtime_state_locked()

                    previous_running = bool(self._spindle_runtime_last_running)
                    previous_spindle_running_observed = self._last_spindle_running_observed
                    previous_axis_moving = dict(self._axis_runtime_last_moving)
                    last_sample = self._spindle_runtime_last_sample_monotonic
                    delta_sec = now - last_sample if last_sample is not None else 0.0
                    self._spindle_runtime_last_sample_monotonic = now

                    if 0.0 < delta_sec <= self.SPINDLE_RUNTIME_DELTA_CLAMP_SEC:
                        self._machine_on_time_sec += delta_sec
                        if spindle_running:
                            self._spindle_runtime_sec += delta_sec
                            self._spindle_warmup_running_sec += delta_sec
                        for axis in ("x", "y", "z"):
                            if axis_moving.get(axis, False):
                                self._axis_runtime_sec[axis] += delta_sec
                    elif not spindle_running:
                        self._spindle_warmup_running_sec = 0.0

                    if previous_spindle_running_observed is None:
                        self._last_spindle_running_observed = spindle_running
                        if spindle_running:
                            self._spindle_warmup_refresh_on_stop = self._is_warmup_currently_valid()
                    else:
                        if spindle_running and not previous_spindle_running_observed:
                            self._spindle_start_count = max(0, int(self._spindle_start_count or 0)) + 1
                            persist_required = True
                            self._spindle_warmup_running_sec = 0.0
                            self._spindle_warmup_run_qualified = False
                            self._spindle_warmup_refresh_on_stop = self._is_warmup_currently_valid()
                        self._last_spindle_running_observed = spindle_running

                    if spindle_running and self._spindle_warmup_running_sec >= self.WARMUP_AUTO_COMPLETE_RUNNING_SEC:
                        if not self._spindle_warmup_run_qualified:
                            warmup_completed_required = True
                        self._spindle_warmup_run_qualified = True
                        self._spindle_warmup_refresh_on_stop = True
                    elif not spindle_running:
                        if previous_running and (self._spindle_warmup_run_qualified or self._spindle_warmup_refresh_on_stop):
                            warmup_refresh_on_stop = True
                        self._spindle_warmup_running_sec = 0.0
                        self._spindle_warmup_run_qualified = False
                        self._spindle_warmup_refresh_on_stop = False

                    if spindle_running != previous_running:
                        status_sync_required = True

                    any_runtime_active = spindle_running or any(axis_moving.values())
                    any_runtime_was_active = previous_running or any(previous_axis_moving.values())
                    periodic_persist_due = (
                        (now - self._spindle_runtime_last_persist_monotonic)
                        >= self.SPINDLE_RUNTIME_PERSIST_INTERVAL_SEC
                    )

                    if periodic_persist_due:
                        persist_required = True
                    elif any_runtime_was_active and not any_runtime_active:
                        persist_required = True

                    self._spindle_runtime_last_running = spindle_running
                    self._axis_runtime_last_moving = {
                        axis: bool(axis_moving.get(axis, False))
                        for axis in ("x", "y", "z")
                    }
                    current_runtime_sec = max(0, int(self._spindle_runtime_sec or 0))

                if persist_required:
                    self._persist_spindle_runtime(force=True)
                if warmup_completed_required:
                    self._mark_warmup_completed(current_runtime_sec)
                    status_sync_required = True
                elif warmup_refresh_on_stop:
                    self._mark_warmup_completed(current_runtime_sec)
                    status_sync_required = True
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
    system_info_service = SystemInfoService(config, hardware_backend, backend_app=None)
    return BackendApp(
        config=config,
        store=store,
        wifi_service=wifi_service,
        shutdown_service=shutdown_service,
        system_info_service=system_info_service,
        hardware_backend=hardware_backend,
        machine_status_service=machine_status_service,
        camera_service=camera_service,
    )
