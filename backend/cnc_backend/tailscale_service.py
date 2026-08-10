from __future__ import annotations

import json
import threading

from .command_utils import format_command_failure, resolve_executable, run_command


class TailscaleService:
    """Read and change the local Tailscale connection without blocking HTTP requests."""

    def __init__(self, command_runner=run_command, executable_resolver=resolve_executable):
        self._run_command = command_runner
        self._resolve_executable = executable_resolver
        self._lock = threading.Lock()
        self._operation_in_progress = False
        self._requested_enabled = None
        self._last_error = ""

    def get_status(self):
        executable = self._resolve_executable("tailscale")
        with self._lock:
            operation_in_progress = self._operation_in_progress
            requested_enabled = self._requested_enabled
            last_error = self._last_error

        if not executable:
            return {
                "installed": False,
                "connected": False,
                "backendState": "NotInstalled",
                "needsLogin": False,
                "ipAddress": "",
                "dnsName": "",
                "operationInProgress": operation_in_progress,
                "requestedEnabled": requested_enabled,
                "error": last_error,
            }

        result = self._run_command([executable, "status", "--json"], timeout=4, allow_sudo=True)
        payload = {}
        status_error = ""
        if result is not None:
            try:
                payload = json.loads(str(result.stdout or "{}"))
            except (TypeError, json.JSONDecodeError):
                status_error = format_command_failure(result, "Tailscale-Status konnte nicht gelesen werden")
        else:
            status_error = "Tailscale-Status konnte nicht gelesen werden"

        if not isinstance(payload, dict):
            payload = {}

        backend_state = str(payload.get("BackendState", "Unknown") or "Unknown").strip()
        self_payload = payload.get("Self", {})
        if not isinstance(self_payload, dict):
            self_payload = {}
        tailscale_ips = self_payload.get("TailscaleIPs", [])
        if not isinstance(tailscale_ips, list):
            tailscale_ips = []

        ip_address = ""
        for candidate in tailscale_ips:
            value = str(candidate or "").strip()
            if value and ":" not in value:
                ip_address = value
                break
        if not ip_address and tailscale_ips:
            ip_address = str(tailscale_ips[0] or "").strip()

        dns_name = str(self_payload.get("DNSName", "") or "").strip().rstrip(".")
        connected = (
            backend_state == "Running"
            and bool(self_payload)
            and bool(self_payload.get("Online", True))
        )

        return {
            "installed": True,
            "connected": connected,
            "backendState": backend_state,
            "needsLogin": backend_state == "NeedsLogin",
            "ipAddress": ip_address,
            "dnsName": dns_name,
            "operationInProgress": operation_in_progress,
            "requestedEnabled": requested_enabled,
            "error": last_error or status_error,
        }

    def request_enabled(self, enabled):
        enabled = bool(enabled)
        status = self.get_status()
        if not status.get("installed"):
            return False, "Tailscale ist nicht installiert", status
        if enabled and status.get("needsLogin"):
            return (
                False,
                "Tailscale muss einmalig per SSH mit 'sudo tailscale up' angemeldet werden",
                status,
            )

        with self._lock:
            if self._operation_in_progress:
                operation_already_running = True
            else:
                operation_already_running = False
                self._operation_in_progress = True
                self._requested_enabled = enabled
                self._last_error = ""

        if operation_already_running:
            return False, "Eine Tailscale-Aktion läuft bereits", status

        worker = threading.Thread(target=self._set_enabled_worker, args=(enabled,), daemon=True)
        worker.start()
        action = "aktiviert" if enabled else "deaktiviert"
        return True, f"Tailscale wird im Hintergrund {action}", self.get_status()

    def _set_enabled_worker(self, enabled):
        error = ""
        try:
            if enabled:
                systemctl = self._resolve_executable("systemctl")
                if systemctl:
                    daemon_result = self._run_command(
                        [systemctl, "enable", "--now", "tailscaled.service"],
                        timeout=20,
                        allow_sudo=True,
                    )
                    if daemon_result is not None and daemon_result.returncode != 0:
                        raise RuntimeError(
                            format_command_failure(daemon_result, "Tailscale-Dienst konnte nicht gestartet werden")
                        )

                tailscale = self._resolve_executable("tailscale")
                result = self._run_command(
                    [tailscale, "up", "--timeout=15s"],
                    timeout=20,
                    allow_sudo=True,
                )
                if result is None or result.returncode != 0:
                    raise RuntimeError(format_command_failure(result, "Tailscale konnte nicht aktiviert werden"))
            else:
                tailscale = self._resolve_executable("tailscale")
                result = self._run_command([tailscale, "down"], timeout=15, allow_sudo=True)
                if result is None or result.returncode != 0:
                    raise RuntimeError(format_command_failure(result, "Tailscale konnte nicht deaktiviert werden"))
        except Exception as exc:  # pragma: no cover - final safety net for the background worker
            error = str(exc)
        finally:
            with self._lock:
                self._operation_in_progress = False
                self._requested_enabled = None
                self._last_error = error
