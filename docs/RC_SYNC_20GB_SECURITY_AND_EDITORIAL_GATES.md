# ClipOps Studio — RC sync, 20 GB media intake and editorial quality gate

**Status: integration contract, NOT a verified 20 GB implementation.** Prepared 2026-11-20 as a review-only handoff. Keep existing PRs #4, #5 and #6 intact. The reported local release `5b99597` was not found on GitHub on 2026-11-20; no code from that local commit has been imported into this branch. The reported 89 tests, synthetic-hour benchmark, and Arabic WER are handoff claims pending reproducible verification.

## 0. First reconcile actual source (mandatory)

- On the machine that contains `/workspace/clipops-rc`, inspect `git status --short`, `git log -1 --oneline`, `git remote -v`, `git show --stat 5b99597`, `git branch -a`, and compare with `origin/main` and existing PR branches. Never reset or force-push.
- Preserve the exact release tree and untracked runbooks/tests/screenshots, but never commit original client video, transcripts, access tokens, machine paths, model caches, rendered private clips or credentials.
- Run local secret scanning, license/provenance scan, unit/e2e tests and output inspection before any push to this **public** repository. Release code only to a new review branch. Open a draft PR, with exact SHA and reproducible test evidence; do not merge or deploy.
- A branch consisting of this file is not the release candidate. Until that code has been pushed, project readiness is **NO-GO** for customer deployment.

## 1. Large-source-video architecture: 15–20 GB

**Local-first lane:** For single-machine editing, prefer an authorized local file reference / file picker, with read-only source and generated proxies; do not copy or upload 20 GB to the same host merely to add it to the UI. Generate a lightweight seeking proxy, waveforms and thumbnails asynchronously. Store jobs and checkpoints durably. The original must never be modified.

**Remote lane (optional; after review and approved infrastructure):** Browser-to-object-store multipart upload using short-lived, scope-limited signed requests; never buffer the entire file in Python, browser memory or reverse proxy. Evaluate Uppy AWS S3 multipart or Uppy Tus + tusd; pick ONE after inspecting the existing studio stack. For S3-compatible storage, start by testing ~64–128 MiB parts, bounded concurrency 3–4, exponential backoff+jitter, per-part checksum, persisted upload ID/part ETags and idempotent completion. Ensure a resumed browser session can recover the exact completed parts; client/server reconcile must reject conflicting offsets/parts. Use a per-user/project quota and server-side ownership checks at every operation.

- **Session lifecycle:** initiated -> uploading -> verifying -> quarantined -> probed -> proxying -> reviewable; distinct expired/failed/cancelled states. Surface progress, speed, ETA only if measured, retries, pause/resume and explicit cancel.
- **Security:** authenticated uploads, CSRF defense as applicable, no trust in filename/content-type, allowlist media types plus `ffprobe` validation, file-signature checks, length/quotas, encrypted private storage, random object keys, no directory traversal or symlink escapes, reject ZIP/container bombs, least-privilege signed URL and expiry, no secret exposure in logs or URLs. Process untrusted media with resource-limited FFmpeg workers (CPU/RAM/disk/time); never invoke shell interpolation with filenames. Restrict local server bind to loopback until independently authorized/authenticated.
- **Integrity/operations:** stream hashes with constant memory; atomic finalize, duplicate detection, orphan cleanup, expiry of abandoned uploads, retention and deletion rules, source ownership log and audit trail. Ensure disk headroom for upload + proxy + render + temporary files, plus pause/resume after power loss. Avoid large data in Git/LFS unless deliberately approved; media belongs in private storage.
- **Acceptance tests:** synthetic sparse 20 GiB fixture and one genuine authorized ~15–20 GB file; resume after network drop, tab closure, server process restart, out-of-order/replayed/missing parts, checksum mismatch, quota exhaustion, invalid media, concurrent imports, cleanup and cancellation. Measure transfer success, stable process memory, duplicate prevention, speed for the user's real link, proxy time, browser responsiveness, processing throughput and free disk. Do NOT mark 20 GB supported based only on mock/sparse tests.
- **Separate publishing adapter:** The PR #4 documented Postiz upload currently loads MP4 into memory and caps it at 300 MB. Large *source* ingestion must not reuse that path. Final short-form exports require per-channel size/duration validation and streaming or signed staging only when the destination explicitly supports it.

Reference: https://docs.aws.amazon.com/AmazonS3/latest/userguide/qfacts.html ; https://uppy.io/docs/aws-s3/ ; https://uppy.io/docs/tus/ ; https://tus.io/protocols/resumable-upload ; https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html

## 2. Editorial quality over automatic cuts

Preserve existing transcript search, captions, manually reviewed pause/filler cuts, framing, batch render and approval-gated MP4/SRT/VTT workflow. Add improvements one validated layer at a time, each with before/after previews, rollback, tests and inspectable edits:

1. **Story:** ranked candidate moments with source citations, semantic boundaries, complete thoughts, 0–3s hook review, one clear payoff, fact/context preservation, transparent explanation of ranking; no “guaranteed viral” claims.
2. **Rhythm:** speech-aware jump cuts with configurable handles, avoid unnatural cuts/breath loss, separate editorial pause removal from transcription VAD, punch-ins and zoom keyframes used intentionally, transition restraint.
3. **Frame:** scene-change detection, active speaker selection with tracking confidence, 9:16/1:1/16:9 variants, multi-speaker split screen, picture-in-picture, keyframed crop and safe-zone checks for captions/logos.
4. **Captions:** accurate word alignment, editable line breaks, style presets, keyword emphasis, language/script selection, Arabic RTL/BiDi/shaping and Egyptian/Franco bilingual quality. Recheck timing after cuts. Preserve SRT/VTT and editable project decisions.
5. **Audio:** voice denoise and loudness normalization with clipping/true-peak checks, speech/music ducking, silence and harsh cut checks; all optional/reversible, only licensed background music.
6. **Visuals:** selective relevant B-roll with source/rights attribution, titles, lower thirds, subtle motion graphics and brand kits; do not make images/quotes that imply unsupported facts.
7. **Delivery:** high-quality master plus platform-tuned exports, deterministic FFmpeg version/settings, measured QC for codec, geometry, fps, black frames, AV sync, frozen frames, captions cropping, errors and content integrity, plus a human final review.

Competitor feature benchmarks (not copying proprietary code): OpusClip text editor, B-roll, speaker framing; Crayo timeline/caption/zoom controls; Captions AI edits. Evaluate open-source WhisperX, auto-editor, and local-first autoclip/clipgen by pinned commit, license, dependencies, exploit exposure, quality and test evidence before reuse. Respect licenses; do not import third-party code by default.

**ASR blocker:** local handoff reports 60.5% word error on the best bilingual synthetic run; Egyptian Arabic and mixed-language footage must require reviewed transcripts until measured production-suitable accuracy is demonstrated. Keep originals and corrections editable.

## 3. Security and accessibility release gates

- Verify authentication and per-project ownership (IDOR), session expiry, CSRF/XSS, HTML escaping, CORS policy, local network exposure, upload trust boundaries, subprocess argument safety, arbitrary file reads/writes, symlink/path traversal, queue races/idempotency, rate limits and request size limits; protect private footage/transcripts throughout processing, logs and download.
- Pin dependencies with reproducible installs and scan important licenses and known critical vulnerabilities. Keep no secrets in Git. Publish jobs remain opt-in per exact approved target, time, rights and output hash; safe default is no outbound requests.
- Make one accessible interface for ingest -> review candidates -> text/timeline edit -> render queue -> quality review -> approved download. Keyboard navigation, focus indicators, captions, screen-reader labels, large-file progress accessible to assistive tech, explicit error/undo, mobile view and low-bandwidth mode. Prefer local desktop shortcut and loopback URL before any external hosting.
- Add regression gates covering existing 89-test claim, Linux/Windows path handling, FFmpeg availability, Arabic font availability, 60-minute realistic source, crash resume, concurrency, PII leakage, delivery approval states, video/audio artifacts.
- **Go/no-go:** require a real authorized 45–60-minute video reviewed from import through delivery, plus the separate genuine 15–20 GB ingest/recovery test, full security gates and editor sign-off. Do not equate an MP4 that passes technical FFprobe checks with professional editorial acceptance.

## 4. Review boundaries and reporting

No merge, deployment, paid APIs, client uploads, outbound messages, publishing, destructive cleanup or public release. Preserve existing branches and project history. Prioritize fixes by severity and acceptance impact, not “refactor every line” indiscriminately. Provide a concise matrix: requested behavior | files changed | tests and measured evidence | limitations | new commit/PR URL | next human sign-off. State **NOT VERIFIED** for any unrun test.

