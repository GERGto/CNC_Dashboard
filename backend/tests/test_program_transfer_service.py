import io
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cnc_backend.program_transfer_service import ProgramTransferService, ProgramValidationError


def make_config(root, **overrides):
    values = {
        "programs_directory": os.path.join(root, "programs"),
        "programs_state_path": os.path.join(root, "programs-state.json"),
        "programs_share_name": "cnc-programs",
        "program_upload_max_bytes": 1024 * 1024,
        "program_scan_interval_sec": 0.01,
        "program_settle_seconds": 0.0,
        "controller_smb_enabled": False,
        "controller_smb_host": "",
        "controller_smb_share": "",
        "controller_smb_username": "",
        "controller_smb_password": "",
        "controller_smb_domain": "",
        "controller_smb_remote_directory": "",
        "controller_smb_protocol": "",
        "controller_smb_timeout_sec": 3.0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class ProgramTransferServiceTests(unittest.TestCase):
    def test_controller_status_reports_live_smb_connection(self):
        with tempfile.TemporaryDirectory() as root:
            service = ProgramTransferService(
                make_config(
                    root,
                    controller_smb_enabled=True,
                    controller_smb_host="192.168.2.5",
                    controller_smb_share="cncdisk",
                )
            )
            connection = Mock()
            with patch(
                "cnc_backend.program_transfer_service.socket.create_connection",
                return_value=connection,
            ) as create_connection:
                status = service.get_controller_status()

            self.assertTrue(status["connected"])
            self.assertEqual(status["connectionState"], "connected")
            create_connection.assert_called_once_with(("192.168.2.5", 445), timeout=0.25)
            connection.close.assert_called_once_with()

    def test_controller_status_reports_unreachable_smb_connection(self):
        with tempfile.TemporaryDirectory() as root:
            service = ProgramTransferService(
                make_config(
                    root,
                    controller_smb_enabled=True,
                    controller_smb_host="192.168.2.5",
                    controller_smb_share="cncdisk",
                )
            )
            with patch(
                "cnc_backend.program_transfer_service.socket.create_connection",
                side_effect=OSError("offline"),
            ) as create_connection:
                status = service.get_controller_status()

            self.assertFalse(status["connected"])
            self.assertEqual(status["connectionState"], "disconnected")
            self.assertIn("offline", status["connectionIssue"])
            self.assertEqual(create_connection.call_count, 2)

    def test_upload_is_persistent_sanitized_and_waits_for_controller(self):
        with tempfile.TemporaryDirectory() as root:
            service = ProgramTransferService(make_config(root))
            service.ensure_storage()

            payload = service.store_upload("Frästeil 01.NC", io.BytesIO(b"G0 X0\n"), 6)
            with patch(
                "cnc_backend.program_transfer_service.socket.create_connection",
                side_effect=OSError("offline"),
            ):
                snapshot = service.get_snapshot()

            self.assertEqual(payload["name"], "Frasteil_01.nc")
            self.assertEqual(snapshot["programs"][0]["transferState"], "waitingForController")
            self.assertTrue(os.path.isfile(os.path.join(root, "programs", "Frasteil_01.nc")))

    def test_rejects_unsupported_file_types(self):
        with tempfile.TemporaryDirectory() as root:
            service = ProgramTransferService(make_config(root))
            service.ensure_storage()

            with self.assertRaises(ProgramValidationError):
                service.store_upload("malware.exe", io.BytesIO(b"x"), 1)

    def test_discovers_programs_copied_directly_into_samba_directory(self):
        with tempfile.TemporaryDirectory() as root:
            service = ProgramTransferService(make_config(root))
            service.ensure_storage()
            direct_path = os.path.join(root, "programs", "extern.gcode")
            with open(direct_path, "wb") as handle:
                handle.write(b"G90\n")

            snapshot = service.get_snapshot()

            self.assertEqual(snapshot["programs"][0]["name"], "extern.gcode")
            self.assertEqual(snapshot["programs"][0]["transferState"], "waitingForController")

    def test_configured_worker_uses_smbclient_without_password_argument(self):
        with tempfile.TemporaryDirectory() as root:
            calls = []

            def resolve(name):
                return "/usr/bin/smbclient" if name == "smbclient" else ""

            def run(command, **kwargs):
                calls.append((command, kwargs))
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            config = make_config(
                root,
                controller_smb_enabled=True,
                controller_smb_host="192.168.2.5",
                controller_smb_share="cncdisk",
                controller_smb_username="",
                controller_smb_password="top-secret",
                controller_smb_protocol="NT1",
            )
            service = ProgramTransferService(config, run, resolve)
            service.ensure_storage()
            service.store_upload("job.nc", io.BytesIO(b"M30\n"), 4)

            service._scan_and_transfer_once()
            snapshot = service.get_snapshot()

            self.assertEqual(snapshot["programs"][0]["transferState"], "transferred")
            self.assertGreaterEqual(len(calls), 3)
            self.assertFalse(any("top-secret" in part for command, _kwargs in calls for part in command))
            self.assertTrue(all(kwargs.get("env", {}).get("PASSWD") == "top-secret" for _command, kwargs in calls))
            self.assertTrue(all("--option=client min protocol=NT1" in command for command, _kwargs in calls))
            self.assertTrue(all("NT1" in command for command, _kwargs in calls))


if __name__ == "__main__":
    unittest.main()
