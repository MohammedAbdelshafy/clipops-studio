import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import export_schedule
from clipops import add_job, approve_job


class ExportScheduleTests(unittest.TestCase):
    def test_only_approved_jobs_export(self):
        with tempfile.TemporaryDirectory() as td:
            file = Path(td) / "a.mp4"
            file.write_bytes(b"test")
            db = str(Path(td) / "queue.db")
            out = str(Path(td) / "out.csv")
            dt = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
            with patch("clipops.media_info", return_value={"streams": [{"codec_type": "video"}]}):
                a = add_job(db, str(file), "youtube", "manual", "Approved title", "Approved caption", dt)
                add_job(db, str(file), "instagram", "manual", "Draft title", "Draft caption", dt)
            approve_job(db, a["id"], rights=True)
            result = export_schedule.export_schedule(db, out)
            with open(out, encoding="utf8", newline="") as fp:
                rows = list(csv.DictReader(fp))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["title"], "Approved title")
            self.assertEqual(rows[0]["timezone"], "Africa/Cairo")
            self.assertTrue(rows[0]["scheduled_local"].endswith("+0200"))
            self.assertEqual(rows[0]["editorial_review_required"], "yes")
            self.assertEqual(result["network_requests"], 0)

    def test_formula_injection_sanitized(self):
        for text in ("=SUM(A1)", " +CMD", "-2+1", "@SUM(1)", "fine"):
            self.assertEqual(export_schedule.spreadsheet_safe(text).startswith("'"), text != "fine")

    def test_absent_database_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(FileNotFoundError):
                export_schedule.export_schedule(td + "/missing.sqlite", td + "/out.csv")

    def test_invalid_zone_rejected(self):
        with self.assertRaises(Exception):
            export_schedule.export_schedule("/missing", "/tmp/no-out.csv", "Invalid/Zone")


if __name__ == "__main__":
    unittest.main()
