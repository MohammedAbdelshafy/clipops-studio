"""Regression coverage for private project state, interrupted renders and signed-off delivery."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pilot


class PilotTests(unittest.TestCase):
    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.work = Path(scratch.name)
        self.root = self.work / "projects"
        self.source = self.work / "video.mp4"
        self.source.write_bytes(b"placeholder for the orchestration test")
        self.transcript = self.work / "transcript.json"
        self.transcript.write_text(json.dumps({"segments": [
            {"start": 0.0, "end": 12, "text": "The first step fixes the leak.",
             "words": [{"start": 0.0, "end": .2, "word": "The"}]},
            {"start": 14.0, "end": 26, "text": "A second lesson describes the schedule."},
        ]}))
        self.patches = [
            patch.object(pilot.pilot_qc, "validate_source", return_value={
                "duration": 28., "dimensions": [1920, 1080], "has_audio": True}),
            patch.object(pilot.pilot_intelligence, "rank_candidates", return_value=[
                {"start": 0, "end": 12, "title": "First lesson", "description": "", "cta": "", "score": 75},
                {"start": 14, "end": 26, "title": "Second lesson", "description": "", "cta": "", "score": 65},
            ]),
            patch.object(pilot.pilot_qc, "inspect_export", side_effect=lambda *a, **k: {
                "passed": True, "checks": {"full_decode": True}, "evidence": {}}),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def create(self):
        return pilot.create_project(self.source, self.root, transcript=self.transcript, rights=True)

    def render(self, source, target, start, end, rows, *args, **kwargs):
        target.write_bytes(f"clip {start}-{end}".encode())
        target.with_suffix(".srt").write_text("fixture")
        target.with_suffix(".vtt").write_text("WEBVTT\n")
        return {"dimensions": [1080, 1920], "captions": []}

    def test_rights_and_traversal(self):
        with self.assertRaisesRegex(ValueError, "rights"):
            pilot.create_project(self.source, self.root, transcript=self.transcript)
        with self.assertRaisesRegex(ValueError, "ID"):
            pilot.get_project(self.root, "../elsewhere")
        project = self.create()
        self.assertEqual(pilot.list_projects(self.root)[0]["id"], project)
        self.assertEqual(self.root.stat().st_mode & 0o777, 0o700)
        self.assertNotIn("model_path", pilot.get_project(self.root, project))

    def test_approved_file_integrity_and_edit_invalidation(self):
        job = self.create()
        with patch.object(pilot.pilot_edit, "render", self.render):
            pilot.process_project(self.root, job, render_count=1)
            with self.assertRaisesRegex(ValueError, "named reviewer"):
                pilot.get_media_path(self.root, job, "c01", "export")
            pilot.review_clip(self.root, job, "c01", "approved", "Editor", True)
            path = pilot.get_media_path(self.root, job, "c01", "export")
            path.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "Approved file changed"):
                pilot.get_media_path(self.root, job, "c01", "export")
            resumed = pilot.process_project(self.root, job, render_count=1)
            self.assertEqual(resumed["candidates"][0]["review"], "pending")
            pilot.review_clip(self.root, job, "c01", "approved", "Editor", True)
            rows = resumed["segments"]
            rows[0]["text"] = "A revised sentence."
            changed = pilot.edit_project(self.root, job, segments=rows)
            self.assertNotIn("words", changed["segments"][0])
            self.assertFalse(changed["candidates"][0]["rendered"])

    def test_resume_after_interruption_keeps_completed_bundle(self):
        job = self.create()

        def interrupt(source, target, start, *args, **kwargs):
            if start == 14:
                raise KeyboardInterrupt()
            return self.render(source, target, start, *args, **kwargs)

        with patch.object(pilot.pilot_edit, "render", interrupt):
            with self.assertRaises(KeyboardInterrupt):
                pilot.process_project(self.root, job)
        self.assertEqual(pilot.get_project(self.root, job)["status"], "failed")
        with patch.object(pilot.pilot_edit, "render", self.render):
            state = pilot.process_project(self.root, job)
        self.assertEqual(state["runs"][-1]["cached"], 1)
        self.assertTrue(all(c["rendered"] for c in state["candidates"]))
        pilot.purge_project(self.root, job)
        self.assertEqual(pilot.list_projects(self.root), [])


if __name__ == "__main__":
    unittest.main()
