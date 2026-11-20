# ClipOps Studio — cross-conversation release and Google Drive integration audit

**Snapshot:** 2026-11-20. This review used prior conversation requirements, live GitHub connector results, the private Google Drive connector's **metadata-only** results, Google OAuth official documentation, and fresh offline tests of the local Drive pilot.

## Snapshot and provenance

- GitHub repository: https://github.com/MohammedAbdelshafy/clipops-studio
- Latest inspected `main` commit: `e93f9d54e935475d95edfdd5f2b59e2221fdc2fe` (may move while parallel work continues).
- PRs **#12, #13 and #14 are merged**. Their respective PR-head GitHub Actions `ClipOps offline release gate` workflow runs were successful (IDs `44712639202`, `44719795037`, `44730799179`). The merge commits themselves were not independently retested in this environment.
- Draft PRs **#5, #6, #7, #8, #9, #10** remain open. Do not force-merge, auto-close, or rebase these while peers may still be using them. Compare specific unique hunks before any cleanup.
- No code from this review has been committed to or pushed to GitHub. Current folder is a standalone pilot patch, **not** a live server/browser integration.

## Current user goal and evidence gates

| Requirement | Evidence | Outcome |
|---|---|---|
| Source-grounded clipping, editing, captions, export | Integrated Studio code/documents and successful PR #12/#13 runs | Verified in automated integration tests; real human editorial acceptance still needed |
| Human rights and output approval | `AGENTS.md`, `PILOT.md`, Studio code, CI | Implemented local gate; real user-asset review unverified |
| 15–20 GiB resumable file intake | Existing `studio_uploads.UploadStore` with 8 MiB checksum chunks and max capacity | Configured and smaller recovery checks; physical 20 GiB test still missing |
| Arabic/Franco mixed-language quality | FFmpeg shaping/format workflow documented | Manual bilingual story/typography review missing |
| Android phone access | Merged PR #14 Cloud Shell launcher; CI tests | The app has a supervised account-gated preview path; actual user Android login/browser remains unverified |
| Google Drive folder-link preview | User-provided folder metadata via connected Drive and offline parser | Verified folder "Clothes Club El Bedaya" and 7 downloadable MOVs; separate ClipOps OAuth not yet exercised |
| Google Drive import of specific MOV | `studio_drive_reader.py`, `studio_drive_bridge.py`, `studio_drive_local.py` | 28 mocked offline tests; **real OAuth and actual Drive byte transfer NOT verified** |
| Paste Drive folder URL in Studio UI | Existing Studio UI plus reviewed pilot packages | **Not implemented in merged app.** CLI pilot only; requires authenticated routes, background worker, UI and browser tests |
| Secure OAuth on local Web client | Registered callback should be `http://localhost:8766/`; `check-oauth` validation | User reported URI entered; cannot verify Cloud Console or actual consent here |
| Cloud Shell Drive OAuth on Android | Merged Cloud Shell preview uses HTTPS remote proxy, but pilot OAuth expects local loopback | **Unsupported in the pilot.** An Android browser's `localhost` does not reach Cloud Shell; separate secure HTTPS redirect + server-side session/CSRF required |
| Agency multi-user accounts and publishing | Single-user localhost design, approval-gated export | Not production-ready; tenant isolation and publishing auth/live channel tests missing |
| $49/$149 pilot offer | Historical staged materials | Offers are staged only; no payment or commercial delivery verified |

## High-confidence code findings fixed locally

1. **Storage root symlink bypass (moderate):** `secure_root()` resolved the caller's path before checking symlinks, which made its `is_symlink()` test ineffective. The reviewed pilot now rejects a symlink at the requested private root. Fresh negative test first failed then passed.
2. **Drive filename metadata mismatch (moderate):** a Drive item name could include newline/control characters or exceed Studio's 180-character limit and still get past the reader. The pilot now enforces the matching Studio filename contract before creating checkpoints. New tests fail on old behavior and pass after patch.
3. **Browser opening in WSL2 (usability):** added `connect --no-browser` to print the Google sign-in URL without requiring a local Linux graphical browser.
4. **Cloud Shell redirect confusion (reliability/security):** `connect` fails clearly when run under Cloud Shell `WEB_HOST`, rather than presenting a localhost callback that would be unreachable from the user's Android browser.
5. **OAuth configuration preflight:** added `check-oauth --client-secrets PATH` to verify Web client redirect and client type without issuing Google network requests. This prints no client ID, client secret, access token, or refresh token.

## Outstanding engineering actions, in dependency order

1. **Local authorized test on a PC/WSL2:** Use `check-oauth`, then `connect --no-browser`. Do not paste the OAuth JSON, Google consent link, token, or customer media into chat or GitHub. The user must sign in interactively on the computer with port 8766 reachable on that same computer.
2. **Metadata-only preview** of the already-verified Drive folder URL in the real ClipOps OAuth context. Confirm the same seven videos. Connected ChatGPT Drive access does not prove the ClipOps OAuth access.
3. **Small real import** after explicit rights verification using `IMG_6657.MOV` (27,104,038 bytes). The user needs an authentic timed transcript or a previously installed supported offline speech model. Verify byte checksum and project creation with approved local processing. No default publishing.
4. **UI vertical slice on current main**, not a competing importer: add "Import from Drive" in `studio/app.js`, server-side APIs in `studio.py`, reusable owner-scoped worker/job with cancellation/status, CSRF and session auth, and existing `studio_uploads.UploadStore` as the only spool. Do not expose OAuth tokens to client JavaScript. Perform synthetic HTTP/browser and server-restart tests.
5. **Capacity/media validation:** repeat with a representative 1.1GB MOV, rights-cleared 45–60 minute clip, and physical 15–20GiB interruption/disk-pressure test on a qualified workstation with free space, plus Arabic/Franco editorial acceptance.
6. **Phone OAuth design:** if Android/Cloud Shell import is essential, design a separate registered HTTPS redirect for a trusted authenticated host, or use a secured workstation session with Drive connected on the workstation. Do not assume Cloud Shell Web Preview is a production OAuth callback or bypass its authentication.
7. **Release gate:** full `python -m unittest discover -v`, `node --check studio/app.js`, branded-Chrome desktop/mobile smoke, render/video QA, and approval-gated exports on exact final commit before public/customer use. CI green on old PR heads is not proof of new code's integration.

## Local pilot validation in this review

- Baseline Web OAuth package: **24 tests passed** (`python -m unittest discover -q -p 'test_studio_drive*.py'`).
- Three hardening tests first reproduced red cases against the baseline (storage root, filename rejection, `open_browser`). Cloud Shell test reproduced missing fail-fast.
- After fixes: **28 tests passed**, Python compile passed; independent `check-oauth` CLI smoke returned 0 using synthetic fake OAuth JSON. No Google network/media requests.
- No credentials or real footage included in this archive.

**Release verdict:** **CONDITIONALLY READY FOR SUPERVISED LOCAL CLIPOPS TESTING**, but **NOT READY for end-user Google Drive folder import inside the browser** or multi-user/public agency production. The local CLI Drive pilot requires actual OAuth and a rights-authorized small media test first.
