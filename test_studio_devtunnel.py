"""Private Microsoft Dev Tunnels origin, one-use pairing and CSRF tests."""
from http.client import HTTPConnection
from http.cookies import SimpleCookie
from pathlib import Path
from unittest.mock import Mock
import json
import tempfile
import threading
import time
import unittest
from urllib.parse import urlencode
from studio import DeskServer
from studio_preview import devtunnel_origin


class DevTunnelTests(unittest.TestCase):
    HOST = 'cl7opsa-8765.usw2.devtunnels.ms'
    ORIGIN = 'https://' + HOST

    def test_only_valid_private_port_forward_host(self):
        self.assertEqual(devtunnel_origin(self.ORIGIN + '/'), self.ORIGIN)
        for value in (
                '', 'http://' + self.HOST, 'https://' + self.HOST + ':8765',
                self.ORIGIN + '/api/projects', self.ORIGIN + '?code=secret',
                'https://username:password@' + self.HOST,
                'https://' + self.HOST + '.evil.net',
                'https://cl7opsa-8765-inspect.usw2.devtunnels.ms',
                'https://cl7opsa-99.usw2.devtunnels.ms',
                'https://cl7opsa-8765.usw2.devtunnels.ms\\nHost:evil.net',
                'https://cl7opsa-8765.usw2.devtunnels.ms#fragment',
                'https://laptop.example-tailnet.ts.net',
                'https://cl7opsa-8765..devtunnels.ms'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                devtunnel_origin(value)

    def test_one_time_pair_protects_static_and_api(self):
        engine = Mock()
        project = 'b' * 32
        engine.get_project.return_value = {
            'id': project, 'source': {'duration': 10}, 'segments': [], 'candidates': []}
        with tempfile.TemporaryDirectory() as tmp:
            with DeskServer(0, Path(tmp), engine, devtunnel_url=self.ORIGIN) as srv:
                thread = threading.Thread(target=srv.serve_forever, daemon=True)
                thread.start()

                def request(method, path, body=None, **headers):
                    conn = HTTPConnection('127.0.0.1', srv.server_port, timeout=5)
                    try:
                        conn.request(method, path, body=body, headers=headers)
                        reply = conn.getresponse()
                        return reply.status, dict(reply.getheaders()), reply.read()
                    finally:
                        conn.close()

                def pair(code, **headers):
                    encoded = urlencode({'code': code})
                    return request('POST', '/api/devtunnel/pair', encoded,
                                   Host=self.HOST,
                                   **{'Content-Type': 'application/x-www-form-urlencoded',
                                      **headers})

                try:
                    status, heads, data = request('GET', '/', Host=self.HOST)
                    self.assertEqual(status, 200)
                    self.assertNotIn('Set-Cookie', heads)
                    self.assertIn(b'Pair ClipOps Studio', data)
                    self.assertEqual(request('GET', '/app.js', Host=self.HOST)[0], 403)
                    self.assertEqual(request('GET', '/api/session', Host=self.HOST)[0], 403)
                    self.assertEqual(pair(srv.dev_pair_code)[0], 403)
                    self.assertEqual(pair(srv.dev_pair_code,
                                          Origin='https://evil.net')[0], 403)
                    self.assertEqual(pair('0' * 32, Origin=self.ORIGIN)[0], 403)
                    self.assertEqual(srv.dev_pair_attempts, 1)
                    status, heads, _ = pair(srv.dev_pair_code, Origin=self.ORIGIN)
                    self.assertEqual(status, 303)
                    self.assertEqual(heads.get('Location'), '/')
                    self.assertIn('Secure', heads['Set-Cookie'])
                    self.assertIn('HttpOnly', heads['Set-Cookie'])
                    self.assertIn('SameSite=Strict', heads['Set-Cookie'])
                    cookies = SimpleCookie(heads['Set-Cookie'])
                    cookie = '; '.join(f'{k}={v.value}' for k, v in cookies.items())
                    self.assertEqual(pair('1' * 32, Origin=self.ORIGIN)[0], 429)
                    auth = {'Host': self.HOST, 'Cookie': cookie}
                    self.assertEqual(request('GET', '/', **auth)[0], 200)
                    self.assertEqual(request('GET', '/app.js', **auth)[0], 200)
                    status, _, data = request('GET', '/api/session', **auth)
                    self.assertEqual(status, 200)
                    csrf = json.loads(data)['csrf']
                    route = f'/api/projects/{project}/edit'
                    invalid = b'{"model_path":"injected"}'
                    write = {**auth, 'Content-Type': 'application/json', 'X-ClipOps-CSRF': csrf}
                    self.assertEqual(request('POST', route, invalid, Origin=self.ORIGIN, **write)[0], 400)
                    self.assertEqual(request('POST', route, invalid,
                                    Origin='https://evil.net', **write)[0], 403)
                    self.assertEqual(request('POST', route, invalid,
                                    Origin=self.ORIGIN,
                                    **{**write, 'X-ClipOps-CSRF': 'invalid'})[0], 403)
                    engine.edit_project.assert_not_called()
                finally:
                    srv.shutdown()

    def test_expired_pair_and_exclusive_modes(self):
        with tempfile.TemporaryDirectory() as tmp:
            for combo in (
                    {'devtunnel_url': self.ORIGIN, 'tailnet_host': 'laptop.x.ts.net',
                     'tailnet_user': 'owner@example.com'},
                    {'devtunnel_url': self.ORIGIN, 'cloud_shell': True}):
                with self.subTest(mode=combo), self.assertRaises(ValueError):
                    DeskServer(0, Path(tmp), Mock(), **combo)

            with DeskServer(0, Path(tmp), Mock(), devtunnel_url=self.ORIGIN) as srv:
                srv.dev_pair_deadline = time.monotonic() - 1
                thread = threading.Thread(target=srv.serve_forever, daemon=True)
                thread.start()
                try:
                    conn = HTTPConnection('127.0.0.1', srv.server_port, timeout=5)
                    body = urlencode({'code': srv.dev_pair_code})
                    conn.request('POST', '/api/devtunnel/pair', body,
                                 headers={'Host': self.HOST, 'Origin': self.ORIGIN,
                                          'Content-Type': 'application/x-www-form-urlencoded'})
                    self.assertEqual(conn.getresponse().status, 429)
                    conn.close()
                finally:
                    srv.shutdown()


if __name__ == '__main__':
    unittest.main()
