# ClipOps Drive folder — verified pilot handoff

**2026-11-20 — metadata-only verification through connected Google Drive.**

- Folder: **Clothes Club El Bedaya**
- Folder URL: https://drive.google.com/drive/folders/1h40Cw399zPpR5bBoAhICxYVAZPVSswC-
- Folder ID: `1h40Cw399zPpR5bBoAhICxYVAZPVSswC-`
- Direct children: **7 supported MOV videos**, reported downloadable by Google Drive.
- Total reported bytes: **3,086,874,280** (3.087 GB decimal).
- Smallest selected test media: `IMG_6657.MOV` (**27,104,038 bytes**, about 27.1 MB).
- Smallest video ID: `1h2UMW8r6q4he1-urL3pxt5PXku9-fhjH`
- Ownership/rights: **not verified by metadata**; process only after the user confirms rights.
- Broader sharing visibility: **not verified**. No changes to Drive permissions.
- No footage has been downloaded or processed in this handoff.

## Your existing Google **Web application** OAuth client

1. Open https://console.cloud.google.com/auth/clients and select the existing client in the Google Cloud project.
2. Ensure Authorized redirect URIs includes **exactly** `http://localhost:8766/` (including `/`).
3. If OAuth Consent is External and Testing, ensure your Google account is on https://console.cloud.google.com/auth/audience as a test user.
4. Enable https://console.cloud.google.com/apis/library/drive.googleapis.com .
5. Download a fresh **Web application OAuth JSON** after saving changes, to a private local folder outside the Git repo; never paste/upload secrets in chat.
6. Install requirements and run in the existing ClipOps repository with the package's Python files copied to its root on a review branch.

## PowerShell commands

```powershell
py -3 -m pip install -r .\requirements-drive-local.txt
py -3 -m unittest -q test_studio_drive_reader.py test_studio_drive_bridge.py test_studio_drive_local.py test_studio_drive_web_oauth.py

# One-time browser sign-in to the separate ClipOps app. Replace private path only.
py -3 studio_drive_local.py --root .\out\pilot connect --client-secrets "C:\PRIVATE\client_secret_web.json"

# Preview YOUR already-verified folder. Metadata only.
py -3 studio_drive_local.py --root .\out\pilot preview "https://drive.google.com/drive/folders/1h40Cw399zPpR5bBoAhICxYVAZPVSswC-"

# For a real import, use either an authentic timestamped transcript:
py -3 studio_drive_local.py --root .\out\pilot start "https://drive.google.com/drive/folders/1h40Cw399zPpR5bBoAhICxYVAZPVSswC-" "1h2UMW8r6q4he1-urL3pxt5PXku9-fhjH" --transcript "C:\PRIVATE\authentic_timed_transcript.json" --rights-confirmed --render-count 0

# OR use an already-installed local ASR model instead of --transcript:
# py -3 studio_drive_local.py --root .\out\pilot start "https://drive.google.com/drive/folders/1h40Cw399zPpR5bBoAhICxYVAZPVSswC-" "1h2UMW8r6q4he1-urL3pxt5PXku9-fhjH" --model "C:\PRIVATE\local_asr_model" --rights-confirmed --render-count 0
```

**Do not run the `start` command unless you have authorized the footage and have a genuine timed transcript or working local ASR model.** Check the returned checkpoint ID for recovery. Source import does not publish social posts; `--process` is opt-in. Run `launch-studio` on the same `--root` to see projects.

## Evidence and limitations

- **24/24 offline tests passed in the packaging environment**; `python -m py_compile` and folder-link parser also passed.
- Existing `studio_uploads.UploadStore` will be imported from your ClipOps checkout. These tests mock it; live end-to-end compatibility on your machine remains unverified.
- Google Web OAuth consent, real MOV download, video format probe, Windows ACLs, actual Studio UI tab, and 20 GiB transfers **not yet validated**.
- The connected ChatGPT Google Drive token is **not** the ClipOps application token.
- No GitHub branch, commit, PR, Drive file or permission was changed.
