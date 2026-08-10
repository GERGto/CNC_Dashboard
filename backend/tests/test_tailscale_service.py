import json
import unittest
from types import SimpleNamespace

from cnc_backend.tailscale_service import TailscaleService


class FakeCommands:
    def __init__(self, backend_state="Running", online=True):
        self.backend_state = backend_state
        self.online = online
        self.calls = []

    @staticmethod
    def resolve(name):
        return f"/usr/bin/{name}" if name in {"tailscale", "systemctl"} else ""

    def run(self, command, **_kwargs):
        self.calls.append(command)
        if command[1:] == ["status", "--json"]:
            payload = {
                "BackendState": self.backend_state,
                "Self": {
                    "Online": self.online,
                    "TailscaleIPs": ["100.64.1.23", "fd7a:115c:a1e0::1"],
                    "DNSName": "cnc-dashboard.example.ts.net.",
                },
            }
            return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")


class TailscaleServiceTests(unittest.TestCase):
    def test_status_exposes_connection_address_and_dns_name(self):
        commands = FakeCommands()
        service = TailscaleService(commands.run, commands.resolve)

        status = service.get_status()

        self.assertTrue(status["installed"])
        self.assertTrue(status["connected"])
        self.assertEqual(status["ipAddress"], "100.64.1.23")
        self.assertEqual(status["dnsName"], "cnc-dashboard.example.ts.net")

    def test_enable_requires_one_time_login(self):
        commands = FakeCommands(backend_state="NeedsLogin", online=False)
        service = TailscaleService(commands.run, commands.resolve)

        accepted, message, status = service.request_enabled(True)

        self.assertFalse(accepted)
        self.assertTrue(status["needsLogin"])
        self.assertIn("sudo tailscale up", message)
        self.assertFalse(any(command[1:2] == ["up"] for command in commands.calls))

    def test_background_worker_uses_down_without_forgetting_enrollment(self):
        commands = FakeCommands()
        service = TailscaleService(commands.run, commands.resolve)

        service._set_enabled_worker(False)

        self.assertIn(["/usr/bin/tailscale", "down"], commands.calls)
        self.assertFalse(any("logout" in command for command in commands.calls))


if __name__ == "__main__":
    unittest.main()
