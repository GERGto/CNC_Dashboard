from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import threading
import time
from datetime import datetime

from .command_utils import resolve_executable
from .common import iso_now_utc


class RecordingError(Exception):
    """Raised for recording requests that cannot be fulfilled."""

    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


class RecordingService:
    """Records the camera stream on the Pi instead of in the browser.

    MediaMTX already carries H.264, so ffmpeg only remuxes into MP4 (-c copy).
    That costs almost no CPU, keeps the full stream quality and produces a
    playable MP4 regardless of what the viewing browser can encode.
    """

    FILE_NAME_PATTERN = re.compile(r"^aufnahme_[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{2}-[0-9]{2}-[0-9]{2}\.mp4$")
    STOP_GRACE_SEC = 10.0
    STREAM_HOLD_INTERVAL_SEC = 5.0
    # The camera publisher needs roughly eight seconds from a cold start until
    # it opens the USB camera and publishes to MediaMTX.
    STREAM_READY_TIMEOUT_SEC = 30.0
    STREAM_PROBE_INTERVAL_SEC = 1.0

    def __init__(self, config, camera_service=None):
        self.config = config
        self.camera_service = camera_service
        self._lock = threading.Lock()
        self._process = None
        self._file_name = ""
        self._started_at = ""
        self._started_monotonic = 0.0
        self._last_error = ""
        self._stopping = False
        self._stderr_thread = None
        self._stderr_tail = ""

    # ---------------------------------------------------------------- storage

    @property
    def directory(self):
        return str(self.config.recordings_directory or "").strip()

    def ensure_storage(self):
        if not self.directory:
            return
        try:
            os.makedirs(self.directory, exist_ok=True)
        except OSError as exc:  # pragma: no cover - unwritable storage is reported on use
            print(f"Recording directory could not be created: {exc}", flush=True)

    def list_recordings(self):
        recordings = []
        try:
            names = sorted(os.listdir(self.directory), reverse=True)
        except OSError:
            return recordings

        for name in names:
            if not self.FILE_NAME_PATTERN.match(name):
                continue
            path = os.path.join(self.directory, name)
            try:
                stat = os.stat(path)
            except OSError:
                continue
            recordings.append(
                {
                    "name": name,
                    "sizeBytes": int(stat.st_size),
                    "createdAt": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(),
                    "downloadPath": f"/api/camera/recordings/{name}/download",
                }
            )
        return recordings

    def resolve_recording_path(self, name):
        candidate = str(name or "").strip()
        if not self.FILE_NAME_PATTERN.match(candidate):
            raise RecordingError("Unbekannte Aufnahme", status_code=404)
        path = os.path.join(self.directory, candidate)
        if not os.path.isfile(path):
            raise RecordingError("Unbekannte Aufnahme", status_code=404)
        return path

    def delete_recording(self, name):
        path = self.resolve_recording_path(name)
        with self._lock:
            active_name = self._file_name if self._process is not None else ""
        if active_name and os.path.basename(path) == active_name:
            raise RecordingError("Die laufende Aufnahme kann nicht gelöscht werden", status_code=409)
        try:
            os.remove(path)
        except OSError as exc:
            raise RecordingError(f"Aufnahme konnte nicht gelöscht werden: {exc}", status_code=500)
        return {"ok": True, "name": os.path.basename(path)}

    def _free_bytes(self):
        try:
            usage = shutil.disk_usage(self.directory)
            return int(usage.free)
        except OSError:
            return None

    def _prune_recordings(self, keep_name=""):
        """Drops the oldest recordings once the archive exceeds its budget."""
        recordings = self.list_recordings()
        max_files = max(1, int(self.config.recording_max_files))
        max_total_bytes = max(0, int(self.config.recording_max_total_bytes))

        total_bytes = sum(entry["sizeBytes"] for entry in recordings)
        # list_recordings() is newest first, so walk from the back.
        for entry in reversed(recordings):
            over_count = len(recordings) > max_files
            over_size = max_total_bytes and total_bytes > max_total_bytes
            if not over_count and not over_size:
                break
            if entry["name"] == keep_name:
                continue
            try:
                os.remove(os.path.join(self.directory, entry["name"]))
            except OSError:
                continue
            total_bytes -= entry["sizeBytes"]
            recordings = [item for item in recordings if item["name"] != entry["name"]]

    # ----------------------------------------------------------------- status

    def get_status(self):
        with self._lock:
            process = self._process
            file_name = self._file_name
            started_at = self._started_at
            started_monotonic = self._started_monotonic
            last_error = self._last_error

        active = process is not None and process.poll() is None
        if process is not None and not active:
            # The process ended on its own (duration limit or stream loss).
            self._finalize_finished_process()
            with self._lock:
                last_error = self._last_error
                file_name = ""

        return {
            "available": bool(self.directory and resolve_executable(self.config.camera_ffmpeg_path)),
            "active": active,
            "fileName": file_name if active else "",
            "startedAt": started_at if active else "",
            "elapsedSec": round(max(0.0, time.monotonic() - started_monotonic), 1) if active else 0.0,
            "maxDurationSec": max(0, int(self.config.recording_max_duration_sec)),
            "freeBytes": self._free_bytes(),
            "error": last_error,
            "recordings": self.list_recordings(),
        }

    def _finalize_finished_process(self):
        with self._lock:
            process = self._process
            if process is None or process.poll() is None:
                return
            stderr_thread = self._stderr_thread

        if stderr_thread is not None:
            stderr_thread.join(timeout=2.0)

        with self._lock:
            process = self._process
            if process is None:
                return
            file_name = self._file_name
            stopping = self._stopping
            stderr_tail = self._stderr_tail
            self._process = None
            self._file_name = ""
            self._started_at = ""
            self._stopping = False
            self._stderr_thread = None
            if process.returncode not in (0, 255) and not stopping:
                detail = f": {stderr_tail}" if stderr_tail else ""
                self._last_error = f"Die Aufnahme wurde unerwartet beendet{detail}"

        path = os.path.join(self.directory, file_name) if file_name else ""
        if path and os.path.isfile(path) and os.path.getsize(path) == 0:
            try:
                os.remove(path)
            except OSError:
                pass
        self._prune_recordings(keep_name=file_name)

    # ---------------------------------------------------------------- control

    def start(self):
        ffmpeg = resolve_executable(self.config.camera_ffmpeg_path)
        if not ffmpeg:
            raise RecordingError("ffmpeg wurde nicht gefunden", status_code=503)
        if not self.directory:
            raise RecordingError("Kein Speicherort für Aufnahmen konfiguriert", status_code=503)

        self.ensure_storage()

        free_bytes = self._free_bytes()
        min_free_bytes = max(0, int(self.config.recording_min_free_bytes))
        if free_bytes is not None and free_bytes < min_free_bytes:
            raise RecordingError("Zu wenig freier Speicher auf der SD-Karte", status_code=507)

        with self._lock:
            if self._process is not None and self._process.poll() is None:
                raise RecordingError("Es läuft bereits eine Aufnahme", status_code=409)

        # A systemd-active publisher is not the same as a published stream:
        # ffmpeg exits instantly with "no stream is available on path" if it
        # connects during the camera's startup window.
        if not self._wait_for_stream(ffmpeg):
            raise RecordingError("Der Kamera-Stream war nicht rechtzeitig bereit", status_code=503)

        with self._lock:
            if self._process is not None and self._process.poll() is None:
                raise RecordingError("Es läuft bereits eine Aufnahme", status_code=409)

            file_name = f"aufnahme_{time.strftime('%Y-%m-%d_%H-%M-%S')}.mp4"
            target_path = os.path.join(self.directory, file_name)
            command = self._build_command(ffmpeg, target_path)
            try:
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    start_new_session=True,
                )
            except OSError as exc:
                raise RecordingError(f"Aufnahme konnte nicht gestartet werden: {exc}", status_code=500)

            self._process = process
            self._file_name = file_name
            self._started_at = iso_now_utc()
            self._started_monotonic = time.monotonic()
            self._last_error = ""
            self._stopping = False
            self._stderr_tail = ""
            # Drained in a thread: a full stderr pipe would otherwise block
            # ffmpeg in the middle of a long recording.
            self._stderr_thread = threading.Thread(
                target=self._stderr_worker, args=(process,), daemon=True
            )
            self._stderr_thread.start()

        threading.Thread(target=self._hold_stream_worker, args=(process,), daemon=True).start()
        return self.get_status()

    def _stderr_worker(self, process):
        lines = []
        try:
            for raw_line in process.stderr:
                line = raw_line.decode("utf-8", "replace").strip()
                if line:
                    lines.append(line)
                    del lines[:-3]
        except (OSError, ValueError):  # pragma: no cover - pipe closed with the process
            pass
        with self._lock:
            self._stderr_tail = " | ".join(lines)

    def _stream_url(self):
        rtsp_port = max(1, int(self.config.camera_rtsp_port or 8554))
        stream_path = str(self.config.camera_stream_path or "camera").strip().strip("/") or "camera"
        return f"rtsp://127.0.0.1:{rtsp_port}/{stream_path}"

    def _wait_for_stream(self, ffmpeg):
        deadline = time.monotonic() + self.STREAM_READY_TIMEOUT_SEC
        probe_command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel", "error",
            "-rtsp_transport", "tcp",
            "-i", self._stream_url(),
            "-t", "0.2",
            "-f", "null",
            "-",
        ]

        while time.monotonic() < deadline:
            if self.camera_service is not None:
                try:
                    self.camera_service.get_status(ensure_active=True)
                except Exception as exc:  # pragma: no cover - camera state is reported below
                    print(f"Camera activation before recording failed: {exc}", flush=True)
            try:
                probe = subprocess.run(
                    probe_command,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    timeout=10,
                    check=False,
                )
                if probe.returncode == 0:
                    return True
            except (OSError, subprocess.SubprocessError):
                pass
            time.sleep(self.STREAM_PROBE_INTERVAL_SEC)
        return False

    def _build_command(self, ffmpeg, target_path):
        max_duration_sec = max(1, int(self.config.recording_max_duration_sec))
        return [
            ffmpeg,
            "-hide_banner",
            "-loglevel", "error",
            "-rtsp_transport", "tcp",
            "-i", self._stream_url(),
            "-an",
            # Remux only: the publisher already delivers H.264, so no frame is
            # re-encoded and the Pi stays idle during a recording.
            "-c", "copy",
            "-movflags", "+faststart",
            "-t", str(max_duration_sec),
            "-y",
            target_path,
        ]

    def _hold_stream_worker(self, process):
        """Keeps the on-demand camera services alive while ffmpeg records.

        Without this the idle watchdog would shut the stream down as soon as the
        last browser stops polling - mid-recording.
        """
        while process.poll() is None:
            if self.camera_service is not None:
                try:
                    self.camera_service.get_status(ensure_active=True)
                except Exception as exc:  # pragma: no cover - background safety net
                    print(f"Recording stream hold failed: {exc}", flush=True)
            time.sleep(self.STREAM_HOLD_INTERVAL_SEC)
        self._finalize_finished_process()

    def stop(self):
        with self._lock:
            process = self._process
            file_name = self._file_name
            if process is None or process.poll() is not None:
                raise RecordingError("Es läuft keine Aufnahme", status_code=409)
            self._stopping = True

        # SIGINT is ffmpeg's clean shutdown: it writes the MP4 index before
        # exiting. A kill would leave an unplayable file behind.
        try:
            process.send_signal(signal.SIGINT)
            process.wait(timeout=self.STOP_GRACE_SEC)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
        except OSError:
            pass

        self._finalize_finished_process()

        status = self.get_status()
        recording = next(
            (entry for entry in status.get("recordings", []) if entry["name"] == file_name),
            None,
        )
        if recording is None:
            raise RecordingError("Die Aufnahme enthielt keine Daten", status_code=500)
        return status, recording
