"""Tests for review-gated prompt retrieval and real local video scene analysis."""
import json
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import clipops_creative_review as creative
import clipops_scene_review as scenes


class PromptMomentTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {'start': 0.0, 'end': 4, 'text': 'إزاي تبدأ مشروع محتوى من غير ميزانية؟', 'speaker': 'Moe'},
            {'start': 4.2, 'end': 12, 'text': 'أول خطوة تختار العميل وتشرح له قيمة الخدمة.', 'speaker': 'Moe'},
            {'start': 18.5, 'end': 22, 'text': 'Unrelated story with a long pause.'},
            {'start': 320, 'end': 328, 'text': 'Why do customers need a correct transcript?'},
            {'start': 328.1, 'end': 341, 'text': 'They should review the words before they edit the source video.'},
            {'start': 900, 'end': 908, 'text': 'Why do customers need a correct transcript?'},
            {'start': 908.1, 'end': 921, 'text': 'They should review the words before they edit the source video.'},
        ]

    def test_english_and_arabic_queries_find_only_real_contiguous_spans(self):
        ar = creative.find_moments(self.rows, 'كيف تبدأ مشروع')
        self.assertNotIn('كيف', ar[0]['matched_terms'])  # no invented synonym match
        ar = creative.find_moments(self.rows, 'ازاي تبدأ مشروع')
        self.assertEqual(len(ar), 1)
        self.assertEqual((ar[0]['start'], ar[0]['end']), (0, 12))
        self.assertIn('إزاي', ar[0]['verbatim'])
        en = creative.find_moments(self.rows, 'correct transcript')
        self.assertEqual(len(en), 2)
        self.assertEqual({(v['start'], v['end']) for v in en}, {(320, 341), (900, 921)})
        self.assertEqual(en[0]['method'], 'offline_transcript_tokens')
        self.assertEqual(en[0]['evidence'][0]['verbatim'], self.rows[3]['text'])

    def test_no_content_fabrication_or_cross_gap_splicing(self):
        rows = [
            {'start': 0,'end': 2,'text':'Launch now'},
            {'start': 150,'end': 152,'text':'Now launch'},
        ]
        self.assertEqual(creative.find_moments(rows, 'launch'), [])
        self.assertEqual(creative.find_moments(self.rows, 'this information is not spoken'), [])
        before = json.dumps(self.rows, sort_keys=True)
        creative.find_moments(self.rows, 'client')
        self.assertEqual(json.dumps(self.rows, sort_keys=True), before)

    def test_invalid_queries_and_content_are_rejected(self):
        for bad in (None, '', 'x', '***', 'a '*200):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                creative.find_moments(self.rows,bad)
        with self.assertRaises(ValueError):
            creative.find_moments(self.rows,'client', limit=13)
        with self.assertRaises(ValueError):
            creative.find_moments([{'start':-1,'end':6,'text':'bad'}],'bad')

    def test_no_auto_edit_and_human_proposal_invalidates_approval_when_applied(self):
        clip = {'id':'c01','start':0,'end':25,'score':80,'review':'approved','approval':{'hashes':{}},'remove_ranges':[]}
        original = json.dumps(clip, sort_keys=True)
        match = creative.find_moments(self.rows,'العميل')[0]
        proposal = creative.propose_edit(clip,
            f"start {match['start']:.3f}; end {match['end']:.3f}", 1000)
        self.assertFalse(proposal['applied'])
        self.assertEqual(json.dumps(clip, sort_keys=True),original)
        self.assertEqual(proposal['proposed_updates']['start'],match['start'])
        self.assertEqual(proposal['proposed_updates']['end'],match['end'])


class SceneAnalysisTests(unittest.TestCase):
    def test_validation_prevents_unbounded_scans(self):
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/'clip.mp4'; path.write_bytes(b'fake')
            for args in ((-1,4), (0,181), (True,2), (2,2), (float('nan'),3), (None, 2)):
                with self.subTest(args=args), self.assertRaises(ValueError):
                    scenes.scene_review(path,*args)
            with self.assertRaises(ValueError):
                scenes.scene_review(path,0,3,threshold=.99)
            with self.assertRaises(ValueError):
                scenes.scene_review(Path(tmp)/'missing.mp4',0,3)
            (Path(tmp)/'alias.mp4').symlink_to(path)
            with self.assertRaises(ValueError):
                scenes.scene_review(Path(tmp)/'alias.mp4',0,3)

    def test_ffmpeg_fails_closed_and_sanitizes_tool_output(self):
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/'fake.mp4'; path.write_bytes(b'synthetic')
            with patch('clipops_scene_review.subprocess.run',return_value=type('R',(),{'returncode':1,'stderr':b'/secret/file'})()):
                with self.assertRaisesRegex(ValueError,'Unable to inspect visual changes') as context:
                    scenes.scene_review(path,0,2)
                self.assertNotIn('/secret/file',str(context.exception))

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required for deterministic synthetic video')
    def test_decodes_real_frames_and_detects_transition_from_seek(self):
        with TemporaryDirectory() as tmp:
            out=Path(tmp)/'cuts.mp4'
            build = [
                'ffmpeg','-nostdin','-hide_banner','-loglevel','error',
                '-f','lavfi','-i','color=c=red:s=320x180:r=24:d=1.5',
                '-f','lavfi','-i','color=c=blue:s=320x180:r=24:d=1.5',
                '-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0',
                '-pix_fmt','yuv420p','-y',str(out),
            ]
            subprocess.run(build,check=True,timeout=20,capture_output=True)
            info=scenes.scene_review(out,.5,2.5,threshold=.2)
            self.assertTrue(info['advisory_only'])
            self.assertEqual(info['scene_boundaries'],[1.5])
            self.assertEqual(info['source_range'],[.5,2.5])

if __name__=='__main__':
    unittest.main()
