"""Encoder-selection regression tests: probe, order, metadata and CPU fallback."""
import shutil
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pilot_edit as edit


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-filter_threads", "1", "-y",
                    *map(str, args)], check=True, stdout=subprocess.DEVNULL)


class EncoderSelectionTests(unittest.TestCase):
    def tearDown(self):
        edit._encoder_available.cache_clear()

    def test_cpu_mode_skips_hardware_probes(self):
        with patch.object(edit, "_encoder_available") as available:
            args, chosen, trace = edit._select_encoder("cpu")
        self.assertEqual(chosen, "libx264")
        self.assertEqual(args, edit._ENCODER_ARGS["cpu"])
        available.assert_not_called()
        self.assertEqual([entry["status"] for entry in trace], ["requested"])

    def test_forced_hardware_mode_uses_it_when_available(self):
        with patch.object(edit, "_encoder_available", return_value=True):
            args, chosen, trace = edit._select_encoder("qsv")
        self.assertEqual(chosen, "qsv")
        self.assertEqual(args, edit._ENCODER_ARGS["qsv"])
        self.assertEqual(trace[-1], {"mode": "qsv", "status": "available"})

    def test_auto_keeps_original_cpu_policy_without_opt_in(self):
        with patch.object(edit, "_encoder_available", side_effect=[False, True]) as available:
            args, chosen, trace = edit._select_encoder("auto")
        self.assertEqual(chosen, "libx264")
        self.assertEqual(args, edit._ENCODER_ARGS["cpu"])
        self.assertEqual(available.call_args_list[0].args, ("nvenc",))
        self.assertEqual(available.call_count, 1)
        self.assertEqual([entry["status"] for entry in trace],
                         ["unavailable", "fallback"])

    def test_auto_qsv_opt_in_is_explicit(self):
        with patch.dict(os.environ, {"CLIPOPS_AUTO_QSV": "1"}):
            with patch.object(edit, "_encoder_available", side_effect=[False, True]) as available:
                args, chosen, trace = edit._select_encoder("auto")
        self.assertEqual(chosen, "qsv")
        self.assertEqual(args, edit._ENCODER_ARGS["qsv"])
        self.assertEqual([c.args[0] for c in available.call_args_list],
                         ["nvenc", "qsv"])
        self.assertEqual([entry["status"] for entry in trace],
                         ["unavailable", "available"])

    def test_auto_falls_back_to_cpu_when_no_hardware(self):
        with patch.object(edit, "_encoder_available", return_value=False):
            args, chosen, trace = edit._select_encoder("auto")
        self.assertEqual(chosen, "libx264")
        self.assertEqual(args, edit._ENCODER_ARGS["cpu"])
        self.assertEqual([entry["status"] for entry in trace][-2:],
                         ["unavailable", "fallback"])

    def test_forced_hardware_unavailable_falls_back_to_cpu(self):
        with patch.object(edit, "_encoder_available", return_value=False):
            args, chosen, _ = edit._select_encoder("nvenc")
        self.assertEqual((chosen, args), ("libx264", edit._ENCODER_ARGS["cpu"]))

    def test_unknown_mode_rejected(self):
        with self.assertRaises(ValueError):
            edit._select_encoder("gpuz")

    def test_probe_uses_real_one_frame_encode(self):
        edit._encoder_available.cache_clear()
        calls = []
        def fake_run(args, **kwargs):
            calls.append((args, kwargs))
        with patch.object(edit, "_local_run", side_effect=fake_run):
            self.assertTrue(edit._encoder_available("qsv"))
        self.assertIn("h264_qsv", calls[0][0])
        self.assertEqual(calls[0][1]["timeout"], 15)

    def test_probe_outcomes_are_cached(self):
        edit._encoder_available.cache_clear()
        calls = []

        def fail_once(args, **kwargs):
            calls.append(args)
            raise RuntimeError("no device")

        with patch.object(edit, "_local_run", side_effect=fail_once):
            self.assertFalse(edit._encoder_available("nvenc"))
            self.assertFalse(edit._encoder_available("nvenc"))
        self.assertEqual(len(calls), 1)
        edit._encoder_available.cache_clear()


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg toolchain required")
class EncoderRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.root = Path(cls.tmp.name)
        cls.source = cls.root / "source.mp4"
        ffmpeg("-f", "lavfi", "-i", "testsrc2=s=320x180:r=12", "-t", "3",
               "-c:v", "libx264", "-threads", "1", "-pix_fmt", "yuv420p", cls.source)
        cls.rows = [{"start": 0, "end": 1, "text": "encoder probe"}]

    def test_cpu_render_records_encoder_metadata(self):
        result = edit.render(self.source, self.root / "cpu.mp4", 0, 1, self.rows,
                             resolution=720, encoder="cpu")
        self.assertEqual(result["encoder"], "libx264")
        self.assertEqual(result["encoder_requested"], "cpu")
        self.assertEqual(result["encoder_probes"][0]["status"], "requested")

    def test_runtime_hardware_failure_falls_back_to_cpu(self):
        real_run = edit._local_run
        attempts = []

        def flaky_run(args, **kwargs):
            if "-c:v" in args and "h264_qsv" in args:
                attempts.append("qsv")
                if len(attempts) == 1:
                    raise RuntimeError("simulated QSV device loss")
            return real_run(args, **kwargs)

        with patch.object(edit, "_encoder_available", return_value=True), \
             patch.object(edit, "_local_run", side_effect=flaky_run):
            result = edit.render(self.source, self.root / "fallback.mp4", 0, 1, self.rows,
                                 resolution=720, encoder="qsv")
        self.assertEqual(attempts, ["qsv"])
        self.assertEqual(result["encoder"], "libx264")
        self.assertEqual(result["encoder_requested"], "qsv")
        self.assertTrue((self.root / "fallback.mp4").exists())

    def test_unknown_encoder_rejected_before_render(self):
        with self.assertRaises(ValueError):
            edit.render(self.source, self.root / "bad.mp4", 0, 1, self.rows,
                        resolution=720, encoder="gpuz")


if __name__ == "__main__":
    unittest.main()
