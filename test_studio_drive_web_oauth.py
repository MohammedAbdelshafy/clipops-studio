"""Offline regression for Google Web OAuth client on an exact localhost redirect."""
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch, Mock
import sys
import studio_drive_local as app


class WebOAuthTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.client = self.root / "oauth.json"
        self.client.write_text(json.dumps({"web": {
            "client_id":"test-public-client-id", "client_secret":"not-a-real-secret",
            "auth_uri":"https://accounts.google.com/o/oauth2/auth",
            "token_uri":"https://oauth2.googleapis.com/token",
            "redirect_uris":["http://localhost:8766/"]}}))

    def test_exact_redirect_including_slash_and_port(self):
        self.assertEqual(app.oauth_configuration(self.client), (self.client,"web","http://localhost:8766/"))
        with self.assertRaisesRegex(ValueError,"authorize exactly"):
            app.oauth_configuration(self.client, web_port=8767)
        with self.assertRaisesRegex(ValueError,"1024"):
            app.oauth_configuration(self.client, web_port=80)

    def test_wrong_client_or_malformed_json_rejected_before_authorization(self):
        self.client.write_text('{bad')
        with self.assertRaisesRegex(ValueError,"invalid"):
            app.oauth_configuration(self.client)
        self.client.write_text(json.dumps({"web": {"client_id":"abc","client_secret":"def","redirect_uris":["http://127.0.0.1:8766/"]}}))
        with self.assertRaisesRegex(ValueError,"authorize exactly"):
            app.oauth_configuration(self.client)

    def test_run_local_server_fixed_port_and_private_token_save(self):
        credentials=Mock(valid=True)
        credentials.to_json.return_value=json.dumps({"token":"test-not-real", "refresh_token":"fake"})
        flow=Mock()
        flow.run_local_server.return_value=credentials
        fake=types.ModuleType("google_auth_oauthlib.flow")
        fake.InstalledAppFlow=Mock()
        fake.InstalledAppFlow.from_client_secrets_file.return_value=flow
        pkg=types.ModuleType("google_auth_oauthlib")
        pkg.flow=fake
        with patch.dict(sys.modules, {"google_auth_oauthlib":pkg,"google_auth_oauthlib.flow":fake}):
            app.connect(self.root / "private",self.client)
        kw=flow.run_local_server.call_args.kwargs
        self.assertEqual(kw["host"],"localhost")
        self.assertEqual(kw["port"],8766)
        self.assertEqual(kw["access_type"],"offline")
        self.assertEqual(kw["prompt"],"consent")
        args=fake.InstalledAppFlow.from_client_secrets_file.call_args
        self.assertTrue(args.kwargs["autogenerate_code_verifier"])
        self.assertEqual(args.kwargs["scopes"],[app.DRIVE_SCOPE])
        self.assertTrue((self.root / "private" / app.TOKEN_FILE).exists())

    def test_desktop_config_still_supported(self):
        self.client.write_text(json.dumps({"installed": {"client_id":"desktop-id","client_secret":"desktop-test"}}))
        self.assertEqual(app.oauth_configuration(self.client), (self.client,"installed",None))

if __name__ == "__main__": unittest.main()
