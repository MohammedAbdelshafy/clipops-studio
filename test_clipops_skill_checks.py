"""Standalone, stdlib-only unit checks for the Google-inspired skill evidence card."""
import copy
import unittest

from clipops_skill_checks import review_skill_checks


class SkillCheckTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {'start':0.0,'end':4.0,'text':'Why does this opening make sense?'},
            {'start':4.0,'end':9.0,'text':'Because it explains the full lesson.'},
            {'start':9.0,'end':13.0,'text':'الدرس المفيد يبدأ من البداية.'},
        ]
        self.review = {
            'source_range':[0,13],
            'hook_source':{'start':0,'end':4,'verbatim':self.rows[0]['text']},
            'quote_bank':[{'start':0,'end':4,'verbatim':self.rows[0]['text']}],
            'warnings':[],
        }

    def checks(self, review=None, duration=13.0):
        output = review_skill_checks(self.rows, review if review is not None else self.review, duration)
        return {c['key']: c['status'] for c in output['checks']}

    def test_grounded_quote_and_bounds(self):
        before = copy.deepcopy(self.review)
        checks = self.checks()
        self.assertEqual(checks['source_bounds'], 'verified')
        self.assertEqual(checks['hook_grounding'], 'verified')
        self.assertEqual(checks['quote_ranges'], 'verified')
        self.assertEqual(checks['visual_audio'], 'not_verified')
        self.assertEqual(before, self.review)
        card = review_skill_checks(self.rows,self.review,13)
        self.assertTrue(card['requires_human_review'])
        self.assertFalse(card['grants_export_approval'])
        self.assertFalse(card['network_or_model_calls'])

    def test_fabricated_quote_rejected(self):
        fake = copy.deepcopy(self.review)
        fake['hook_source']['verbatim'] = 'I earned a million dollars.'
        self.assertEqual(self.checks(fake)['hook_grounding'],'needs_review')

    def test_quote_crossing_clip_boundary_rejected(self):
        clipped = copy.deepcopy(self.review)
        clipped['source_range'] = [1,13]
        self.assertEqual(self.checks(clipped)['hook_grounding'],'needs_review')
        self.assertEqual(self.checks(clipped)['quote_ranges'],'needs_review')

    def test_empty_and_missing_duration_do_not_invent_evidence(self):
        empty = {'source_range':[0,13],'hook_source':None,'quote_bank':[]}
        self.assertEqual(self.checks(empty)['hook_grounding'],'needs_review')
        self.assertEqual(review_skill_checks(self.rows,self.review)['checks'][0]['status'],'not_verified')

    def test_timing_risk_and_overshoot(self):
        changed = {**self.review,'warnings':['Overlapping cues: review caption synchronization']}
        self.assertEqual(self.checks(changed)['caption_timing'],'needs_review')
        self.assertEqual(self.checks(duration=12.0)['source_bounds'],'needs_review')

    def test_invalid_inputs_fail_closed(self):
        with self.assertRaises(ValueError):
            review_skill_checks(self.rows, self.review, float('nan'))
        with self.assertRaises(ValueError):
            review_skill_checks(self.rows, None, 13)
        malformed = {**self.review,'source_range':[0,float('inf')]}
        self.assertEqual(self.checks(malformed)['source_bounds'],'needs_review')


if __name__ == '__main__':
    unittest.main()
