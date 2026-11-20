# ClipOps Studio — local competitive upgrade verification receipt

**Snapshot:** November 20, 2026 (local sandbox). **Source:** extracted GitHub Actions test artifact corresponding to `MohammedAbdelshafy/clipops-studio` main `e93f9d54e935475d95edfdd5f2b59e2221fdc2fe`. This is an **unpublished local build**, not merged or deployed.

## Delivery

- `clipops_creative_review.find_moments`: source-grounded English/Arabic token retrieval with intact start/end timestamps, source proof excerpts, overlap suppression and limits. This is **not** semantic, sentiment, action or multimodal retrieval and has **no virality prediction**.
- New authenticated `POST /api/projects/{id}/search-moments`, Creative review form and preview-only proposal UI; applying goes through the established editor, invalidating approvals before rerendering.
- `clipops_scene_review.scene_review`: local FFmpeg scene-change suggestions for a selected segment, scan window ≤180 seconds, hard timeout 45 seconds, one concurrent scan, local file protocol only, no shell execution, no automatic edits.
- New authenticated `GET /api/projects/{id}/{clip}/visual`, reviewer-facing scene times and warning, no cloud services.
- Existing FFmpeg H.264/AAC render, Arabic caption support, named approval gates, QA and MP4/SRT/VTT delivery left intact.
- Local optional PySceneDetect 0.7.3 pin is listed for later evaluation, but **package installation was unsuccessful here because DNS/network to pip index was blocked**. The working scene reviewer depends only on the already-installed FFmpeg.

## Checks run

- `python -m unittest discover -q`: **125 tests passed** after changes; includes existing full suite plus 8 new targeted checks (new `test_competitive_upgrades.py` and `test_studio.py` HTTP checks).
- `node --check studio/app.js`: **passed**.
- New live FFmpeg synthetic color-transition fixture: source changes red→blue at 1.5 sec; analysis of cropped source `[0.5, 2.5]` detected scene boundary **1.5 sec**.
- New source-moment search on synthetic studio recording: `biography` located one contiguous, genuine source excerpt. Its actual MP4 render completed with `pilot_edit.render` as 720 × 1280 H.264/AAC (about 15.5 sec), produced captions and passed `pilot_qc.inspect_export` including sidecars.
- API tests included missing session, forged CSRF, unknown clip, extra search parameters, 429 when scene scan already in progress, and no automatically applied edits.
- **Browser E2E not verified here**: Chromium returned `net::ERR_BLOCKED_BY_ADMINISTRATOR` at loopback navigation even before loading the page. This is an environment restriction, not evidence of app success or app failure. The updated `tools/test_studio_browser.py` includes new browser scenarios for a clean Chrome runner, but no passing run is claimed.

## Known limitations

1. On-page scene scan may block one request for up to 45 seconds. Background queue/cache with persisted state is necessary before scaling to a shared agency environment.
2. Frame difference detection at 4 fps is insufficient to detect silent emotional reactions, gestures, transitions between camera pans, or semantic hooks. The editor must check source context and captions.
3. Text keyword matching does not understand synonyms, code-switching spelling differences or visual action. Egyptian Arabic / English / Franco transcript accuracy remains unverified on an independent customer sample.
4. No physical 15–20 GiB upload, full 60-minute human editorial acceptance or multi-user security assessment was run for this build.
5. No optional tool installation on the user's workstation was performed. DevKit Code and Skillhook Cloud did not have paired execution machines at last verification.
6. This release source package does not contain the separately drafted native Android PR #15. These enhancements target the main local browser Studio.
7. Test warnings for some unclosed SQLite connections in historical mock-based tests remain; tests passed, but tracking the warnings would improve test hygiene.

## Competitive baseline and next evidence gate

- OpusClip ClipAnything documents multimodal visual/audio/sentiment moment discovery: https://www.opus.pro/clipanything
- Submagic documents automatic caption/B-roll/transition/zoom editing: https://care.submagic.co/en/article/how-to-use-ai-auto-edit-in-submagic-gaxw7t/
- Vizard documents AI edit workflows with source transcript/reframing: https://help.vizard.ai/en/articles/16658532-what-is-ai-edit
- PySceneDetect official project documents BSD-3-Clause scene detection: https://github.com/Breakthrough/PySceneDetect

Next, before any commercial 'best editor' claim: use a rights-cleared 45–60-minute source with Egyptian Arabic/English and distinct visual scenes, compare top 10 candidates against human annotation, produce three approved 1080 × 1920 exports, and log editor acceptance, latency, ASR error, caption timing, cut naturalness and cost. Benchmark against one competitor on the **same source**; do not upload customer footage externally without specific permission.

**Authorization:** No GitHub branch/PR/merge, public deployment, external provider upload, spending or outreach occurred in this local build. Applying the patch to public GitHub requires user approval.
