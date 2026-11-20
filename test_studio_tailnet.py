"""Tailscale Serve owner-authentication and HTTPS origin regressions."""
from http.client import HTTPConnection
from http.cookies import SimpleCookie
from pathlib import Path
from unittest.mock import Mock
import json
import tempfile
import threading
import unittest

from studio import DeskServer
from studio_preview import tailnet_login, tailnet_origin


class TailnetTests(unittest.TestCase):
    def test_strict_host_validation(self):
        self.assertEqual(tailnet_origin('laptop.example-tailnet.ts.net'),
                         'https://laptop.example-tailnet.ts.net')
        for value in ('', 'laptop.ts.net', 'https://laptop.example.ts.net',
                      'laptop.example.ts.net.evil.org', 'laptop.example.ts.net:443',
                      'laptop.example.ts.net/path', 'a..ts.net',
                      'a.b.c.ts.net', 'laptop.bad host.ts.net',
                      'laptop.example.ts.net\\nInjected:1'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                tailnet_origin(value)
        self.assertEqual(tailnet_login('Owner@Example.COM'), 'owner@example.com')
        for value in ('', 'unknown', 'bad@@example.com', 'a b@example.com',
                      'name@example.com\\nEvil:1', 'héllo@example.com'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                tailnet_login(value)

    def test_all_requests_require_real_owner_and_csrf(self):
        host, owner = 'laptop.example-tailnet.ts.net', 'owner@example.com'
        with tempfile.TemporaryDirectory() as tmp:
            engine = Mock()
            project = 'a' * 32
            engine.get_project.return_value = {
                'id': project, 'source': {'duration': 10}, 'segments': [], 'candidates': []}
            with DeskServer(0, Path(tmp), engine, tailnet_host=host, tailnet_user=owner) as server:
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                def request(method, path, body=None, **headers):
                    conn = HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                    try:
                        conn.request(method, path, body=body, headers=headers)
                        response = conn.getresponse()
                        return response.status, dict(response.getheaders()), response.read()
                    finally:
                        conn.close()
                try:
                    self.assertEqual(request('GET','/',Host=host)[0],403)
                    self.assertEqual(request('GET','/',Host=host,
                        **{'Tailscale-User-Login':'visitor@example.com'})[0],403)
                    code, headers, _ = request('GET','/',Host=host,
                        **{'Tailscale-User-Login':owner})
                    self.assertEqual(code,200)
                    self.assertIn('Secure',headers['Set-Cookie'])
                    self.assertIn('SameSite=Strict',headers['Set-Cookie'])
                    cookie = SimpleCookie(headers['Set-Cookie'])
                    token = '; '.join(f'{k}={v.value}' for k,v in cookie.items())
                    auth = {'Host':host, 'Cookie':token,'Tailscale-User-Login':owner}
                    code, _, reply = request('GET','/api/session',**auth)
                    self.assertEqual(code,200)
                    csrf=json.loads(reply)['csrf']
                    write={**auth,'Content-Type':'application/json','X-ClipOps-CSRF':csrf}
                    route=f'/api/projects/{project}/edit'
                    body=b'{"model_path":"bogus"}'
                    self.assertEqual(request('POST',route,body,Origin=f'https://{host}',**write)[0],400)
                    self.assertEqual(request('POST',route,body,Origin='https://evil.org',**write)[0],403)
                    self.assertEqual(request('POST',route,body,Origin=f'https://{host}',
                        **{**write,'Tailscale-User-Login':'other@example.com'})[0],403)
                    self.assertEqual(request('POST',route,body,Origin=f'https://{host}',
                        **{**write,'X-ClipOps-CSRF':'invalid'})[0],403)
                    engine.edit_project.assert_not_called()
                finally:
                    server.shutdown()

    def test_no_ambiguous_proxy_modes(self):
        with tempfile.TemporaryDirectory() as tmp:
            for extras in (
                {'tailnet_host':'a.b.ts.net'},
                {'tailnet_user':'owner@example.com'},
                {'cloud_shell':True,'tailnet_host':'a.b.ts.net',
                 'tailnet_user':'owner@example.com'}):
                with self.subTest(extras=extras), self.assertRaises(ValueError):
                    DeskServer(0,Path(tmp),Mock(),**extras)


if __name__ == '__main__':
    unittest.main()
