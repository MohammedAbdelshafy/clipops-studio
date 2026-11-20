"""Offline regressions for transcript boundaries, multilingual ranking and ASR checkpoints."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pilot_intelligence as intelligence


class RankingTests(unittest.TestCase):
    def test_arabic_hook_and_source_copy(self):
        rows = [{'start': 0.2, 'end': 6, 'text': 'إزاي تراجع القماش قبل ما تشتري القميص؟', 'speaker': 'أحمد'},
                {'start': 6.2, 'end': 15, 'text': 'أول خطوة هي تجربة القطن في الضوء الطبيعي.', 'speaker': 'سارة'}]
        picks = intelligence.rank_candidates(rows, audience='fashion')
        self.assertEqual(len(picks), 1)
        result = picks[0]
        self.assertEqual(result['title'], rows[0]['text'])
        self.assertIn('question', result['signals'])
        self.assertIn('fashion', result['signals'])
        self.assertGreater(result['score_components']['audience_fit'], 0)
        self.assertEqual(result['score_type'], 'editorial_heuristic')
        self.assertTrue(result['rationale'])
        self.assertEqual((result['start'], result['end']), (0.2, 15))
        self.assertTrue(intelligence.ARABIC.search(result['cta']))

    def test_disjoint_repeats_filtered_but_new_content_at_end_kept(self):
        rows = [{'start': 0, 'end': 12, 'text': 'Why do customers return a cotton shirt after washing?'},
                {'start': 12, 'end': 23, 'text': 'The fabric changes shape when the sizing is wrong.'},
                {'start': 1800, 'end': 1812, 'text': 'Why do customers return a cotton shirt after washing?'},
                {'start': 1812, 'end': 1823, 'text': 'The fabric changes shape when the sizing is wrong.'},
                {'start': 3000, 'end': 3012, 'text': 'ازاي تنجح في اول ورشة عمل؟ جرب مثال مع الجمهور.'},
                {'start': 3012, 'end': 3023, 'text': 'اطلب من المشاركين كتابة جملة ومناقشة الفكرة بصوت واضح.'}]
        picks = intelligence.rank_candidates(rows, min_seconds=18, max_seconds=30)
        self.assertEqual({p['start'] for p in picks}, {0, 3000})
        self.assertEqual(picks, intelligence.rank_candidates(rows[::-1], min_seconds=18, max_seconds=30))

    def test_no_time_fabrication_and_sparse_input(self):
        self.assertFalse(intelligence.rank_candidates([{'start': 0, 'end': 75, 'text': 'A sentence without word alignment.'}]))
        self.assertFalse(intelligence.rank_candidates([{'start': 0, 'end': 35, 'text': 'um'}]))
        self.assertFalse(intelligence.rank_candidates([]))
        self.assertFalse(intelligence.rank_candidates([{'start': 1, 'end': 5, 'text': 'Why pay the full price?'},
                                                      {'start': 14, 'end': 20, 'text': 'Because it has value.'}]))
        with self.assertRaises(ValueError):
            intelligence.rank_candidates([], audience='unknown')

    def test_old_transcript_edit_and_invalid_bounds(self):
        rows = [{'start': 0, 'end': 12, 'text': 'Why does the edited transcript need the corrected phrase?',
                 'words': [{'start': 1, 'end': 3, 'word': 'obsolete'}]}]
        self.assertIn('edited', intelligence.rank_candidates(rows)[0]['title'])
        for value in (-1, True, float('nan'), float('inf')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                intelligence.normalize([{'start': value, 'end': 2, 'text': 'word'}])
        with self.assertRaises(ValueError):
            intelligence.normalize([{'start': 0, 'end': 2, 'text': 'two',
                                     'words': [{'start': 0, 'end': 3, 'text': 'two'}]}])

    def test_spoken_repetition_survives_and_seam_artifact_joins(self):
        def row(start, end):
            return {'start': start, 'end': end, 'text': 'No', 'words': [{'start': start, 'end': end, 'text': 'No'}]}
        rows = [row(9.7, 10)]
        intelligence._append_piece(rows, [row(10, 10.2)], 10)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['words'][0]['end'], 10.2)
        intelligence._append_piece(rows, [row(10.21, 10.4)], 10)
        self.assertEqual(len(rows), 2)


class OfflineAsrTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.root / 'one.mp4'
        self.source.write_bytes(b'synthetic')
        self.model = self.root / 'model'
        self.model.mkdir()
        for name in ('model.bin', 'config.json', 'tokenizer.json'):
            (self.model / name).write_bytes(b'fixture')
        self.cache = self.root / 'cache'

    def test_no_network_fallback_for_missing_tokenizer_or_invalid_track(self):
        with patch('pilot_intelligence._probe_audio', return_value=(13.5, 1)), \
                patch('pilot_intelligence._load_speech_model') as load:
            with self.assertRaises(ValueError):
                intelligence.transcribe_local(self.source, self.model, self.cache, speaker_tracks={1: 'Host'})
            (self.model / 'tokenizer.json').unlink()
            with self.assertRaisesRegex(ValueError, 'tokenizer.json'):
                intelligence.transcribe_local(self.source, self.model, self.cache)
            load.assert_not_called()

    def test_resume_after_interruption_and_cache_invalidation(self):
        def piece(_model, _wav, _lang, _left, start, end, speaker):
            if start == 10 and self.interrupted:
                self.interrupted = False
                raise RuntimeError('fixture interruption')
            return {'language': 'en', 'segments': [{'start': start, 'end': end, 'text': 'A timed example.', 'speaker': speaker}]}
        self.interrupted = True
        options = dict(language='en', chunk_seconds=10, speaker_tracks={0: 'Host'})
        with patch('importlib.metadata.version', return_value='1'), patch('pilot_intelligence._probe_audio', return_value=(25, 1)), \
                patch('pilot_intelligence._load_speech_model', return_value=(object(), 'cpu')) as load, \
                patch('pilot_intelligence._audio'), patch('pilot_intelligence._decode_piece', side_effect=piece) as decode:
            with self.assertRaisesRegex(RuntimeError, 'interruption'):
                intelligence.transcribe_local(self.source, self.model, self.cache, **options)
            self.assertEqual(len(list(self.cache.rglob('*.json'))), 1)
            result = intelligence.transcribe_local(self.source, self.model, self.cache, **options)
            self.assertEqual(result['cached_chunks'], 1)
            self.assertEqual([s['start'] for s in result['segments']], [0, 10, 20])
            self.assertTrue(all(s['speaker'] == 'Host' for s in result['segments']))
            self.assertEqual(result['speaker_method'], 'isolated_audio_tracks')
            load.reset_mock(); decode.reset_mock()
            result = intelligence.transcribe_local(self.source, self.model, self.cache, **options)
            self.assertEqual(result['cached_chunks'], 3)
            load.assert_not_called(); decode.assert_not_called()
            next(self.cache.rglob('*chunk-1.json')).write_text('{')
            self.assertEqual(intelligence.transcribe_local(self.source, self.model, self.cache, **options)['cached_chunks'], 2)
            self.source.write_bytes(b'changed data')
            self.assertEqual(intelligence.transcribe_local(self.source, self.model, self.cache, **options)['cached_chunks'], 0)


if __name__ == '__main__':
    unittest.main()
