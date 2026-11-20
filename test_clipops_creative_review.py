"""Purely offline creator-assistance safety and content regressions."""
import json
from pathlib import Path
import tempfile
import unittest

import clipops_creative_review as creative


class CreativeReviewTests(unittest.TestCase):
    def setUp(self):
        self.rows = creative.clean_segments([
            {'start':0.0,'end':5.0,'speaker':'Host','text':'Why do clients need a clear opening hook?'},
            {'start':5.0,'end':12.0,'speaker':'Host','text':'Because a complete idea beats random editing.'},
            {'start':12.0,'end':17.0,'speaker':'Guest','text':'That is a good lesson for every editor.'},
        ])
        self.clip = {'id':'c01','start':0.0,'end':17.0,'score':78,'remove_ranges':[]}

    def test_quotes_are_verbatim_and_timed_with_speaker_review(self):
        result = creative.review_candidate(self.rows,self.clip)
        self.assertEqual(result['candidate_id'],'c01')
        self.assertEqual(result['hook_source']['start'],0.0)
        self.assertEqual(result['hook_source']['verbatim'],self.rows[0]['text'])
        self.assertEqual(len(result['quote_bank']),3)
        self.assertEqual(result['speaker_counts'],{'Guest':1,'Host':2})
        self.assertTrue(any('Multiple speakers' in s for s in result['warnings']))
        self.assertEqual(result['possible_profanity'],[])

    def test_profanity_is_a_manual_review_flag_not_an_edit(self):
        rows=creative.clean_segments([{'start':0,'end':5,'text':'This is shit, never publish it automatically.'}])
        result=creative.review_candidate(rows,{'id':'c02','start':0,'end':5})
        self.assertEqual(result['possible_profanity'],['shit'])
        self.assertIn('manual review', ' '.join(result['warnings']))
        self.assertEqual(rows[0]['text'],'This is shit, never publish it automatically.')

    def test_half_words_and_overlap_risks(self):
        rows=creative.clean_segments([{'start':0,'end':6,'text':'A question about editing which matters.'},
                                      {'start':5,'end':10,'text':'Another timed sentence for testing.'}])
        result=creative.review_candidate(rows, {'id':'c03','start':1,'end':9})
        self.assertTrue(any('Start intersects' in w for w in result['warnings']))
        self.assertTrue(any('End intersects' in w for w in result['warnings']))
        self.assertTrue(any('Overlapping cues' in w for w in result['warnings']))

    def test_proposal_is_not_applied_and_validates_duration(self):
        result=creative.propose_edit(self.clip,'start 00:01; end 00:15; title: New title; cta: Watch more; remove 00:06 to 00:07',20)
        self.assertFalse(result['applied'])
        self.assertEqual(result['proposed_updates']['start'],1)
        self.assertEqual(result['proposed_updates']['end'],15)
        self.assertEqual(result['proposed_updates']['remove_ranges'],[[6,7]])
        self.assertEqual(self.clip['start'],0)
        for instruction in ('publish now','remove 0 to 99','start 999','start -3','title: ','start 3;start 4'):
            with self.subTest(instruction=instruction), self.assertRaises(ValueError):
                creative.propose_edit(self.clip,instruction,20)

    def test_existing_cuts_cannot_be_bypassed(self):
        c={**self.clip,'remove_ranges':[[5,6]]}
        with self.assertRaises(ValueError):
            creative.propose_edit(c,'start 1; remove 7 to 8',20)
        with self.assertRaises(ValueError):
            creative.propose_edit(c,'remove 5.5 to 6.5',20)

    def test_rejects_malformed_or_unsafe_transcripts(self):
        for value in (float('nan'),float('inf'),True,-1):
            with self.subTest(value=value),self.assertRaises(ValueError):
                creative.clean_segments([{'start':value,'end':2,'text':'text'}])
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'project.json').write_text(json.dumps({'transcript_file':'../../etc/passwd','candidates':[]}))
            with self.assertRaisesRegex(ValueError,'revision'):
                creative.project_review(root)

    def test_private_project_cli_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            name='transcript-'+'a'*32+'.json'
            (root/name).write_text(json.dumps(self.rows,ensure_ascii=False))
            (root/'project.json').write_text(json.dumps({'id':'b'*32,'transcript_file':name,'candidates':[self.clip]}))
            result=creative.project_review(root)
            self.assertEqual(result['project'],'b'*32)
            self.assertEqual(len(result['candidate_reviews']),1)
            self.assertEqual(sorted(p.name for p in root.iterdir()),['project.json',name])


if __name__=='__main__':
    unittest.main()
