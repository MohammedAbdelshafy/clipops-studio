#!/usr/bin/env python3
"""Tests for the Gemini Batch overnight image client (clipops-studio).

Hermetic: no network, no API key. HTTP is mocked with unittest.mock.
Run:  python3 -m unittest test_batch_images -v   (from clipops-studio/)
"""
import json
import os
import sys
import unittest
from contextlib import contextmanager
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import batch_images as bi


@contextmanager
def _no_keys():
    saved = {k: os.environ.pop(k, None)
             for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY")}
    try:
        with patch.object(bi, "_connector_probe_cache", False):
            yield
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


def _mock_response(payload):
    if isinstance(payload, dict):
        payload = json.dumps(payload).encode("utf-8")
    elif isinstance(payload, str):
        payload = payload.encode("utf-8")
    m = MagicMock()
    m.read.return_value = payload
    m.__enter__.return_value = m
    m.__exit__.return_value = False
    return m


class TestCostMath(unittest.TestCase):
    def test_worked_example_batch_2k_defaults(self):
        # Source's worked example: Batch 2K with default tokens = $0.0732/image
        out = bi.estimate_cost(1, "2K")
        self.assertAlmostEqual(out["per_image_usd"], 0.0732, places=4)
        self.assertAlmostEqual(out["total_usd"], 0.0732, places=4)

    def test_ten_images(self):
        out = bi.estimate_cost(10, "2K")
        self.assertAlmostEqual(out["total_usd"], 0.732, places=3)

    def test_1k_same_rate(self):
        out = bi.estimate_cost(1, "1K")
        self.assertAlmostEqual(out["per_image_usd"], 0.0732, places=4)

    def test_4k_pricing_unverified_refuses(self):
        with self.assertRaises(ValueError):
            bi.estimate_cost(1, "4K")


class TestJsonlShape(unittest.TestCase):
    def test_line_matches_verified_schema(self):
        line = bi.build_line("sku-00001", "a red sneaker on white", "2K", "4:5")
        self.assertEqual(line, {
            "key": "sku-00001",
            "request": {
                "contents": [{"parts": [{"text": "a red sneaker on white"}]}],
                "generation_config": {
                    "responseModalities": ["TEXT", "IMAGE"],
                    "imageConfig": {"imageSize": "2K", "aspectRatio": "4:5"},
                },
            },
        })

    def test_invalid_size_rejected(self):
        with self.assertRaises(ValueError):
            bi.build_line("sku-00001", "x", size="8K")

    def test_build_jsonl_keys_and_roundtrip(self):
        path = bi.build_jsonl(["first prompt", "second prompt"], size="1K")
        try:
            with open(path, encoding="utf-8") as fh:
                lines = [json.loads(l) for l in fh if l.strip()]
        finally:
            os.unlink(path)
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]["key"], "sku-00001")
        self.assertEqual(lines[1]["key"], "sku-00002")
        self.assertEqual(lines[0]["request"]["generation_config"]
                         ["imageConfig"]["imageSize"], "1K")
        self.assertIn("first prompt",
                      lines[0]["request"]["contents"][0]["parts"][0]["text"])


class TestParseResults(unittest.TestCase):
    def test_per_key_matching_with_failure(self):
        text = "\n".join([
            json.dumps({"key": "sku-00001",
                        "response": {"candidates": [{"content": {}}]}}),
            json.dumps({"key": "sku-00002",
                        "error": {"code": 8, "message": "quota"}}),
            "not json at all",
            json.dumps({"response": {}}),
        ])
        out = bi.parse_results_jsonl(text)
        self.assertTrue(out["sku-00001"]["ok"])
        self.assertFalse(out["sku-00002"]["ok"])
        self.assertEqual(out["sku-00002"]["error"]["code"], 8)
        self.assertEqual(len(out["_failed_lines"]), 2)  # bad JSON + missing key


class TestDryRun(unittest.TestCase):
    def test_dry_run_zero_network(self):
        def boom(req, timeout=None):
            raise AssertionError("network touched during dry-run")

        with _no_keys(), patch("urllib.request.urlopen", boom):
            client = bi.GeminiBatchClient()
            self.assertTrue(client.dry_run)
            plan = client.run_overnight(["a cat astronaut"], "test-job")

        self.assertTrue(plan["dry_run"])
        self.assertEqual(plan["blocked_on"], "gemini_credential")
        self.assertEqual(plan["num_requests"], 1)
        self.assertAlmostEqual(plan["per_image_usd"], 0.0732, places=4)
        self.assertTrue(os.path.exists(plan["jsonl_path"]))
        os.unlink(plan["jsonl_path"])  # plan built the file offline
        self.assertEqual(plan["limits"]["target_turnaround_h"], 24)
        self.assertEqual(plan["limits"]["expires_h"], 48)

    def test_alias_key_accepted(self):
        with _no_keys():
            os.environ["GOOGLE_API_KEY"] = "AIza-alias"
            try:
                client = bi.GeminiBatchClient()
            finally:
                os.environ.pop("GOOGLE_API_KEY", None)
        self.assertFalse(client.dry_run)


class TestTransport(unittest.TestCase):
    def _client(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "AIza-test"}):
            return bi.GeminiBatchClient()

    def test_create_batch_body_and_auth(self):
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["auth"] = req.get_header("X-goog-api-key")
            captured["body"] = json.loads(req.data.decode())
            return _mock_response({"name": "batches/abc123", "done": False})

        client = self._client()
        with patch("urllib.request.urlopen", fake_urlopen), \
                patch.object(bi.FilesTransport, "upload_jsonl",
                             return_value="files/jsonl-1"):
            path = bi.build_jsonl(["p1", "p2"])
            try:
                op = client.create_batch(path, "nightly")
            finally:
                os.unlink(path)

        self.assertEqual(
            captured["url"],
            "https://generativelanguage.googleapis.com/v1beta/"
            "models/gemini-3-pro-image:batchGenerateContent")
        self.assertEqual(captured["auth"], "AIza-test")
        self.assertEqual(captured["body"]["displayName"], "nightly")
        self.assertEqual(captured["body"]["inputConfig"]["fileName"],
                         "files/jsonl-1")
        self.assertEqual(op["name"], "batches/abc123")
        self.assertIn("estimated_cost_usd", op)

    def test_poll_pending_then_succeeded(self):
        states = [
            {"name": "batches/abc123", "done": False},
            {"name": "batches/abc123", "done": True,
             "response": {"state": "BATCH_STATE_SUCCEEDED",
                          "output": {"inlinedResponses":
                                     {"inlinedResponses": []}}}},
        ]

        def fake_urlopen(req, timeout=None):
            return _mock_response(states.pop(0))

        client = self._client()
        with patch("urllib.request.urlopen", fake_urlopen), \
                patch("time.sleep", lambda s: None):
            op = client.wait("batches/abc123", timeout_s=60, poll_s=0)
        self.assertTrue(op["done"])

    def test_expired_raises(self):
        op = {"name": "batches/old", "done": True,
              "error": {"code": 4, "message": "batch EXPIRED after 48h"}}

        def fake_urlopen(req, timeout=None):
            return _mock_response(op)

        client = self._client()
        with patch("urllib.request.urlopen", fake_urlopen), \
                patch("time.sleep", lambda s: None):
            with self.assertRaises(bi.BatchExpired):
                client.wait("batches/old", timeout_s=60, poll_s=0)

    def test_download_inlined_results(self):
        op = {"done": True, "response": {"output": {"inlinedResponses": {
            "inlinedResponses": [
                {"metadata": {"key": "sku-00001"},
                 "response": {"candidates": [{}]}},
                {"metadata": {"key": "sku-00002"},
                 "error": {"code": 8, "message": "quota"}},
            ]}}}}
        client = self._client()
        out = client.download_results(op)
        self.assertTrue(out["sku-00001"]["ok"])
        self.assertFalse(out["sku-00002"]["ok"])


if __name__ == "__main__":
    unittest.main()
