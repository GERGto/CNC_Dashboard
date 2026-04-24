from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

from .common import iso_now_utc


WARMUP_TASK_ID = "spindle-warmup"
WARMUP_VALIDITY_SEC = 2 * 3600


def _normalize_status(raw_status):
    key = str(raw_status or "").strip().lower()
    aliases = {
        "idle": "IDLE",
        "idling": "IDLE",
        "on": "IDLE",
        "ready": "IDLE",
        "running": "RUNNING",
        "run": "RUNNING",
        "active": "RUNNING",
        "error": "ERROR",
        "alarm": "ERROR",
        "estop": "ERROR",
        "e-stop": "ERROR",
        "emergency-stop": "ERROR",
    }
    return aliases.get(key, "IDLE")


def _to_non_negative_int(value, default_value=0):
    try:
        return max(0, int(value))
    except (ValueError, TypeError):
        return int(default_value)


def _add_months(base_date, months):
    year = base_date.year + ((base_date.month - 1 + months) // 12)
    month = ((base_date.month - 1 + months) % 12) + 1
    day = min(
        base_date.day,
        (
            31,
            29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
            31,
            30,
            31,
            30,
            31,
            31,
            30,
            31,
            30,
            31,
        )[month - 1],
    )
    return base_date.replace(year=year, month=month, day=day)


def _has_automatic_interval(task):
    if not isinstance(task, dict):
        return False
    interval_type = str(task.get("intervalType", "")).strip()
    interval_value = task.get("intervalValue")
    if interval_type == "none":
        return False
    if isinstance(interval_value, str) and interval_value.strip() == "-":
        return False
    return interval_type in {"runtimeHours", "calendarMonths", "backendStarts"}


def _parse_iso_datetime(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None

def is_maintenance_task_due(task, spindle_runtime_sec, now=None, backend_start_count=0, spindle_running=False):
    if not _has_automatic_interval(task):
        return False

    completed_at = task.get("lastCompletedAt")
    if not completed_at:
        return True

    task_id = str(task.get("id", "")).strip()
    interval_type = str(task.get("intervalType", "")).strip()
    interval_value = max(1, _to_non_negative_int(task.get("intervalValue"), 1))

    if task_id == WARMUP_TASK_ID:
        completed_dt = _parse_iso_datetime(completed_at)
        if completed_dt is None:
            return True

        if isinstance(now, datetime):
            current_dt = now
        elif completed_dt.tzinfo is not None:
            current_dt = datetime.now(completed_dt.tzinfo)
        else:
            current_dt = datetime.now(timezone.utc).replace(tzinfo=None)

        if completed_dt.tzinfo is None and current_dt.tzinfo is not None:
            current_dt = current_dt.replace(tzinfo=None)
        elif completed_dt.tzinfo is not None and current_dt.tzinfo is None:
            current_dt = current_dt.replace(tzinfo=completed_dt.tzinfo)

        return current_dt >= (completed_dt + timedelta(seconds=WARMUP_VALIDITY_SEC))

    if interval_type == "runtimeHours":
        last_runtime_sec = _to_non_negative_int(task.get("spindleRuntimeSecAtCompletion"), 0)
        elapsed_sec = max(0, _to_non_negative_int(spindle_runtime_sec, 0) - last_runtime_sec)
        return elapsed_sec >= interval_value * 3600

    if interval_type == "backendStarts":
        last_backend_start_count = _to_non_negative_int(task.get("backendStartCountAtCompletion"), 0)
        elapsed_starts = max(0, _to_non_negative_int(backend_start_count, 0) - last_backend_start_count)
        return elapsed_starts >= interval_value

    if interval_type == "calendarMonths":
        try:
            completed_dt = datetime.fromisoformat(str(completed_at).replace("Z", "+00:00"))
        except ValueError:
            return True
        if isinstance(now, datetime):
            current_dt = now
        elif completed_dt.tzinfo is not None:
            current_dt = datetime.now(completed_dt.tzinfo)
        else:
            current_dt = datetime.now(timezone.utc).replace(tzinfo=None)
        return current_dt >= _add_months(completed_dt, interval_value)

    return False


class MachineStatusService:
    STATUS_COLORS = {
        "idle": {"r": 127, "g": 127, "b": 127},
        "on": {"r": 255, "g": 255, "b": 255},
        "warning": {"r": 255, "g": 96, "b": 0},
        "running": {"r": 0, "g": 255, "b": 0},
        "eStop": {"r": 255, "g": 0, "b": 0},
    }

    def __init__(self):
        self._lock = threading.Lock()
        self._reported_status = "IDLE"
        self._reported_source = "backend"
        self._reported_at = iso_now_utc()

    def update_reported_status(self, status, source="api"):
        normalized_status = _normalize_status(status)
        normalized_source = str(source or "api").strip() or "api"
        updated_at = iso_now_utc()
        with self._lock:
            self._reported_status = normalized_status
            self._reported_source = normalized_source
            self._reported_at = updated_at
        return self.get_reported_status()

    def get_reported_status(self):
        with self._lock:
            return {
                "status": self._reported_status,
                "source": self._reported_source,
                "reportedAt": self._reported_at,
            }

    def build_snapshot(self, spindle_runtime_sec, maintenance_tasks, relay_board, backend_start_count=0):
        reported = self.get_reported_status()
        runtime_sec = _to_non_negative_int(spindle_runtime_sec, 0)
        spindle_running = self._is_spindle_running(relay_board)
        due_task_ids = self._collect_due_task_ids(
            maintenance_tasks,
            runtime_sec,
            backend_start_count,
            spindle_running=spindle_running,
        )
        maintenance_due = bool(due_task_ids)
        warmup_due = WARMUP_TASK_ID in due_task_ids
        hardware_estop_engaged = self._is_hardware_estop_engaged(relay_board)
        hardware_estop_input_ids = self._get_hardware_estop_input_ids(relay_board)
        spindle_running_input_ids = self._get_spindle_running_input_ids(relay_board)
        estop_engaged = self._is_estop_engaged(relay_board)
        estop_reset_locked = hardware_estop_engaged

        effective_status = "IDLE"
        effective_reason = "machine-on"
        indicator_state = "idle"

        if estop_engaged:
            effective_status = "ERROR"
            effective_reason = "hardware-e-stop" if hardware_estop_engaged else "e-stop"
            indicator_state = "eStop"
        elif reported["status"] == "ERROR":
            effective_status = "ERROR"
            effective_reason = "reported-error"
            indicator_state = "eStop"
        elif maintenance_due:
            effective_status = "WARNING"
            effective_reason = "warmup-due" if warmup_due else "maintenance-due"
            indicator_state = "warning"
        elif spindle_running:
            effective_status = "RUNNING"
            effective_reason = "spindle-running-input"
            indicator_state = "running"
        elif reported["status"] == "RUNNING":
            effective_status = "RUNNING"
            effective_reason = "reported-running"
            indicator_state = "running"

        return {
            "reportedStatus": reported["status"],
            "reportedSource": reported["source"],
            "reportedAt": reported["reportedAt"],
            "spindleRuntimeSec": runtime_sec,
            "backendStartCount": _to_non_negative_int(backend_start_count, 0),
            "warmupDue": warmup_due,
            "maintenanceDue": maintenance_due,
            "maintenanceDueTaskIds": due_task_ids,
            "eStopEngaged": estop_engaged,
            "hardwareEStopEngaged": hardware_estop_engaged,
            "hardwareEStopInputIds": hardware_estop_input_ids,
            "eStopResetLocked": estop_reset_locked,
            "spindleRunning": spindle_running,
            "spindleRunningInputIds": spindle_running_input_ids,
            "effectiveStatus": effective_status,
            "effectiveReason": effective_reason,
            "indicator": {
                "state": indicator_state,
                "color": dict(self.STATUS_COLORS[indicator_state]),
                "reason": effective_reason,
            },
        }

    def _collect_due_task_ids(self, maintenance_tasks, spindle_runtime_sec, backend_start_count=0, spindle_running=False):
        due_task_ids = []
        for task in maintenance_tasks if isinstance(maintenance_tasks, list) else []:
            if not isinstance(task, dict):
                continue
            task_id = str(task.get("id", "")).strip()
            if not task_id:
                continue
            if is_maintenance_task_due(
                task,
                spindle_runtime_sec,
                backend_start_count=backend_start_count,
                spindle_running=spindle_running,
            ):
                due_task_ids.append(task_id)
        return due_task_ids

    def _is_estop_engaged(self, relay_board):
        estop = self._get_estop_channel(relay_board)
        return bool(
            estop.get("engaged", estop.get("on", False))
            or estop.get("hardwareInputEngaged", False)
        )

    def _is_hardware_estop_engaged(self, relay_board):
        estop = self._get_estop_channel(relay_board)
        return bool(estop.get("hardwareInputEngaged", False))

    def _get_hardware_estop_input_ids(self, relay_board):
        estop = self._get_estop_channel(relay_board)
        return [
            str(input_id)
            for input_id in estop.get("triggeredInputIds", [])
            if str(input_id).strip()
        ]

    def _get_estop_channel(self, relay_board):
        channels = relay_board.get("channels", {}) if isinstance(relay_board, dict) else {}
        return channels.get("eStop", {}) if isinstance(channels, dict) else {}

    def _is_spindle_running(self, relay_board):
        safety_inputs = self._get_safety_inputs(relay_board)
        return bool(safety_inputs.get("spindleRunning", False))

    def _get_spindle_running_input_ids(self, relay_board):
        safety_inputs = self._get_safety_inputs(relay_board)
        return [
            str(input_id)
            for input_id in safety_inputs.get("spindleRunningInputIds", [])
            if str(input_id).strip()
        ]

    def _get_safety_inputs(self, relay_board):
        return relay_board.get("safetyInputs", {}) if isinstance(relay_board, dict) else {}
