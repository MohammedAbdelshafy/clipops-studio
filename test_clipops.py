"""Hermetic logic tests and optional local FFmpeg smoke coverage."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import clipops


class TranscriptTests(unittest.TestCase):
    def test_cues_and_vtt(self):
        cues = clipops.caption_groups([
            {"start": 0., "end": .3, "text": "Hello"},
            {"start": .4, "end": .7, "text": "world"},
            {"start": 2.4, "end": 3.0, "text": "Again"},
        ])
        self.assertEqual(len(cues), 2)
        self.assertIn("00:00:00,000 --> 00:00:00,700", clipops.subtitle_text(cues))
        self.assertTrue(clipops.subtitle_text(cues, vtt=True).startswith("WEBVTT"))
        self.assertIn("00:00:00.000", clipops.subtitle_text(cues, vtt=True))

    def test_clip_relative_captions(self):
        cues = [{"start": 8, "end": 12, "text": "Hello"}, {"start": 18, "end": 21, "text": "Bye"}]
        out = clipops.subtitle_text(cues, start=10, end=20)
        self.assertIn("00:00:00,000 --> 00:00:02,000", out)
        self.assertIn("00:00:08,000 --> 00:00:10,000", out)

    def test_invalid_cues_rejected(self):
        with self.assertRaises(ValueError):
            clipops.normalize_segments([{"start": 3, "end": 1, "text": "Hi"}])

    def test_clip_suggestions_no_overlap(self):
        segs = [{"start": float(i), "end": float(i + 1), "text": ("Why" if i % 11 == 0 else "this")}
                for i in range(80)]
        candidates = clipops.suggest_clips(segs, min_seconds=8, max_seconds=14)
        self.assertTrue(1 <= len(candidates) <= 5)
        self.assertTrue(all(x["end"] - x["start"] <= 14 for x in candidates))

    def test_timestamps(self):
        self.assertEqual(clipops.sec_to_stamp(3661.2), "01:01:01,200")


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "queue.db")
        self.media = Path(self.tmp.name) / "clip.mp4"
        self.media.write_bytes(b"test fixture")
        self.patcher = patch.object(clipops, "media_info", return_value={"format": {"duration": "15"}, "streams": [{"codec_type": "video"}]})
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def job(self):
        return clipops.add_job(self.db, str(self.media), "youtube", "channel_123", "Launch", "Video text", "2027-01-15T12:00:00+02:00")

    def test_postiz_payload_and_unlisted_privacy(self):
        j = self.job()
        job = clipops.list_jobs(self.db)[0]
        class Reply:
            def __init__(self, data):
                self.data = data
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass
            def read(self):
                return json.dumps(self.data).encode()
        events = []
        def respond(req, timeout=None):
            events.append(req)
            if len(events) == 1:
                return Reply({"id": "img-test", "path": "https://uploads.postiz.com/test.mp4"})
            return Reply([{"postId": "post-test", "integration": "channel_123"}])
        with patch.object(clipops.request, "urlopen", side_effect=respond):
            result = clipops.postiz_publish(job, "test-key")
        self.assertEqual(len(events), 2)
        self.assertTrue(events[0].full_url.endswith("/upload"))
        payload = json.loads(events[1].data)
        self.assertEqual(payload["type"], "schedule")
        self.assertEqual(payload["posts"][0]["settings"]["type"], "unlisted")
        self.assertEqual(payload["posts"][0]["settings"]["selfDeclaredMadeForKids"], "no")
        self.assertEqual(payload["posts"][0]["value"][0]["image"][0]["id"], "img-test")

    def test_queue_requires_approval(self):
        j = self.job()
        with self.assertRaises(ValueError):
            clipops.dispatch(self.db, j["id"], False)
        with self.assertRaises(ValueError):
            clipops.approve_job(self.db, j["id"], False)
        clipops.approve_job(self.db, j["id"], True)
        self.assertTrue(clipops.dispatch(self.db, j["id"], False)["dry_run"])
        with patch.dict(os.environ, {"CLIPOPS_ALLOW_PUBLISH": "0"}):
            with self.assertRaisesRegex(RuntimeError, "CLIPOPS_ALLOW_PUBLISH"):
                clipops.dispatch(self.db, j["id"], True)
        self.assertEqual(clipops.list_jobs(self.db)[0]["status"], "approved")

    def test_datetime_must_have_tz(self):
        with self.assertRaises(ValueError):
            clipops.iso_utc("2027-01-01T12:00:00")
        self.assertEqual(clipops.iso_utc("2027-01-01T12:00:00+02:00"), "2027-01-01T10:00:00Z")

    def test_reject_unknown_platform(self):
        with self.assertRaises(ValueError):
            clipops.add_job(self.db, str(self.media), "fake", "x", "T", "C", "2027-01-01T10:00:00Z")

    def test_live_post_requires_credentials_and_keeps_approval(self):
        j = self.job()
        clipops.approve_job(self.db, j["id"], True)
        with patch.dict(os.environ, {"CLIPOPS_ALLOW_PUBLISH": "1", "POSTIZ_API_KEY": ""}):
            with self.assertRaisesRegex(RuntimeError, "POSTIZ_API_KEY"):
                clipops.dispatch(self.db, j["id"], True)
        self.assertEqual(clipops.list_jobs(self.db)[0]["status"], "approved")

    def test_claim_on_postiz_timeout_no_retries(self):
        j = self.job()
        clipops.approve_job(self.db, j["id"], True)
        with patch.dict(os.environ, {"CLIPOPS_ALLOW_PUBLISH": "1", "POSTIZ_API_KEY": "fake"}), patch.object(clipops, "postiz_publish", side_effect=TimeoutError("network uncertainty")):
            with self.assertRaises(TimeoutError):
                clipops.dispatch(self.db, j["id"], True)
        self.assertEqual(clipops.list_jobs(self.db)[0]["status"], "needs_manual_review")


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg not installed")
class FFmpegSmokeTests(unittest.TestCase):
    def test_render_clip_and_promo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "original.mp4"
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=15", "-t", "3", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src)], check=True)
            segs = root / "transcript.json"
            segs.write_text(json.dumps({"segments": [{"start": 0, "end": 1.5, "text": "A sample subtitle"}]}))
            for fit in ("crop", "blur"):
                target = root / f"{fit}.mp4"
                data = clipops.render_clip(str(src), str(target), 0.2, 2, str(segs), fit, width=180, height=320)
                self.assertGreater(target.stat().st_size, 0)
                self.assertTrue(data["captions"])
            brief = root / "brief.json"
            brief.write_text(json.dumps({"scenes": [{"text": "Meet ClipOps", "seconds": .6}, {"text": "Create More", "seconds": .6}]}))
            promo_file = root / "promo.mp4"
            result = clipops.promo(str(brief), str(promo_file), width=180, height=320)
            self.assertEqual(result["scenes"], 2)
            self.assertGreater(promo_file.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
