#!/usr/bin/env python3
"""Export approved ClipOps jobs for human-reviewed manual platform scheduling.

No network requests. Never marks a job submitted or changes database rows.
CSV output is an operational checklist, not an auto-publishing queue.
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

HEADERS = ("job_id", "platform", "scheduled_local", "timezone", "scheduled_utc", "title", "caption", "media_file", "rights_confirmed", "status", "editorial_review_required", "publish_result_url")


def spreadsheet_safe(value: object) -> str:
    raw = str(value if value is not None else "")
    if raw.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + raw
    return raw


def export_schedule(db: str, out: str, tz: str = "Africa/Cairo") -> dict:
    zone = ZoneInfo(tz)
    path = Path(db).expanduser().resolve(strict=True)
    output = Path(out).expanduser().resolve()
    with sqlite3.connect(path) as con:
        con.row_factory = sqlite3.Row
        jobs = list(con.execute("""SELECT id,platform,scheduled_utc,title,caption,file,rights_confirmed,status
                                 FROM jobs WHERE status='approved' AND rights_confirmed=1
                                 ORDER BY scheduled_utc,id"""))
    rows = []
    for j in jobs:
        when = datetime.fromisoformat(j["scheduled_utc"].replace("Z", "+00:00")).astimezone(zone)
        rows.append({
            "job_id": j["id"], "platform": j["platform"],
            "scheduled_local": when.strftime('%Y-%m-%d %H:%M %z'), "timezone": tz,
            "scheduled_utc": j["scheduled_utc"], "title": j["title"], "caption": j["caption"],
            "media_file": j["file"], "rights_confirmed": "yes", "status": j["status"],
            "editorial_review_required": "yes", "publish_result_url": "",
        })
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows([{key: spreadsheet_safe(row[key]) for key in HEADERS} for row in rows])
    return {"out": str(output), "eligible_jobs": len(rows), "timezone": tz, "method": "manual_review_only", "network_requests": 0}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="clipops_queue.sqlite3")
    parser.add_argument("--out", required=True)
    parser.add_argument("--timezone", default="Africa/Cairo")
    args = parser.parse_args()
    try:
        result = export_schedule(args.db, args.out, args.timezone)
    except (ValueError, OSError, sqlite3.Error, KeyError) as exc:
        parser.exit(2, f"Export failed: {exc}\n")
    print(result)


if __name__ == "__main__":
    main()
