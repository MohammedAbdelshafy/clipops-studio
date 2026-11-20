# ClipOps Studio — Google Drive folder import pilot

Date: 20 November 2026. **Status: 24 offline contract tests passed. Google OAuth, a real Drive download, a full-size 20 GiB transfer, Windows credential permissions, and the Studio browser UI have not been tested.** This package is an opt-in local CLI adapter; it is **not** a merged or deployed ClipOps feature.

## Why this package exists

The existing ClipOps `studio_uploads.py` owns the canonical 20 GiB resumable upload state. This pilot imports Drive videos directly into **that same store**. It never copies 20 GiB into another new source spool, and it never posts or publishes. Checkpoint IDs let operators continue after interruption.

The user must explicitly grant **Google Drive OAuth** to the ClipOps test app. ChatGPT's connected Google Drive authorization **does not** authorize a separate ClipOps application. No OAuth credentials have been shared with the assistant.

## Exact Google links

1. Create/select Cloud project: https://console.cloud.google.com/projectcreate
2. Enable Google Drive API: https://console.cloud.google.com/apis/library/drive.googleapis.com
3. Configure OAuth consent: https://console.cloud.google.com/auth/overview
4. Configure audience/test users: https://console.cloud.google.com/auth/audience
5. Create an OAuth client (Web application or Desktop app): https://console.cloud.google.com/auth/clients
6. Official OAuth guide: https://developers.google.com/identity/protocols/oauth2/web-server
7. Official Drive scopes guide: https://developers.google.com/workspace/drive/api/guides/api-specific-auth

For a folder **link** with arbitrary private videos, the initial CLI uses Google's `drive.readonly` (restricted) scope. Google may require app verification/security assessment for external production. For commercial UI, evaluate Google Picker with non-sensitive `drive.file` grants (per video, not just folder) to minimize permissions.

## First local pilot (PowerShell, Windows)

**You need Python 3.11+, FFmpeg on PATH, the current ClipOps repository, and the new Python modules from this bundle.** Copy the `.py` files into the *top-level directory of a local, trusted ClipOps checkout*. Do this on a separate local review branch, preserving all current work; do not overwrite existing files. This package includes the test modules as optional safety checks.

Use the actual ClipOps project root you start Studio with. **Do not put a client-secret file inside the GitHub checkout.** Download the OAuth Web application JSON into a private local folder. On Windows, check that the Studio project root and downloaded JSON are accessible only by the intended Windows account; this package has not validated Windows ACLs.

```powershell
# In the existing ClipOps repository, after placing the new files:
py -3 -m pip install -r .\requirements-drive-local.txt
py -3 -m unittest -q test_studio_drive_reader.py test_studio_drive_bridge.py test_studio_drive_local.py

# 1. Authorize this local application by signing in through your browser.
py -3 studio_drive_local.py --root .\out\pilot connect --client-secrets "C:\PRIVATE\PATH\client_secret_web.json"

# 2. Preview a folder (use YOUR Drive folder link).
py -3 studio_drive_local.py --root .\out\pilot preview "https://drive.google.com/drive/folders/YOUR_FOLDER_ID"

# 3. Copy one selected video using the ID returned in preview and a genuine timestamped transcript.
py -3 studio_drive_local.py --root .\out\pilot start "https://drive.google.com/drive/folders/YOUR_FOLDER_ID" "YOUR_VIDEO_ID" --transcript "C:\PRIVATE\PATH\transcript.json" --rights-confirmed --render-count 0

# 4. If interrupted, reuse the printed upload checkpoint ID (same private root).
py -3 studio_drive_local.py --root .\out\pilot resume "YOUR_UPLOAD_CHECKPOINT_ID"
```

If ClipOps already has a local speech-recognition model directory, use `--model "C:\PRIVATE\PATH\model"` instead of `--transcript`. Add `--process` to run ClipOps's existing local analysis and rendering in the foreground; it is opt-in to avoid accidentally using large compute. The single-user Studio should use the same `--root` to see the newly created project. The `resume` path needs `--model` if the project was started without a transcript.

The printed ID is the durable recovery key. If the import is interrupted by Ctrl+C or loss of Drive access, reauthorize Google if required and use `resume` with exactly that ID. Never delete the `.uploads` checkpoint before finishing.

## Test acceptance and guardrails

- Source folder must be readable to the signed-in account; the video must be directly inside it, not a nested folder. Download must be permitted.
- Test with one small personal video before trying 45–60 minutes or 15–20 GiB. Compare original duration, audio, frames, and SHA-256/Drive checksum as available.
- Google Drive is read-only. Imports are explicitly selected and rights-confirmed; there is no bulk folder auto-import and no social publishing.
- Tokens are written to `.google-drive-oauth.json` inside the private Studio root. Never paste or upload that file, its refresh token, or the desktop client secret into GitHub or chat. For **Web application** credentials, register the **exact** redirect URI `http://localhost:8766/` in the Google Cloud OAuth client. This callback is local only and does not deploy anything. The login command uses Google OAuth; it does not need your Google password typed into ClipOps.
- Local pilot uses Google API calls over HTTPS after manual authorization. External OAuth testing-mode refresh tokens may expire after seven days; reauthorize when prompted. Network failures and unknown platform-specific behavior must be measured; don't claim a 20 GiB success from synthetic tests.
- Authenticated multi-user hosting, web OAuth, and in-browser Drive-folder selection/status are **separate future integration work**. This package is not a replacement for that feature.

## Included files

`studio_drive_reader.py`: strict Google Drive folder URL validation, metadata and 206/range media reader.

`studio_drive_bridge.py`: Drive-to-existing-UploadStore streaming copy, source version integrity, Drive MD5 verification.

`studio_drive_local.py`: local OAuth Web or Desktop client authorization, token refresh, CLI preview/start/resume, existing project finalization.

`requirements-drive-local.txt`: optional dependencies; no changes to ClipOps base lockfiles.

`test_studio_drive_reader.py`, `test_studio_drive_bridge.py`, `test_studio_drive_local.py`, `test_studio_drive_web_oauth.py`: offline tests, including simulated interrupted transfers and protected token files.

## GitHub integration target

- Main repo: https://github.com/MohammedAbdelshafy/clipops-studio
- Main branch verified 20 Nov 2026 at `019bde802d0774bcba80365d52d9497c82b83d75` (subject to further concurrent changes).
- PR #11 merged at check time. PR #9/#10 were still draft. Reconfirm before any new PR.
- Stage these additive files in **one private local review branch** from the latest verified main, inspect for collisions, then add the UI/API and independent browser tests. Do not merge or deploy automatically.

## Unresolved production requirements

Single-user local OAuth pilot is prepared but **the final ClipOps UI tab is not yet wired**. A production web UI will require application-owned per-user OAuth, authenticated/CSRF-protected preview and job-status routes, durable queue and cancellation, secure token storage, real Drive error cases, verified Windows ACLs, browser flows, and an authorized long-form source test.

## Web application OAuth quick-start (tested via offline mocks)

1. In the Google OAuth client, set **Authorized redirect URI** exactly `http://localhost:8766/` (including trailing slash). `http://localhost:8765` is an optional JavaScript origin and is NOT the redirect URI.
2. Confirm Drive API is enabled. For a private folder-link pilot choose the **restricted** read-only Drive scope, and if using an External / Testing consent screen, add your Google account to Test users. Use the broader scope only for the supervised pilot; Google Picker + `drive.file` is preferable for commercial production.
3. Download the **Web application** OAuth JSON to a private folder OUTSIDE the repo. Do not paste client_secret, refresh_token, access token, or contents of the JSON into ChatGPT, Gmail or GitHub.
4. Run the same `connect` command above; it now detects Web clients and binds the one-time sign-in callback to port **8766**. If your port is busy, choose `--oauth-port 8767` **and register `http://localhost:8767/` first**. Google requires an exact match.
5. Use `preview` and `start` as before. The separate ClipOps web UI folder-picker remains a follow-up integration, not claimed complete here.

No GitHub changes, public deployment, emails, Drive writes, or real OAuth requests were performed to produce this package.

## November 20 hardening addendum

For the latest reconciled GitHub version, exact test evidence and requirements coverage, see `RELEASE_AUDIT_2026-11-20.md` and `RUN_ON_YOUR_PC.md`.

New local CLI features: `check-oauth` validates your saved Google Web client without signing in, and `connect --no-browser` prints the Google consent URL for use in the browser on the **same** workstation (particularly WSL2). The pilot explicitly rejects the `localhost` callback when executed inside remote Cloud Shell. For Android phone tests, use the existing merged Cloud Shell preview of ClipOps with a small manually uploaded rights-cleared video; Drive OAuth still needs a separate secure HTTPS callback design there.

The 28 offline tests prove neither a completed Google OAuth exchange nor the Studio browser UI integration.
