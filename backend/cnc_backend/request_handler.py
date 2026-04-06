from __future__ import annotations

import json
import time
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from cnc_hardware.sensors import HardwareError

from .common import clamp, json_response, parse_bool_query_flag, send_sse


def create_request_handler(app):
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
            params = parse_qs(parsed.query or "")

            if path == "/api/health":
                return json_response(self, 200, app.get_health())

            if path == "/api/axes":
                return json_response(self, 200, app.get_axes())

            if path == "/api/hardware":
                force_refresh = parse_bool_query_flag(params, "refresh")
                return json_response(self, 200, app.get_hardware_snapshot(force_refresh=force_refresh))

            if path == "/api/hardware/spindle-temperature":
                force_refresh = parse_bool_query_flag(params, "refresh")
                return json_response(self, 200, app.get_spindle_temperature(force_refresh=force_refresh))

            if path == "/api/hardware/axis-loads":
                force_refresh = parse_bool_query_flag(params, "refresh")
                return json_response(self, 200, app.get_axis_loads(force_refresh=force_refresh))

            if path == "/api/hardware/relays":
                return json_response(self, 200, app.get_relay_board())

            if path == "/api/machine/status":
                return json_response(self, 200, app.get_machine_status())

            if path == "/api/axes/stream":
                interval_ms = app.config.default_interval_ms
                if "intervalMs" in params:
                    try:
                        interval_ms = int(params["intervalMs"][0])
                    except (ValueError, TypeError):
                        interval_ms = app.config.default_interval_ms
                interval_ms = clamp(interval_ms, 50, 5000)

                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()

                try:
                    while True:
                        send_sse(self, "axes", app.get_axes())
                        time.sleep(interval_ms / 1000.0)
                except (BrokenPipeError, ConnectionResetError):
                    return
                except Exception:
                    return

            if path == "/api/settings":
                return json_response(self, 200, app.get_settings())

            if path == "/api/wifi/networks":
                return json_response(self, 200, {"networks": app.scan_wifi_networks()})

            if path == "/api/wifi/status":
                return json_response(self, 200, app.get_wifi_status())

            if path == "/api/maintenance/tasks":
                return json_response(self, 200, {"tasks": app.get_maintenance_tasks()})

            json_response(self, 404, {"error": "Not found"})

        def do_POST(self):
            parsed = urlparse(self.path)
            if parsed.path == "/api/shutdown":
                ok, message = app.request_system_shutdown()
                status = 202 if ok else 503
                return json_response(self, status, {"ok": ok, "message": message})

            if parsed.path == "/api/wifi/connect":
                payload, error = self._read_json_payload()
                if error:
                    return json_response(self, 400, {"error": error})

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

                ok, message, status = app.connect_wifi(ssid, password, auto_connect)
                http_status = 200 if ok else 503
                return json_response(
                    self,
                    http_status,
                    {
                        "ok": ok,
                        "message": message,
                        "connected": bool(status.get("connected", False)),
                        "ssid": str(status.get("ssid", ssid)),
                        "autoConnect": bool(auto_connect),
                    },
                )

            if parsed.path == "/api/wifi/disconnect":
                ok, message, status = app.disconnect_wifi()
                http_status = 200 if ok else 503
                return json_response(
                    self,
                    http_status,
                    {
                        "ok": ok,
                        "message": message,
                        "connected": bool(status.get("connected", False)),
                        "ssid": str(status.get("ssid", "")),
                        "autoConnect": app.get_wifi_autoconnect(),
                    },
                )

            if parsed.path == "/api/settings":
                payload, error = self._read_json_payload()
                if error:
                    return json_response(self, 400, {"error": error})

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
                    updated["axisVisibility"] = app.store.normalize_axis_visibility(payload["axisVisibility"])
                if "axisLoadCalibration" in payload:
                    if not isinstance(payload["axisLoadCalibration"], dict):
                        return json_response(self, 400, {"error": "Invalid axisLoadCalibration"})
                    updated["axisLoadCalibration"] = app.store.normalize_axis_load_calibration(
                        payload["axisLoadCalibration"]
                    )
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
                    updated["maintenanceTasks"] = app.store.normalize_maintenance_tasks(payload["maintenanceTasks"])

                saved, wifi_error = app.save_settings(updated)
                if wifi_error:
                    return json_response(
                        self,
                        503,
                        {
                            "error": wifi_error,
                            **saved,
                        },
                    )
                return json_response(self, 200, saved)

            if parsed.path == "/api/machine/status":
                payload, error = self._read_json_payload()
                if error:
                    return json_response(self, 400, {"error": error})

                status = payload.get("status")
                if not isinstance(status, str):
                    return json_response(self, 400, {"error": "Invalid status"})

                source = payload.get("source", "api")
                if not isinstance(source, str):
                    return json_response(self, 400, {"error": "Invalid source"})

                return json_response(self, 200, app.report_machine_status(status, source=source))

            relay_path_map = {
                "/api/hardware/light": ("light", ("on",)),
                "/api/hardware/fan": ("fan", ("on",)),
                "/api/hardware/e-stop": ("eStop", ("engaged", "on")),
                "/api/hardware/relay-4": ("relay4", ("on",)),
            }
            if parsed.path in relay_path_map:
                output_id, bool_keys = relay_path_map[parsed.path]
                return self._handle_relay_output_post(output_id, bool_keys)

            maintenance_complete_prefix = "/api/maintenance/tasks/"
            maintenance_complete_suffix = "/complete"
            if parsed.path.startswith(maintenance_complete_prefix) and parsed.path.endswith(maintenance_complete_suffix):
                task_id = parsed.path[len(maintenance_complete_prefix) : -len(maintenance_complete_suffix)]
                task_id = str(task_id or "").strip()
                if not task_id:
                    return json_response(self, 400, {"error": "Invalid task id"})

                updated_task = app.complete_maintenance_task(task_id)
                if updated_task is None:
                    return json_response(self, 404, {"error": "Task not found"})

                return json_response(self, 200, {"ok": True, "task": updated_task})

            json_response(self, 404, {"error": "Not found"})

        def log_message(self, format, *args):
            return

        def _read_json_payload(self):
            try:
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length) if length > 0 else b"{}"
                payload = json.loads(raw.decode("utf-8")) if raw else {}
                if not isinstance(payload, dict):
                    return None, "Invalid payload"
                return payload, ""
            except (ValueError, json.JSONDecodeError):
                return None, "Invalid payload"

        def _read_bool_payload_field(self, payload, keys):
            for key in keys:
                if key not in payload:
                    continue
                value = payload[key]
                if isinstance(value, bool):
                    return value, ""
                if isinstance(value, (int, float)) and value in (0, 1):
                    return bool(value), ""
                return None, f"Invalid {key}"
            return None, f"Missing {' or '.join(keys)}"

        def _handle_relay_output_post(self, output_id, bool_keys):
            payload, error = self._read_json_payload()
            if error:
                return json_response(self, 400, {"error": error})

            enabled, value_error = self._read_bool_payload_field(payload, bool_keys)
            if value_error:
                return json_response(self, 400, {"error": value_error})

            try:
                result = app.set_relay_output(output_id, enabled)
            except HardwareError as exc:
                return json_response(
                    self,
                    503,
                    {
                        "ok": False,
                        "error": str(exc),
                        "relayBoard": app.get_relay_board(),
                    },
                )

            return json_response(self, 200, {"ok": True, **result})

    return Handler
