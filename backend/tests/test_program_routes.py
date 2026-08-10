import json
import os
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

from cnc_backend.program_transfer_service import ProgramTransferService
from cnc_backend.request_handler import create_request_handler
from test_program_transfer_service import make_config


class ProgramApp:
    def __init__(self, service):
        self.service = service

    def get_programs(self):
        return self.service.get_snapshot()

    def upload_program(self, name, source, content_length):
        return self.service.store_upload(name, source, content_length)

    def get_program_download(self, name):
        return self.service.get_download(name)

    def delete_program(self, name):
        return self.service.delete_program(name)

    def request_program_transfer(self, name):
        return self.service.request_transfer(name)


class ProgramRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        service = ProgramTransferService(make_config(self.temp_dir.name))
        service.ensure_storage()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), create_request_handler(ProgramApp(service)))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp_dir.cleanup()

    def test_upload_list_download_and_delete(self):
        upload = urllib.request.Request(
            f"{self.base_url}/api/programs/upload?name=test.nc",
            data=b"G1 X10\n",
            headers={"Content-Type": "application/octet-stream"},
            method="POST",
        )
        with urllib.request.urlopen(upload, timeout=2) as response:
            self.assertEqual(response.status, 201)
            uploaded = json.load(response)
        self.assertEqual(uploaded["program"]["name"], "test.nc")

        with urllib.request.urlopen(f"{self.base_url}/api/programs", timeout=2) as response:
            listing = json.load(response)
        self.assertEqual(len(listing["programs"]), 1)

        with urllib.request.urlopen(f"{self.base_url}/api/programs/test.nc/download", timeout=2) as response:
            self.assertEqual(response.read(), b"G1 X10\n")

        delete = urllib.request.Request(f"{self.base_url}/api/programs/test.nc", method="DELETE")
        with urllib.request.urlopen(delete, timeout=2) as response:
            self.assertTrue(json.load(response)["ok"])
        self.assertFalse(os.path.exists(os.path.join(self.temp_dir.name, "programs", "test.nc")))


if __name__ == "__main__":
    unittest.main()
