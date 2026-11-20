"""Pilot media QC, digest-bound approvals, and pre-network rejection."""
from contextlib import closing
import hashlib
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import clipops
import pilot_qc as qc


def make_video(target, video="testsrc2=size=180x320:rate=15", audio="sine=frequency=500:sample_rate=48000",
               audio_offset=None):
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-f", "lavfi", "-i", video]
    if audio:
        if audio_offset is not None:
            command += ["-itsoffset", str(audio_offset)]
        command += ["-f", "lavfi", "-i", audio, "-c:a", "aac"]
    command += ["-t", "3", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-threads", "1",
                "-movflags", "+faststart", str(target)]
    subprocess.run(command, check=True, timeout=30)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "Requires FFmpeg")
class PilotQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        cls.good = cls.root / "generated.mp4"
        make_video(cls.good)
        cls.cues = [{"start": 0.1, "end": 1.4, "text": "أهلاً ClipOps", "lines": ["أهلاً ClipOps"],
                     "max_width": 140, "line_widths": [110]}]

    def inspect(self, path, **kwargs):
        return qc.inspect_export(path, **{"expected_duration": 3, "dimensions": [180, 320],
                                          "segments": self.cues, **kwargs})

    def test_valid_clip_checks_frametime_pcm_and_captions(self):
        source = qc.validate_source(self.good)
        self.assertEqual(source["mime"], "video/mp4")
        self.assertEqual(source["dimensions"], [180, 320])
        self.assertTrue(source["has_audio"])
        report = self.inspect(self.good, source_info=source)
        self.assertTrue(report["passed"], report)
        self.assertEqual(report["evidence"]["decoded_frames"], 45)
        self.assertGreater(report["evidence"]["decoded_audio_samples"], 140000)
        self.assertEqual(report["evidence"]["captions"]["cues_with_measured_widths"], 1)
        self.assertGreater(len(report["manual_review"]), 0)
        self.assertNotIn(str(self.root), str(report))

    def test_probe_rejects_empty_truncated_mislabeled_and_oversized(self):
        for name, data in [("empty.mp4", b""), ("broken.mp4", self.good.read_bytes()[:16]),
                           ("wrong.webm", self.good.read_bytes()), ("text.mp4", b"ordinary text")]:
            with self.subTest(name):
                path = self.root / name
                path.write_bytes(data)
                with self.assertRaises(ValueError):
                    qc.validate_source(path)
                self.assertFalse(self.inspect(path)["passed"])
        with (self.root / "sparse.mp4").open("wb") as f:
            f.truncate(qc.MAX_SOURCE_BYTES + 1)
        with self.assertRaisesRegex(ValueError, "20 GiB"):
            qc.validate_source(self.root / "sparse.mp4")

    def test_truncated_faststart_payload_fails_full_report(self):
        broken = self.root / "truncated-payload.mp4"
        data = self.good.read_bytes()
        broken.write_bytes(data[:len(data) // 2])
        self.assertFalse(self.inspect(broken)["passed"])

    def test_duplicate_media_detected_even_after_metadata_remux(self):
        original = self.inspect(self.good)
        remux = self.root / "remux.mp4"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(self.good), "-c", "copy",
                        "-metadata", "title=second container", str(remux)], check=True, timeout=30)
        self.assertNotEqual(hashlib.sha256(self.good.read_bytes()).digest(), hashlib.sha256(remux.read_bytes()).digest())
        report = self.inspect(remux, prior_fingerprints={original["evidence"]["decoded_media_sha256"]})
        self.assertFalse(report["checks"]["distinct_decoded_media"])
        self.assertFalse(report["passed"])

    def test_wrong_geometry_duration_and_caption_bounds(self):
        cues = [{"start": -1, "end": 3.5, "text": "Caption", "lines": ["Caption"],
                 "max_width": 100, "line_widths": [130]}]
        result = self.inspect(self.good, expected_duration=2.5, dimensions=[200, 320], segments=cues)
        for name in ("export_dimensions", "export_duration", "caption_timing", "caption_line_bounds"):
            self.assertFalse(result["checks"][name])
        self.assertFalse(self.inspect(self.good, segments=None)["passed"])

    def test_third_line_requires_measured_fit_in_safe_height(self):
        cue = dict(self.cues[0], lines=["أهلاً", "ClipOps", "Studio"], line_widths=[55, 75, 60])
        fit = dict(cue, block_height=60, max_height=70)
        self.assertTrue(qc._caption_report([fit], 3, [180, 320])[0]["caption_line_bounds"])
        for invalid in (cue, dict(fit, block_height=71), dict(fit, max_height=75), dict(fit, line_widths=None)):
            self.assertFalse(qc._caption_report([invalid], 3, [180, 320])[0]["caption_line_bounds"])

    def test_edited_sidecars_must_match_the_render(self):
        clip = self.root / "with-sidecars.mp4"
        shutil.copyfile(self.good, clip)
        clip.with_suffix(".srt").write_text("1\n00:00:00,100 --> 00:00:01,400\nأهلاً ClipOps\n\n", encoding="utf8")
        clip.with_suffix(".vtt").write_text("WEBVTT\n\n00:00:00.100 --> 00:00:01.400\nأهلاً ClipOps\n", encoding="utf8")
        self.assertTrue(self.inspect(clip, require_sidecars=True)["checks"]["editable_sidecars_match"])
        clip.with_suffix(".srt").write_text("outdated captions", encoding="utf8")
        report = self.inspect(clip, require_sidecars=True)
        self.assertFalse(report["checks"]["editable_sidecars_match"])
        self.assertFalse(report["passed"])

    def test_frozen_black_and_silent_are_independently_flagged(self):
        black = self.root / "black.mp4"
        make_video(black, video="color=black:s=180x320:r=15", audio="anullsrc=r=48000:cl=mono")
        result = self.inspect(black)
        self.assertTrue(result["checks"]["full_decode"])
        for name in ("no_black_run", "no_freeze_2s", "audible_signal"):
            self.assertFalse(result["checks"][name])
        self.assertFalse(result["passed"])
        self.assertEqual(result["evidence"]["freeze_starts_s"], [0.])

    def test_offset_sample_peaks_and_missing_audio(self):
        offset = self.root / "late.mp4"
        make_video(offset, audio="aevalsrc=1.2*sin(2*PI*500*t):s=48000", audio_offset=0.5)
        result = self.inspect(offset)
        self.assertGreater(result["evidence"]["av_start_delta_s"], .4)
        self.assertFalse(result["checks"]["av_start_alignment"])
        self.assertFalse(result["checks"]["true_peak_headroom"])
        silent = self.root / "video-only.mp4"
        make_video(silent, audio=None)
        self.assertFalse(qc.validate_source(silent)["has_audio"])
        self.assertFalse(self.inspect(silent)["checks"]["aac_audio"])

    def test_rotation_adjusts_display_dimensions(self):
        rotated = self.root / "rotated.mp4"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-display_rotation", "90", "-i",
                        str(self.good), "-c", "copy", str(rotated)], check=True, timeout=30)
        source = qc.validate_source(rotated)
        self.assertEqual(source["coded_dimensions"], [180, 320])
        self.assertEqual(source["dimensions"], [320, 180])
        self.assertFalse(self.inspect(rotated, dimensions=[320, 180])["checks"]["export_dimensions"])


class ApprovalIntegrityTests(unittest.TestCase):
    def test_unclaimed_transport_cannot_send_even_with_environment_opt_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "local.mp4"
            media.write_bytes(b"test bytes")
            job = {"id": "unclaimed", "platform": "youtube", "file": str(media)}
            with patch.dict(clipops.os.environ, CLIPOPS_ALLOW_PUBLISH="1"), \
                    patch.object(clipops.urllib_request, "urlopen") as network:
                with self.assertRaisesRegex(ValueError, "claimed dispatch"):
                    clipops.postiz_publish(job, "inert-test")
                network.assert_not_called()

    def test_byte_replacement_after_approval_is_rejected_before_transport(self):
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "local.mp4"
            media.write_bytes(b"first synthetic opaque fixture")
            db = str(Path(tmp) / "queue.db")
            with patch.object(clipops, "media_info"):
                job = clipops.add_job(db, str(media), "youtube", "test", "test", "test", "2099-01-15T12:00:00Z")
            clipops.approve_job(db, job["id"], rights=True)
            media.write_bytes(b"replacement opaque fixture")
            with patch.dict(clipops.os.environ, CLIPOPS_ALLOW_PUBLISH="1", POSTIZ_API_KEY="inert-test"), \
                    patch.object(clipops, "postiz_publish") as outbound:
                with self.assertRaisesRegex(ValueError, "changed after approval"):
                    clipops.dispatch(db, job["id"], live=True)
                outbound.assert_not_called()
            self.assertEqual(clipops.list_jobs(db)[0]["status"], "approved")

    def test_existing_unbound_approval_requires_reapproval_after_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "old.sqlite3")
            old_schema = clipops.SCHEMA.replace(", approved_sha256 TEXT", "")
            with closing(sqlite3.connect(db)) as con:
                con.execute(old_schema)
                con.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                            ("previous", "old.mp4", "youtube", "fake", "title", "caption",
                             "2099-01-01T00:00:00Z", "approved", 1, None, "2026-11-19T00:00:00Z"))
                con.commit()
            row = clipops.list_jobs(db)[0]
            self.assertEqual(row["status"], "draft")
            self.assertEqual(row["rights_confirmed"], 0)
            self.assertIsNone(row["approved_sha256"])
