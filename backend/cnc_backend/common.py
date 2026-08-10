from __future__ import annotations

import json
import os
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
    # The appliance is switched off at the wall, so a plain truncating write can
    # leave a half-written settings/tasks file behind. Write beside the target
    # and rename: the reader either sees the old file or the complete new one.
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
