import json
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

from cnc_backend.request_handler import create_request_handler


class FakeApp:
    def __init__(self):
        self.requested_enabled = None

    @staticmethod
    def get_tailscale_status():
        return {
            "installed": True,
            "connected": False,
            "backendState": "Stopped",
            "needsLogin": False,
            "operationInProgress": False,
        }

    def request_tailscale_enabled(self, enabled):
        self.requested_enabled = enabled
        return True, "scheduled", {
            **self.get_tailscale_status(),
            "operationInProgress": True,
            "requestedEnabled": enabled,
        }


class TailscaleRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = FakeApp()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), create_request_handler(self.app))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_status_and_enable_routes(self):
        with urllib.request.urlopen(f"{self.base_url}/api/tailscale/status", timeout=2) as response:
            status_payload = json.load(response)
        self.assertEqual(status_payload["backendState"], "Stopped")

        request = urllib.request.Request(
            f"{self.base_url}/api/tailscale/enable",
            data=b"{}",
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            enable_payload = json.load(response)
            self.assertEqual(response.status, 202)

        self.assertTrue(enable_payload["ok"])
        self.assertTrue(enable_payload["status"]["requestedEnabled"])
        self.assertTrue(self.app.requested_enabled)


if __name__ == "__main__":
    unittest.main()
