"""Cloud Shell host, cookie, and CSRF regression tests."""
from http.client import HTTPConnection
from http.cookies import SimpleCookie
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock
from studio import DeskServer
from studio_preview import cloud_shell_origin


class PreviewTests(unittest.TestCase):
    def test_only_cloudshell_domain_and_valid_port(self):
        host = 'cs-1234-default.cs-us-east1-vpcf.cloudshell.dev'
        self.assertEqual(cloud_shell_origin(8080, host), 'https://8080-' + host)
        for bad in ('', 'evil.example.com', 'cloudshell.dev',
                    'a.cloudshell.dev.evil.com', 'good.cloudshell.dev:8080',
                    'a..cloudshell.dev', 'a.cloudshell.dev\nHost:evil.com'):
            with self.subTest(host=bad), self.assertRaises(ValueError):
                cloud_shell_origin(8080, bad)
        for port in (80, 0, 65536, True):
            with self.subTest(port=port), self.assertRaises(ValueError):
                cloud_shell_origin(port, 'a.cloudshell.dev')

    def test_cloud_proxy_host_cookie_and_csrf_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine = Mock()
            project_id = 'b' * 32
            engine.get_project.return_value = {'id': project_id, 'name': 'Demo',
                'source': {'duration': 15}, 'segments': [], 'candidates': []}
            with DeskServer(0, root, engine, cloud_shell=True,
                            web_host='cs-123-default.cs-us-east1-vpcf.cloudshell.dev') as server:
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    origin = server.preview_origin
                    host = origin.removeprefix('https://')

                    def request(method, path, body=None, **headers):
                        conn = HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                        try:
                            conn.request(method, path, body=body, headers=headers)
                            response = conn.getresponse()
                            return response.status, dict(response.getheaders()), response.read()
                        finally:
                            conn.close()

                    status, headers, _ = request('GET', '/', Host=host)
                    self.assertEqual(status, 200)
                    self.assertIn('Secure', headers['Set-Cookie'])
                    self.assertIn('SameSite=Strict', headers['Set-Cookie'])
                    cookies = SimpleCookie(headers['Set-Cookie'])
                    cookie_value = '; '.join(f'{k}={v.value}' for k, v in cookies.items())
                    status, _, body = request('GET', '/api/session', Host=host, Cookie=cookie_value)
                    self.assertEqual(status, 200)
                    csrf = json.loads(body)['csrf']
                    auth = {'Host': host, 'Cookie': cookie_value,
                            'Content-Type': 'application/json', 'X-ClipOps-CSRF': csrf}
                    path = f'/api/projects/{project_id}/edit'
                    bad_edit = b'{"model_path":"injected"}'
                    self.assertEqual(request('POST', path, bad_edit, Origin=origin, **auth)[0], 400)
                    self.assertEqual(request('POST', path, bad_edit,
                        Origin='https://evil.example.com', **auth)[0], 403)
                    self.assertEqual(request('POST', path, bad_edit, Origin=origin,
                        **{**auth, 'Host': 'evil.example.com'})[0], 403)
                    self.assertEqual(request('POST', path, bad_edit, Origin=origin,
                        **{**auth, 'X-ClipOps-CSRF':'wrong'})[0], 403)
                    # Google proxies may replace Host with the local destination.
                    local = {'Host': f'localhost:{server.server_port}', 'Cookie': cookie_value,
                             'X-ClipOps-CSRF': csrf, 'Content-Type':'application/json'}
                    self.assertEqual(request('POST', path, bad_edit, Origin=origin, **local)[0], 400)
                    engine.edit_project.assert_not_called()
                finally:
                    server.shutdown()


if __name__ == '__main__':
    unittest.main()
