from __future__ import annotations

import os
import threading
import time

from .command_utils import (
    dedupe_strings,
    format_command_failure,
    is_posix_root,
    read_text_file,
    run_command,
)


class WiFiService:
    def __init__(self, config, store):
        self.config = config
        self.store = store
        self.operation_lock = threading.Lock()

    def get_wifi_interface(self):
        interfaces = self._discover_wifi_interfaces()
        return interfaces[0] if interfaces else ""

    def get_wifi_config_interface(self):
        interface = self.get_wifi_interface()
        if interface:
            return interface
        if self.config.wifi_interface_name:
            return self.config.wifi_interface_name
        return "wlan0"

    def get_wifi_runtime_status(self, saved_settings=None):
        saved = self.store.normalize_ui_settings(
            saved_settings if isinstance(saved_settings, dict) else self.store.load_ui_settings()
        )
        interface = self.get_wifi_interface()
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

        result = run_command(
            ["wpa_cli", "-i", interface, "status"],
            timeout=4,
            allow_sudo=True,
            prefer_sudo=True,
            sudo_only=True,
        )
        supplicant_completed = False
        if result and result.returncode == 0:
            data = self._parse_key_value_lines(result.stdout)
            status["state"] = str(data.get("wpa_state", "")).strip()
            supplicant_completed = data.get("wpa_state") == "COMPLETED"
            status["ssid"] = str(data.get("ssid", "")).strip() or status["ssid"]
            status["ipAddress"] = str(data.get("ip_address", "")).strip()

        network_entry = self._get_wpa_network_entry(interface, status["ssid"] or str(saved.get("wifiSsid", "")).strip())
        if network_entry:
            flags = str(network_entry.get("flags", "")).strip()
            if "TEMP-DISABLED" in flags:
                status["issueCode"] = "TEMP_DISABLED"
                status["issue"] = "Gespeicherte WLAN-Zugangsdaten wurden vom Access Point abgelehnt. Passwort oder Sicherheitsmodus prÃ¼fen."

        result = run_command(
            ["iw", "dev", interface, "link"],
            timeout=4,
            allow_sudo=True,
            prefer_sudo=True,
            sudo_only=True,
        )
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

    def build_wpa_supplicant_config(self, saved_settings):
        settings = self.store.normalize_ui_settings(
            saved_settings if isinstance(saved_settings, dict) else self.store.load_ui_settings()
        )
        header_lines = self._read_wpa_supplicant_header()
        ssid = str(settings.get("wifiSsid", "")).strip()
        password = str(settings.get("wifiPassword", ""))
        lines = list(header_lines)

        if ssid:
            lines.append("")
            lines.append("network={")
            lines.append(f'    ssid="{self._escape_wpa_value(ssid)}"')
            if password:
                lines.append(f'    psk="{self._escape_wpa_value(password)}"')
            else:
                lines.append("    key_mgmt=NONE")
            lines.append("}")

        return "\n".join(lines).strip() + "\n"

    def build_interface_wpa_supplicant_path(self, interface):
        directory = os.path.dirname(self.config.wpa_supplicant_conf_path) or "/etc/wpa_supplicant"
        return os.path.join(directory, f"wpa_supplicant-{interface}.conf")

    def build_wpa_supplicant_service_name(self, interface):
        return f"wpa_supplicant@{interface}.service"

    def apply_saved_wifi_configuration(self, saved_settings=None):
        settings = self.store.normalize_ui_settings(
            saved_settings if isinstance(saved_settings, dict) else self.store.load_ui_settings()
        )
        interface = self.get_wifi_config_interface()

        wpa_content = self.build_wpa_supplicant_config(settings)
        ok, error = self._write_system_text_file(self.config.wpa_supplicant_conf_path, wpa_content, mode="600")
        if not ok:
            return False, error
        ok, error = self._write_system_text_file(
            self.build_interface_wpa_supplicant_path(interface),
            wpa_content,
            mode="600",
        )
        if not ok:
            return False, error

        interfaces_content = read_text_file(self.config.network_interfaces_path)
        if not interfaces_content and os.name == "posix":
            cat_result = run_command(
                ["cat", self.config.network_interfaces_path],
                timeout=5,
                allow_sudo=True,
                prefer_sudo=True,
                sudo_only=True,
            )
            if cat_result and cat_result.returncode == 0:
                interfaces_content = str(cat_result.stdout or "")

        if interfaces_content:
            updated_content = self._update_allow_hotplug(
                interfaces_content,
                interface,
                bool(settings.get("wifiAutoConnect", False)),
            )
            ok, error = self._write_system_text_file(self.config.network_interfaces_path, updated_content)
            if not ok:
                return False, error

        return True, ""

    def scan_wifi_networks(self):
        candidates = []
        interface = self.get_wifi_interface()

        if interface and os.name == "posix":
            run_command(
                ["ip", "link", "set", interface, "up"],
                timeout=5,
                allow_sudo=True,
                prefer_sudo=True,
                sudo_only=True,
            )

            result = run_command(
                ["iw", "dev", interface, "scan", "ap-force"],
                timeout=max(5, self.config.wifi_scan_timeout_sec),
                allow_sudo=True,
                prefer_sudo=True,
                sudo_only=True,
            )
            if result and result.returncode == 0:
                candidates.extend(self._parse_scan_results_from_iw(result.stdout))

            if not candidates:
                trigger_result = run_command(
                    ["wpa_cli", "-i", interface, "scan"],
                    timeout=5,
                    allow_sudo=True,
                    prefer_sudo=True,
                    sudo_only=True,
                )
                if trigger_result and trigger_result.returncode == 0:
                    time.sleep(2)
                    result = run_command(
                        ["wpa_cli", "-i", interface, "scan_results"],
                        timeout=5,
                        allow_sudo=True,
                        prefer_sudo=True,
                        sudo_only=True,
                    )
                    if result and result.returncode == 0:
                        candidates.extend(self._parse_scan_results_from_wpa_cli(result.stdout))

        if not candidates:
            result = run_command(["nmcli", "-t", "-f", "SSID", "dev", "wifi", "list"], timeout=3)
            if result and result.returncode == 0:
                candidates.extend([line.strip() for line in (result.stdout or "").splitlines()])

        if not candidates:
            result = run_command(["iwlist", "scan"], timeout=4, allow_sudo=True, prefer_sudo=True, sudo_only=True)
            if result and result.returncode == 0:
                for line in (result.stdout or "").splitlines():
                    line = line.strip()
                    if "ESSID:" not in line:
                        continue
                    essid = line.split("ESSID:", 1)[1].strip().strip('"')
                    candidates.append(essid)

        if not candidates and os.name == "nt":
            result = run_command(["netsh", "wlan", "show", "networks", "mode=Bssid"], timeout=4)
            if result and result.returncode == 0:
                for line in (result.stdout or "").splitlines():
                    line = line.strip()
                    if not line.startswith("SSID "):
                        continue
                    parts = line.split(":", 1)
                    if len(parts) != 2:
                        continue
                    candidates.append(parts[1].strip())

        networks = dedupe_strings(candidates)
        saved_ssid = self.store.load_ui_settings().get("wifiSsid", "")
        if saved_ssid:
            networks = dedupe_strings(networks + [saved_ssid])
        return networks

    def connect_wifi(self):
        with self.operation_lock:
            saved_settings = self.store.load_ui_settings()
            interface = self.get_wifi_config_interface()
            ssid = str(saved_settings.get("wifiSsid", "")).strip()
            if not ssid:
                return False, "SSID is required", self.get_wifi_runtime_status(saved_settings)

            if os.name != "posix":
                status = self.get_wifi_runtime_status(saved_settings)
                status["connected"] = False
                return False, "Real Wi-Fi control is only supported on Linux", status

            apply_ok, apply_error = self.apply_saved_wifi_configuration(saved_settings)
            if not apply_ok:
                return False, apply_error, self.get_wifi_runtime_status(saved_settings)

            run_command(["rfkill", "unblock", "wifi"], timeout=5, allow_sudo=True, prefer_sudo=True, sudo_only=True)
            run_command(["ip", "link", "set", interface, "up"], timeout=5, allow_sudo=True, prefer_sudo=True, sudo_only=True)

            status_result = run_command(
                ["wpa_cli", "-i", interface, "status"],
                timeout=5,
                allow_sudo=True,
                prefer_sudo=True,
                sudo_only=True,
            )
            if status_result and status_result.returncode == 0:
                run_command(["wpa_cli", "-i", interface, "reconfigure"], timeout=5, allow_sudo=True, prefer_sudo=True, sudo_only=True)
                run_command(["wpa_cli", "-i", interface, "reconnect"], timeout=5, allow_sudo=True, prefer_sudo=True, sudo_only=True)
            else:
                run_command(["ifdown", "--force", interface], timeout=15, allow_sudo=True, prefer_sudo=True, sudo_only=True)
                result = run_command(["ifup", interface], timeout=20, allow_sudo=True, prefer_sudo=True, sudo_only=True)
                if not result or result.returncode != 0:
                    return (
                        False,
                        format_command_failure(result, "Failed to raise Wi-Fi interface"),
                        self.get_wifi_runtime_status(saved_settings),
                    )

            last_status = self.get_wifi_runtime_status(saved_settings)
            deadline = time.time() + max(1.0, self.config.wifi_connect_timeout_sec)
            connected_since = None
            while time.time() < deadline:
                if last_status.get("issueCode") == "TEMP_DISABLED":
                    return (
                        False,
                        str(last_status.get("issue", "")).strip()
                        or "Gespeicherte WLAN-Zugangsdaten wurden vom Access Point abgelehnt.",
                        last_status,
                    )
                if last_status.get("connected") and last_status.get("ssid", "") == ssid:
                    if connected_since is None:
                        connected_since = time.time()
                    stable_for_sec = time.time() - connected_since
                    if last_status.get("ipAddress") or stable_for_sec >= 2.0:
                        return True, "Wi-Fi connected", last_status
                else:
                    connected_since = None
                time.sleep(1)
                last_status = self.get_wifi_runtime_status(saved_settings)

            if last_status.get("issueCode") == "TEMP_DISABLED":
                return (
                    False,
                    str(last_status.get("issue", "")).strip()
                    or "Gespeicherte WLAN-Zugangsdaten wurden vom Access Point abgelehnt.",
                    last_status,
                )

            status_result = run_command(
                ["wpa_cli", "-i", interface, "status"],
                timeout=5,
                allow_sudo=True,
                prefer_sudo=True,
                sudo_only=True,
            )
            return False, format_command_failure(status_result, "Wi-Fi connection failed"), last_status

    def disconnect_wifi(self):
        with self.operation_lock:
            saved_settings = self.store.load_ui_settings()
            interface = self.get_wifi_config_interface()

            if os.name != "posix":
                status = self.get_wifi_runtime_status(saved_settings)
                status["connected"] = False
                return False, "Real Wi-Fi control is only supported on Linux", status

            run_command(["wpa_cli", "-i", interface, "disconnect"], timeout=5, allow_sudo=True, prefer_sudo=True, sudo_only=True)
            run_command(["ifdown", "--force", interface], timeout=15, allow_sudo=True, prefer_sudo=True, sudo_only=True)
            run_command(["ip", "link", "set", interface, "down"], timeout=5, allow_sudo=True, prefer_sudo=True, sudo_only=True)
            time.sleep(1)

            status = self.get_wifi_runtime_status(saved_settings)
            if not status.get("connected"):
                status["ssid"] = str(saved_settings.get("wifiSsid", "")).strip()
                return True, "Wi-Fi disconnected", status
            return False, "Wi-Fi disconnect failed", status

    def autoconnect_wifi_on_startup(self):
        if os.name != "posix":
            return

        settings = self.store.load_ui_settings()
        target_ssid = str(settings.get("wifiSsid", "")).strip()
        if not settings.get("wifiAutoConnect") or not target_ssid:
            return

        if self.config.wifi_autoconnect_startup_delay_sec > 0:
            time.sleep(self.config.wifi_autoconnect_startup_delay_sec)

        attempts = max(1, self.config.wifi_autoconnect_max_attempts)
        for attempt in range(1, attempts + 1):
            current_settings = self.store.load_ui_settings()
            target_ssid = str(current_settings.get("wifiSsid", "")).strip()
            if not current_settings.get("wifiAutoConnect") or not target_ssid:
                print("Wi-Fi autoconnect skipped: auto-connect disabled or SSID missing.", flush=True)
                return

            current_status = self.get_wifi_runtime_status(current_settings)
            if current_status.get("connected") and current_status.get("ssid", "") == target_ssid:
                print(f"Wi-Fi autoconnect skipped: already connected to {target_ssid}.", flush=True)
                return

            print(f"Wi-Fi autoconnect attempt {attempt}/{attempts} for {target_ssid}.", flush=True)
            ok, message, status = self.connect_wifi()
            if ok and status.get("connected") and status.get("ssid", "") == target_ssid:
                time.sleep(3)
                confirmed_status = self.get_wifi_runtime_status(current_settings)
                if confirmed_status.get("connected") and confirmed_status.get("ssid", "") == target_ssid:
                    print(f"Wi-Fi autoconnect succeeded on attempt {attempt}: {target_ssid}.", flush=True)
                    return
                message = "Wi-Fi connection was not stable after initial connect."

            print(f"Wi-Fi autoconnect attempt {attempt}/{attempts} failed: {message}", flush=True)
            if attempt < attempts and self.config.wifi_autoconnect_retry_delay_sec > 0:
                time.sleep(self.config.wifi_autoconnect_retry_delay_sec)

        print("Wi-Fi autoconnect exhausted all startup attempts.", flush=True)

    def merge_wifi_runtime_settings(self, ui_settings):
        runtime = self.get_wifi_runtime_status(ui_settings)
        saved = self.store.normalize_ui_settings(ui_settings)
        merged = self.store.normalize_ui_settings(
            {
                **saved,
                "wifiConnected": bool(runtime.get("connected", False)),
                "wifiSsid": str(runtime.get("ssid", "")).strip() or str(saved.get("wifiSsid", "")).strip(),
            }
        )
        merged["wifiConnected"] = bool(runtime.get("connected", False))
        merged["wifiSsid"] = str(runtime.get("ssid", "")).strip() or str(saved.get("wifiSsid", "")).strip()
        merged["wifiState"] = str(runtime.get("state", "")).strip()
        merged["wifiIssueCode"] = str(runtime.get("issueCode", "")).strip()
        merged["wifiIssue"] = str(runtime.get("issue", "")).strip()
        return merged

    def _parse_key_value_lines(self, text):
        data = {}
        for raw_line in str(text or "").splitlines():
            if "=" not in raw_line:
                continue
            key, value = raw_line.split("=", 1)
            data[key.strip()] = value.strip()
        return data

    def _parse_wpa_network_lines(self, text):
        networks = []
        for index, raw_line in enumerate(str(text or "").splitlines()):
            line = raw_line.strip()
            if not line or index == 0:
                continue
            parts = raw_line.split("\t")
            if len(parts) < 4:
                continue
            networks.append(
                {
                    "id": parts[0].strip(),
                    "ssid": parts[1].strip(),
                    "bssid": parts[2].strip(),
                    "flags": parts[3].strip(),
                }
            )
        return networks

    def _get_wpa_network_entry(self, interface, target_ssid=""):
        if not interface:
            return None

        result = run_command(
            ["wpa_cli", "-i", interface, "list_networks"],
            timeout=4,
            allow_sudo=True,
            prefer_sudo=True,
            sudo_only=True,
        )
        if not result or result.returncode != 0:
            return None

        networks = self._parse_wpa_network_lines(result.stdout)
        wanted_ssid = str(target_ssid or "").strip()
        if wanted_ssid:
            for network in networks:
                if network.get("ssid", "") == wanted_ssid:
                    return network
        return networks[0] if networks else None

    def _discover_wifi_interfaces(self):
        candidates = []
        if self.config.wifi_interface_name:
            candidates.append(self.config.wifi_interface_name)

        if os.name == "posix":
            for preferred in ("wlan0", "wlan1"):
                if os.path.exists(os.path.join("/sys/class/net", preferred)):
                    candidates.append(preferred)

            result = run_command(["iw", "dev"], timeout=3)
            if result and result.returncode == 0:
                for raw_line in str(result.stdout or "").splitlines():
                    line = raw_line.strip()
                    if line.startswith("Interface "):
                        candidates.append(line.split(None, 1)[1].strip())

            result = run_command(["ip", "-o", "link", "show"], timeout=3)
            if result and result.returncode == 0:
                for raw_line in str(result.stdout or "").splitlines():
                    parts = raw_line.split(":", 2)
                    if len(parts) < 2:
                        continue
                    name = parts[1].strip()
                    if name.startswith("wl"):
                        candidates.append(name)

        return dedupe_strings(candidates)

    def _escape_wpa_value(self, value):
        return str(value or "").replace("\\", "\\\\").replace('"', '\\"')

    def _read_wpa_supplicant_header(self):
        content = read_text_file(self.config.wpa_supplicant_conf_path)
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
            normalized.insert(0, f"country={self.config.wifi_country}")
        if "ctrl_interface" not in seen_keys:
            normalized.append("ctrl_interface=DIR=/run/wpa_supplicant GROUP=netdev")
        if "update_config" not in seen_keys:
            normalized.append("update_config=1")
        return normalized

    def _write_text_file(self, path, content):
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(content)
            return True, ""
        except OSError as exc:
            return False, str(exc)

    def _write_system_text_file(self, path, content, mode=None):
        if os.name != "posix":
            return self._write_text_file(path, content)

        if is_posix_root():
            ok, error = self._write_text_file(path, content)
            if not ok:
                return False, error
            if mode:
                chmod_result = run_command(["chmod", mode, path], timeout=5)
                if not chmod_result or chmod_result.returncode != 0:
                    return False, format_command_failure(chmod_result, f"Failed to chmod {path}")
            return True, ""

        tee_result = run_command(
            ["tee", path],
            timeout=5,
            allow_sudo=True,
            input_text=content,
            prefer_sudo=True,
            sudo_only=True,
        )
        if not tee_result or tee_result.returncode != 0:
            return False, format_command_failure(tee_result, f"Failed to write {path}")

        if mode:
            chmod_result = run_command(
                ["chmod", mode, path],
                timeout=5,
                allow_sudo=True,
                prefer_sudo=True,
                sudo_only=True,
            )
            if not chmod_result or chmod_result.returncode != 0:
                return False, format_command_failure(chmod_result, f"Failed to chmod {path}")
        return True, ""

    def _update_allow_hotplug(self, content, interface, enabled):
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
            indent = lines[allow_index][: len(lines[allow_index]) - len(lines[allow_index].lstrip(" \t"))]
            lines[allow_index] = f"{indent}{desired_line}"
        else:
            insert_at = iface_index if iface_index is not None else len(lines)
            lines.insert(insert_at, desired_line)
            if iface_index is not None and insert_at <= iface_index:
                iface_index += 1

        if iface_index is None:
            if lines and lines[-1].strip():
                lines.append("")
            lines.extend(
                [
                    iface_line,
                    f"    wpa-conf {self.config.wpa_supplicant_conf_path}",
                ]
            )
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
            lines.insert(iface_index + 1, f"    wpa-conf {self.config.wpa_supplicant_conf_path}")
        elif len(wpa_conf_indices) > 1:
            keep_index = wpa_conf_indices[0]
            lines = [
                line
                for index, line in enumerate(lines)
                if index == keep_index or index not in wpa_conf_indices[1:]
            ]

        return "\n".join(lines).strip() + "\n"

    def _parse_scan_results_from_iw(self, text):
        candidates = []
        for raw_line in str(text or "").splitlines():
            line = raw_line.strip()
            if line.startswith("SSID:"):
                candidates.append(line.split(":", 1)[1].strip())
        return candidates

    def _parse_scan_results_from_wpa_cli(self, text):
        candidates = []
        for raw_line in str(text or "").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("bssid /"):
                continue
            parts = line.split("\t")
            if len(parts) >= 5:
                candidates.append(parts[4].strip())
        return candidates
