---
name: clipops-scheduling-publishing
description: Stage, review, approve and schedule ClipOps videos through an explicit opt-in Postiz adapter.
---
# ClipOps Scheduling and Publishing

1. Confirm the channel is owned/authorized, the media rights are documented, content/hashtags and scheduling time are approved. Never infer consent to publish from a project brief alone.
2. Run `qc` on the MP4. Create a *local* draft with `queue` and a timezone-aware `--when`; no outbound traffic occurs.
3. Inspect `jobs` and have the user approve the exact job ID and rights. Then run `approve JOB_ID --rights-confirmed`.
4. Run `publish JOB_ID` without `--live` first; it returns a dry run. Only after specific confirmation, credentials and a future time, run `CLIPOPS_ALLOW_PUBLISH=1 python3 clipops.py publish JOB_ID --live` with `POSTIZ_API_KEY` set in the environment.
5. A successful API response means **submitted to Postiz**, not that it is already live. Verify calendar/queue status and link before reporting published. Network timeouts enter `needs_manual_review`; never blindly retry.
6. YouTube defaults to **unlisted**; Instagram video uses `post_type=post`; TikTok live dispatch is intentionally disabled until provider-specific settings are vetted.
7. Never share API keys, publish copyrighted clips, or bypass platform restrictions.

References: https://docs.postiz.com/public-api/introduction ; https://docs.postiz.com/public-api/posts/create ; https://docs.postiz.com/public-api/providers/youtube
