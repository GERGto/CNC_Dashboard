from __future__ import annotations

import os
import subprocess
import threading

from .command_utils import resolve_command, resolve_executable


class CameraService:
    STREAM_BOUNDARY = "frame"

    def __init__(self, config):
        self.config = config
        self._lock = threading.Lock()
        self._last_error = ""

    def get_status(self):
        ffmpeg_path = resolve_executable(self.config.camera_ffmpeg_path)
        device_path = str(self.config.camera_device_path or "").strip()
        device_exists = bool(device_path) and os.path.exists(device_path)

        available = bool(
            self.config.camera_enabled
            and os.name == "posix"
            and ffmpeg_path
            and device_exists
        )

        error = ""
        if not self.config.camera_enabled:
            error = "Kamera-Streaming ist deaktiviert."
        elif os.name != "posix":
            error = "USB-Kamera-Streaming wird aktuell nur auf Linux/Pi unterstuetzt."
        elif not ffmpeg_path:
            error = "ffmpeg wurde nicht gefunden."
        elif not device_exists:
            error = f"Kamerageraet {device_path or '/dev/video0'} wurde nicht gefunden."

        with self._lock:
            last_error = self._last_error

        if not error and last_error:
            error = last_error

        width = max(0, int(self.config.camera_width))
        height = max(0, int(self.config.camera_height))
        fps = max(1, int(self.config.camera_fps))

        return {
            "enabled": bool(self.config.camera_enabled),
            "available": bool(available),
            "devicePath": device_path,
            "ffmpegPath": ffmpeg_path,
            "streamUrl": "/api/camera/stream",
            "backend": "ffmpeg-v4l2",
            "width": width,
            "height": height,
            "fps": fps,
            "inputFormat": str(self.config.camera_input_format or "").strip(),
            "error": error,
        }

    def stream_mjpeg(self, handler):
        status = self.get_status()
        if not status["available"]:
            return self._send_unavailable(handler, status["error"] or "Kamera-Stream ist nicht verfuegbar.")

        command = self._build_ffmpeg_command()
        if not command:
            return self._send_unavailable(handler, "ffmpeg konnte nicht gestartet werden.")

        handler.send_response(200)
        handler.send_header(
            "Content-Type",
            f"multipart/x-mixed-replace; boundary={self.STREAM_BOUNDARY}",
        )
        handler.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        handler.send_header("Pragma", "no-cache")
        handler.send_header("Access-Control-Allow-Origin", "*")
        handler.end_headers()

        process = None
        disconnected = False
        try:
            self._set_last_error("")
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=0,
            )
        except OSError as exc:
            self._set_last_error(f"ffmpeg Start fehlgeschlagen: {exc}")
            return

        buffer = bytearray()
        try:
            while True:
                chunk = process.stdout.read(4096) if process.stdout else b""
                if not chunk:
                    if process.poll() is not None:
                        break
                    continue
                buffer.extend(chunk)
                self._write_available_frames(handler, buffer)
        except (BrokenPipeError, ConnectionResetError):
            disconnected = True
        finally:
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
            if process and not disconnected and process.returncode not in (None, 0):
                self._set_last_error(f"ffmpeg wurde mit Exit-Code {process.returncode} beendet.")

    def _build_ffmpeg_command(self):
        ffmpeg_command = resolve_command([self.config.camera_ffmpeg_path])
        if not ffmpeg_command:
            return []

        width = max(0, int(self.config.camera_width))
        height = max(0, int(self.config.camera_height))
        fps = max(1, int(self.config.camera_fps))

        command = [
            *ffmpeg_command,
            "-hide_banner",
            "-loglevel",
            "error",
            "-fflags",
            "nobuffer",
            "-f",
            "video4linux2",
        ]

        input_format = str(self.config.camera_input_format or "").strip()
        if input_format:
            command.extend(["-input_format", input_format])

        command.extend(["-framerate", str(fps)])
        if width > 0 and height > 0:
            command.extend(["-video_size", f"{width}x{height}"])

        command.extend(
            [
                "-i",
                self.config.camera_device_path,
                "-an",
                "-q:v",
                str(max(2, min(31, int(self.config.camera_jpeg_quality)))),
                "-f",
                "image2pipe",
                "-vcodec",
                "mjpeg",
                "-",
            ]
        )
        return command

    def _write_available_frames(self, handler, buffer):
        while True:
            start = buffer.find(b"\xff\xd8")
            if start < 0:
                if len(buffer) > 1:
                    del buffer[:-1]
                return

            if start > 0:
                del buffer[:start]
                start = 0

            end = buffer.find(b"\xff\xd9", start + 2)
            if end < 0:
                if len(buffer) > 2_000_000:
                    del buffer[:start]
                return

            frame = bytes(buffer[start : end + 2])
            del buffer[: end + 2]
            self._write_frame(handler, frame)

    def _write_frame(self, handler, frame):
        header = (
            f"--{self.STREAM_BOUNDARY}\r\n"
            "Content-Type: image/jpeg\r\n"
            f"Content-Length: {len(frame)}\r\n\r\n"
        ).encode("ascii")
        handler.wfile.write(header)
        handler.wfile.write(frame)
        handler.wfile.write(b"\r\n")
        handler.wfile.flush()

    def _send_unavailable(self, handler, message):
        payload = str(message or "Kamera-Stream ist nicht verfuegbar.").encode("utf-8", errors="replace")
        handler.send_response(503)
        handler.send_header("Content-Type", "text/plain; charset=utf-8")
        handler.send_header("Content-Length", str(len(payload)))
        handler.send_header("Access-Control-Allow-Origin", "*")
        handler.end_headers()
        handler.wfile.write(payload)

    def _set_last_error(self, message):
        with self._lock:
            self._last_error = str(message or "").strip()
