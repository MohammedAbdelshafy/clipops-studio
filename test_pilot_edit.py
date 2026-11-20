"""Real FFmpeg integration and editorial-timing regression tests for pilot presets."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import pilot_edit as edit
from pilot_qc import validate_source


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-filter_threads", "1", "-y",
                    *map(str, args)], check=True, stdout=subprocess.DEVNULL)


class CaptionTests(unittest.TestCase):
    def captions(self, rows, ranges, style="podcast"):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = edit.STYLES[style]
            cues = edit._caption_files(root, rows, ranges, profile, "shorts", (720, 1280),
                                       edit._brand(None, profile))
            return cues, (root / "captions.ass").read_text(), (root / "captions.vtt").read_text()

    def test_genuine_word_timings_mixed_script_and_clipped_boundaries(self):
        rows = [{"start": 10, "end": 12, "text": "ليه RGB مهم؟",
                 "words": [{"start": 10, "end": 10.45, "word": "ليه"},
                           {"start": 10.6, "end": 11, "word": "RGB"},
                           {"start": 11.4, "end": 12, "word": "مهم؟"}]}]
        cues, ass, vtt = self.captions(rows, [(10.3, 11.9)])
        self.assertEqual([c["timing"] for c in cues], ["word-highlight"])
        self.assertEqual((cues[0]["start"], cues[0]["end"]), (0, 1.6))
        self.assertIn("0:00:00.30,0:00:00.70", ass)
        self.assertIn("00:00:00.000 --> 00:00:01.600", vtt)
        self.assertIn("ليه RGB مهم؟", vtt)
        self.assertLessEqual(max(cues[0]["line_widths"]), cues[0]["max_width"])

    def test_caption_edit_discards_stale_word_animation_and_escapes_markup(self):
        rows = [{"start": 2, "end": 3, "text": "Edited <b> a {tag}",
                 "words": [{"start": 2, "end": 3, "word": "Original"}]}]
        cues, ass, vtt = self.captions(rows, [(1, 3)])
        self.assertEqual(cues[0]["timing"], "phrase")
        self.assertIn("&lt;b&gt;", vtt)
        self.assertIn(r"\{tag\}", ass)
        self.assertNotIn("Original", ass)
        self.assertEqual(ass.count("Dialogue:"), 1)

    def test_reviewed_removal_remaps_sidecars_and_does_not_fill_silence(self):
        rows = [{"start": 2, "end": 3, "text": "Keep this."}, {"start": 5, "end": 6, "text": "Next phrase."}]
        cues, _, _ = self.captions(rows, [(1, 3.25), (4.75, 8)])
        self.assertEqual([(c["start"], c["end"]) for c in cues], [(1, 2), (2.5, 3.5)])
        trims = edit.suggest_trims(rows, 1, 8)
        self.assertEqual((trims[0]["start"], trims[0]["end"]), (3.25, 4.75))
        with self.assertRaises(ValueError):
            edit._keep_ranges(1, 8, [(2, 5), (4, 6)])

    def test_caption_overflow_refuses_unreadable_text(self):
        with self.assertRaisesRegex(ValueError, "safe area"):
            self.captions([{"start": 0, "end": 2, "text": "x" * 512}], [(0, 2)])

    def test_safe_speaker_fallback_and_crosstalk(self):
        rows = [{"start": 0, "end": 2, "speaker": "guest"}, {"start": 1, "end": 3, "speaker": "host"}]
        self.assertEqual(edit._speaker_points(rows, 0, 3, {"host": .2, "guest": .8}), [])
        self.assertEqual(edit._speaker_points(rows, 0, 3, {}), [])
        with self.assertRaises(ValueError):
            edit._anchors({"guest": float("nan")})
        with self.assertRaises(ValueError):
            edit._brand({"logo": "any.png"}, edit.STYLES["fashion"])


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg toolchain required")
class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.root = Path(cls.tmp.name)
        cls.source = cls.root / "test.mp4"
        ffmpeg("-f", "lavfi", "-i", "testsrc2=s=320x180:r=12", "-f", "lavfi", "-i",
               "sine=frequency=432:sample_rate=48000", "-t", "3", "-c:v", "libx264",
               "-threads", "1", "-pix_fmt", "yuv420p", "-c:a", "aac", cls.source)
        cls.rows = [{"start": 0, "end": .75, "text": "Warm light", "speaker": "A"},
                    {"start": 1.2, "end": 2.8, "text": "شكل الضوء", "speaker": "B"}]

    def test_cutaway_logo_two_person_crop_cleanup_and_sidecars(self):
        from PIL import Image
        logo = self.root / "logo.png"
        Image.new("RGBA", (60, 30), (225, 65, 138, 180)).save(logo)
        result = edit.render(self.source, self.root / "layout.mp4", .25, 2.5, self.rows,
                             "egyptian", "reels", resolution=720, framing="split",
                             speaker_positions={"A": .23, "B": .75}, cleanup=True, push_in=True,
                             remove_ranges=[(.85, 1.1)],
                             cutaways=[{"path": self.source, "at": .3, "until": .75, "rights_confirmed": True}],
                             brand={"logo": logo, "rights_confirmed": True})
        info = validate_source(result["file"])
        self.assertEqual(info["dimensions"], [720, 1280])
        self.assertEqual(result["expected_duration"], 2)
        self.assertAlmostEqual(info["duration"], 2, delta=.09)
        self.assertEqual(result["framing"], "split")
        self.assertEqual(result["cutaway_count"], 1)
        self.assertTrue(info["has_audio"])
        text = Path(result["srt"]).read_text()
        self.assertIn("00:00:00,700 --> 00:00:02,000", text)
        self.assertIn("شكل الضوء", text)

    def test_rejected_4k_and_unlicensed_asset_leave_no_output(self):
        out = self.root / "bad.mp4"
        with self.assertRaisesRegex(ValueError, "4K"):
            edit.render(self.source, out, 0, 1, self.rows, resolution=2160)
        with self.assertRaisesRegex(ValueError, "rights"):
            edit.render(self.source, out, 0, 1, self.rows, resolution=720,
                        cutaways=[{"at": 0, "until": .5, "path": self.source}])
        self.assertFalse(out.exists())
        self.assertFalse(out.with_suffix(".vtt").exists())
        self.assertFalse(list(self.root.glob(".clipops-render-*")))

    def test_fractional_jump_cut_and_local_accent_pass_full_decode(self):
        from pilot_qc import inspect_export
        accent = self.root / "cue.wav"
        ffmpeg("-f", "lavfi", "-i", "sine=frequency=660:sample_rate=48000", "-t", "0.18", accent)
        out = self.root / "edit-clock.mp4"
        result = edit.render(self.source, out, .11, 2.73, self.rows, resolution=720, encoder="cpu",
                             remove_ranges=[(.83, 1.13)],
                             sound_accents=[{"path": accent, "at": .28, "rights_confirmed": True}])
        self.assertEqual(result["sound_accent_count"], 1)
        quality = inspect_export(out, result["expected_duration"], result["dimensions"], result["captions"],
                                 source_info=validate_source(self.source), require_sidecars=True)
        self.assertTrue(quality["passed"], quality)

    def test_uhd_supported_source_exports_landscape_at_native_resolution(self):
        src = self.root / "uhd.mp4"
        ffmpeg("-f", "lavfi", "-i", "testsrc2=s=3840x2160:r=8", "-t", "0.375",
               "-frames:v", "3", "-c:v", "libx264", "-threads", "1", "-preset", "ultrafast",
               "-pix_fmt", "yuv420p", src)
        out = self.root / "native.mp4"
        result = edit.render(src, out, 0, .375, [], "minimal", "landscape", resolution=2160)
        self.assertEqual(validate_source(out)["dimensions"], [3840, 2160])
        self.assertFalse(result["upscaled"])

    def test_interrupted_render_preserves_existing_output_and_sidecars(self):
        out = self.root / "preserved.mp4"
        out.write_bytes(b"previous")
        out.with_suffix(".srt").write_text("previous")
        with patch.object(edit, "_local_run", side_effect=RuntimeError("cancelled ffmpeg")):
            with self.assertRaisesRegex(RuntimeError, "cancelled"):
                edit.render(self.source, out, 0, 1, [], resolution=720)
        self.assertEqual(out.read_bytes(), b"previous")
        self.assertEqual(out.with_suffix(".srt").read_text(), "previous")
        self.assertFalse(list(self.root.glob(".clipops-render-*")))


if __name__ == "__main__":
    unittest.main()
