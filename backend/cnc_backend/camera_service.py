from __future__ import annotations

import os

from .command_utils import resolve_executable


class CameraService:
    def __init__(self, config):
        self.config = config

    def get_status(self):
        ffmpeg_path = resolve_executable(self.config.camera_ffmpeg_path)
        mediamtx_path = resolve_executable(self.config.camera_mediamtx_path)
        device_path = str(self.config.camera_device_path or "").strip()
        device_exists = bool(device_path) and os.path.exists(device_path)

        available = bool(
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

        width = max(0, int(self.config.camera_width))
        height = max(0, int(self.config.camera_height))
        fps = max(1, int(self.config.camera_fps))
        stream_path = str(self.config.camera_stream_path or "camera").strip().strip("/") or "camera"
        video_bitrate = max(0, int(self.config.camera_video_bitrate or 0))
        webrtc_port = max(0, int(self.config.camera_webrtc_port or 0))
        rtsp_port = max(0, int(self.config.camera_rtsp_port or 0))

        return {
            "enabled": bool(self.config.camera_enabled),
            "available": bool(available),
            "devicePath": device_path,
            "ffmpegPath": ffmpeg_path,
            "mediamtxPath": mediamtx_path,
            "backend": "mediamtx-webrtc",
            "transport": "webrtc",
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
