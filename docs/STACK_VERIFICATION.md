# Release-candidate provenance and local QC

Read-only review on November 19, 2026. The ClipOps worktree starts at PR #5, `aa6d38a45bbe238e7636c76e004503f07bea7b98`. Git confirmed that the PR #4 head `a00fe9ffaaae4c61e1c07a4525b2ecf71bff80a7` is its ancestor. The engineering changes belong to the local ClipOps worktree.

| Component | Evidence and handoff |
| --- | --- |
| Video and quality branches | Both PRs were open drafts. PR #5 targets the PR #4 branch. The read-only GitHub query for pull-request workflow runs returned zero runs for the #5 head. CI remains unverified. [PR #4](https://github.com/MohammedAbdelshafy/clipops-studio/pull/4) · [PR #5](https://github.com/MohammedAbdelshafy/clipops-studio/pull/5) |
| Revenue | Jarvis #151, head `cda9a4f71b31c57834558cc42c4bdbe96b67fe69`, was open and draft. GitHub returned `mergeable: true` at inspection, updating the earlier conflict report. The launch kit scopes the $49 text brief separately, makes the $149 three-clip pilot conditional on real-media QA and records $497/month as a catalog hypothesis. Buyer acceptance, checkout and deployments require separate evidence. [PR #151](https://github.com/MohammedAbdelshafy/jarvis-mbm/pull/151) · [Launch kit](https://github.com/MohammedAbdelshafy/jarvis-mbm/blob/cda9a4f71b31c57834558cc42c4bdbe96b67fe69/Sales/ClipOps/PAID_PILOT_LAUNCH.md) |
| MBM-Social | The existing ClipFactory describes an event bus spanning source intake, editing, quality review, packaging and publication. The generator consumes clip ranges, calls FFmpeg and emits an event. ClipOps can create the reviewed local media artifact. Connecting a downstream consumer requires a separate integration test and explicit owner approval. [Pipeline](https://github.com/MohammedAbdelshafy/MBM-Social/blob/bbea2fff639f5cf32c345bcb6a5ffea9e20020af/Factories/ClipFactory/PIPELINE.md) · [Generator](https://github.com/MohammedAbdelshafy/MBM-Social/blob/bbea2fff639f5cf32c345bcb6a5ffea9e20020af/Factories/ClipFactory/clip_generator.py) |
| MBM-Control | Its source-of-truth contract assigns clipping and social execution to MBM-Social. Its distribution optimizer consumes numeric signals and has defaults. Verified first-party activity is necessary before displaying performance analytics. [Ownership contract](https://github.com/MohammedAbdelshafy/MBM-Control/blob/12a28134635d0a4034ef6fe1b8353ea0d977391a/docs/control-plane/SOURCE_OF_TRUTH.md) · [Optimizer](https://github.com/MohammedAbdelshafy/MBM-Control/blob/12a28134635d0a4034ef6fe1b8353ea0d977391a/clipping-factory/MBM-Social/mbm_social/distribution_optimizer.py) |
| Distribution | Pilot approvals enable local export. Legacy Postiz payloads and approval failures have synthetic or mocked tests. YouTube defaults to unlisted. Instagram prepares a single-video post. TikTok dispatch is disabled. Live service authentication, platform behavior, Facebook and LinkedIn delivery, published URLs and analytics are unverified. The CSV fallback is local. [Existing workflow](../VIDEO_WORKFLOW.md) · [Manual distribution](LAUNCH_CHANNEL_FALLBACKS.md) |

## Pilot quality gate

`pilot_qc.validate_source` opens a regular file, checks its signature and container, then probes its stream properties using file-only protocol and demuxer allowlists. Pilot input supports self-contained MP4, MOV, MKV and WebM, an 8 GiB maximum and a three-hour maximum. Videos can have a single soundless picture track for inspection. Narrated exports require an audible audio track. FFprobe has a 40-second timeout, 32-stream cap, finite dimensions and duration checks. Card art, transport streams, playlists and arbitrary display rotation require preparation outside this workflow.

`inspect_export` decodes the full export with FFmpeg's fatal error options. The per-clip report records checks, measurements and the outstanding human review. An unpassed check blocks approval in the pilot. The older `clipops.py qc` remains the basic compatibility check for the older vertical-clip and silent-card workflow. The release decision uses the pilot report.

| Automated check | Decision and evidence |
| --- | --- |
| Delivery picture | Match exact requested dimensions, upright orientation, square pixels, H.264, YUV 4:2:0, finite frame rate, MP4, one video and one AAC track. Decode all frames and reconcile the count to the MP4 header. |
| Timing | Compare expected clip length and A/V start and end timestamps within the greater of 0.10 seconds or two frames. Check decoded PCM sample duration against the audio stream. A human listens for speech drift and lip sync. |
| Audio | Require 44.1 or 48 kHz, mono/stereo, a measured peak above −60 dBTP and headroom at or below −0.1 dBTP. Record integrated LUFS and true peak. A true-peak violation warrants a listening pass. Previously distorted dialogue can remain below the peak threshold. |
| Black and freeze detection | Record near-black intervals with a 98% picture threshold. Hold continuous intervals at or above 0.30 s, and freezes at or above 2 s. The measurement uses a downsampled frame for every decoded frame. Intentional fades, held artwork, face occlusion and motion behind captions require context from an editor. |
| Captions | Require positive, ordered, nonoverlapping clip-relative cues within the requested interval, and line widths within the supplied layout budget. Two lines are the default. A third line requires measured width and a measured block height inside a 22%-of-frame-height safe area. When independently supplied cues lack pixel metrics, a 48-column limit catches gross overflow and the report gives the measured count. A human verifies timing against speech, contrast, glyph shaping and phone readability. |
| Fidelity | Record probed source and export dimensions, duration bound and whether source pixel count is lower. A 4K output must have supporting source dimensions. Cropping, compression, faces, logos, overlays and color are verified against the source by an editor. |
| Duplicates | The batch compares a SHA-256 fingerprint over decoded, downsized grayscale frames and mono PCM. This catches identical decoded samples even after container metadata changes. The ranker and batch also screen ranges and similar transcript text. Editorial review resolves similar storytelling across different takes. |

The published FFmpeg filter specification and the installed FFmpeg filter and demuxer help were checked while implementing the measurements. [Filters](https://ffmpeg.org/ffmpeg-filters.html) · [FFprobe](https://ffmpeg.org/ffprobe.html) · [Formats](https://ffmpeg.org/ffmpeg-formats.html)

## Dependency advisory check

This runner uses Debian 13 (trixie). The table compares the installed Debian *source* versions from `dpkg-query` with the trixie releases in the official Security Tracker data, retrieved November 19, 2026. Comparisons used `dpkg --compare-versions`, respecting the Debian epoch and distribution backports. The retrieved JSON had SHA-256 `74074d861fc1ac06e52ee2b50d3d950effbe95e1fe6700e2dac071ef0743cd52`. [Debian tracker data](https://security-tracker.debian.org/tracker/data/json)

| Source package | Installed version | Open / undetermined trixie records | Resolved records requiring a newer version |
| --- | --- | ---: | ---: |
| ffmpeg (including libavcodec, libavformat and libavfilter) | 7:7.1.5-0+deb13u1 | 128 / 1 | 0 |
| libass | 1:0.17.3-1+deb13u1 | 1 / 0 | 0 |
| freetype | 2.13.3+dfsg-1+deb13u1 | 1 / 0 | 0 |
| harfbuzz | 10.2.0-1+deb13u1 | 0 / 0 | 0 |
| fribidi | 1.0.16-1 | 0 / 0 | 0 |
| x264 | 2:0.164.3108+git31e19f9-2 | 1 / 0 | 0 |
| dav1d | 1.5.1-1 | 0 / 0 | 0 |
| libvpx | 1.15.0-2.1+deb13u1 | 0 / 0 | 0 |

These counts refer to complete source packages. Applicability to the selected formats, codecs, fonts and linked components still requires triage. This audit covers the eight named Debian packages. It excludes kernel, browser, other libraries, optional Python wheels and model supply chains. The exposure decision remains **NO-GO for public or untrusted uploads**. Recheck the tracker on the intended workstation before accepting third-party footage. [FFmpeg advisories](https://security-tracker.debian.org/tracker/source-package/ffmpeg) · [libass advisories](https://security-tracker.debian.org/tracker/source-package/libass)

## Approval integrity and focused regression

For existing scheduling databases, the first open migrates the table and returns prior unbound approvals to draft for fresh review. A new approval stores the SHA-256 of the media bytes. Live dispatch checks that digest before claiming the job and the transport checks the exact payload before transmitting. The upload size cap is enforced before and during the read. Authorization headers use urllib's origin-request-only header store. The pilot exposes local export and has no publication endpoint.

```bash
python3 -m unittest -v test_pilot_qc test_clipops test_export_schedule
```

The focused run passed 28 tests, including ten new tests for corrupt and mislabeled input, limits, positive full-decode evidence, silent/black/frozen footage, out-of-range timing and caption width, true-peak excess, stream drift, duplicate normalized media, rotation, queue migration and byte replacement after approval. The scheduling transport tests use mocks.
