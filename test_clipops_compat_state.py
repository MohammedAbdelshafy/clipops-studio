"""Targeted Windows state-compatibility tests for the post-shared_read code.

These complement the full suite: they exercise the exact sharing violation the
2026-11-20 fix addresses, the per-path reader/writer lock, and the real
save_json/load_json path under repeated concurrent load.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import clipops_compat as compat
import pilot


class CompatStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="clipops-compat-state-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_shared_read_retries_sharing_violation(self):
        target = self.root / "state.json"
        target.write_text('{"ok": true}', encoding="utf-8")
        real_open = open
        calls = []

        def flaky_open(path, *args, **kwargs):
            calls.append(path)
            if len(calls) < 3:
                raise PermissionError("sharing violation")
            return real_open(path, *args, **kwargs)

        with patch("builtins.open", side_effect=flaky_open):
            with compat.shared_read(target, attempts=3, delay=0) as stream:
                self.assertEqual(json.load(stream), {"ok": True})
        self.assertEqual(len(calls), 3)

    def test_shared_read_does_not_retry_missing_file(self):
        calls = []

        def missing(path, *args, **kwargs):
            calls.append(path)
            raise FileNotFoundError(path)

        with patch("builtins.open", side_effect=missing):
            with self.assertRaises(FileNotFoundError):
                with compat.shared_read(self.root / "missing.json", delay=0):
                    pass
        self.assertEqual(len(calls), 1)

    def test_replace_file_retries_windows_sharing_violation(self):
        source = self.root / "new.json"
        target = self.root / "old.json"
        source.write_text("new", encoding="utf-8")
        target.write_text("old", encoding="utf-8")
        real_replace = os.replace
        calls = []

        def flaky_replace(a, b):
            calls.append((a, b))
            if len(calls) < 3:
                raise PermissionError("file in use")
            return real_replace(a, b)

        with patch.object(compat.os, "name", "nt"), \
                patch.object(compat.os, "replace", side_effect=flaky_replace):
            compat.replace_file(source, target, delay=0)
        self.assertEqual(len(calls), 3)
        self.assertEqual(target.read_text(encoding="utf-8"), "new")

    def test_serialised_excludes_reader_and_writer(self):
        path = self.root / "shared.json"
        events = []
        barrier = threading.Barrier(2)

        def writer():
            with compat.serialised(path, timeout=5):
                events.append("writer-enter")
                barrier.wait(timeout=5)
                events.append("writer-exit")

        def reader():
            barrier.wait(timeout=5)
            with compat.serialised(path, timeout=5):
                events.append("reader-enter")
                events.append("reader-exit")

        threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
            self.assertFalse(thread.is_alive())
        self.assertEqual(events, ["writer-enter", "writer-exit", "reader-enter", "reader-exit"])

    def test_repeated_concurrent_json_state_race(self):
        path = self.root / "project.json"
        pilot.save_json(path, {"seq": 0, "clips": ["a"]})
        errors = []
        barrier = threading.Barrier(5)

        def writer():
            try:
                barrier.wait(timeout=10)
                for seq in range(1, 21):
                    pilot.save_json(path, {"seq": seq, "clips": ["a" if seq % 2 else "b"]})
            except BaseException as exc:  # surfaced below, not swallowed
                errors.append(exc)

        def reader(index):
            try:
                barrier.wait(timeout=10)
                for _ in range(20):
                    data = pilot.load_json(path, maximum=1024 * 1024)
                    if not isinstance(data.get("seq"), int) or data["clips"] not in (["a"], ["b"]):
                        raise AssertionError(f"corrupt state: {data!r}")
            except BaseException as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer)] + [
            threading.Thread(target=reader, args=(i,)) for i in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
            self.assertFalse(thread.is_alive(), "state race hung")
        self.assertEqual(errors, [], f"concurrent load/save errors: {errors!r}")
        self.assertEqual(pilot.load_json(path)["seq"], 20)

    def test_symlink_state_is_rejected(self):
        real = self.root / "real.json"
        link = self.root / "link.json"
        real.write_text('{"ok": true}', encoding="utf-8")
        try:
            link.symlink_to(real)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaises(ValueError):
            pilot.load_json(link)


if __name__ == "__main__":
    unittest.main()
