"""Private hybrid laptop/cloud pairing regression coverage.

All traffic in these tests uses a loopback HTTP test server and mocked media;
no Tailscale service, cloud VM or customer footage is touched.
"""
from http.client import HTTPConnection
from http.cookies import SimpleCookie
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import json
import re
import unittest
from unittest.mock import Mock

from studio import DeskServer
from studio_preview import tailnet_origin


class TailnetAddressTests(unittest.TestCase):
    def test_only_exact_private_https_tailnet_device(self):
        self.assertEqual(tailnet_origin('https://clipops.mytailnet.ts.net'),
                         'https://clipops.mytailnet.ts.net')
        self.assertEqual(tailnet_origin('https://clipops.mytailnet.ts.net/'),
                         'https://clipops.mytailnet.ts.net')
        for value in ('http://clipops.mytailnet.ts.net',
                      'https://clipops.ts.net', 'https://ts.net',
                      'https://clipops.ts.net.evil.example',
                      'https://evil.example.com', 'https://clipops.mytailnet.ts.net:8443',
                      'https://clipops.mytailnet.ts.net/?token=secret',
                      'https://user@clipops.mytailnet.ts.net',
                      'https://clipops.mytailnet.ts.net/#fragment',
                      'https://clipops.mytailnet.ts.net/secret',
                      'https://clipops..ts.net', ' https://clipops.mytailnet.ts.net',
                      'https://clipops.mytailnet.ts.net\nX-Custom: true', None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                tailnet_origin(value)

    def test_cloud_shell_and_tailnet_are_mutually_exclusive(self):
        with TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                DeskServer(0, Path(tmp), Mock(), cloud_shell=True,
                           web_host='a.cloudshell.dev',
                           private_origin='https://clipops.mytailnet.ts.net')


class RemotePairingTests(unittest.TestCase):
    def test_anonymous_remote_has_no_session_and_code_is_one_use(self):
        with TemporaryDirectory() as tmp:
            engine = Mock()
            project = 'b'*32
            engine.get_project.return_value = {'id': project, 'source': {'duration': 5},
                                                'candidates': [], 'segments': []}
            with DeskServer(0, Path(tmp), engine, private_origin='https://clipops.mytailnet.ts.net') as server:
                worker = Thread(target=server.serve_forever, daemon=True)
                worker.start()
                host = 'clipops.mytailnet.ts.net'

                def req(method, path, data=None, host=host, **headers):
                    conn = HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                    try:
                        conn.request(method, path, body=data,
                                     headers={'Host': host, **headers})
                        response = conn.getresponse()
                        return response.status, dict(response.getheaders()), response.read()
                    finally:
                        conn.close()

                try:
                    status, headers, body = req('GET', '/')
                    self.assertEqual(status, 200)
                    self.assertNotIn('Set-Cookie', headers)
                    self.assertIn(b'Private Pairing', body)
                    self.assertEqual(req('GET', '/api/session')[0], 403)
                    self.assertEqual(req('GET', '/api/projects')[0], 403)

                    entry = json.dumps({'code': server.pair_code}).encode()
                    headers = {'Content-Type': 'application/json'}
                    self.assertEqual(req('POST', '/api/remote-pair', entry,
                                         host='attacker.example', **headers)[0], 403)
                    self.assertEqual(req('POST', '/api/remote-pair', entry,
                                         Origin='https://attacker.example', **headers)[0], 403)
                    self.assertEqual(req('POST', '/api/remote-pair',
                                         b'{"code":"wrong"}', **headers)[0], 403)
                    self.assertEqual(req('GET', '/api/session')[0], 403)
                    status, headers, body = req('POST', '/api/remote-pair', entry, **headers)
                    self.assertEqual(status, 204)
                    self.assertIn('Secure', headers['Set-Cookie'])
                    self.assertIn('HttpOnly', headers['Set-Cookie'])
                    self.assertIn('SameSite=Strict', headers['Set-Cookie'])
                    self.assertEqual(req('POST', '/api/remote-pair', entry, **{'Content-Type':'application/json'})[0], 429)
                    cookie = SimpleCookie(headers['Set-Cookie'])
                    value = '; '.join(f'{name}={item.value}' for name,item in cookie.items())
                    status, _, body = req('GET', '/api/session', Cookie=value)
                    self.assertEqual(status, 200)
                    csrf = json.loads(body)['csrf']
                    self.assertEqual(req('GET', '/api/projects', Cookie=value)[0], 200)
                    path = f'/api/projects/{project}/edit'
                    invalid = json.dumps({'unknown_option': 'never apply'}).encode()
                    auth = {'Cookie': value, 'X-ClipOps-CSRF': csrf, 'Content-Type': 'application/json'}
                    self.assertEqual(req('POST',path,invalid,Origin='https://evil.example', **auth)[0],403)
                    self.assertEqual(req('POST',path,invalid,Origin='https://clipops.mytailnet.ts.net',
                                         **{**auth, 'X-ClipOps-CSRF':'wrong'})[0],403)
                    self.assertEqual(req('POST',path,invalid,Origin='https://clipops.mytailnet.ts.net',**auth)[0],400)
                    self.assertEqual(req('GET','/',Cookie=value)[0],200)
                    engine.edit_project.assert_not_called()
                finally:
                    server.shutdown()

    def test_form_pairing_and_localhost_relay_require_code(self):
        with TemporaryDirectory() as tmp:
            with DeskServer(0, Path(tmp), Mock(),
                            private_origin='https://clipops.mytailnet.ts.net') as server:
                worker = Thread(target=server.serve_forever, daemon=True)
                worker.start()
                local = f'localhost:{server.server_port}'
                try:
                    def call(path, body=None, headers=None):
                        c = HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                        try:
                            c.request('GET' if body is None else 'POST', path, body,
                                      headers={'Host':local, **(headers or {})})
                            r=c.getresponse()
                            return r.status,dict(r.getheaders()),r.read()
                        finally:
                            c.close()
                    self.assertNotIn('Set-Cookie',call('/')[1])
                    raw=f'code={server.pair_code}'.encode()
                    status, headers, _=call('/api/remote-pair',raw,{
                        'Content-Type':'application/x-www-form-urlencoded',
                        'Origin':'http://'+local})
                    self.assertEqual(status,303)
                    self.assertEqual(headers['Location'],'/')
                    self.assertNotIn('Secure', headers['Set-Cookie'])
                finally:
                    server.shutdown()


if __name__ == '__main__':
    unittest.main()
