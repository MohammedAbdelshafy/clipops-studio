"""Local ZIP delivery must never bypass the existing approval and integrity gate."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import studio_delivery


class Engine:
    PROJECT_FILE = 'project.json'

    def project_dir(self, root, job):
        return root / job

    @contextmanager
    def lock(self, directory, filename):
        yield

    def load_json(self, path):
        return json.loads(path.read_text(encoding='utf-8'))

    def sha256(self, path):
        digest = hashlib.sha256()
        with path.open('rb') as source:
            for block in iter(lambda: source.read(256 * 1024), b''):
                digest.update(block)
        return digest.hexdigest()

    def approved_media(self, directory, clip, kind, verify=True):
        if not (clip.get('rendered') and clip.get('qc', {}).get('passed') and
                clip.get('review') == 'approved' and clip.get('approval', {}).get('rights')):
            raise PermissionError('No current rights/QC approval')
        name = {'export':'clip.mp4','srt':'clip.srt','vtt':'clip.vtt'}[kind]
        path = directory / clip['bundle'] / name
        if path.is_symlink() or not path.is_file():
            raise PermissionError('Missing approved file')
        if verify and self.sha256(path) != clip['approval']['hashes'][name]:
            raise PermissionError('Approved file changed')
        return path


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.job = 'b' * 32
        self.project = self.root / self.job
        self.bundle = self.project / 'render-01'
        self.bundle.mkdir(parents=True)
        files = {'clip.mp4':b'approved media', 'clip.srt':b'1\n00:00:01,000 --> 00:00:02,000\nHello',
                 'clip.vtt':b'WEBVTT\n'}
        for name, data in files.items():
            (self.bundle / name).write_bytes(data)
        self.engine = Engine()
        self.clip = {'id':'c01','start':1,'end':4,'rendered':True,'qc':{'passed':True},
                     'review':'approved','bundle':'render-01',
                     'approval':{'rights':True,'hashes':{name:self.engine.sha256(self.bundle/name) for name in files}}}
        self.save()

    def save(self):
        (self.project/'project.json').write_text(json.dumps({'candidates':[self.clip]}))

    def test_approved_zip_has_source_timestamps_and_checksums_but_no_source_footage(self):
        output = self.root / 'approved.zip'
        receipt = studio_delivery.bundle_approved(self.engine,self.root,self.job,output)
        self.assertEqual(receipt['clips'],1)
        self.assertEqual(receipt['files'],3)
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(set(archive.namelist()),{'c01/clip.mp4','c01/clip.srt','c01/clip.vtt','delivery-manifest.json'})
            self.assertEqual(archive.read('c01/clip.mp4'),b'approved media')
            manifest = json.loads(archive.read('delivery-manifest.json'))
            self.assertEqual(manifest['files'][0]['source_range'],[1,4])
            self.assertEqual(manifest['files'][0]['sha256'],self.clip['approval']['hashes']['clip.mp4'])
        with self.assertRaises(ValueError):
            studio_delivery.bundle_approved(self.engine,self.root,self.job,output)

    def test_unapproved_or_tampered_clips_are_not_distributed(self):
        output = self.root / 'no.zip'
        self.clip['review'] = 'pending'
        self.save()
        with self.assertRaises(PermissionError):
            studio_delivery.bundle_approved(self.engine,self.root,self.job,output)
        self.assertFalse(output.exists())
        self.clip['review'] = 'approved'
        (self.bundle/'clip.mp4').write_bytes(b'changed')
        self.save()
        with self.assertRaises(PermissionError):
            studio_delivery.bundle_approved(self.engine,self.root,self.job,output)
        self.assertFalse(output.exists())

    def test_invalid_candidate_name_and_project_folder_destination(self):
        self.clip['id'] = '../escape'
        self.save()
        with self.assertRaises(ValueError):
            studio_delivery.bundle_approved(self.engine,self.root,self.job,self.root/'out.zip')
        self.clip['id'] = 'c01'
        self.save()
        with self.assertRaises(ValueError):
            studio_delivery.bundle_approved(self.engine,self.root,self.job,self.project/'out.zip')


if __name__=='__main__':
    unittest.main()
