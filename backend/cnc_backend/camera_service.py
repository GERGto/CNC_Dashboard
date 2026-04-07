from __future__ import annotations

import os
import threading
import time

from .command_utils import format_command_failure, resolve_executable, run_command


class CameraService:
    CAMERA_PUBLISHER_SERVICE = "cnc-dashboard-camera-publisher.service"
    MEDIAMTX_SERVICE = "cnc-dashboard-mediamtx.service"
    SERVICE_CHECK_INTERVAL_SEC = 2.0
    START_RETRY_INTERVAL_SEC = 2.0

    def __init__(self, config):
        self.config = config
        self._lock = threading.Lock()
        self._last_demand_monotonic = time.monotonic()
        self._last_start_attempt_monotonic = 0.0
        self._last_start_error = ""

    def start_background_tasks(self):
        if not self._supports_on_demand():
            return
        threading.Thread(target=self._idle_worker, daemon=True).start()

    def get_status(self, ensure_active=False):
        ffmpeg_path = resolve_executable(self.config.camera_ffmpeg_path)
        mediamtx_path = resolve_executable(self.config.camera_mediamtx_path)
        device_path = str(self.config.camera_device_path or "").strip()
        device_exists = bool(device_path) and os.path.exists(device_path)
        on_demand_enabled = bool(self.config.camera_on_demand_enabled)

        base_ready = bool(
            self.config.camera_enabled
            and os.name == "posix"
            and ffmpeg_path
            and mediamtx_path
            and device_exists
        )

        error = ""
        if not self.config.camera_enabled:
            error = "Kamera-Streaming ist deaktiviert."
        elif os.name != "posix":
            error = "USB-Kamera-Streaming wird aktuell nur auf Linux/Pi unterstuetzt."
        elif not ffmpeg_path:
            error = "ffmpeg wurde nicht gefunden."
        elif not mediamtx_path:
            error = "MediaMTX wurde nicht gefunden."
        elif not device_exists:
            error = f"Kamerageraet {device_path or '/dev/video0'} wurde nicht gefunden."

        stream_state = "inactive"
        service_states = {"mediamtx": "unknown", "publisher": "unknown"}
        if on_demand_enabled and self._supports_on_demand():
            if ensure_active and base_ready:
                self._register_demand()
                start_error = self._ensure_stream_services_started()
                if start_error:
                    error = start_error

            service_states = self._get_service_states()
            all_active = self._all_services_active(service_states)
            if all_active:
                stream_state = "active"
            elif ensure_active and base_ready:
                stream_state = "starting"
                if not error:
                    error = "Kamera-Stream wird gestartet."
            else:
                if not error:
                    error = "Kamera-Stream ist inaktiv und wird bei Bedarf gestartet."

        available = bool(base_ready and (not on_demand_enabled or self._all_services_active(service_states)))
        if available:
            error = ""
            stream_state = "active"

        width = max(0, int(self.config.camera_width))
        height = max(0, int(self.config.camera_height))
        fps = max(1, int(self.config.camera_fps))
        stream_path = str(self.config.camera_stream_path or "camera").strip().strip("/") or "camera"
        video_bitrate = max(0, int(self.config.camera_video_bitrate or 0))
        webrtc_port = max(0, int(self.config.camera_webrtc_port or 0))
        rtsp_port = max(0, int(self.config.camera_rtsp_port or 0))

        return {
            "enabled": bool(self.config.camera_enabled),
            "onDemandEnabled": on_demand_enabled,
            "idleTimeoutSec": max(0.0, float(self.config.camera_idle_timeout_sec)),
            "available": bool(available),
            "devicePath": device_path,
            "ffmpegPath": ffmpeg_path,
            "mediamtxPath": mediamtx_path,
            "backend": "mediamtx-webrtc",
            "transport": "webrtc",
            "streamState": stream_state,
            "serviceStates": service_states,
            "streamPath": stream_path,
            "whepPath": f"/{stream_path}/whep",
            "webrtcPort": webrtc_port,
            "rtspPort": rtsp_port,
            "width": width,
            "height": height,
            "fps": fps,
            "videoBitrate": video_bitrate,
            "inputFormat": str(self.config.camera_input_format or "").strip(),
            "error": error,
        }

    def _supports_on_demand(self):
        return bool(self.config.camera_on_demand_enabled and os.name == "posix")

    def _register_demand(self):
        with self._lock:
            self._last_demand_monotonic = time.monotonic()

    def _get_service_states(self):
        if not self._supports_on_demand():
            return {"mediamtx": "unknown", "publisher": "unknown"}

        result = run_command(
            ["systemctl", "is-active", self.MEDIAMTX_SERVICE, self.CAMERA_PUBLISHER_SERVICE],
            timeout=3,
            allow_sudo=True,
            prefer_sudo=True,
        )
        stdout_lines = [line.strip() for line in str(result.stdout or "").splitlines() if line.strip()] if result else []
        mediamtx_state = stdout_lines[0] if len(stdout_lines) >= 1 else "unknown"
        publisher_state = stdout_lines[1] if len(stdout_lines) >= 2 else "unknown"
        return {
            "mediamtx": mediamtx_state,
            "publisher": publisher_state,
        }

    def _all_services_active(self, states):
        return bool(states.get("mediamtx") == "active" and states.get("publisher") == "active")

    def _any_service_active(self, states):
        return bool(states.get("mediamtx") == "active" or states.get("publisher") == "active")

    def _ensure_stream_services_started(self):
        if not self._supports_on_demand():
            return ""

        states = self._get_service_states()
        if self._all_services_active(states):
            with self._lock:
                self._last_start_error = ""
            return ""

        now = time.monotonic()
        with self._lock:
            if now - self._last_start_attempt_monotonic < self.START_RETRY_INTERVAL_SEC:
                return self._last_start_error
            self._last_start_attempt_monotonic = now

        result = run_command(
            ["systemctl", "start", self.MEDIAMTX_SERVICE, self.CAMERA_PUBLISHER_SERVICE],
            timeout=10,
            allow_sudo=True,
            prefer_sudo=True,
        )
        if result is not None and result.returncode == 0:
            with self._lock:
                self._last_start_error = ""
            return ""

        message = format_command_failure(result, "Kamera-Stream konnte nicht gestartet werden")
        with self._lock:
            self._last_start_error = message
        return message

    def _stop_stream_services(self):
        if not self._supports_on_demand():
            return
        result = run_command(
            ["systemctl", "stop", self.CAMERA_PUBLISHER_SERVICE, self.MEDIAMTX_SERVICE],
            timeout=10,
            allow_sudo=True,
            prefer_sudo=True,
        )
        if result is not None and result.returncode != 0:
            detail = format_command_failure(result, "Kamera-Stream konnte nicht gestoppt werden")
            print(detail, flush=True)
            return

        run_command(
            ["systemctl", "reset-failed", self.CAMERA_PUBLISHER_SERVICE, self.MEDIAMTX_SERVICE],
            timeout=10,
            allow_sudo=True,
            prefer_sudo=True,
        )

    def _idle_worker(self):
        idle_timeout_sec = max(5.0, float(self.config.camera_idle_timeout_sec or 0.0))
        while True:
            try:
                now = time.monotonic()
                with self._lock:
                    last_demand = self._last_demand_monotonic
                if (now - last_demand) >= idle_timeout_sec:
                    states = self._get_service_states()
                    if self._any_service_active(states):
                        self._stop_stream_services()
            except Exception as exc:  # pragma: no cover - background safety net
                print(f"Camera idle worker failed: {exc}", flush=True)
            time.sleep(self.SERVICE_CHECK_INTERVAL_SEC)
