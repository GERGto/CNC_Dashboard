from __future__ import annotations

import os
from dataclasses import dataclass


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


@dataclass(frozen=True)
class AppConfig:
    backend_root: str
    port: int
    default_interval_ms: int
    settings_path: str
    tasks_path: str
    machine_stats_path: str
    enable_real_shutdown: bool
    shutdown_command: str
    kiosk_display: str
    kiosk_xauthority: str
    wifi_interface_name: str
    wpa_supplicant_conf_path: str
    network_interfaces_path: str
    wifi_country: str
    shutdown_delay_sec: float
    wifi_connect_timeout_sec: float
    wifi_scan_timeout_sec: float
    wifi_autoconnect_startup_delay_sec: float
    wifi_autoconnect_retry_delay_sec: float
    wifi_autoconnect_max_attempts: int


def load_app_config():
    backend_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return AppConfig(
        backend_root=backend_root,
        port=int(os.getenv("PORT", "8080")),
        default_interval_ms=int(os.getenv("AXES_INTERVAL_MS", "250")),
        settings_path=os.path.join(backend_root, "settings.json"),
        tasks_path=os.path.join(backend_root, "tasks.json"),
        machine_stats_path=os.path.join(backend_root, "machine_stats.json"),
        enable_real_shutdown=str(os.getenv("ENABLE_REAL_SHUTDOWN", "")).strip().lower() in {"1", "true", "yes", "on"},
        shutdown_command=str(os.getenv("SHUTDOWN_COMMAND", "")).strip(),
        kiosk_display=str(os.getenv("KIOSK_DISPLAY", ":0")).strip() or ":0",
        kiosk_xauthority=str(
            os.getenv("KIOSK_XAUTHORITY", os.path.join(os.path.expanduser("~"), ".Xauthority"))
        ).strip(),
        wifi_interface_name=str(os.getenv("WIFI_INTERFACE", "")).strip(),
        wpa_supplicant_conf_path=str(
            os.getenv("WPA_SUPPLICANT_CONF_PATH", "/etc/wpa_supplicant/wpa_supplicant.conf")
        ).strip(),
        network_interfaces_path=str(
            os.getenv("NETWORK_INTERFACES_PATH", "/etc/network/interfaces")
        ).strip(),
        wifi_country=str(os.getenv("WIFI_COUNTRY", "DE")).strip() or "DE",
        shutdown_delay_sec=_read_non_negative_float_env("SHUTDOWN_DELAY_SEC", 1.0),
        wifi_connect_timeout_sec=_read_non_negative_float_env("WIFI_CONNECT_TIMEOUT_SEC", 12.0),
        wifi_scan_timeout_sec=_read_non_negative_float_env("WIFI_SCAN_TIMEOUT_SEC", 8.0),
        wifi_autoconnect_startup_delay_sec=_read_non_negative_float_env(
            "WIFI_AUTOCONNECT_STARTUP_DELAY_SEC", 6.0
        ),
        wifi_autoconnect_retry_delay_sec=_read_non_negative_float_env(
            "WIFI_AUTOCONNECT_RETRY_DELAY_SEC", 8.0
        ),
        wifi_autoconnect_max_attempts=_read_non_negative_int_env("WIFI_AUTOCONNECT_MAX_ATTEMPTS", 4),
    )
