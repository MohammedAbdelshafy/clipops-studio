# ClipOps Studio — Video Workflow MVP

**Release candidate on a review branch.** Existing `batch_images.py` and `test_batch_images.py` are preserved unchanged. The new `clipops.py` is a local-first FFmpeg workflow with an optional faster-whisper transcriber and an opt-in Postiz scheduler.

## What actually ships in this branch

- **Inspect** an authorized local video with FFprobe.
- **Transcribe** to timestamped JSON using optional `faster-whisper` (CPU int8). Models may require a download on first use. Or import your own reviewed transcript JSON.
- **Make captions** in SRT/VTT and burn them into short vertical clips.
- **Suggest highlights** with a transparent keyword heuristic; a human chooses final ranges. Suggestions are **not** AI-scored virality guarantees.
- **Render vertical clips** in crop/blur layouts; no browser or Remotion required.
- **Generate text-card promos** from a JSON scene brief with FFmpeg (not text-to-video generative AI).
- **Validate output** for video encoding, short duration, dimensions and nonempty file.
- **Draft/approve/schedule** posts in a local SQLite queue, optionally submitting approved MP4 clips to the documented Postiz API. No social credentials are stored in the repository.
- **Four agent skills** in `skills/` for repeatable video generation, clipping, transcription/captions and scheduling/publishing.

## Setup

```bash
# FFmpeg + FFprobe must be on PATH. Python 3.10+.
python3 -m unittest -v test_clipops.py
python3 clipops.py --help
# Only if automatic speech recognition is required:
python3 -m pip install faster-whisper
```

## Full local workflow

```bash
python3 clipops.py inspect source.mp4
python3 clipops.py transcribe source.mp4 --out out/transcript.json --model small
# Alternative: manually create out/transcript.json with `segments: [{start,end,text}, ...]`
python3 clipops.py suggest out/transcript.json --out out/highlights.json --min 15 --max 45
python3 clipops.py captions out/transcript.json --out out/full.srt --words 6
# Choose a specific start/end from the reviewed highlights.json:
python3 clipops.py clip source.mp4 --start 12 --end 37 --fit blur --captions out/transcript.json --out out/clip-01.mp4
python3 clipops.py qc out/clip-01.mp4
python3 clipops.py promo examples/promo.json --out out/promo.mp4
```

The SRT/VTT file is an optional deliverable. For burning captions, use the timestamped JSON so the renderer can shift original timestamps correctly for the selected clip.

## Posting and scheduling with Postiz

Postiz is an optional downstream publishing provider; it handles the actual posting at the scheduled UTC time. **No background worker is required** for Postiz scheduling after submission. Never put tokens in command history or Git; configure `POSTIZ_API_KEY` in the runtime environment. Obtain the exact integration/channel id from your Postiz account.

```bash
# 1. Create a local draft; timezone is REQUIRED and converted to UTC.
python3 clipops.py queue out/clip-01.mp4 --db out/queue.sqlite3 \
  --platform youtube --integration "your-postiz-channel-id" \
  --title 'ClipOps example' --caption 'Approved clip description' \
  --when '2026-12-15T17:00:00+02:00'
python3 clipops.py jobs --db out/queue.sqlite3
# 2. REVIEW video, caption, channel, time, rights. Approve the returned job ID.
python3 clipops.py approve JOB_ID --db out/queue.sqlite3 --rights-confirmed
# 3. Default = dry-run: zero outbound requests.
python3 clipops.py publish JOB_ID --db out/queue.sqlite3
# 4. Explicit opt-in only, after review and a valid API key:
export POSTIZ_API_KEY='...'
CLIPOPS_ALLOW_PUBLISH=1 python3 clipops.py publish JOB_ID --db out/queue.sqlite3 --live
```

### Publisher limitations

- YouTube is submitted **unlisted** in this MVP; change visibility manually in Postiz only with explicit publication approval. (YouTube's Postiz `type` means privacy, **not** 'short'.)
- Instagram single-video Reels use Postiz `post_type: post` per its published schema. Verify connected account rules before real use.
- Facebook/LinkedIn have basic API payloads but need a real account-specific validation run.
- TikTok draft jobs may be tracked locally but live dispatch deliberately stops: its required privacy/duet/stitch settings cannot be guessed.
- Scheduling a post in Postiz is not evidence that it was published; verify post status and live URL in Postiz afterwards.
- Network errors during upload/submission leave the local job as `needs_manual_review` to prevent duplicate retries. Check Postiz before any re-queue.
- This branch has **no live authenticated publishing test**. No posts have been submitted. Only controlled unit/smoke tests are claimed.
- The code loads the MP4 into memory for upload; 300 MB maximum. Higher-volume/prod uploads need streaming, content checks, and per-channel hardening.

## Repo relationship and provenance

- `MBM-Social` remains the more elaborate 15-stage orchestration architecture. This lightweight CLI makes a smaller independently testable delivery lane; it does **not** replace MBM Social or rewrite its data stores.
- The original `clipops-studio` `batch_images.py` stays untouched. The former planned Remotion renderer is **not** represented as implemented here. The new FFmpeg text-card promo renderer is a distinct, simpler feature.
- Only use footage you own or are expressly authorized to process and publish. Approving a job requires confirming those rights.

## Official engineering references

- [FFmpeg filters (crop, scale, overlay, subtitles, drawtext)](https://ffmpeg.org/ffmpeg-filters.html)
- [FFmpeg / FFprobe documentation](https://ffmpeg.org/documentation.html)
- [faster-whisper word timestamps and VAD](https://github.com/SYSTRAN/faster-whisper/blob/master/README.md)
- [Postiz Public API](https://docs.postiz.com/public-api/introduction)
- [Postiz upload](https://docs.postiz.com/public-api/uploads/upload-file)
- [Postiz create/schedule post](https://docs.postiz.com/public-api/posts/create)
- [Postiz YouTube provider fields](https://docs.postiz.com/public-api/providers/youtube)
- [Postiz Instagram provider fields](https://docs.postiz.com/public-api/providers/instagram)

## Launch gate

Before selling fully automated posting: verify a legitimate authorized sample run with actual customer media and tokens; check captions (including Arabic right-to-left styling), vertical framing, music licences, YouTube visibility, channel connection, schedule timing, privacy/compliance and post status. Obtain explicit approval before any public posting or paid generative media API call.
