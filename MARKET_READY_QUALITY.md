# ClipOps Studio — Release & Customer Delivery QA

**Status:** PR review only. No public posting or customer claims until the gates are complete.

## Why this check exists
Commercial content editing is judged on storytelling and delivery, not simply whether an MP4 file exists. External clipping products already provide inexpensive automatic cuts and captions. ClipOps must be a reviewed **service** with clear output acceptance, not a claim of guaranteed virality or better AI.

## Technical gate (automated)
The pending `clipops.py` change invokes `qc_media(job["file"])` on the **live** publishing path before claiming a job or sending anything to Postiz.

Mandatory existing `qc_media` checks:
- Valid MP4 file with sufficient bytes
- H.264 video codec
- Portrait dimensions (minimum 180×320)
- Duration between 0.2 and 180 seconds

**Important:** These are minimum machine checks, NOT customer acceptance. A 180×320 valid technical file is not automatically an appropriate client-quality deliverable. Draft scheduling still requires explicit rights confirmation, a future scheduled time, runtime opt-in, and API credentials. Unsupported platform settings remain blocked.

## Human release acceptance checklist (each clip)
- Source material: owned/expressly licensed by client; permission recorded
- Correct start/end: no mid-sentence hook, truncated key claim, accidental scene swap, or unrelated B-roll
- Fact integrity: spoken/source quotes, product details and claims are verified against provided source
- Captions: complete, accurately timed, readable over mobile safe zones and in the source language
- Framing: subject/action centered, no cut-off face, logo or essential on-screen text
- Audio: clean enough for the requested channel; silence/missing voice is never accepted by default
- Brand: correct names, colors, fonts, CTA and any agreed disclaimers; no unsupported metrics
- Output: target resolution/framerate/channel as stated in the customer scope (9:16 alone isn't enough)
- Privacy: no identifiable third-party details without an authorized purpose; preserve client confidentiality
- Approval: named customer/editor reviewer signed off on exact file and publication destination
- Delivery: actual MP4, source timestamps, captions, revision notes and delivery receipt verified

A failure requires a revised file and a new review; do not treat synthetic smoke renders as customer proof.

## Safe local checks
```bash
python -m unittest -v test_clipops.py test_batch_images.py
python clipops.py qc path/to/reviewed-clip.mp4
# Human additionally checks the MP4 and accompanying rights/approval record
```

## Known verification gaps
- Existing video MVP is draft PR #4; deployment and real authorized customer footage not demonstrated.
- Stacked CI PR #5 has release gate and test coverage but has not run through a clean GitHub runner at this point.
- True animated caption quality, Arabic RTL, dubbing and Postiz account-specific posting are not verified.
- No unrestricted automatic publishing, guaranteed views or fully automated customer editing claimed.
- Existing docs: https://github.com/MohammedAbdelshafy/clipops-studio/blob/feat/clipops-video-mvp-20261112/VIDEO_WORKFLOW.md
- Official FFmpeg reference: https://ffmpeg.org/ffmpeg-filters.html
