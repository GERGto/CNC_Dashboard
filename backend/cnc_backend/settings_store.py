from __future__ import annotations

import os
from copy import deepcopy

from .common import clamp, iso_now_utc, read_json_dict, to_int, write_json_dict


class SettingsStore:
    def __init__(self, config):
        self.config = config

    def default_maintenance_tasks(self):
        now_iso = iso_now_utc()
        return [
            {
                "id": "axes-grease",
                "title": "Achsen Fetten",
                "intervalType": "runtimeHours",
                "intervalValue": 8,
                "effortMin": 5,
                "description": "Fettpunkte der X/Y/Z-Achsen abschmieren.",
                "steps": [
                    {
                        "instruction": "Schmierpresse befÃ¼llen und auf die Schmiernippel der Achsen ansetzen.",
                        "image": "assets/images/presse.png",
                        "imageAlt": "Schmierpresse fÃ¼r die Achsenschmierung",
                    },
                    {
                        "instruction": "Je Schmierpunkt 1 bis 2 HÃ¼be ausfÃ¼hren und auf gleichmÃ¤ÃŸigen Fettfluss achten.",
                    },
                    {
                        "instruction": "ÃœberschÃ¼ssiges Fett entfernen und Schmierstellen auf Dichtheit prÃ¼fen.",
                    },
                ],
                "lastCompletedAt": None,
                "spindleRuntimeSecAtCompletion": 0,
            },
            {
                "id": "coolant-check",
                "title": "KÃ¼hlmittelstand prÃ¼fen",
                "intervalType": "calendarMonths",
                "intervalValue": 1,
                "effortMin": 3,
                "description": "KÃ¼hlmittelstand kontrollieren und bei Bedarf nachfÃ¼llen.",
                "lastCompletedAt": now_iso,
                "spindleRuntimeSecAtCompletion": 0,
            },
            {
                "id": "emergency-stop-test",
                "title": "Not-Aus prÃ¼fen",
                "intervalType": "calendarMonths",
                "intervalValue": 3,
                "effortMin": 10,
                "description": "Funktion aller Not-Aus-Schalter prÃ¼fen.",
                "lastCompletedAt": now_iso,
                "spindleRuntimeSecAtCompletion": 0,
            },
            {
                "id": "lubrication-lines-check",
                "title": "Schmierleitungen prÃ¼fen",
                "intervalType": "calendarMonths",
                "intervalValue": 6,
                "effortMin": 8,
                "description": "SichtprÃ¼fung der Schmierleitungen auf Undichtigkeiten.",
                "lastCompletedAt": now_iso,
                "spindleRuntimeSecAtCompletion": 0,
            },
        ]

    def default_ui_settings(self):
        return {
            "graphWindowSec": 60,
            "rgbStripBrightness": 75,
            "fanSpeed": 40,
            "fanAuto": False,
            "wifiSsid": "",
            "wifiPassword": "",
            "wifiAutoConnect": False,
            "wifiConnected": False,
            "axisVisibility": {
                "spindle": True,
                "x": True,
                "y": True,
                "z": True,
            },
            "axisLoadCalibration": {
                "x": {"minA": 0.0, "maxA": 10.0},
                "y": {"minA": 0.0, "maxA": 10.0},
                "z": {"minA": 0.0, "maxA": 10.0},
            },
        }

    def default_machine_stats(self):
        return {
            "spindleRuntimeSec": 0,
        }

    def normalize_axis_visibility(self, raw_value):
        defaults = self.default_ui_settings()["axisVisibility"]
        if not isinstance(raw_value, dict):
            return deepcopy(defaults)

        normalized = {}
        for axis in defaults.keys():
            if axis in raw_value:
                normalized[axis] = bool(raw_value[axis])
            else:
                normalized[axis] = defaults[axis]
        return normalized

    def normalize_axis_load_calibration(self, raw_value):
        defaults = self.default_ui_settings()["axisLoadCalibration"]
        if not isinstance(raw_value, dict):
            return deepcopy(defaults)

        normalized = {}
        for axis, axis_defaults in defaults.items():
            axis_value = raw_value.get(axis, {})
            if not isinstance(axis_value, dict):
                axis_value = {}
            try:
                min_a = float(axis_value.get("minA", axis_defaults["minA"]))
            except (ValueError, TypeError):
                min_a = float(axis_defaults["minA"])
            try:
                max_a = float(axis_value.get("maxA", axis_defaults["maxA"]))
            except (ValueError, TypeError):
                max_a = float(axis_defaults["maxA"])

            min_a = max(0.0, min(10.0, min_a))
            max_a = max(0.0, min(10.0, max_a))
            if max_a < min_a:
                max_a = min_a

            normalized[axis] = {
                "minA": round(min_a, 2),
                "maxA": round(max_a, 2),
            }
        return normalized

    def sanitize_spindle_runtime_sec(self, raw_value):
        try:
            value = int(raw_value)
        except (ValueError, TypeError):
            value = 0
        return max(0, value)

    def normalize_maintenance_tasks(self, raw_tasks):
        defaults = self.default_maintenance_tasks()
        defaults_by_id = {task["id"]: task for task in defaults}
        if not isinstance(raw_tasks, list):
            return defaults

        normalized = []
        seen_ids = set()
        for item in raw_tasks:
            if not isinstance(item, dict):
                continue
            task_id = str(item.get("id", "")).strip()
            if not task_id or task_id in seen_ids:
                continue
            seen_ids.add(task_id)

            template = defaults_by_id.get(
                task_id,
                {
                    "id": task_id,
                    "title": task_id,
                    "intervalType": "runtimeHours",
                    "intervalValue": 8,
                    "effortMin": 5,
                    "description": "",
                    "steps": [],
                    "lastCompletedAt": None,
                    "spindleRuntimeSecAtCompletion": 0,
                },
            )

            interval_type_raw = str(item.get("intervalType", template["intervalType"])).strip()
            raw_interval_value = item.get("intervalValue", template["intervalValue"])

            interval_value_marker = raw_interval_value
            if isinstance(interval_value_marker, str):
                interval_value_marker = interval_value_marker.strip()

            interval_disabled = interval_type_raw == "none" or interval_value_marker == "-"

            if interval_disabled:
                interval_type = "none"
                interval_value = "-"
            else:
                interval_type = interval_type_raw
                if interval_type not in ("runtimeHours", "calendarMonths"):
                    interval_type = template["intervalType"]

                try:
                    interval_value = int(raw_interval_value)
                except (ValueError, TypeError):
                    try:
                        interval_value = int(template["intervalValue"])
                    except (ValueError, TypeError):
                        interval_value = 1
                interval_value = max(1, interval_value)

            try:
                effort_min = int(item.get("effortMin", template["effortMin"]))
            except (ValueError, TypeError):
                effort_min = int(template["effortMin"])
            effort_min = max(1, effort_min)

            completed_at = item.get("lastCompletedAt", template["lastCompletedAt"])
            if completed_at is not None:
                completed_at = str(completed_at)

            try:
                runtime_at_completion = int(
                    item.get("spindleRuntimeSecAtCompletion", template["spindleRuntimeSecAtCompletion"])
                )
            except (ValueError, TypeError):
                runtime_at_completion = int(template["spindleRuntimeSecAtCompletion"])
            runtime_at_completion = max(0, runtime_at_completion)

            raw_steps = item.get("steps", template.get("steps", []))
            steps = []
            if isinstance(raw_steps, list):
                for step in raw_steps:
                    if not isinstance(step, dict):
                        continue
                    instruction = str(
                        step.get("instruction", step.get("text", step.get("title", "")))
                    ).strip()
                    if not instruction:
                        continue
                    step_item = {
                        "instruction": instruction,
                    }
                    image = str(step.get("image", "")).strip()
                    if image:
                        step_item["image"] = image
                    image_alt = str(step.get("imageAlt", "")).strip()
                    if image_alt:
                        step_item["imageAlt"] = image_alt
                    steps.append(step_item)

            normalized.append(
                {
                    "id": task_id,
                    "title": str(item.get("title", template["title"])),
                    "intervalType": interval_type,
                    "intervalValue": interval_value,
                    "effortMin": effort_min,
                    "description": str(item.get("description", template["description"])),
                    "steps": steps,
                    "lastCompletedAt": completed_at,
                    "spindleRuntimeSecAtCompletion": runtime_at_completion,
                }
            )

        if not normalized:
            return defaults
        return normalized

    def normalize_ui_settings(self, raw_data):
        defaults = self.default_ui_settings()
        data = raw_data if isinstance(raw_data, dict) else {}
        wifi_ssid = str(data.get("wifiSsid", defaults["wifiSsid"])).strip()
        wifi_password = str(data.get("wifiPassword", defaults["wifiPassword"]))
        rgb_strip_brightness = data.get("rgbStripBrightness", data.get("lightBrightness", defaults["rgbStripBrightness"]))
        normalized = {
            "graphWindowSec": clamp(
                to_int(data.get("graphWindowSec", defaults["graphWindowSec"]), defaults["graphWindowSec"]),
                10,
                120,
            ),
            "rgbStripBrightness": clamp(
                to_int(rgb_strip_brightness, defaults["rgbStripBrightness"]),
                10,
                100,
            ),
            "fanSpeed": clamp(
                to_int(data.get("fanSpeed", defaults["fanSpeed"]), defaults["fanSpeed"]),
                0,
                100,
            ),
            "fanAuto": bool(data.get("fanAuto", defaults["fanAuto"])),
            "wifiSsid": wifi_ssid,
            "wifiPassword": wifi_password,
            "wifiAutoConnect": bool(data.get("wifiAutoConnect", defaults["wifiAutoConnect"])),
            "wifiConnected": False,
            "axisVisibility": self.normalize_axis_visibility(data.get("axisVisibility")),
            "axisLoadCalibration": self.normalize_axis_load_calibration(data.get("axisLoadCalibration")),
        }
        return normalized

    def load_legacy_settings(self):
        return read_json_dict(self.config.settings_path)

    def load_ui_settings(self):
        return self.normalize_ui_settings(read_json_dict(self.config.settings_path))

    def save_ui_settings(self, patch):
        current = self.load_ui_settings()
        merged = {**current, **(patch if isinstance(patch, dict) else {})}
        normalized = self.normalize_ui_settings(merged)
        write_json_dict(self.config.settings_path, normalized)
        return normalized

    def load_machine_stats(self, fallback=None):
        defaults = self.default_machine_stats()
        raw = read_json_dict(self.config.machine_stats_path)
        if not raw and isinstance(fallback, dict):
            raw = {"spindleRuntimeSec": fallback.get("spindleRuntimeSec", defaults["spindleRuntimeSec"])}
        return {
            "spindleRuntimeSec": self.sanitize_spindle_runtime_sec(
                raw.get("spindleRuntimeSec", defaults["spindleRuntimeSec"])
            )
        }

    def save_machine_stats(self, patch):
        current = self.load_machine_stats()
        merged = {**current, **(patch if isinstance(patch, dict) else {})}
        normalized = {
            "spindleRuntimeSec": self.sanitize_spindle_runtime_sec(merged.get("spindleRuntimeSec", 0))
        }
        write_json_dict(self.config.machine_stats_path, normalized)
        return normalized

    def load_maintenance_tasks(self, fallback=None):
        raw = read_json_dict(self.config.tasks_path)
        raw_tasks = raw.get("maintenanceTasks")
        if not isinstance(raw_tasks, list) and isinstance(fallback, dict):
            raw_tasks = fallback.get("maintenanceTasks")
        return self.normalize_maintenance_tasks(raw_tasks)

    def save_maintenance_tasks(self, tasks):
        normalized = self.normalize_maintenance_tasks(tasks)
        write_json_dict(self.config.tasks_path, {"maintenanceTasks": normalized})
        return normalized

    def ensure_split_storage(self):
        legacy = read_json_dict(self.config.settings_path)

        self.save_ui_settings(legacy)

        if self.config.tasks_path and os.path.exists(self.config.tasks_path):
            self.save_maintenance_tasks(self.load_maintenance_tasks())
        else:
            if isinstance(legacy.get("maintenanceTasks"), list):
                self.save_maintenance_tasks(legacy.get("maintenanceTasks"))
            else:
                self.save_maintenance_tasks(self.default_maintenance_tasks())

        if self.config.machine_stats_path and os.path.exists(self.config.machine_stats_path):
            self.save_machine_stats(self.load_machine_stats())
        else:
            self.save_machine_stats(
                {
                    "spindleRuntimeSec": legacy.get(
                        "spindleRuntimeSec", self.default_machine_stats()["spindleRuntimeSec"]
                    )
                }
            )
