from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone


def iso_now_utc():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def clamp(value, min_value, max_value):
    return max(min_value, min(max_value, value))


def to_int(raw_value, default_value):
    try:
        return int(raw_value)
    except (ValueError, TypeError):
        return int(default_value)


# The machine is regularly switched off at the wall instead of being shut down,
# so every state file has to survive losing power mid-write.
BACKUP_SUFFIX = ".bak"
BACKUP_MIN_AGE_SEC = 300.0


def _fsync_directory(path):
    """Makes a rename durable - fsync on the file alone does not cover it."""
    directory = os.path.dirname(os.path.abspath(path)) or "."
    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _load_json_file(path):
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else None


def read_json_dict(path):
    """Reads a state file, falling back to its backup if it is unreadable.

    A truncated file used to be silently treated as "empty", which reset
    runtime counters and maintenance history to their defaults.
    """
    for candidate in (path, f"{path}{BACKUP_SUFFIX}"):
        try:
            data = _load_json_file(candidate)
        except FileNotFoundError:
            continue
        except (OSError, json.JSONDecodeError) as exc:
            print(f"State file {candidate} is unreadable ({exc}), trying the backup.", flush=True)
            continue
        if data is None:
            continue
        if candidate != path:
            print(f"State file {path} was restored from its backup.", flush=True)
        return data
    return {}


def _refresh_backup(path):
    """Keeps one older generation of a state file that is known to parse."""
    backup_path = f"{path}{BACKUP_SUFFIX}"
    try:
        if (time.time() - os.path.getmtime(backup_path)) < BACKUP_MIN_AGE_SEC:
            return
    except OSError:
        pass

    try:
        if _load_json_file(path) is None:
            return
        with open(path, "rb") as source:
            payload = source.read()
    except (OSError, json.JSONDecodeError):
        return

    temp_path = f"{backup_path}.tmp"
    try:
        with open(temp_path, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, backup_path)
        _fsync_directory(backup_path)
    except OSError:
        try:
            os.unlink(temp_path)
        except OSError:
            pass


def write_json_dict(path, data):
    # Write beside the target and rename: the reader either sees the old file or
    # the complete new one, never a half-written mixture.
    _refresh_backup(path)

    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.chmod(temp_path, os.stat(path).st_mode & 0o7777)
    except OSError:
        pass
    os.replace(temp_path, path)
    _fsync_directory(path)


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


def parse_bool_query_flag(params, name):
    raw_values = params.get(name)
    if not raw_values:
        return False
    raw_value = str(raw_values[0]).strip().lower()
    return raw_value in {"1", "true", "yes", "on"}
