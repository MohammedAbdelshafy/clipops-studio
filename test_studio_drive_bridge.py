"""Offline contract tests for StudioDriveBridge without a real Drive connection."""
from __future__ import annotations

from base64 import b64encode
from hashlib import md5, sha256
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from studio_drive_bridge import StudioDriveBridge
from studio_drive_reader import DriveImportError, DriveImportCancelled
from test_studio_drive_reader import FakeDrive, LINK, FILE


class FakeStudioStore:
    def __init__(self, root: Path, capacity=20*1024**3, chunk=8):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.capacity, self.chunk = capacity, chunk
        self.jobs = {}
    def path(self, uid):
        return self.root / uid
    def begin(self, uid, size, meta):
        self.path(uid).mkdir()
        (self.path(uid) / meta['filename']).write_bytes(b'')
        state = {'size': size, 'offset': 0, 'metadata': meta}
        self.jobs[uid] = state
        return state
    def inspect(self, uid):
        return self.jobs[uid]
    def append(self, uid, offset, size, digest, stream):
        state=self.jobs[uid]
        body=stream.read()
        assert offset == state['offset'] and len(body)==size and sha256(body).digest()==digest
        with (self.path(uid) / state['metadata']['filename']).open('ab') as fp:
            fp.write(body)
        state['offset'] += size
        return state


class BridgeTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store=FakeStudioStore(Path(tmp.name))
        self.reader=FakeDrive()
        self.bridge=StudioDriveBridge(self.store,self.reader,max_chunk=5)
        self.spec={'filename':'episode.mp4','transcript':[], 'render_count':0, 'name':'Episode'}

    def test_preview_does_not_expose_resource_keys(self):
        items=self.bridge.preview(LINK)
        self.assertEqual(items[0]['name'],'episode.mp4')
        self.assertNotIn('resource_key',items[0])

    def test_start_requires_rights_and_validated_filename(self):
        with self.assertRaises(DriveImportError):
            self.bridge.start(LINK,FILE,self.spec,rights_confirmed=False)
        with self.assertRaises(DriveImportError):
            self.bridge.start(LINK,FILE,{**self.spec,'filename':'wrong.mp4'},rights_confirmed=True)
        self.assertFalse(self.store.jobs)
        result=self.bridge.start(LINK,FILE,self.spec,rights_confirmed=True)
        self.assertEqual(result['received_bytes'],0)

    def test_interrupted_copy_resumes_existing_studio_offset(self):
        job=self.bridge.start(LINK,FILE,self.spec,rights_confirmed=True)
        uid=job['upload_id']
        first=self.bridge.copy_pass(uid,max_chunks=1)
        self.assertEqual(first['received_bytes'],5)
        self.assertGreater(first['total_bytes'],first['received_bytes'])
        second=self.bridge.copy_pass(uid,max_chunks=6)
        self.assertEqual(second['received_bytes'],second['total_bytes'])
        self.bridge.verify_complete(uid)
        self.assertEqual((self.store.path(uid)/self.spec['filename']).read_bytes(),self.reader.media)

    def test_revoked_access_and_source_drift_fail_closed(self):
        uid=self.bridge.start(LINK,FILE,self.spec,rights_confirmed=True)['upload_id']
        self.reader.version='v99'
        with self.assertRaises(DriveImportError):
            self.bridge.copy_pass(uid)
        self.assertEqual(self.store.inspect(uid)['offset'],0)

    def test_cancel_before_download_writes_no_bytes(self):
        uid=self.bridge.start(LINK,FILE,self.spec,rights_confirmed=True)['upload_id']
        with self.assertRaises(DriveImportCancelled):
            self.bridge.copy_pass(uid,continue_allowed=lambda:False)
        self.assertEqual(self.store.inspect(uid)['offset'],0)

    def test_no_auto_finalize_or_publish(self):
        uid=self.bridge.start(LINK,FILE,self.spec,rights_confirmed=True)['upload_id']
        self.bridge.copy_pass(uid,max_chunks=10)
        self.assertFalse(self.store.inspect(uid).get('done'))

if __name__=='__main__': unittest.main()
