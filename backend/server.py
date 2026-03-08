import json
import math
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs


PORT = int(os.getenv("PORT", "8080"))
DEFAULT_INTERVAL_MS = int(os.getenv("AXES_INTERVAL_MS", "250"))
SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "settings.json")
DEFAULT_SETTINGS = {
    "graphWindowSec": 60,
    "lightBrightness": 75,
    "fanSpeed": 40,
    "fanAuto": False,
    "spindleRuntimeSec": 0,
}


def clamp(value, min_value, max_value):
    return max(min_value, min(max_value, value))


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


def mock_axes_load(t_ms):
    def base(i):
        value = (math.sin(t_ms / 700.0 + i) * 40.0 + 50.0)
        return round(value, 1)

    return {
        "spindle": base(0),
        "x": base(1),
        "y": base(2),
        "z": base(3),
    }


def load_settings():
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            if isinstance(data, dict):
                return {**DEFAULT_SETTINGS, **data}
    except FileNotFoundError:
        return DEFAULT_SETTINGS.copy()
    except (OSError, json.JSONDecodeError):
        return DEFAULT_SETTINGS.copy()
    return DEFAULT_SETTINGS.copy()


def save_settings(settings):
    data = {**load_settings(), **settings}
    with open(SETTINGS_PATH, "w", encoding="utf-8") as handle:
        json.dump(data, handle)
    return data


class Handler(BaseHTTPRequestHandler):
    def handle_one_request(self):
        try:
            return super().handle_one_request()
        except ConnectionAbortedError:
            return

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/health":
            return json_response(self, 200, {"status": "ok", "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})

        if path == "/api/axes":
            return json_response(self, 200, {"timestamp": int(time.time() * 1000), "axes": mock_axes_load(int(time.time() * 1000))})

        if path == "/api/axes/stream":
            params = parse_qs(parsed.query or "")
            interval_ms = DEFAULT_INTERVAL_MS
            if "intervalMs" in params:
                try:
                    interval_ms = int(params["intervalMs"][0])
                except (ValueError, TypeError):
                    interval_ms = DEFAULT_INTERVAL_MS
            interval_ms = clamp(interval_ms, 50, 5000)

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            try:
                while True:
                    payload = {"timestamp": int(time.time() * 1000), "axes": mock_axes_load(int(time.time() * 1000))}
                    send_sse(self, "axes", payload)
                    time.sleep(interval_ms / 1000.0)
            except (BrokenPipeError, ConnectionResetError):
                return
            except Exception:
                return

        if path == "/api/settings":
            return json_response(self, 200, load_settings())

        json_response(self, 404, {"error": "Not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/shutdown":
            return json_response(self, 202, {"ok": True, "message": "Shutdown scheduled (mock)"})
        if parsed.path == "/api/settings":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length) if length > 0 else b"{}"
                payload = json.loads(raw.decode("utf-8")) if raw else {}
                if not isinstance(payload, dict):
                    return json_response(self, 400, {"error": "Invalid payload"})
            except (ValueError, json.JSONDecodeError):
                return json_response(self, 400, {"error": "Invalid payload"})

            updated = {}
            if "graphWindowSec" in payload:
                try:
                    value = int(payload["graphWindowSec"])
                    updated["graphWindowSec"] = clamp(value, 10, 120)
                except (ValueError, TypeError):
                    return json_response(self, 400, {"error": "Invalid graphWindowSec"})
            if "lightBrightness" in payload:
                try:
                    value = int(payload["lightBrightness"])
                    updated["lightBrightness"] = clamp(value, 0, 100)
                except (ValueError, TypeError):
                    return json_response(self, 400, {"error": "Invalid lightBrightness"})
            if "fanSpeed" in payload:
                try:
                    value = int(payload["fanSpeed"])
                    updated["fanSpeed"] = clamp(value, 0, 100)
                except (ValueError, TypeError):
                    return json_response(self, 400, {"error": "Invalid fanSpeed"})
            if "fanAuto" in payload:
                value = payload["fanAuto"]
                if isinstance(value, bool):
                    updated["fanAuto"] = value
                elif isinstance(value, (int, float)) and value in (0, 1):
                    updated["fanAuto"] = bool(value)
                else:
                    return json_response(self, 400, {"error": "Invalid fanAuto"})
            if "spindleRuntimeSec" in payload:
                try:
                    value = int(payload["spindleRuntimeSec"])
                    if value < 0:
                        raise ValueError()
                    updated["spindleRuntimeSec"] = value
                except (ValueError, TypeError):
                    return json_response(self, 400, {"error": "Invalid spindleRuntimeSec"})

            saved = save_settings(updated)
            return json_response(self, 200, saved)
        json_response(self, 404, {"error": "Not found"})

    def log_message(self, format, *args):
        return


def main():
    server = ThreadingHTTPServer(("", PORT), Handler)
    print(f"Hardware API listening on http://localhost:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
