from __future__ import annotations

import json
import os
import re
import socket
import tempfile
import threading
import time
import unicodedata
from datetime import datetime, timezone

from .command_utils import format_command_failure, resolve_executable, run_command
from .common import iso_now_utc


class ProgramTransferError(Exception):
    status_code = 500


class ProgramValidationError(ProgramTransferError):
    status_code = 400


class ProgramTooLargeError(ProgramTransferError):
    status_code = 413


class ProgramNotFoundError(ProgramTransferError):
    status_code = 404


class ProgramTransferService:
    ALLOWED_EXTENSIONS = frozenset({".gcode", ".nc", ".tap", ".ngc"})
    COPY_CHUNK_SIZE = 1024 * 1024
    RETRY_INTERVAL_SEC = 30.0
    CONTROLLER_STATUS_CACHE_SEC = 3.0
    CONTROLLER_STATUS_TIMEOUT_SEC = 0.25
    CONTROLLER_SMB_PORTS = (445, 139)

    def __init__(self, config, command_runner=run_command, executable_resolver=resolve_executable):
        self.config = config
        self._run_command = command_runner
        self._resolve_executable = executable_resolver
        self._lock = threading.RLock()
        self._wake_event = threading.Event()
        self._worker_started = False
        self._last_attempt_monotonic = {}
        self._controller_connection_cache = None
        self._controller_connection_cache_until = 0.0
        self._state = {"programs": {}}

    def ensure_storage(self):
        os.makedirs(self.config.programs_directory, mode=0o770, exist_ok=True)
        state_parent = os.path.dirname(self.config.programs_state_path)
        if state_parent:
            os.makedirs(state_parent, mode=0o750, exist_ok=True)
        with self._lock:
            self._state = self._read_state()
            self._sync_directory_locked()

    def start_background_tasks(self):
        with self._lock:
            if self._worker_started:
                return
            self._worker_started = True
        threading.Thread(target=self._worker, daemon=True).start()

    def get_snapshot(self):
        with self._lock:
            self._sync_directory_locked()
            programs = [self._public_entry(name, entry) for name, entry in self._programs().items()]
        programs.sort(key=lambda item: item.get("modifiedAt", ""), reverse=True)
        return {
            "programs": programs,
            "controller": self.get_controller_status(),
            "share": {
                "name": self.config.programs_share_name,
                "path": self.config.programs_directory,
            },
            "allowedExtensions": sorted(self.ALLOWED_EXTENSIONS),
            "maxUploadBytes": self.config.program_upload_max_bytes,
        }

    def get_controller_status(self):
        configured, issue = self._controller_configuration_status()
        connected = False
        connection_issue = issue
        checked_at = ""
        if configured:
            connected, connection_issue, checked_at = self._get_cached_controller_connection()
        return {
            "enabled": bool(self.config.controller_smb_enabled),
            "configured": configured,
            "connected": connected,
            "connectionState": "connected" if connected else ("disconnected" if configured else "notConfigured"),
            "connectionIssue": connection_issue,
            "checkedAt": checked_at,
            "host": self.config.controller_smb_host,
            "share": self.config.controller_smb_share,
            "remoteDirectory": self.config.controller_smb_remote_directory,
            "protocol": self.config.controller_smb_protocol,
            "issue": issue,
        }

    def _get_cached_controller_connection(self):
        now = time.monotonic()
        with self._lock:
            if self._controller_connection_cache is not None and now < self._controller_connection_cache_until:
                return self._controller_connection_cache

        result = self._probe_controller_connection()
        with self._lock:
            self._controller_connection_cache = result
            self._controller_connection_cache_until = time.monotonic() + self.CONTROLLER_STATUS_CACHE_SEC
        return result

    def _probe_controller_connection(self):
        host = self.config.controller_smb_host.strip().strip("/\\")
        checked_at = iso_now_utc()
        last_error = ""
        for port in self.CONTROLLER_SMB_PORTS:
            try:
                connection = socket.create_connection(
                    (host, port),
                    timeout=self.CONTROLLER_STATUS_TIMEOUT_SEC,
                )
                connection.close()
                return True, "", checked_at
            except OSError as exc:
                last_error = str(exc).strip()
        detail = f" ({last_error})" if last_error else ""
        return False, f"DDCS-SMB ist nicht erreichbar{detail}", checked_at

    def store_upload(self, requested_name, source, content_length):
        try:
            content_length = int(content_length)
        except (TypeError, ValueError):
            raise ProgramValidationError("Ungültige Upload-Größe")
        if content_length < 0:
            raise ProgramValidationError("Ungültige Upload-Größe")
        if content_length > self.config.program_upload_max_bytes:
            raise ProgramTooLargeError("Die Datei überschreitet die zulässige Upload-Größe")

        safe_name = self._sanitize_program_name(requested_name)
        os.makedirs(self.config.programs_directory, mode=0o770, exist_ok=True)

        with self._lock:
            self._sync_directory_locked()
            safe_name = self._unique_name_locked(safe_name)

        temporary_path = ""
        remaining = content_length
        try:
            descriptor, temporary_path = tempfile.mkstemp(
                prefix=".upload-",
                dir=self.config.programs_directory,
            )
            with os.fdopen(descriptor, "wb") as output:
                while remaining > 0:
                    chunk = source.read(min(self.COPY_CHUNK_SIZE, remaining))
                    if not chunk:
                        raise ProgramValidationError("Der Upload wurde vorzeitig beendet")
                    output.write(chunk)
                    remaining -= len(chunk)
                output.flush()
                os.fsync(output.fileno())

            destination = os.path.join(self.config.programs_directory, safe_name)
            os.replace(temporary_path, destination)
            temporary_path = ""
            self._apply_shared_file_permissions(destination)
        finally:
            if temporary_path:
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass

        with self._lock:
            self._register_path_locked(safe_name, force_pending=True)
            self._write_state_locked()
            payload = self._public_entry(safe_name, self._programs()[safe_name])
        self._wake_event.set()
        return payload

    def get_download(self, name):
        safe_name = self._validate_existing_name(name)
        with self._lock:
            self._sync_directory_locked()
            entry = self._programs().get(safe_name)
            path = os.path.join(self.config.programs_directory, safe_name)
            if entry is None or not os.path.isfile(path):
                raise ProgramNotFoundError("Programmdatei wurde nicht gefunden")
            return path, self._public_entry(safe_name, entry)

    def delete_program(self, name):
        safe_name = self._validate_existing_name(name)
        path = os.path.join(self.config.programs_directory, safe_name)
        with self._lock:
            if not os.path.isfile(path):
                raise ProgramNotFoundError("Programmdatei wurde nicht gefunden")
            try:
                os.unlink(path)
            except OSError as exc:
                raise ProgramTransferError(f"Programmdatei konnte nicht gelöscht werden: {exc}")
            self._programs().pop(safe_name, None)
            self._last_attempt_monotonic.pop(safe_name, None)
            self._write_state_locked()
        return {"ok": True, "name": safe_name}

    def request_transfer(self, name):
        safe_name = self._validate_existing_name(name)
        with self._lock:
            self._sync_directory_locked()
            entry = self._programs().get(safe_name)
            if entry is None:
                raise ProgramNotFoundError("Programmdatei wurde nicht gefunden")
            entry["transferState"] = "pending"
            entry["transferMessage"] = ""
            self._last_attempt_monotonic.pop(safe_name, None)
            self._write_state_locked()
            payload = self._public_entry(safe_name, entry)
        self._wake_event.set()
        return payload

    def _worker(self):
        interval = max(1.0, float(self.config.program_scan_interval_sec))
        while True:
            try:
                self._scan_and_transfer_once()
            except Exception as exc:  # pragma: no cover - worker must survive transient filesystem/network errors
                print(f"Program transfer worker failed: {exc}", flush=True)
            self._wake_event.wait(interval)
            self._wake_event.clear()

    def _scan_and_transfer_once(self):
        configured, _issue = self._controller_configuration_status()
        with self._lock:
            self._sync_directory_locked()
            if not configured:
                return
            candidate = self._next_transfer_candidate_locked()
            if candidate is None:
                return
            name, entry = candidate
            entry["transferState"] = "transferring"
            entry["transferMessage"] = "Übertragung zum CNC-Controller läuft"
            entry["lastAttemptAt"] = iso_now_utc()
            entry["transferAttempts"] = max(0, int(entry.get("transferAttempts", 0) or 0)) + 1
            self._last_attempt_monotonic[name] = time.monotonic()
            self._write_state_locked()

        ok, message = self._transfer_to_controller(name)

        with self._lock:
            current = self._programs().get(name)
            if current is None:
                return
            current["transferState"] = "transferred" if ok else "failed"
            current["transferMessage"] = message
            current["transferredAt"] = iso_now_utc() if ok else ""
            self._write_state_locked()

    def _next_transfer_candidate_locked(self):
        now_monotonic = time.monotonic()
        now_epoch = time.time()
        candidates = []
        for name, entry in self._programs().items():
            if entry.get("transferState") not in {"pending", "failed"}:
                continue
            last_attempt = self._last_attempt_monotonic.get(name)
            if last_attempt is not None and (now_monotonic - last_attempt) < self.RETRY_INTERVAL_SEC:
                continue
            try:
                modified_epoch = float(entry.get("modifiedEpoch", 0.0) or 0.0)
            except (TypeError, ValueError):
                modified_epoch = 0.0
            if (now_epoch - modified_epoch) < self.config.program_settle_seconds:
                continue
            candidates.append((name, entry))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[1].get("modifiedAt", ""))
        return candidates[0]

    def _transfer_to_controller(self, name):
        executable = self._resolve_executable("smbclient")
        if not executable:
            return False, "smbclient ist nicht installiert"

        host = self.config.controller_smb_host.strip().strip("/\\")
        share = self.config.controller_smb_share.strip().strip("/\\")
        unc_path = f"//{host}/{share}"
        local_path = os.path.join(self.config.programs_directory, name)
        remote_temp_name = f".{name}.uploading"

        upload_command = self._with_remote_directory(
            f"put {self._smb_quote(local_path)} {self._smb_quote(remote_temp_name)}"
        )
        upload_result = self._run_smbclient_command(executable, unc_path, upload_command)
        if upload_result is None or upload_result.returncode != 0:
            return False, format_command_failure(upload_result, "SMB-Upload ist fehlgeschlagen")

        protocol = self.config.controller_smb_protocol.strip().upper()
        if protocol == "NT1":
            delete_command = self._with_remote_directory(f"del {self._smb_quote(name)}")
            self._run_smbclient_command(executable, unc_path, delete_command)
            rename_command = self._with_remote_directory(
                f"rename {self._smb_quote(remote_temp_name)} {self._smb_quote(name)}"
            )
        else:
            rename_command = self._with_remote_directory(
                f"rename {self._smb_quote(remote_temp_name)} {self._smb_quote(name)} -f"
            )
        rename_result = self._run_smbclient_command(executable, unc_path, rename_command)
        if rename_result is None or rename_result.returncode != 0:
            return False, format_command_failure(rename_result, "SMB-Zieldatei konnte nicht aktiviert werden")
        return True, "An CNC-Controller übertragen"

    def _run_smbclient_command(self, executable, unc_path, smb_command):
        command = [executable, unc_path]
        protocol = self.config.controller_smb_protocol.strip().upper()
        if protocol:
            command.extend([f"--option=client min protocol={protocol}", "-m", protocol])
        username = self.config.controller_smb_username.strip()
        domain = self.config.controller_smb_domain.strip()
        if username:
            account = f"{domain}\\{username}" if domain else username
            command.extend(["-U", account])
        else:
            command.append("-N")
        command.extend(["-c", smb_command])
        env = {}
        if username or self.config.controller_smb_password:
            env["PASSWD"] = self.config.controller_smb_password
        return self._run_command(
            command,
            timeout=self.config.controller_smb_timeout_sec,
            env=env,
        )

    def _with_remote_directory(self, command):
        remote_directory = self.config.controller_smb_remote_directory.strip().strip("/\\")
        if not remote_directory:
            return command
        return f"cd {self._smb_quote(remote_directory)}; {command}"

    @staticmethod
    def _smb_quote(value):
        return f'"{str(value).replace(chr(34), "")}"'

    def _controller_configuration_status(self):
        if not self.config.controller_smb_enabled:
            return False, "CNC-Controller-SMB ist noch deaktiviert"
        host = self.config.controller_smb_host.strip().strip("/\\")
        share = self.config.controller_smb_share.strip().strip("/\\")
        if not host or not share:
            return False, "SMB-Host oder Freigabe des CNC-Controllers fehlt"
        if not re.fullmatch(r"[A-Za-z0-9_.:-]+", host):
            return False, "SMB-Host des CNC-Controllers ist ungültig"
        if not re.fullmatch(r"[A-Za-z0-9_.$ -]+", share):
            return False, "SMB-Freigabe des CNC-Controllers ist ungültig"
        remote_directory = self.config.controller_smb_remote_directory.strip()
        if remote_directory and not re.fullmatch(r"[A-Za-z0-9_./\\ $-]+", remote_directory):
            return False, "SMB-Zielverzeichnis des CNC-Controllers ist ungültig"
        protocol = self.config.controller_smb_protocol.strip().upper()
        if protocol and protocol not in {"NT1", "SMB2", "SMB3"}:
            return False, "SMB-Protokoll des CNC-Controllers ist ungültig"
        return True, ""

    def _sync_directory_locked(self):
        changed = False
        disk_names = set()
        try:
            directory_entries = list(os.scandir(self.config.programs_directory))
        except FileNotFoundError:
            os.makedirs(self.config.programs_directory, mode=0o770, exist_ok=True)
            directory_entries = []

        for item in directory_entries:
            if item.name.startswith(".") or not item.is_file(follow_symlinks=False):
                continue
            if os.path.splitext(item.name)[1].lower() not in self.ALLOWED_EXTENSIONS:
                continue
            disk_names.add(item.name)
            if self._register_path_locked(item.name):
                changed = True

        for missing_name in set(self._programs()) - disk_names:
            self._programs().pop(missing_name, None)
            self._last_attempt_monotonic.pop(missing_name, None)
            changed = True

        if changed:
            self._write_state_locked()

    def _register_path_locked(self, name, force_pending=False):
        path = os.path.join(self.config.programs_directory, name)
        try:
            stat = os.stat(path, follow_symlinks=False)
        except OSError:
            return False
        signature = f"{stat.st_size}:{stat.st_mtime_ns}"
        modified_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).replace(microsecond=0)
        entry = self._programs().get(name)
        changed = entry is None or entry.get("signature") != signature or force_pending
        if not changed:
            return False
        self._programs()[name] = {
            "signature": signature,
            "sizeBytes": stat.st_size,
            "modifiedAt": modified_at.isoformat().replace("+00:00", "Z"),
            "modifiedEpoch": stat.st_mtime,
            "transferState": "pending",
            "transferMessage": "",
            "transferAttempts": 0,
            "lastAttemptAt": "",
            "transferredAt": "",
        }
        self._last_attempt_monotonic.pop(name, None)
        return True

    def _public_entry(self, name, entry):
        transfer_state = str(entry.get("transferState", "pending"))
        message = str(entry.get("transferMessage", "") or "")
        configured, issue = self._controller_configuration_status()
        if transfer_state == "pending" and not configured:
            transfer_state = "waitingForController"
            message = issue
        return {
            "name": name,
            "sizeBytes": max(0, int(entry.get("sizeBytes", 0) or 0)),
            "modifiedAt": str(entry.get("modifiedAt", "")),
            "transferState": transfer_state,
            "transferMessage": message,
            "transferAttempts": max(0, int(entry.get("transferAttempts", 0) or 0)),
            "lastAttemptAt": str(entry.get("lastAttemptAt", "") or ""),
            "transferredAt": str(entry.get("transferredAt", "") or ""),
        }

    def _sanitize_program_name(self, requested_name):
        raw_name = os.path.basename(str(requested_name or "").strip().replace("\\", "/"))
        extension = os.path.splitext(raw_name)[1].lower()
        if extension not in self.ALLOWED_EXTENSIONS:
            allowed = ", ".join(sorted(self.ALLOWED_EXTENSIONS))
            raise ProgramValidationError(f"Nicht unterstütztes Dateiformat. Erlaubt: {allowed}")
        stem = os.path.splitext(raw_name)[0]
        ascii_stem = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode("ascii")
        ascii_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", ascii_stem).strip("._-")
        if not ascii_stem:
            ascii_stem = "programm"
        return f"{ascii_stem[:100]}{extension}"

    def _validate_existing_name(self, name):
        value = str(name or "").strip()
        if not value or value != os.path.basename(value) or value.startswith("."):
            raise ProgramValidationError("Ungültiger Dateiname")
        if os.path.splitext(value)[1].lower() not in self.ALLOWED_EXTENSIONS:
            raise ProgramValidationError("Ungültiges Dateiformat")
        return value

    def _unique_name_locked(self, safe_name):
        stem, extension = os.path.splitext(safe_name)
        candidate = safe_name
        number = 2
        while candidate in self._programs() or os.path.exists(os.path.join(self.config.programs_directory, candidate)):
            candidate = f"{stem[:92]}-{number}{extension}"
            number += 1
        return candidate

    def _apply_shared_file_permissions(self, path):
        try:
            directory_stat = os.stat(self.config.programs_directory)
            if hasattr(os, "chown"):
                os.chown(path, directory_stat.st_uid, directory_stat.st_gid)
            os.chmod(path, 0o660)
        except OSError:
            pass

    def _programs(self):
        programs = self._state.setdefault("programs", {})
        if not isinstance(programs, dict):
            programs = {}
            self._state["programs"] = programs
        return programs

    def _read_state(self):
        try:
            with open(self.config.programs_state_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if isinstance(payload, dict) and isinstance(payload.get("programs", {}), dict):
                return payload
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            pass
        return {"programs": {}}

    def _write_state_locked(self):
        parent = os.path.dirname(self.config.programs_state_path) or "."
        os.makedirs(parent, mode=0o750, exist_ok=True)
        descriptor, temporary_path = tempfile.mkstemp(prefix=".program-state-", dir=parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(self._state, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.config.programs_state_path)
        finally:
            if os.path.exists(temporary_path):
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass
