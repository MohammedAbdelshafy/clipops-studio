"""Offline Drive-folder import tests; no real Google access, OAuth or 20GB load."""
from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from types import SimpleNamespace
from studio_drive_reader import (
    DriveFolderImporter, DriveImportError, GoogleDriveV3Reader,
    parse_drive_folder_link, parse_drive_folder_reference,
)

FOLDER = "abcdefghijklmnopqrstuvwxyzABCDEF1234"
FILE = "ZYXWVUTSRQPONMLKJIHGFEDCBA9876543210"
LINK = f"https://drive.google.com/drive/folders/{FOLDER}?usp=sharing"


class FakeDrive:
    def __init__(self, media=b"123456789ABCDE"):
        self.media = media
        self.filename = "episode.mp4"
        self.version = "7"
        self.md5 = hashlib.md5(media, usedforsecurity=False).hexdigest()
        self.interrupt = False
        self.download = True
        self.pages = 0

    def metadata(self, file_id, resource_key=None):
        if file_id == FOLDER:
            return {"id": FOLDER, "mimeType": "application/vnd.google-apps.folder", "trashed": False}
        if file_id == FILE:
            return {"id": FILE, "name": self.filename, "size": str(len(self.media)),
                    "mimeType": "video/mp4", "version": self.version, "md5Checksum": self.md5,
                    "parents": [FOLDER], "capabilities": {"canDownload": self.download}}
        raise DriveImportError("not found")

    def list_children(self, folder_id, page_token=None, folder_resource_key=None):
        self.pages += 1
        if not page_token:
            return {"files": [self.metadata(FILE),
                    {"id": "different-item-0123456", "name": "invoice.pdf", "mimeType": "application/pdf"}],
                    "nextPageToken": "second"}
        return {"files": [], "nextPageToken": None}

    def read_range(self, file_id, start, length, total, resource_key=None):
        if self.interrupt and start >= 5:
            raise DriveImportError("simulated network disconnect")
        return self.media[start:start+length]


class DriveImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ingest = SimpleNamespace(max_size=20*1024**3)
        self.drive = FakeDrive()
        self.service = DriveFolderImporter(self.ingest, self.drive)

    def test_folder_link_only_and_validate_domain(self):
        self.assertEqual(parse_drive_folder_link(LINK), FOLDER)
        self.assertEqual(parse_drive_folder_link(f"https://drive.google.com/drive/u/0/folders/{FOLDER}"), FOLDER)
        for x in [
            f"http://drive.google.com/drive/folders/{FOLDER}",
            f"https://drive.google.com.evil.test/drive/folders/{FOLDER}",
            f"https://drive.google.com/drive/folders/{FOLDER}/extra",
            f"https://drive.google.com/file/d/{FILE}/view",
            "https://drive.google.com/drive/folders/../../etc/passwd",
            "file:///home/videos", "https://evil.example/drive/folders/abcdefghijklmnop",
        ]:
            with self.subTest(link=x), self.assertRaises(DriveImportError):
                parse_drive_folder_link(x)

    def test_shared_folder_resource_key_is_parsed_and_sent_only_to_google(self):
        link = LINK + '&resourcekey=0-testResourceKey_123'
        folder = parse_drive_folder_reference(link)
        self.assertEqual(folder.folder_id, FOLDER)
        self.assertEqual(folder.resource_key, '0-testResourceKey_123')
        self.assertEqual(parse_drive_folder_link(link), FOLDER)
        with self.assertRaises(DriveImportError):
            parse_drive_folder_reference(link + '&resourcekey=another')
        with self.assertRaises(DriveImportError):
            parse_drive_folder_reference(LINK + '&resourcekey=%0Aattack')

    def test_reader_resource_key_header_is_fixed_to_google_api(self):
        from unittest.mock import Mock
        client = GoogleDriveV3Reader(lambda: 'token')
        class Response:
            status_code = 200
            headers = {}
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def json(self): return {'id': FILE}
        session = Mock()
        session.get.return_value = Response()
        client._session = session
        client.metadata(FILE, resource_key='0-key')
        args, kwargs = session.get.call_args
        self.assertEqual(args[0], f'https://www.googleapis.com/drive/v3/files/{FILE}')
        self.assertEqual(kwargs['headers']['X-Goog-Drive-Resource-Keys'], f'{FILE}/0-key')

    def test_paginated_preview_excludes_nonvideo(self):
        videos = self.service.preview(LINK)
        self.assertEqual([(v.id, v.name) for v in videos], [(FILE, "episode.mp4")])
        self.assertEqual(self.drive.pages, 2)





    def test_no_download_permission_and_size_limit(self):
        self.drive.download = False
        self.assertEqual(self.service.preview(LINK), [])
        self.drive.download = True
        smaller = DriveFolderImporter(SimpleNamespace(max_size=4), self.drive)
        self.assertEqual(smaller.preview(LINK), [])

    def test_refuse_drive_range_200_or_mismatched_content_range(self):
        client = GoogleDriveV3Reader(lambda: "token")
        class Response:
            status_code = 200
            headers = {}
            def close(self): pass
            def __enter__(self): return self
            def __exit__(self, *_): self.close()
        class FakeSession:
            trust_env = False
            def get(self, *args, **kwargs):
                return Response()
        client._session = FakeSession()
        with self.assertRaisesRegex(DriveImportError, "ignored byte range"):
            client.read_range(FILE, 0, 5, 14)

    def test_http_client_rejects_redirects(self):
        client = GoogleDriveV3Reader(lambda: "token")
        class Redirect:
            status_code = 302
            def close(self): pass
        class FakeSession:
            def get(self, *args, **kwargs):
                self.kwargs = kwargs
                return Redirect()
        client._session = FakeSession()
        with self.assertRaisesRegex(DriveImportError, "redirect"):
            client.metadata(FILE)

    def test_no_token_in_url_requested(self):
        # Auth is server-managed and HTTPS endpoints are fixed.
        self.assertRaises(DriveImportError, parse_drive_folder_link, f"https://drive.google.com@evil.com/drive/folders/{FOLDER}")


if __name__ == '__main__':
    unittest.main()
