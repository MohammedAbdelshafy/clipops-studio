# ClipOps Studio — client delivery and fallback routes

ClipOps is an independent video editing tool. Existing local functionality is FFmpeg clip extraction, vertical formatting, subtitle export/burn-in, an optional local faster-whisper transcription route, manual QA, a SQLite approval queue and an opt-in Postiz integration. This document does not imply working public account connections.

## Priority route

1. Get customer-owned source footage with written permission and an accepted creative brief. Never repurpose leaks, copyrighted music or other creators' footage without authorization.
2. Run a local sample: inspect -> transcribe (if model installed) -> suggest -> clip -> captions -> QC. Human editors check framing, context, word accuracy and subtitles.
3. Deliver an MP4 plus copy for editorial review. Keep a copy of the final approved files and scope.
4. Schedule only after the customer explicitly grants channel access and approves exact media, caption, account, date, platform settings and time zone.
5. Publishing adapter: Postiz; confirm actual authenticated connected channel before live use. Trigger only with the two explicit live gates documented in clipops.py. Check post status and public URL afterward.

## Publishing fallbacks

| Preferred | Fallback | What must be verified |
| --- | --- | --- |
| Postiz authorized channel | Metricool authorized channel | Channel identity, settings, plan, timezone, media upload; never assume Postiz ID works in Metricool |
| Metricool authorized channel | Publora authorized channel | Client ownership, allowance, provider-specific settings, request approval |
| All APIs unavailable | Manual YouTube Studio / TikTok Studio / Meta Business Suite | Secure MP4 + caption/asset handoff, owner manually schedules |
| Any scheduler cannot meet review, legal or rights gates | Download-only client delivery | No auto-post; record delivery acceptance |

Manual schedule export from this repo:
    python3 export_schedule.py --db clipops_queue.sqlite3 --out publish_handoff.csv --timezone Africa/Cairo

Only approved, rights-confirmed jobs are exported; drafts and submitted jobs are not. The CSV contains local media paths: share files separately through an authorized private delivery channel, not a public spreadsheet. The exporter makes zero network calls and never updates the queue. It spreadsheet-sanitizes user captions/titles.

## Selling responsibly

Sell a small pilot whose scope and turnaround are confirmed before payment. Deliverables: creator-supplied footage -> reviewed vertical MP4 -> caption options -> ready-to-post calendar. Do not sell automatic publication, untested transcription quality, or guaranteed viral views as working evidence. Payment routing is external and must be verified with a lawful live payment provider; test-mode Stripe is not a real checkout. No public GTA logos, leaked footage or false Rockstar affiliation.

## Release gates

- Run: python3 -m unittest -q test_clipops.py test_export_schedule.py
- QA real authorized sample, transcript accuracy, vertical framing, licensed sound, render and caption accessibility
- Confirm social OAuth, live platform requirements and one approved draft test
- Confirm customer intake, invoice and payment route
- Obtain approval to merge/deploy or initiate outbound sales; do not merge this draft automatically.
