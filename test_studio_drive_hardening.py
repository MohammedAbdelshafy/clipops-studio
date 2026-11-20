"""Additional negative tests for the opt-in local Drive pilot; never contacts Google."""
from pathlib import Path
import json
import tempfile
import types
import sys
import unittest
from unittest.mock import Mock, patch

from studio_drive_reader import _video_from_metadata, DriveImportError
import studio_drive_local as app


class DrivePilotHardeningTests(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.root = Path(work.name)

    def test_refuse_symlinked_private_root(self):
        real = self.root / "safe"
        real.mkdir()
        link = self.root / "linked"
        try:
            link.symlink_to(real, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks unavailable on this host")
        with self.assertRaisesRegex(ValueError, "symbolic"):
            app.secure_root(link)

    def test_reject_names_that_studio_import_metadata_rejects(self):
        base = {"id":"abcdefghijk1234567890","mimeType":"video/quicktime",
                "size":"123","version":"7","capabilities":{"canDownload":True}}
        for name in ["\nstream.mov", "stream\r.mov", "z"*181+".mov", "video\t.mov"]:
            with self.subTest(name=repr(name)), self.assertRaisesRegex(DriveImportError, "filename"):
                _video_from_metadata({**base, "name":name})
        self.assertEqual(_video_from_metadata({**base,"name":"فيديو-2026.MOV"}).name, "فيديو-2026.MOV")

    def test_cloud_shell_loopback_oauth_fails_before_opening_browser(self):
        config = self.root / "oauth.json"
        config.write_text(json.dumps({"web": {"client_id": "test-id",
            "client_secret": "fake", "redirect_uris": ["http://localhost:8766/"]}}))
        with patch.dict('os.environ', {"WEB_HOST":"test.cloudshell.dev"}):
            with self.assertRaisesRegex(RuntimeError, "Cloud Shell"):
                app.connect(self.root / "private", config, open_browser=False)

    def test_opt_out_of_auto_browser_for_wsl_sessions(self):
        creds = Mock(valid=True)
        creds.to_json.return_value=json.dumps({"token":"fake-only-for-test", "refresh_token":"fake"})
        flow = Mock()
        flow.run_local_server.return_value = creds
        authflow = types.ModuleType('google_auth_oauthlib.flow')
        authflow.InstalledAppFlow = Mock()
        authflow.InstalledAppFlow.from_client_secrets_file.return_value=flow
        authpkg = types.ModuleType('google_auth_oauthlib')
        authpkg.flow=authflow
        config=self.root / 'oauth.json'
        config.write_text(json.dumps({"web":{"client_id":"test-id","client_secret":"fake",
                           "redirect_uris":["http://localhost:8766/"]}}))
        with patch.dict(sys.modules, {'google_auth_oauthlib':authpkg,'google_auth_oauthlib.flow':authflow}):
            app.connect(self.root/'private', config, open_browser=False)
        self.assertFalse(flow.run_local_server.call_args.kwargs['open_browser'])


if __name__ == '__main__': unittest.main()
