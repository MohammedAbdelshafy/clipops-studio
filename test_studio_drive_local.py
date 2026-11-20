"""No-network contract tests for the interactive Drive Desktop OAuth pilot."""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

import studio_drive_local as app
from clipops_compat import is_private_path


class LocalAuthTests(unittest.TestCase):
    def test_save_token_0600_and_no_browser_or_google_calls(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            app.save_token(root, {"token":"sensitive-only-on-disk", "refresh_token":"not-for-logs"})
            saved=root / app.TOKEN_FILE
            self.assertTrue(is_private_path(saved), "OAuth token must be private to the OS account")
            self.assertEqual(json.loads(saved.read_text())["token"], "sensitive-only-on-disk")
            app.save_token(root, {"token":"renewed"})
            self.assertEqual(json.loads(saved.read_text())["token"], "renewed")
            self.assertEqual(len(list(root.glob(".google-auth-*"))), 0)

    def test_rejects_missing_token_and_symlink(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            with self.assertRaises(ValueError):
                app.save_token(root, {"refresh_token":"missing access"})
            target=root / "other.json"
            target.write_text("data")
            try:
                (root / app.TOKEN_FILE).symlink_to(target)
            except OSError as exc:
                self.skipTest(f"symlinks unavailable in this environment: {exc.__class__.__name__}")
            with self.assertRaisesRegex(ValueError,"symbolic"):
                app.save_token(root, {"token":"abc"})
            self.assertEqual(target.read_text(),"data")


class DrivePilotTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.link="https://drive.google.com/drive/folders/abcdefghijklmnopq"
        self.fid="abcdefghijklmnopq23456"
        self.upload_id="f"*32
        self.movie={"id":self.fid,"name":"sample.mp4","mime_type":"video/mp4"}
        self.transcript=self.root / "transcript.json"
        self.transcript.write_text('{"segments":[{"start":0,"end":1,"text":"Hello"}]}')
        self.bridge=Mock()
        self.bridge.preview.return_value=[self.movie]
        self.bridge.start.return_value={"upload_id":self.upload_id}
        self.bridge.copy_pass.return_value={"upload_id":self.upload_id,"total_bytes":8,"received_bytes":8}
        self.store=Mock()
        self.store.inspect.return_value={"metadata": {"filename":"sample.mp4", "name":"sample", "render_count":0,"transcript":[],"style":"podcast","platform":"shorts"}}
        def finish(jobid, root, handler):
            stage=root / ".uploads" / jobid
            stage.mkdir(parents=True,exist_ok=True)
            media=stage / "sample.mp4"
            media.write_bytes(b"private")
            handler(media,stage,self.store.inspect.return_value["metadata"])
            return jobid,0
        self.store.finish.side_effect=finish
        self.pilot=types.ModuleType("pilot")
        self.pilot.create_project=Mock(return_value=self.upload_id)
        self.pilot.save_json=lambda path, data: path.write_text(json.dumps(data))
        self.pilot.process_project=Mock()

    def test_denied_rights_no_google_download(self):
        with self.assertRaisesRegex(ValueError, "permission"):
            app.import_source(self.bridge,self.store,self.root,folder_url=self.link,file_id=self.fid,
                              transcript=self.transcript,rights=False,write=lambda _:None)
        self.bridge.preview.assert_not_called()
        self.store.finish.assert_not_called()

    def test_selected_file_requires_transcript_or_local_model(self):
        with self.assertRaisesRegex(ValueError,"transcript or --model"):
            app.import_source(self.bridge,self.store,self.root,folder_url=self.link,file_id=self.fid,
                              rights=True,write=lambda _:None)
        self.bridge.start.assert_not_called()

    def test_full_local_checkpoint_import_never_dispatches_without_process_flag(self):
        output=[]
        with patch.dict(sys.modules,{"pilot":self.pilot}):
            job=app.import_source(self.bridge,self.store,self.root,folder_url=self.link,file_id=self.fid,
                                  transcript=self.transcript,rights=True,write=output.append)
        self.assertEqual(job,self.upload_id)
        self.bridge.start.assert_called_once()
        self.bridge.verify_complete.assert_called_once_with(self.upload_id)
        kwargs=self.pilot.create_project.call_args.kwargs
        self.assertEqual(kwargs["job_id"],self.upload_id)
        self.assertTrue(kwargs["rights"])
        self.assertTrue(kwargs["staged_upload"])
        self.assertEqual(kwargs["render_count"],0)
        self.assertTrue(kwargs["transcript"].exists())
        self.pilot.process_project.assert_not_called()
        self.assertTrue(any(self.upload_id in m for m in output))

    def test_resume_uses_original_checkpoint_and_never_reselects(self):
        with patch.dict(sys.modules,{"pilot":self.pilot}):
            job=app.import_source(self.bridge,self.store,self.root,upload_id=self.upload_id,write=lambda _:None)
        self.assertEqual(job,self.upload_id)
        self.bridge.start.assert_not_called()
        self.bridge.preview.assert_not_called()
        self.bridge.copy_pass.assert_called_once_with(self.upload_id,max_chunks=4)

if __name__=="__main__": unittest.main()
