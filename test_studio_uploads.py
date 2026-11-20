"""Local resumable transport and reference import regressions."""
from base64 import b64encode
from contextlib import closing
from hashlib import sha256
from http.client import HTTPConnection
from http.cookies import SimpleCookie
from io import BytesIO
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

import pilot
from studio import DeskServer
from studio_uploads import UploadError, UploadStore


class StoreTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.key = "b" * 32
        self.spec = {"filename": "sample.mp4", "render_count": 0}
        self.store = UploadStore(self.root, chunk=8)

    def test_checkpoint_survives_restart_early_end_and_bad_checksum(self):
        self.store.begin(self.key, 8, self.spec)
        self.store.append(self.key, 0, 4, sha256(b"test").digest(), BytesIO(b"test"))
        store = UploadStore(self.root, chunk=8)
        path = store.path(self.key) / "sample.mp4"
        with path.open("ab") as medium:
            medium.write(b"uncommitted")
        for attempted, status in ((b"z", 400), (b"junk", 460)):
            with self.assertRaises(UploadError) as expected:
                store.append(self.key, 4, 4, sha256(b"data").digest(), BytesIO(attempted))
            self.assertEqual(expected.exception.status, status)
            self.assertEqual(store.inspect(self.key)["offset"], 4)
            self.assertEqual(path.read_bytes(), b"test")
        with self.assertRaises(UploadError) as expected:
            store.append(self.key, 0, 4, sha256(b"blah").digest(), BytesIO(b"blah"))
        self.assertEqual(expected.exception.status, 409)
        store.append(self.key, 4, 4, sha256(b"data").digest(), BytesIO(b"data"))
        self.assertEqual(path.read_bytes(), b"testdata")

    def test_cancel_expires_and_disk_reservation(self):
        self.store.begin(self.key, 8, self.spec)
        self.store.cancel(self.key)
        with self.assertRaises(UploadError):
            self.store.inspect(self.key)
        expiring = UploadStore(self.root, ttl=-1)
        expiring.begin(self.key, 8, self.spec)
        with self.assertRaises(UploadError) as expected:
            expiring.inspect(self.key)
        self.assertEqual(expected.exception.status, 410)
        expiring.begin("c"*32, 8, self.spec)
        self.assertFalse((expiring.location / self.key).exists())
        with patch("studio_uploads.shutil.disk_usage", return_value=Mock(free=100)):
            with self.assertRaises(UploadError) as expected:
                self.store.begin("d"*32, 8, self.spec)
            self.assertEqual(expected.exception.status, 507)

    def test_idempotent_import_after_lost_response(self):
        self.store.begin(self.key, 4, self.spec)
        self.store.append(self.key, 0, 4, sha256(b"data").digest(), BytesIO(b"data"))
        project = self.root / self.key
        project.mkdir()
        (project / "project.json").write_text("{}")
        create = Mock()
        self.assertEqual(self.store.finish(self.key, self.root, create), (self.key, 0))
        self.assertEqual(self.store.finish(self.key, self.root, create), (self.key, 0))
        create.assert_not_called()

    def test_source_reference_is_private_and_detects_changes(self):
        source = self.root / "sample.mp4"
        source.write_bytes(b"normal video input")
        transcript = self.root / "cue.json"
        transcript.write_text('{"segments":[{"start":0,"end":1,"text":"Source"}]}')
        projects = self.root / "projects"
        with patch("pilot.pilot_qc.validate_source", return_value={"duration": 1.1, "has_audio": True}):
            job = pilot.create_project(source, projects, rights=True, reference=True, transcript=transcript)
        self.assertEqual(pilot.get_media_path(projects, job, kind="source"), source)
        self.assertNotIn("source_reference", pilot.get_project(projects, job))
        self.assertFalse((projects / job / "input.mp4").exists())
        source.write_bytes(b"a replaced original")
        with self.assertRaisesRegex(ValueError, "changed or moved"):
            pilot.get_media_path(projects, job, kind="source")


class UploadHTTPTests(unittest.TestCase):
    def test_authenticated_tus_offsets_and_termination(self):
        with tempfile.TemporaryDirectory() as folder, DeskServer(0, Path(folder), Mock()) as server:
            threading.Thread(target=server.serve_forever, daemon=True).start()
            def request(method, path, body=None, **headers):
                with closing(HTTPConnection("127.0.0.1", server.server_port, timeout=4)) as connection:
                    connection.request(method, path, body, headers)
                    response = connection.getresponse()
                    return response.status, dict(response.getheaders()), response.read()
            try:
                _, headers, _ = request("GET", "/")
                cookies = SimpleCookie(headers["Set-Cookie"])
                auth = {"Cookie": "; ".join(f"{k}={v.value}" for k,v in cookies.items()),
                        "Origin": f"http://127.0.0.1:{server.server_port}",
                        "X-ClipOps-CSRF": server.csrf, "Tus-Resumable": "1.0.0"}
                source = {"rights": True, "filename": "sample.mp4", "transcript": []}
                payload = json.dumps({"id": "a"*32, "size": 4, "metadata": source})
                status, headers, _ = request("POST", "/api/uploads", payload,
                                             **auth, **{"Content-Type": "application/json"})
                self.assertEqual(status, 201)
                path = headers["Location"]
                data = b"test"
                chunk = {"Content-Type":"application/offset+octet-stream", "Upload-Offset":"0",
                         "Upload-Checksum":"sha256 "+b64encode(sha256(data).digest()).decode()}
                self.assertEqual(request("PATCH", path, data, **chunk)[0], 403)
                self.assertEqual(request("PATCH", path, data, **auth, **chunk)[0], 204)
                self.assertEqual(request("HEAD", path, **auth)[1]["Upload-Offset"], "4")
                self.assertEqual(request("PATCH", path, data, **auth, **chunk)[0], 409)
                self.assertEqual(request("DELETE", path, **auth)[0], 204)
                self.assertEqual(request("HEAD", path, **auth)[0], 404)
            finally:
                server.shutdown()
