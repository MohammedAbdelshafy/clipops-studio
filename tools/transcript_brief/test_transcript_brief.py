import unittest
from transcript_brief import generate


class BriefTests(unittest.TestCase):
    def test_extracts(self):
        result = generate('A short-form video starts with a clear promise. Viewers need to understand the value before the next sentence. Every claim should be checked against the original recording.', 'Demo')
        self.assertEqual(result['status'], 'DRAFT_REVIEW_REQUIRED')
        self.assertEqual(len(result['clip_candidates']), 3)
        self.assertTrue(all(x['needs_editorial_review'] for x in result['clip_candidates']))

    def test_rejects_short(self):
        with self.assertRaises(ValueError):
            generate('Too short.')

    def test_rejects_unpunctuated(self):
        with self.assertRaises(ValueError):
            generate('This is a long line without any punctuation and there are no sentence boundaries here')

    def test_no_invented_timestamps(self):
        result = generate('First sentence has useful context. Second sentence has a useful detail about the offer. Third sentence describes the outcome.')
        self.assertTrue(all('timestamp' not in c for c in result['clip_candidates']))


if __name__ == '__main__':
    unittest.main()
