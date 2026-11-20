"""HTTP regression tests for the local review desk, using a private fixture project."""
from http.client import HTTPConnection
from http.cookies import SimpleCookie
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from studio import DeskServer


class DeskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.files.cleanup)
        cls.root = Path(cls.files.name)
        cls.media = cls.root / 'authorized.mp4'
        cls.media.write_bytes(bytes(range(100)))
        cls.webm = cls.root / 'review.webm'
        cls.webm.write_bytes(bytes(range(60)))
        cls.engine = Mock()
        cls.project_id = 'b' * 32
        cls.project = {'id': cls.project_id, 'name': 'Test project', 'source': {'name': 'authorized.mp4'},
                       'status': 'review', 'model_path': '/private/model', 'segments': [], 'candidates': []}
        cls.engine.get_project.return_value = cls.project
        cls.engine.list_projects.return_value = [cls.project]
        cls.engine.get_media_path.return_value = cls.media
        cls.engine.browser_preview.return_value = cls.webm
        cls.server = DeskServer(0, cls.root, cls.engine)
        cls.addClassCleanup(cls.server.server_close)
        thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        thread.start()
        cls.addClassCleanup(cls.server.shutdown)
        cls.host = f'127.0.0.1:{cls.server.server_port}'

    def request(self, verb, path, body=None, **headers):
        conn = HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            conn.request(verb, path, body=body, headers=headers)
            result = conn.getresponse()
            return result.status, dict(result.getheaders()), result.read()
        finally:
            conn.close()

    def session(self):
        status, headers, _ = self.request('GET', '/')
        self.assertEqual(status, 200)
        self.assertIn('HttpOnly', headers['Set-Cookie'])
        self.assertIn('frame-ancestors', headers['Content-Security-Policy'])
        cookies = SimpleCookie(headers['Set-Cookie'])
        auth = {'Cookie': '; '.join(f'{k}={v.value}' for k,v in cookies.items())}
        _, _, session = self.request('GET', '/api/session', **auth)
        return {**auth, 'Origin': 'http://' + self.host, 'X-ClipOps-CSRF': json.loads(session)['csrf']}

    def test_session_scopes_host_origin_and_private_state(self):
        url = '/api/projects/' + self.project_id
        self.assertEqual(self.request('GET', url)[0], 403)
        self.assertEqual(self.request('GET', '/', Host='foreign.invalid')[0], 403)
        auth = self.session()
        self.assertEqual(self.request('GET', url, **auth, **{'Sec-Fetch-Site': 'cross-site'})[0], 403)
        status, _, body = self.request('GET', url, **auth)
        self.assertEqual(status, 200)
        self.assertNotIn(b'model_path', body)
        for field in ('Origin', 'X-ClipOps-CSRF'):
            altered = {**auth, field: 'incorrect'}
            self.assertEqual(self.request('POST', url+'/edit', b'{}', **altered)[0], 403)
        self.assertEqual(self.request('POST', url+'/edit', b'{"model_path":"test"}', **auth,
                                      **{'Content-Type':'application/json'})[0], 400)

    def test_free_fallbacks_requires_local_session(self):
        self.assertEqual(self.request('GET','/api/fallbacks')[0],403)
        status, _, body = self.request('GET','/api/fallbacks', **self.session())
        self.assertEqual(status,200)
        data = json.loads(body)
        self.assertEqual(data["network_requests"],0)
        self.assertTrue(any(row["id"] == "clipops_export" for row in data["routes"]))
        self.assertFalse(any(row["automatic"] for row in data["routes"]))

    def test_preview_seek_head_and_download_gate(self):
        auth = self.session()
        url = '/media/' + self.project_id + '/c01/preview'
        s, h, data = self.request('GET', url, Range='bytes=9-11', **auth)
        self.assertEqual((s,h['Content-Range'],data),(206,'bytes 9-11/100',bytes([9,10,11])))
        s, _, data = self.request('GET', url, Range='bytes=-4', **auth)
        self.assertEqual((s,data),(206,bytes(range(96,100))))
        self.assertEqual(self.request('GET', url, Range='bytes=101-', **auth)[0], 416)
        self.assertEqual(self.request('HEAD', url, **auth)[2], b'')
        self.assertEqual(self.request('GET', url+'/../source', **auth)[0], 404)
        self.engine.get_media_path.side_effect = PermissionError('Pending')
        try:
            self.assertEqual(self.request('GET', url.replace('preview','export'), **auth)[0], 403)
        finally:
            self.engine.get_media_path.side_effect = None

    def test_webm_preview_is_authenticated_and_preserves_export_gate(self):
        url = '/media/' + self.project_id + '/c01/webm'
        self.assertEqual(self.request('GET', url)[0], 403)
        auth = self.session()
        status, headers, data = self.request('GET', url, Range='bytes=4-7', **auth)
        self.assertEqual(status, 206)
        self.assertEqual(headers['Content-Type'], 'video/webm')
        self.assertEqual(headers['Content-Range'], 'bytes 4-7/60')
        self.assertEqual(data, bytes(range(4,8)))
        self.engine.browser_preview.assert_called_with(self.root, self.project_id, 'c01')

    def test_upload_validates_rights_filename_and_content_before_pipeline(self):
        auth = self.session()
        def upload(metadata):
            head = json.dumps(metadata).encode()
            return self.request('POST','/api/import',head+b'video',**auth,**{
                'Content-Type':'application/octet-stream','X-ClipOps-Metadata-Length':str(len(head))})[0]
        base = {'rights':True, 'filename':'sample.mp4', 'mime':'video/mp4', 'transcript':{'segments':[]},'render_count':0}
        self.assertEqual(upload({**base,'rights':False}),400)
        self.assertEqual(upload({**base,'filename':'../sample.mp4'}),400)
        self.assertEqual(upload({**base,'mime':'text/html'}),415)
        self.assertEqual(upload({**base,'transcript':None}),400)
        self.engine.create_project.assert_not_called()
        def create(source, root, **kwargs):
            self.assertEqual(source.read_bytes(),b'video')
            self.assertEqual(json.loads(kwargs['transcript'].read_text()),{'segments':[]})
            return self.project_id
        self.engine.create_project.side_effect = create
        self.assertEqual(upload(base),201)
        self.assertEqual(list(self.root.glob('.ingest-*')),[])
        self.engine.create_project.reset_mock()

    def test_creative_review_is_local_and_edit_preview_does_not_mutate(self):
        auth = self.session()
        project = self.project
        old_source = project['source']
        old_rows = project['segments']
        old_candidates = project['candidates']
        self.engine.edit_project.reset_mock()
        try:
            project['source'] = {'name': 'authorized.mp4', 'duration': 20}
            project['segments'] = [{'start': 0, 'end': 7, 'text': 'Why do our editors need careful caption reviews?',
                                    'speaker': 'Host'}]
            project['candidates'] = [{'id': 'c01', 'start': 0, 'end': 7, 'score': 80,
                                      'remove_ranges': [], 'review': 'pending'}]
            review_url = f'/api/projects/{self.project_id}/c01/creative'
            status, _, body = self.request('GET', review_url, **auth)
            self.assertEqual(status, 200)
            result = json.loads(body)
            self.assertEqual(result['hook_source']['start'], 0)
            self.assertEqual(result['candidate_id'], 'c01')
            self.assertEqual(self.request('GET', review_url.replace('/c01/', '/c99/'), **auth)[0], 404)

            proposal_url = f'/api/projects/{self.project_id}/propose'
            headers = {**auth, 'Content-Type': 'application/json'}
            status, _, body = self.request('POST', proposal_url,
                                           json.dumps({'candidate_id': 'c01', 'instruction': 'start 00:01; end 00:06'}), **headers)
            self.assertEqual(status, 200)
            preview = json.loads(body)
            self.assertEqual(preview['proposed_updates'], {'start': 1.0, 'end': 6.0})
            self.assertFalse(preview['applied'])
            self.assertEqual(project['candidates'][0]['start'], 0)
            self.engine.edit_project.assert_not_called()
            self.assertEqual(self.request('POST', proposal_url, json.dumps(
                {'candidate_id': 'c01', 'instruction': 'publish now'}), **headers)[0], 400)
        finally:
            project['source'] = old_source
            project['segments'] = old_rows
            project['candidates'] = old_candidates

    def test_moment_search_and_visual_review_respect_session_and_do_not_edit(self):
        project = self.project
        old_source, old_rows, old_candidates = project['source'], project['segments'], project['candidates']
        self.engine.edit_project.reset_mock()
        try:
            project['source'] = {'name':'authorized.mp4', 'duration':30}
            project['segments'] = [{'start':0,'end':4,'text':'Why do customers ask for podcast clips?'},
                                   {'start':4.1,'end':15,'text':'Because a coherent story helps people understand the full lesson.'}]
            project['candidates'] = [{'id':'c01','start':0,'end':15,'score':60,'review':'pending'}]
            url=f'/api/projects/{self.project_id}/search-moments'
            body=json.dumps({'query':'customers podcast'})
            headers={'Content-Type':'application/json'}
            self.assertEqual(self.request('POST',url,body,**headers)[0],403)
            auth=self.session()
            self.assertEqual(self.request('POST',url,body,**{**auth,'X-ClipOps-CSRF':'bad'},**headers)[0],403)
            status,_,data=self.request('POST',url,body,**auth,**headers)
            self.assertEqual(status,200)
            found=json.loads(data)
            self.assertEqual(found['matches'][0]['start'],0)
            self.assertEqual(found['matches'][0]['end'],15)
            self.assertEqual(self.request('POST',url,json.dumps({'query':'***'}),**auth,**headers)[0],400)
            self.assertEqual(self.request('POST',url,json.dumps({'query':'podcast','model':'remote'}),**auth,**headers)[0],400)
            visual_url=f'/api/projects/{self.project_id}/c01/visual'
            self.assertEqual(self.request('GET',visual_url)[0],403)
            self.assertTrue(self.server.visual_slots.acquire(blocking=False))
            try:
                self.assertEqual(self.request('GET', visual_url, **auth)[0], 429)
            finally:
                self.server.visual_slots.release()
            with patch('studio.clipops_scene_review.scene_review',return_value={
                    'source_range':[0,15], 'scene_boundaries':[7.5], 'advisory_only':True}) as analyzer:
                status,_,data=self.request('GET',visual_url,**auth)
                self.assertEqual(status,200)
                self.assertEqual(json.loads(data)['scene_boundaries'],[7.5])
                analyzer.assert_called_once_with(self.media,0,15)
            self.assertEqual(self.request('GET',visual_url.replace('/c01/','/c99/'),**auth)[0],404)
            self.engine.edit_project.assert_not_called()
        finally:
            project['source'],project['segments'],project['candidates']=old_source,old_rows,old_candidates

    def test_batch_zip_requires_session_and_uses_private_temporary_storage(self):
        path = f'/api/projects/{self.project_id}/approved-delivery.zip'
        self.assertEqual(self.request('GET', path)[0], 403)
        auth = self.session()
        with patch('studio.studio_delivery.bundle_approved') as make_bundle:
            make_bundle.side_effect = lambda engine, root, project_id, destination: destination.write_bytes(b'private zip fixture')
            status, headers, body = self.request('GET', path, **auth)
            self.assertEqual(status, 200)
            self.assertEqual(body, b'private zip fixture')
            self.assertIn('attachment', headers['Content-Disposition'])
            self.assertEqual(self.request('HEAD', path, **auth)[0], 405)
        self.assertEqual(list(self.root.glob('.delivery-*')), [])

        with patch('studio.studio_delivery.bundle_approved', side_effect=PermissionError('No approved clips')):
            self.assertEqual(self.request('GET', path, **auth)[0], 403)
        self.assertEqual(list(self.root.glob('.delivery-*')), [])

    def test_destructive_action_requires_matching_project_name(self):
        status, _, _ = self.request('POST',f'/api/projects/{self.project_id}/purge',b'{"confirm_name":"elsewhere"}',
                                    **self.session(),**{'Content-Type':'application/json'})
        self.assertEqual(status,400)
        self.engine.purge_project.assert_not_called()
