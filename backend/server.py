import json
import math
import os
import shlex
import shutil
import subprocess
import threading
import time
import sys
from copy import deepcopy
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

BACKEND_ROOT = os.path.dirname(os.path.abspath(__file__))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from cnc_hardware import create_hardware_backend


PORT = int(os.getenv("PORT", "8080"))
DEFAULT_INTERVAL_MS = int(os.getenv("AXES_INTERVAL_MS", "250"))
SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "settings.json")
TASKS_PATH = os.path.join(os.path.dirname(__file__), "tasks.json")
MACHINE_STATS_PATH = os.path.join(os.path.dirname(__file__), "machine_stats.json")
ENABLE_REAL_SHUTDOWN = str(os.getenv("ENABLE_REAL_SHUTDOWN", "")).strip().lower() in {"1", "true", "yes", "on"}
SHUTDOWN_COMMAND = str(os.getenv("SHUTDOWN_COMMAND", "")).strip()
KIOSK_DISPLAY = str(os.getenv("KIOSK_DISPLAY", ":0")).strip() or ":0"
KIOSK_XAUTHORITY = str(os.getenv("KIOSK_XAUTHORITY", os.path.join(os.path.expanduser("~"), ".Xauthority"))).strip()
WIFI_INTERFACE_NAME = str(os.getenv("WIFI_INTERFACE", "")).strip()
WPA_SUPPLICANT_CONF_PATH = str(os.getenv("WPA_SUPPLICANT_CONF_PATH", "/etc/wpa_supplicant/wpa_supplicant.conf")).strip()
NETWORK_INTERFACES_PATH = str(os.getenv("NETWORK_INTERFACES_PATH", "/etc/network/interfaces")).strip()
WIFI_COUNTRY = str(os.getenv("WIFI_COUNTRY", "DE")).strip() or "DE"


def _read_non_negative_float_env(name, default_value):
    raw_value = str(os.getenv(name, str(default_value))).strip()
    try:
        return max(0.0, float(raw_value))
    except ValueError:
        return float(default_value)


def _read_non_negative_int_env(name, default_value):
    raw_value = str(os.getenv(name, str(default_value))).strip()
    try:
        return max(0, int(float(raw_value)))
    except ValueError:
        return int(default_value)


SHUTDOWN_DELAY_SEC = _read_non_negative_float_env("SHUTDOWN_DELAY_SEC", 1.0)
WIFI_CONNECT_TIMEOUT_SEC = _read_non_negative_float_env("WIFI_CONNECT_TIMEOUT_SEC", 12.0)
WIFI_SCAN_TIMEOUT_SEC = _read_non_negative_float_env("WIFI_SCAN_TIMEOUT_SEC", 8.0)
WIFI_AUTOCONNECT_STARTUP_DELAY_SEC = _read_non_negative_float_env("WIFI_AUTOCONNECT_STARTUP_DELAY_SEC", 6.0)
WIFI_AUTOCONNECT_RETRY_DELAY_SEC = _read_non_negative_float_env("WIFI_AUTOCONNECT_RETRY_DELAY_SEC", 8.0)
WIFI_AUTOCONNECT_MAX_ATTEMPTS = _read_non_negative_int_env("WIFI_AUTOCONNECT_MAX_ATTEMPTS", 4)


WIFI_OPERATION_LOCK = threading.Lock()
HARDWARE_BACKEND = create_hardware_backend()


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
        "wifiConnected": False,
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


def _parse_bool_query_flag(params, name):
    raw_values = params.get(name)
    if not raw_values:
        return False
    raw_value = str(raw_values[0]).strip().lower()
    return raw_value in {"1", "true", "yes", "on"}


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


def _is_posix_root():
    return os.name == "posix" and hasattr(os, "geteuid") and os.geteuid() == 0


def _resolve_executable(executable):
    value = str(executable or "").strip()
    if not value:
        return ""
    if os.path.isabs(value):
        return value if os.path.exists(value) else ""

    resolved = shutil.which(value)
    if resolved:
        return resolved

    if os.name == "posix":
        for directory in ("/usr/local/sbin", "/usr/local/bin", "/usr/sbin", "/usr/bin", "/sbin", "/bin"):
            candidate = os.path.join(directory, value)
            if os.path.exists(candidate):
                return candidate
    return ""


def _resolve_command(command):
    if not isinstance(command, (list, tuple)) or not command:
        return []
    executable = _resolve_executable(command[0])
    if not executable:
        return []
    return [executable, *[str(part) for part in command[1:]]]


def _read_text_file(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    except (FileNotFoundError, OSError):
        return ""


def _run_command(command, timeout=5, allow_sudo=False, input_text=None, prefer_sudo=False, sudo_only=False, env=None):
    resolved = _resolve_command(command)
    if not resolved:
        return None

    attempts = [resolved]
    if allow_sudo and os.name == "posix" and not _is_posix_root():
        sudo_executable = _resolve_executable("sudo")
        if sudo_executable:
            sudo_command = [sudo_executable, "-n", *resolved]
            if sudo_only:
                attempts = [sudo_command]
            else:
                attempts = [sudo_command, *attempts] if prefer_sudo else [*attempts, sudo_command]

    last_result = None
    for candidate in attempts:
        try:
            run_env = None
            if env:
                run_env = os.environ.copy()
                run_env.update({str(key): str(value) for key, value in env.items() if value is not None})
            result = subprocess.run(
                candidate,
                input=input_text,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
                env=run_env,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        last_result = result
        if result.returncode == 0:
            return result
    return last_result


def _format_command_failure(result, fallback_message):
    if result is None:
        return fallback_message
    stderr = str(result.stderr or "").strip()
    stdout = str(result.stdout or "").strip()
    detail = stderr or stdout or f"exit code {result.returncode}"
    return f"{fallback_message}: {detail}"


def _parse_key_value_lines(text):
    data = {}
    for raw_line in str(text or "").splitlines():
        if "=" not in raw_line:
            continue
        key, value = raw_line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def _parse_wpa_network_lines(text):
    networks = []
    for index, raw_line in enumerate(str(text or "").splitlines()):
        line = raw_line.strip()
        if not line or index == 0:
            continue
        parts = raw_line.split("\t")
        if len(parts) < 4:
            continue
        networks.append({
            "id": parts[0].strip(),
            "ssid": parts[1].strip(),
            "bssid": parts[2].strip(),
            "flags": parts[3].strip(),
        })
    return networks


def _get_wpa_network_entry(interface, target_ssid=""):
    if not interface:
        return None

    result = _run_command(["wpa_cli", "-i", interface, "list_networks"], timeout=4, allow_sudo=True, prefer_sudo=True, sudo_only=True)
    if not result or result.returncode != 0:
        return None

    networks = _parse_wpa_network_lines(result.stdout)
    wanted_ssid = str(target_ssid or "").strip()
    if wanted_ssid:
        for network in networks:
            if network.get("ssid", "") == wanted_ssid:
                return network
    return networks[0] if networks else None


def _discover_wifi_interfaces():
    candidates = []
    if WIFI_INTERFACE_NAME:
        candidates.append(WIFI_INTERFACE_NAME)

    if os.name == "posix":
        for preferred in ("wlan0", "wlan1"):
            if os.path.exists(os.path.join("/sys/class/net", preferred)):
                candidates.append(preferred)

        result = _run_command(["iw", "dev"], timeout=3)
        if result and result.returncode == 0:
            for raw_line in str(result.stdout or "").splitlines():
                line = raw_line.strip()
                if line.startswith("Interface "):
                    candidates.append(line.split(None, 1)[1].strip())

        result = _run_command(["ip", "-o", "link", "show"], timeout=3)
        if result and result.returncode == 0:
            for raw_line in str(result.stdout or "").splitlines():
                parts = raw_line.split(":", 2)
                if len(parts) < 2:
                    continue
                name = parts[1].strip()
                if name.startswith("wl"):
                    candidates.append(name)

    return _dedupe_strings(candidates)


def get_wifi_interface():
    interfaces = _discover_wifi_interfaces()
    return interfaces[0] if interfaces else ""


def _get_wifi_config_interface():
    interface = get_wifi_interface()
    if interface:
        return interface
    if WIFI_INTERFACE_NAME:
        return WIFI_INTERFACE_NAME
    return "wlan0"


def get_wifi_runtime_status(saved_settings=None):
    saved = normalize_ui_settings(saved_settings if isinstance(saved_settings, dict) else load_ui_settings())
    interface = get_wifi_interface()
    status = {
        "available": bool(interface),
        "interface": interface,
        "connected": False,
        "ssid": str(saved.get("wifiSsid", "")).strip(),
        "ipAddress": "",
        "state": "",
        "issueCode": "",
        "issue": "",
    }
    if not interface:
        return status

    result = _run_command(["wpa_cli", "-i", interface, "status"], timeout=4, allow_sudo=True, prefer_sudo=True, sudo_only=True)
    supplicant_completed = False
    if result and result.returncode == 0:
        data = _parse_key_value_lines(result.stdout)
        status["state"] = str(data.get("wpa_state", "")).strip()
        supplicant_completed = data.get("wpa_state") == "COMPLETED"
        status["ssid"] = str(data.get("ssid", "")).strip() or status["ssid"]
        status["ipAddress"] = str(data.get("ip_address", "")).strip()

    network_entry = _get_wpa_network_entry(interface, status["ssid"] or str(saved.get("wifiSsid", "")).strip())
    if network_entry:
        flags = str(network_entry.get("flags", "")).strip()
        if "TEMP-DISABLED" in flags:
            status["issueCode"] = "TEMP_DISABLED"
            status["issue"] = "Gespeicherte WLAN-Zugangsdaten wurden vom Access Point abgelehnt. Passwort oder Sicherheitsmodus prüfen."

    result = _run_command(["iw", "dev", interface, "link"], timeout=4, allow_sudo=True, prefer_sudo=True, sudo_only=True)
    if result and result.returncode == 0:
        text = str(result.stdout or "")
        if "Connected to " in text:
            for raw_line in text.splitlines():
                line = raw_line.strip()
                if line.startswith("SSID:"):
                    status["ssid"] = line.split(":", 1)[1].strip() or status["ssid"]
                    break
            status["connected"] = True
            return status

    if supplicant_completed:
        status["connected"] = True
    return status


def _escape_wpa_value(value):
    return str(value or "").replace("\\", "\\\\").replace('"', '\\"')


def _read_wpa_supplicant_header():
    content = _read_text_file(WPA_SUPPLICANT_CONF_PATH)
    header_lines = []
    in_network_block = False

    for raw_line in content.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("network={"):
            in_network_block = True
            continue
        if in_network_block:
            if stripped == "}":
                in_network_block = False
            continue
        if stripped:
            header_lines.append(stripped)

    normalized = []
    seen_keys = set()
    for line in header_lines:
        key = line.split("=", 1)[0].strip() if "=" in line else line
        if key in {"country", "ctrl_interface", "update_config"}:
            if key in seen_keys:
                continue
            seen_keys.add(key)
        normalized.append(line)

    if "country" not in seen_keys:
        normalized.insert(0, f"country={WIFI_COUNTRY}")
    if "ctrl_interface" not in seen_keys:
        normalized.append("ctrl_interface=DIR=/run/wpa_supplicant GROUP=netdev")
    if "update_config" not in seen_keys:
        normalized.append("update_config=1")
    return normalized


def build_wpa_supplicant_config(saved_settings):
    settings = normalize_ui_settings(saved_settings if isinstance(saved_settings, dict) else load_ui_settings())
    header_lines = _read_wpa_supplicant_header()
    ssid = str(settings.get("wifiSsid", "")).strip()
    password = str(settings.get("wifiPassword", ""))
    lines = list(header_lines)

    if ssid:
        lines.append("")
        lines.append("network={")
        lines.append(f'    ssid="{_escape_wpa_value(ssid)}"')
        if password:
            lines.append(f'    psk="{_escape_wpa_value(password)}"')
        else:
            lines.append("    key_mgmt=NONE")
        lines.append("}")

    return "\n".join(lines).strip() + "\n"


def build_interface_wpa_supplicant_path(interface):
    directory = os.path.dirname(WPA_SUPPLICANT_CONF_PATH) or "/etc/wpa_supplicant"
    return os.path.join(directory, f"wpa_supplicant-{interface}.conf")


def build_wpa_supplicant_service_name(interface):
    return f"wpa_supplicant@{interface}.service"


def _write_text_file(path, content):
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)
        return True, ""
    except OSError as exc:
        return False, str(exc)


def _write_system_text_file(path, content, mode=None):
    if os.name != "posix":
        return _write_text_file(path, content)

    if _is_posix_root():
        ok, error = _write_text_file(path, content)
        if not ok:
            return False, error
        if mode:
            chmod_result = _run_command(["chmod", mode, path], timeout=5)
            if not chmod_result or chmod_result.returncode != 0:
                return False, _format_command_failure(chmod_result, f"Failed to chmod {path}")
        return True, ""

    tee_result = _run_command(["tee", path], timeout=5, allow_sudo=True, input_text=content, prefer_sudo=True, sudo_only=True)
    if not tee_result or tee_result.returncode != 0:
        return False, _format_command_failure(tee_result, f"Failed to write {path}")

    if mode:
        chmod_result = _run_command(["chmod", mode, path], timeout=5, allow_sudo=True, prefer_sudo=True, sudo_only=True)
        if not chmod_result or chmod_result.returncode != 0:
            return False, _format_command_failure(chmod_result, f"Failed to chmod {path}")
    return True, ""


def _update_allow_hotplug(content, interface, enabled):
    lines = content.splitlines()
    iface_line = f"iface {interface} inet dhcp"
    desired_line = f"allow-hotplug {interface}" if enabled else f"#allow-hotplug {interface}"
    allow_index = None
    iface_index = None

    for index, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        normalized = stripped[1:].strip() if stripped.startswith("#") else stripped
        if normalized == f"allow-hotplug {interface}" and allow_index is None:
            allow_index = index
        if stripped == iface_line and iface_index is None:
            iface_index = index

    if allow_index is not None:
        indent = lines[allow_index][:len(lines[allow_index]) - len(lines[allow_index].lstrip(" \t"))]
        lines[allow_index] = f"{indent}{desired_line}"
    else:
        insert_at = iface_index if iface_index is not None else len(lines)
        lines.insert(insert_at, desired_line)
        if iface_index is not None and insert_at <= iface_index:
            iface_index += 1

    if iface_index is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend([
            iface_line,
            f"    wpa-conf {WPA_SUPPLICANT_CONF_PATH}",
        ])
        return "\n".join(lines).strip() + "\n"

    stanza_end = len(lines)
    for index in range(iface_index + 1, len(lines)):
        stripped = lines[index].strip()
        if not stripped:
            continue
        normalized = stripped[1:].strip() if stripped.startswith("#") else stripped
        if normalized.startswith(("iface ", "auto ", "allow-hotplug ", "mapping ", "source ", "source-directory ")):
            stanza_end = index
            break

    wpa_conf_indices = [
        index
        for index in range(iface_index + 1, stanza_end)
        if lines[index].strip().startswith("wpa-conf ")
    ]
    has_wpa_conf = any(
        lines[index].strip().startswith("wpa-conf ")
        for index in range(iface_index + 1, stanza_end)
    )
    if not has_wpa_conf:
        lines.insert(iface_index + 1, f"    wpa-conf {WPA_SUPPLICANT_CONF_PATH}")
    elif len(wpa_conf_indices) > 1:
        keep_index = wpa_conf_indices[0]
        lines = [
            line
            for index, line in enumerate(lines)
            if index == keep_index or index not in wpa_conf_indices[1:]
        ]

    return "\n".join(lines).strip() + "\n"


def apply_saved_wifi_configuration(saved_settings=None):
    settings = normalize_ui_settings(saved_settings if isinstance(saved_settings, dict) else load_ui_settings())
    interface = _get_wifi_config_interface()

    wpa_content = build_wpa_supplicant_config(settings)
    ok, error = _write_system_text_file(WPA_SUPPLICANT_CONF_PATH, wpa_content, mode="600")
    if not ok:
        return False, error
    ok, error = _write_system_text_file(build_interface_wpa_supplicant_path(interface), wpa_content, mode="600")
    if not ok:
        return False, error

    interfaces_content = _read_text_file(NETWORK_INTERFACES_PATH)
    if not interfaces_content and os.name == "posix":
        cat_result = _run_command(["cat", NETWORK_INTERFACES_PATH], timeout=5, allow_sudo=True, prefer_sudo=True, sudo_only=True)
        if cat_result and cat_result.returncode == 0:
            interfaces_content = str(cat_result.stdout or "")

    if interfaces_content:
        updated_content = _update_allow_hotplug(interfaces_content, interface, bool(settings.get("wifiAutoConnect", False)))
        ok, error = _write_system_text_file(NETWORK_INTERFACES_PATH, updated_content)
        if not ok:
            return False, error

    return True, ""


def _parse_scan_results_from_iw(text):
    candidates = []
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if line.startswith("SSID:"):
            candidates.append(line.split(":", 1)[1].strip())
    return candidates


def _parse_scan_results_from_wpa_cli(text):
    candidates = []
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("bssid /"):
            continue
        parts = line.split("\t")
        if len(parts) >= 5:
            candidates.append(parts[4].strip())
    return candidates


def scan_wifi_networks():
    candidates = []
    interface = get_wifi_interface()

    if interface and os.name == "posix":
        _run_command(["ip", "link", "set", interface, "up"], timeout=5, allow_sudo=True, prefer_sudo=True, sudo_only=True)

        result = _run_command(["iw", "dev", interface, "scan", "ap-force"], timeout=max(5, WIFI_SCAN_TIMEOUT_SEC), allow_sudo=True, prefer_sudo=True, sudo_only=True)
        if result and result.returncode == 0:
            candidates.extend(_parse_scan_results_from_iw(result.stdout))

        if not candidates:
            trigger_result = _run_command(["wpa_cli", "-i", interface, "scan"], timeout=5, allow_sudo=True, prefer_sudo=True, sudo_only=True)
            if trigger_result and trigger_result.returncode == 0:
                time.sleep(2)
                result = _run_command(["wpa_cli", "-i", interface, "scan_results"], timeout=5, allow_sudo=True, prefer_sudo=True, sudo_only=True)
                if result and result.returncode == 0:
                    candidates.extend(_parse_scan_results_from_wpa_cli(result.stdout))

    if not candidates:
        result = _run_command(["nmcli", "-t", "-f", "SSID", "dev", "wifi", "list"], timeout=3)
        if result and result.returncode == 0:
            candidates.extend([line.strip() for line in (result.stdout or "").splitlines()])

    if not candidates:
        result = _run_command(["iwlist", "scan"], timeout=4, allow_sudo=True, prefer_sudo=True, sudo_only=True)
        if result and result.returncode == 0:
            for line in (result.stdout or "").splitlines():
                line = line.strip()
                if "ESSID:" not in line:
                    continue
                essid = line.split("ESSID:", 1)[1].strip().strip('"')
                candidates.append(essid)

    if not candidates and os.name == "nt":
        result = _run_command(["netsh", "wlan", "show", "networks", "mode=Bssid"], timeout=4)
        if result and result.returncode == 0:
            for line in (result.stdout or "").splitlines():
                line = line.strip()
                if not line.startswith("SSID "):
                    continue
                parts = line.split(":", 1)
                if len(parts) != 2:
                    continue
                candidates.append(parts[1].strip())

    networks = _dedupe_strings(candidates)
    saved_ssid = load_ui_settings().get("wifiSsid", "")
    if saved_ssid:
        networks = _dedupe_strings(networks + [saved_ssid])
    return networks


def connect_wifi():
    with WIFI_OPERATION_LOCK:
        saved_settings = load_ui_settings()
        interface = _get_wifi_config_interface()
        ssid = str(saved_settings.get("wifiSsid", "")).strip()
        if not ssid:
            return False, "SSID is required", get_wifi_runtime_status(saved_settings)

        if os.name != "posix":
            status = get_wifi_runtime_status(saved_settings)
            status["connected"] = False
            return False, "Real Wi-Fi control is only supported on Linux", status

        apply_ok, apply_error = apply_saved_wifi_configuration(saved_settings)
        if not apply_ok:
            return False, apply_error, get_wifi_runtime_status(saved_settings)

        _run_command(["rfkill", "unblock", "wifi"], timeout=5, allow_sudo=True, prefer_sudo=True, sudo_only=True)
        _run_command(["ip", "link", "set", interface, "up"], timeout=5, allow_sudo=True, prefer_sudo=True, sudo_only=True)

        status_result = _run_command(["wpa_cli", "-i", interface, "status"], timeout=5, allow_sudo=True, prefer_sudo=True, sudo_only=True)
        if status_result and status_result.returncode == 0:
            _run_command(["wpa_cli", "-i", interface, "reconfigure"], timeout=5, allow_sudo=True, prefer_sudo=True, sudo_only=True)
            _run_command(["wpa_cli", "-i", interface, "reconnect"], timeout=5, allow_sudo=True, prefer_sudo=True, sudo_only=True)
        else:
            _run_command(["ifdown", "--force", interface], timeout=15, allow_sudo=True, prefer_sudo=True, sudo_only=True)
            result = _run_command(["ifup", interface], timeout=20, allow_sudo=True, prefer_sudo=True, sudo_only=True)
            if not result or result.returncode != 0:
                return False, _format_command_failure(result, "Failed to raise Wi-Fi interface"), get_wifi_runtime_status(saved_settings)

        last_status = get_wifi_runtime_status(saved_settings)
        deadline = time.time() + max(1.0, WIFI_CONNECT_TIMEOUT_SEC)
        connected_since = None
        while time.time() < deadline:
            if last_status.get("issueCode") == "TEMP_DISABLED":
                return False, str(last_status.get("issue", "")).strip() or "Gespeicherte WLAN-Zugangsdaten wurden vom Access Point abgelehnt.", last_status
            if last_status.get("connected") and last_status.get("ssid", "") == ssid:
                if connected_since is None:
                    connected_since = time.time()
                stable_for_sec = time.time() - connected_since
                if last_status.get("ipAddress") or stable_for_sec >= 2.0:
                    return True, "Wi-Fi connected", last_status
            else:
                connected_since = None
            time.sleep(1)
            last_status = get_wifi_runtime_status(saved_settings)

        if last_status.get("issueCode") == "TEMP_DISABLED":
            return False, str(last_status.get("issue", "")).strip() or "Gespeicherte WLAN-Zugangsdaten wurden vom Access Point abgelehnt.", last_status

        status_result = _run_command(["wpa_cli", "-i", interface, "status"], timeout=5, allow_sudo=True, prefer_sudo=True, sudo_only=True)
        return False, _format_command_failure(status_result, "Wi-Fi connection failed"), last_status


def disconnect_wifi():
    with WIFI_OPERATION_LOCK:
        saved_settings = load_ui_settings()
        interface = _get_wifi_config_interface()

        if os.name != "posix":
            status = get_wifi_runtime_status(saved_settings)
            status["connected"] = False
            return False, "Real Wi-Fi control is only supported on Linux", status

        _run_command(["wpa_cli", "-i", interface, "disconnect"], timeout=5, allow_sudo=True, prefer_sudo=True, sudo_only=True)
        _run_command(["ifdown", "--force", interface], timeout=15, allow_sudo=True, prefer_sudo=True, sudo_only=True)
        _run_command(["ip", "link", "set", interface, "down"], timeout=5, allow_sudo=True, prefer_sudo=True, sudo_only=True)
        time.sleep(1)

        status = get_wifi_runtime_status(saved_settings)
        if not status.get("connected"):
            status["ssid"] = str(saved_settings.get("wifiSsid", "")).strip()
            return True, "Wi-Fi disconnected", status
        return False, "Wi-Fi disconnect failed", status


def autoconnect_wifi_on_startup():
    if os.name != "posix":
        return

    settings = load_ui_settings()
    target_ssid = str(settings.get("wifiSsid", "")).strip()
    if not settings.get("wifiAutoConnect") or not target_ssid:
        return

    if WIFI_AUTOCONNECT_STARTUP_DELAY_SEC > 0:
        time.sleep(WIFI_AUTOCONNECT_STARTUP_DELAY_SEC)

    attempts = max(1, WIFI_AUTOCONNECT_MAX_ATTEMPTS)
    for attempt in range(1, attempts + 1):
        current_settings = load_ui_settings()
        target_ssid = str(current_settings.get("wifiSsid", "")).strip()
        if not current_settings.get("wifiAutoConnect") or not target_ssid:
            print("Wi-Fi autoconnect skipped: auto-connect disabled or SSID missing.", flush=True)
            return

        current_status = get_wifi_runtime_status(current_settings)
        if current_status.get("connected") and current_status.get("ssid", "") == target_ssid:
            print(f"Wi-Fi autoconnect skipped: already connected to {target_ssid}.", flush=True)
            return

        print(f"Wi-Fi autoconnect attempt {attempt}/{attempts} for {target_ssid}.", flush=True)
        ok, message, status = connect_wifi()
        if ok and status.get("connected") and status.get("ssid", "") == target_ssid:
            time.sleep(3)
            confirmed_status = get_wifi_runtime_status(current_settings)
            if confirmed_status.get("connected") and confirmed_status.get("ssid", "") == target_ssid:
                print(f"Wi-Fi autoconnect succeeded on attempt {attempt}: {target_ssid}.", flush=True)
                return
            message = "Wi-Fi connection was not stable after initial connect."

        print(f"Wi-Fi autoconnect attempt {attempt}/{attempts} failed: {message}", flush=True)
        if attempt < attempts and WIFI_AUTOCONNECT_RETRY_DELAY_SEC > 0:
            time.sleep(WIFI_AUTOCONNECT_RETRY_DELAY_SEC)

    print("Wi-Fi autoconnect exhausted all startup attempts.", flush=True)


def merge_wifi_runtime_settings(ui_settings):
    runtime = get_wifi_runtime_status(ui_settings)
    saved = normalize_ui_settings(ui_settings)
    merged = normalize_ui_settings({
        **saved,
        "wifiConnected": bool(runtime.get("connected", False)),
        "wifiSsid": str(runtime.get("ssid", "")).strip() or str(saved.get("wifiSsid", "")).strip(),
    })
    merged["wifiState"] = str(runtime.get("state", "")).strip()
    merged["wifiIssueCode"] = str(runtime.get("issueCode", "")).strip()
    merged["wifiIssue"] = str(runtime.get("issue", "")).strip()
    return merged


def build_shutdown_commands():
    if SHUTDOWN_COMMAND:
        try:
            return [shlex.split(SHUTDOWN_COMMAND)]
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


def blackout_display_for_shutdown():
    if os.name != "posix":
        return False

    display_env = {"DISPLAY": KIOSK_DISPLAY}
    if KIOSK_XAUTHORITY:
        display_env["XAUTHORITY"] = KIOSK_XAUTHORITY

    xset_result = None
    if KIOSK_DISPLAY:
        _run_command(["xset", "-display", KIOSK_DISPLAY, "+dpms"], timeout=2, env=display_env)
        xset_result = _run_command(
            ["xset", "-display", KIOSK_DISPLAY, "dpms", "force", "off"],
            timeout=2,
            env=display_env,
        )
        if xset_result and xset_result.returncode == 0:
            return True

    if _is_posix_root():
        vcgencmd_result = _run_command(["vcgencmd", "display_power", "0"], timeout=2)
        if vcgencmd_result and vcgencmd_result.returncode == 0:
            return True

    detail = _format_command_failure(xset_result, "Display blackout command failed")
    print(detail, flush=True)
    return False


def _execute_shutdown_request():
    blackout_display_for_shutdown()

    if SHUTDOWN_DELAY_SEC > 0:
        time.sleep(SHUTDOWN_DELAY_SEC)

    commands = build_shutdown_commands()
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


def request_system_shutdown():
    if not ENABLE_REAL_SHUTDOWN:
        return False, "Real shutdown is disabled"

    commands = build_shutdown_commands()
    if not commands:
        return False, "No shutdown command is available"

    worker = threading.Thread(target=_execute_shutdown_request, daemon=True)
    worker.start()
    return True, "Shutdown scheduled"


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
        "wifiConnected": False,
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
    ui_settings = merge_wifi_runtime_settings(load_ui_settings())
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
        params = parse_qs(parsed.query or "")

        if path == "/api/health":
            return json_response(self, 200, {"status": "ok", "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})

        if path == "/api/axes":
            return json_response(self, 200, {"timestamp": int(time.time() * 1000), "axes": mock_axes_load(int(time.time() * 1000))})

        if path == "/api/hardware":
            force_refresh = _parse_bool_query_flag(params, "refresh")
            return json_response(self, 200, HARDWARE_BACKEND.get_snapshot(force_refresh=force_refresh))

        if path == "/api/hardware/spindle-temperature":
            force_refresh = _parse_bool_query_flag(params, "refresh")
            return json_response(self, 200, HARDWARE_BACKEND.get_spindle_temperature(force_refresh=force_refresh))

        if path == "/api/axes/stream":
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
            ok, message = request_system_shutdown()
            status = 202 if ok else 503
            return json_response(self, status, {"ok": ok, "message": message})
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

            save_settings({
                "wifiSsid": ssid,
                "wifiPassword": password,
                "wifiAutoConnect": auto_connect,
            })
            ok, message, status = connect_wifi()
            http_status = 200 if ok else 503
            return json_response(self, http_status, {
                "ok": ok,
                "message": message,
                "connected": bool(status.get("connected", False)),
                "ssid": str(status.get("ssid", ssid)),
                "autoConnect": bool(auto_connect),
            })

        if parsed.path == "/api/wifi/disconnect":
            ok, message, status = disconnect_wifi()
            http_status = 200 if ok else 503
            return json_response(self, http_status, {
                "ok": ok,
                "message": message,
                "connected": bool(status.get("connected", False)),
                "ssid": str(status.get("ssid", "")),
                "autoConnect": bool(load_ui_settings().get("wifiAutoConnect", False)),
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
            if any(key in updated for key in ("wifiSsid", "wifiPassword", "wifiAutoConnect")):
                ok, message = apply_saved_wifi_configuration(load_ui_settings())
                saved = load_settings()
                if not ok:
                    return json_response(self, 503, {
                        "error": message,
                        **saved,
                    })
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
    threading.Thread(target=autoconnect_wifi_on_startup, daemon=True).start()
    server = ThreadingHTTPServer(("", PORT), Handler)
    print(f"Hardware API listening on http://localhost:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
