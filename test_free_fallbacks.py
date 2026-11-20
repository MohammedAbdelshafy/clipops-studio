"""Regression checks for no-cost, user-initiated fallback routes."""
import unittest
from unittest.mock import patch
from free_fallbacks import GROUPS, free_routes


class FreeFallbackTests(unittest.TestCase):
    def test_workflows_and_manual_external_boundaries(self):
        result = free_routes(local_model=False)
        rows = result["routes"]
        self.assertEqual(result["network_requests"], 0)
        self.assertEqual({r["workflow"] for r in rows}, set(GROUPS))
        self.assertEqual(len({r["id"] for r in rows}), len(rows))
        self.assertTrue(all(not r["automatic"] for r in rows))
        self.assertTrue(all(r["url"] is None or r["url"].startswith("https://") for r in rows))
        self.assertTrue(all(r["requires_approval"] for r in rows if r["url"]))

    def test_local_capabilities_without_network(self):
        with patch("free_fallbacks.shutil.which", side_effect=lambda x: "/mock/" + x if x in ("ffmpeg", "ffprobe") else None):
            rows = {x["id"]: x for x in free_routes(local_model=True)["routes"]}
        self.assertTrue(rows["ffmpeg"]["available_here"])
        self.assertTrue(rows["faster_whisper"]["available_here"])
        self.assertTrue(rows["import_transcript"]["available_here"])
        self.assertFalse(rows["whisper_cpp"]["available_here"])

    def test_ffprobe_missing_does_not_block_existing_exports(self):
        with patch("free_fallbacks.shutil.which", side_effect=lambda x: "/mock" if x == "ffmpeg" else None):
            rows = {x["id"]: x for x in free_routes()["routes"]}
        self.assertFalse(rows["ffmpeg"]["available_here"])
        self.assertTrue(rows["clipops_export"]["available_here"])

    def test_unknown_workflow_rejected(self):
        with self.assertRaises(ValueError):
            free_routes(category="unapproved_cloud_service")
        self.assertEqual({x["workflow"] for x in free_routes(category="speech")["routes"]}, {"speech"})


if __name__ == "__main__":
    unittest.main()
