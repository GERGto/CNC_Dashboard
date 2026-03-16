import json
import math
import os
import subprocess
import time
from copy import deepcopy
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs


PORT = int(os.getenv("PORT", "8080"))
DEFAULT_INTERVAL_MS = int(os.getenv("AXES_INTERVAL_MS", "250"))
SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "settings.json")
TASKS_PATH = os.path.join(os.path.dirname(__file__), "tasks.json")
MACHINE_STATS_PATH = os.path.join(os.path.dirname(__file__), "machine_stats.json")


def iso_now_utc():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_maintenance_tasks():
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
                    "instruction": "Schmierpresse befüllen und auf die Schmiernippel der Achsen ansetzen.",
                    "image": "assets/images/presse.png",
                    "imageAlt": "Schmierpresse für die Achsenschmierung",
                },
                {
                    "instruction": "Je Schmierpunkt 1 bis 2 Hübe ausführen und auf gleichmäßigen Fettfluss achten.",
                },
                {
                    "instruction": "Überschüssiges Fett entfernen und Schmierstellen auf Dichtheit prüfen.",
                },
            ],
            "lastCompletedAt": None,
            "spindleRuntimeSecAtCompletion": 0,
        },
        {
            "id": "coolant-check",
            "title": "Kühlmittelstand prüfen",
            "intervalType": "calendarMonths",
            "intervalValue": 1,
            "effortMin": 3,
            "description": "Kühlmittelstand kontrollieren und bei Bedarf nachfüllen.",
            "lastCompletedAt": now_iso,
            "spindleRuntimeSecAtCompletion": 0,
        },
        {
            "id": "emergency-stop-test",
            "title": "Not-Aus prüfen",
            "intervalType": "calendarMonths",
            "intervalValue": 3,
            "effortMin": 10,
            "description": "Funktion aller Not-Aus-Schalter prüfen.",
            "lastCompletedAt": now_iso,
            "spindleRuntimeSecAtCompletion": 0,
        },
        {
            "id": "lubrication-lines-check",
            "title": "Schmierleitungen prüfen",
            "intervalType": "calendarMonths",
            "intervalValue": 6,
            "effortMin": 8,
            "description": "Sichtprüfung der Schmierleitungen auf Undichtigkeiten.",
            "lastCompletedAt": now_iso,
            "spindleRuntimeSecAtCompletion": 0,
        },
    ]


def default_ui_settings():
    return {
        "graphWindowSec": 60,
        "lightBrightness": 75,
        "fanSpeed": 40,
        "fanAuto": False,
        "wifiSsid": "",
        "wifiPassword": "",
        "wifiAutoConnect": False,
        "wifiConnected": True,
        "axisVisibility": {
            "spindle": True,
            "x": True,
            "y": True,
            "z": True,
        },
    }


def default_machine_stats():
    return {
        "spindleRuntimeSec": 0,
    }


def clamp(value, min_value, max_value):
    return max(min_value, min(max_value, value))


def normalize_axis_visibility(raw_value):
    defaults = default_ui_settings()["axisVisibility"]
    if not isinstance(raw_value, dict):
        return deepcopy(defaults)

    normalized = {}
    for axis in defaults.keys():
        if axis in raw_value:
            normalized[axis] = bool(raw_value[axis])
        else:
            normalized[axis] = defaults[axis]
    return normalized


def sanitize_spindle_runtime_sec(raw_value):
    try:
        value = int(raw_value)
    except (ValueError, TypeError):
        value = 0
    return max(0, value)


def to_int(raw_value, default_value):
    try:
        return int(raw_value)
    except (ValueError, TypeError):
        return int(default_value)


def read_json_dict(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            if isinstance(data, dict):
                return data
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    return {}


def write_json_dict(path, data):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def normalize_maintenance_tasks(raw_tasks):
    defaults = default_maintenance_tasks()
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

        template = defaults_by_id.get(task_id, {
            "id": task_id,
            "title": task_id,
            "intervalType": "runtimeHours",
            "intervalValue": 8,
            "effortMin": 5,
            "description": "",
            "steps": [],
            "lastCompletedAt": None,
            "spindleRuntimeSecAtCompletion": 0,
        })

        interval_type_raw = str(item.get("intervalType", template["intervalType"])).strip()
        raw_interval_value = item.get("intervalValue", template["intervalValue"])

        interval_value_marker = raw_interval_value
        if isinstance(interval_value_marker, str):
            interval_value_marker = interval_value_marker.strip()

        interval_disabled = (
            interval_type_raw == "none"
            or interval_value_marker == "-"
        )

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
            runtime_at_completion = int(item.get("spindleRuntimeSecAtCompletion", template["spindleRuntimeSecAtCompletion"]))
        except (ValueError, TypeError):
            runtime_at_completion = int(template["spindleRuntimeSecAtCompletion"])
        runtime_at_completion = max(0, runtime_at_completion)

        raw_steps = item.get("steps", template.get("steps", []))
        steps = []
        if isinstance(raw_steps, list):
            for step in raw_steps:
                if not isinstance(step, dict):
                    continue
                instruction = str(step.get("instruction", step.get("text", step.get("title", "")))).strip()
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

        normalized.append({
            "id": task_id,
            "title": str(item.get("title", template["title"])),
            "intervalType": interval_type,
            "intervalValue": interval_value,
            "effortMin": effort_min,
            "description": str(item.get("description", template["description"])),
            "steps": steps,
            "lastCompletedAt": completed_at,
            "spindleRuntimeSecAtCompletion": runtime_at_completion,
        })

    if not normalized:
        return defaults
    return normalized


def json_response(handler, status, body):
    payload = json.dumps(body).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(payload)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(payload)


def send_sse(handler, event, data):
    handler.wfile.write(f"event: {event}\n".encode("utf-8"))
    handler.wfile.write(f"data: {json.dumps(data)}\n\n".encode("utf-8"))
    handler.wfile.flush()


def _dedupe_strings(values):
    unique = []
    seen = set()
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return unique


def scan_wifi_networks():
    candidates = []

    # Linux (NetworkManager)
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "SSID", "dev", "wifi", "list"],
            capture_output=True,
            text=True,
            check=False,
            timeout=3,
        )
        if result.returncode == 0:
            candidates.extend([line.strip() for line in (result.stdout or "").splitlines()])
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        pass

    # Linux (iwlist)
    if not candidates:
        try:
            result = subprocess.run(
                ["iwlist", "scan"],
                capture_output=True,
                text=True,
                check=False,
                timeout=4,
            )
            if result.returncode == 0:
                for line in (result.stdout or "").splitlines():
                    line = line.strip()
                    if "ESSID:" not in line:
                        continue
                    essid = line.split("ESSID:", 1)[1].strip().strip('"')
                    candidates.append(essid)
        except (FileNotFoundError, OSError, subprocess.SubprocessError):
            pass

    # Windows
    if not candidates and os.name == "nt":
        try:
            result = subprocess.run(
                ["netsh", "wlan", "show", "networks", "mode=Bssid"],
                capture_output=True,
                text=True,
                check=False,
                timeout=4,
            )
            if result.returncode == 0:
                for line in (result.stdout or "").splitlines():
                    line = line.strip()
                    if not line.startswith("SSID "):
                        continue
                    parts = line.split(":", 1)
                    if len(parts) != 2:
                        continue
                    candidates.append(parts[1].strip())
        except (FileNotFoundError, OSError, subprocess.SubprocessError):
            pass

    networks = _dedupe_strings(candidates)
    saved_ssid = load_ui_settings().get("wifiSsid", "")
    if saved_ssid:
        networks = _dedupe_strings(networks + [saved_ssid])
    return networks


def mock_axes_load(t_ms):
    def base(i):
        value = (math.sin(t_ms / 700.0 + i) * 40.0 + 50.0)
        return round(value, 1)

    return {
        "spindle": base(0),
        "x": base(1),
        "y": base(2),
        "z": base(3),
    }


def normalize_ui_settings(raw_data):
    defaults = default_ui_settings()
    data = raw_data if isinstance(raw_data, dict) else {}
    wifi_ssid = str(data.get("wifiSsid", defaults["wifiSsid"])).strip()
    wifi_password = str(data.get("wifiPassword", defaults["wifiPassword"]))
    normalized = {
        "graphWindowSec": clamp(to_int(data.get("graphWindowSec", defaults["graphWindowSec"]), defaults["graphWindowSec"]), 10, 120),
        "lightBrightness": clamp(to_int(data.get("lightBrightness", defaults["lightBrightness"]), defaults["lightBrightness"]), 0, 100),
        "fanSpeed": clamp(to_int(data.get("fanSpeed", defaults["fanSpeed"]), defaults["fanSpeed"]), 0, 100),
        "fanAuto": bool(data.get("fanAuto", defaults["fanAuto"])),
        "wifiSsid": wifi_ssid,
        "wifiPassword": wifi_password,
        "wifiAutoConnect": bool(data.get("wifiAutoConnect", defaults["wifiAutoConnect"])),
        "wifiConnected": bool(data.get("wifiConnected", defaults["wifiConnected"])),
        "axisVisibility": normalize_axis_visibility(data.get("axisVisibility")),
    }
    return normalized


def load_ui_settings():
    return normalize_ui_settings(read_json_dict(SETTINGS_PATH))


def save_ui_settings(patch):
    current = load_ui_settings()
    merged = {**current, **(patch if isinstance(patch, dict) else {})}
    normalized = normalize_ui_settings(merged)
    write_json_dict(SETTINGS_PATH, normalized)
    return normalized


def load_machine_stats(fallback=None):
    defaults = default_machine_stats()
    raw = read_json_dict(MACHINE_STATS_PATH)
    if not raw and isinstance(fallback, dict):
        raw = {"spindleRuntimeSec": fallback.get("spindleRuntimeSec", defaults["spindleRuntimeSec"])}
    return {
        "spindleRuntimeSec": sanitize_spindle_runtime_sec(raw.get("spindleRuntimeSec", defaults["spindleRuntimeSec"]))
    }


def save_machine_stats(patch):
    current = load_machine_stats()
    merged = {**current, **(patch if isinstance(patch, dict) else {})}
    normalized = {
        "spindleRuntimeSec": sanitize_spindle_runtime_sec(merged.get("spindleRuntimeSec", 0))
    }
    write_json_dict(MACHINE_STATS_PATH, normalized)
    return normalized


def load_maintenance_tasks(fallback=None):
    raw = read_json_dict(TASKS_PATH)
    raw_tasks = raw.get("maintenanceTasks")
    if not isinstance(raw_tasks, list) and isinstance(fallback, dict):
        raw_tasks = fallback.get("maintenanceTasks")
    return normalize_maintenance_tasks(raw_tasks)


def save_maintenance_tasks(tasks):
    normalized = normalize_maintenance_tasks(tasks)
    write_json_dict(TASKS_PATH, {"maintenanceTasks": normalized})
    return normalized


def load_settings():
    legacy = read_json_dict(SETTINGS_PATH)
    ui_settings = load_ui_settings()
    machine_stats = load_machine_stats(legacy)
    maintenance_tasks = load_maintenance_tasks(legacy)
    return {
        **ui_settings,
        **machine_stats,
        "maintenanceTasks": maintenance_tasks,
    }


def save_settings(patch):
    payload = patch if isinstance(patch, dict) else {}

    ui_keys = {
        "graphWindowSec",
        "lightBrightness",
        "fanSpeed",
        "fanAuto",
        "wifiSsid",
        "wifiPassword",
        "wifiAutoConnect",
        "wifiConnected",
        "axisVisibility",
    }
    ui_patch = {k: payload[k] for k in ui_keys if k in payload}
    if ui_patch:
        save_ui_settings(ui_patch)

    if "spindleRuntimeSec" in payload:
        save_machine_stats({"spindleRuntimeSec": payload.get("spindleRuntimeSec")})

    if "maintenanceTasks" in payload:
        save_maintenance_tasks(payload.get("maintenanceTasks"))

    return load_settings()


def ensure_split_storage():
    legacy = read_json_dict(SETTINGS_PATH)

    # Keep settings.json focused on UI settings.
    save_ui_settings(legacy)

    if os.path.exists(TASKS_PATH):
        save_maintenance_tasks(load_maintenance_tasks())
    else:
        if isinstance(legacy.get("maintenanceTasks"), list):
            save_maintenance_tasks(legacy.get("maintenanceTasks"))
        else:
            save_maintenance_tasks(default_maintenance_tasks())

    if os.path.exists(MACHINE_STATS_PATH):
        save_machine_stats(load_machine_stats())
    else:
        save_machine_stats({
            "spindleRuntimeSec": legacy.get("spindleRuntimeSec", default_machine_stats()["spindleRuntimeSec"])
        })


class Handler(BaseHTTPRequestHandler):
    def handle_one_request(self):
        try:
            return super().handle_one_request()
        except ConnectionAbortedError:
            return

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/health":
            return json_response(self, 200, {"status": "ok", "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})

        if path == "/api/axes":
            return json_response(self, 200, {"timestamp": int(time.time() * 1000), "axes": mock_axes_load(int(time.time() * 1000))})

        if path == "/api/axes/stream":
            params = parse_qs(parsed.query or "")
            interval_ms = DEFAULT_INTERVAL_MS
            if "intervalMs" in params:
                try:
                    interval_ms = int(params["intervalMs"][0])
                except (ValueError, TypeError):
                    interval_ms = DEFAULT_INTERVAL_MS
            interval_ms = clamp(interval_ms, 50, 5000)

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            try:
                while True:
                    payload = {"timestamp": int(time.time() * 1000), "axes": mock_axes_load(int(time.time() * 1000))}
                    send_sse(self, "axes", payload)
                    time.sleep(interval_ms / 1000.0)
            except (BrokenPipeError, ConnectionResetError):
                return
            except Exception:
                return

        if path == "/api/settings":
            return json_response(self, 200, load_settings())

        if path == "/api/wifi/networks":
            return json_response(self, 200, {"networks": scan_wifi_networks()})

        if path == "/api/maintenance/tasks":
            settings = load_settings()
            return json_response(self, 200, {"tasks": settings.get("maintenanceTasks", [])})

        json_response(self, 404, {"error": "Not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/shutdown":
            return json_response(self, 202, {"ok": True, "message": "Shutdown scheduled (mock)"})
        if parsed.path == "/api/wifi/connect":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length) if length > 0 else b"{}"
                payload = json.loads(raw.decode("utf-8")) if raw else {}
                if not isinstance(payload, dict):
                    return json_response(self, 400, {"error": "Invalid payload"})
            except (ValueError, json.JSONDecodeError):
                return json_response(self, 400, {"error": "Invalid payload"})

            ssid = str(payload.get("ssid", "")).strip()
            password = str(payload.get("password", ""))
            auto_connect = payload.get("autoConnect", False)

            if not ssid:
                return json_response(self, 400, {"error": "SSID is required"})
            if not isinstance(auto_connect, bool):
                if isinstance(auto_connect, (int, float)) and auto_connect in (0, 1):
                    auto_connect = bool(auto_connect)
                else:
                    return json_response(self, 400, {"error": "Invalid autoConnect"})

            # Simuliert eine reale Verbindungsdauer für UI-Feedback-Tests.
            time.sleep(3)

            saved = save_settings({
                "wifiSsid": ssid,
                "wifiPassword": password,
                "wifiAutoConnect": auto_connect,
                "wifiConnected": True,
            })
            return json_response(self, 200, {
                "ok": True,
                "connected": bool(saved.get("wifiConnected", False)),
                "ssid": str(saved.get("wifiSsid", "")),
                "autoConnect": bool(saved.get("wifiAutoConnect", False)),
            })

        if parsed.path == "/api/wifi/disconnect":
            saved = save_settings({"wifiConnected": False})
            return json_response(self, 200, {
                "ok": True,
                "connected": bool(saved.get("wifiConnected", False)),
                "ssid": str(saved.get("wifiSsid", "")),
                "autoConnect": bool(saved.get("wifiAutoConnect", False)),
            })

        if parsed.path == "/api/settings":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length) if length > 0 else b"{}"
                payload = json.loads(raw.decode("utf-8")) if raw else {}
                if not isinstance(payload, dict):
                    return json_response(self, 400, {"error": "Invalid payload"})
            except (ValueError, json.JSONDecodeError):
                return json_response(self, 400, {"error": "Invalid payload"})

            updated = {}
            if "graphWindowSec" in payload:
                try:
                    value = int(payload["graphWindowSec"])
                    updated["graphWindowSec"] = clamp(value, 10, 120)
                except (ValueError, TypeError):
                    return json_response(self, 400, {"error": "Invalid graphWindowSec"})
            if "lightBrightness" in payload:
                try:
                    value = int(payload["lightBrightness"])
                    updated["lightBrightness"] = clamp(value, 0, 100)
                except (ValueError, TypeError):
                    return json_response(self, 400, {"error": "Invalid lightBrightness"})
            if "fanSpeed" in payload:
                try:
                    value = int(payload["fanSpeed"])
                    updated["fanSpeed"] = clamp(value, 0, 100)
                except (ValueError, TypeError):
                    return json_response(self, 400, {"error": "Invalid fanSpeed"})
            if "fanAuto" in payload:
                value = payload["fanAuto"]
                if isinstance(value, bool):
                    updated["fanAuto"] = value
                elif isinstance(value, (int, float)) and value in (0, 1):
                    updated["fanAuto"] = bool(value)
                else:
                    return json_response(self, 400, {"error": "Invalid fanAuto"})
            if "wifiSsid" in payload:
                value = payload["wifiSsid"]
                if not isinstance(value, str):
                    return json_response(self, 400, {"error": "Invalid wifiSsid"})
                updated["wifiSsid"] = value.strip()
            if "wifiPassword" in payload:
                value = payload["wifiPassword"]
                if not isinstance(value, str):
                    return json_response(self, 400, {"error": "Invalid wifiPassword"})
                updated["wifiPassword"] = value
            if "wifiAutoConnect" in payload:
                value = payload["wifiAutoConnect"]
                if isinstance(value, bool):
                    updated["wifiAutoConnect"] = value
                elif isinstance(value, (int, float)) and value in (0, 1):
                    updated["wifiAutoConnect"] = bool(value)
                else:
                    return json_response(self, 400, {"error": "Invalid wifiAutoConnect"})
            if "wifiConnected" in payload:
                value = payload["wifiConnected"]
                if isinstance(value, bool):
                    updated["wifiConnected"] = value
                elif isinstance(value, (int, float)) and value in (0, 1):
                    updated["wifiConnected"] = bool(value)
                else:
                    return json_response(self, 400, {"error": "Invalid wifiConnected"})
            if "axisVisibility" in payload:
                if not isinstance(payload["axisVisibility"], dict):
                    return json_response(self, 400, {"error": "Invalid axisVisibility"})
                updated["axisVisibility"] = normalize_axis_visibility(payload["axisVisibility"])
            if "spindleRuntimeSec" in payload:
                try:
                    value = int(payload["spindleRuntimeSec"])
                    if value < 0:
                        raise ValueError()
                    updated["spindleRuntimeSec"] = value
                except (ValueError, TypeError):
                    return json_response(self, 400, {"error": "Invalid spindleRuntimeSec"})
            if "maintenanceTasks" in payload:
                if not isinstance(payload["maintenanceTasks"], list):
                    return json_response(self, 400, {"error": "Invalid maintenanceTasks"})
                updated["maintenanceTasks"] = normalize_maintenance_tasks(payload["maintenanceTasks"])

            saved = save_settings(updated)
            return json_response(self, 200, saved)

        maintenance_complete_prefix = "/api/maintenance/tasks/"
        maintenance_complete_suffix = "/complete"
        if parsed.path.startswith(maintenance_complete_prefix) and parsed.path.endswith(maintenance_complete_suffix):
            task_id = parsed.path[len(maintenance_complete_prefix):-len(maintenance_complete_suffix)]
            task_id = str(task_id or "").strip()
            if not task_id:
                return json_response(self, 400, {"error": "Invalid task id"})

            settings = load_settings()
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
                return json_response(self, 404, {"error": "Task not found"})

            save_settings({"maintenanceTasks": tasks})
            return json_response(self, 200, {"ok": True, "task": updated_task})
        json_response(self, 404, {"error": "Not found"})

    def log_message(self, format, *args):
        return


def main():
    ensure_split_storage()
    server = ThreadingHTTPServer(("", PORT), Handler)
    print(f"Hardware API listening on http://localhost:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
