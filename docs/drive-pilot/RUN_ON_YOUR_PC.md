# Run the verified Google Drive pilot on your laptop / WSL2

These steps are for the **Google Web application** OAuth client you already created. They are not instructions for the Android Cloud Shell host, where `localhost:8766/` cannot receive a Google callback from the phone.

1. **Google Cloud settings:** Select the existing client at https://console.cloud.google.com/auth/clients, choose the right project, and confirm that its **Authorized redirect URIs** includes `http://localhost:8766/` **including the slash**. The Google Drive API must be enabled at https://console.cloud.google.com/apis/library/drive.googleapis.com; ensure the sign-in account is an OAuth test user at https://console.cloud.google.com/auth/audience when the audience is External / Testing.
2. **Supported local runtime:** Use an Ubuntu / WSL2 Ubuntu checkout of https://github.com/MohammedAbdelshafy/clipops-studio. Keep the application source and OAuth JSON on the same trusted PC, but the secret JSON must be stored outside the repository. Store private ClipOps data outside synced/public folders. Native Windows and macOS media workflows are not qualified.
3. **Review files:** Copy the `studio_drive_*.py`, `requirements-drive-local.txt` and `test_studio_drive_*.py` files into your local ClipOps checkout only in a separately saved review/worktree; don't overwrite active peer changes. No remote push is required. Do not copy any OAuth JSON, token or media file to the repository.

In **WSL2 Ubuntu** from the ClipOps checkout:

```bash
python3 -m pip install -r requirements-drive-local.txt
python3 -m unittest -q test_studio_drive_reader test_studio_drive_bridge test_studio_drive_local test_studio_drive_web_oauth test_studio_drive_hardening

# Validate the Web OAuth callback locally, no Google login or token disclosure.
python3 studio_drive_local.py --root "$HOME/ClipOps-private" check-oauth --client-secrets "/private/location/client_secret_web.json"

# Start OAuth on the same workstation; copy the URL printed in WSL into
# that workstation's browser. Leave the terminal active for the callback.
python3 studio_drive_local.py --root "$HOME/ClipOps-private" connect --no-browser --client-secrets "/private/location/client_secret_web.json"

# Once connected: list video choices without downloading media.
python3 studio_drive_local.py --root "$HOME/ClipOps-private" preview "https://drive.google.com/drive/folders/1h40Cw399zPpR5bBoAhICxYVAZPVSswC-"
```

If the `pip install` command reports an externally managed Python environment, use the existing ClipOps `.venv/bin/python` or create a local virtual environment and run commands through it. Do not bypass your package manager's protections.

For the *first real test only*, after verifying processing rights and having an authentic transcript or local ASR model:

```bash
python3 studio_drive_local.py --root "$HOME/ClipOps-private" start \
  "https://drive.google.com/drive/folders/1h40Cw399zPpR5bBoAhICxYVAZPVSswC-" \
  "1h2UMW8r6q4he1-urL3pxt5PXku9-fhjH" \
  --transcript "/private/location/verified_transcript.json" \
  --rights-confirmed --render-count 0
```

To restart an interrupted media transfer, copy the checkpoint ID printed by the CLI and run `python3 studio_drive_local.py --root "$HOME/ClipOps-private" resume UPLOAD_ID`, supplying `--model` if your original import used ASR instead of a transcript.

Use ClipOps `launch-studio --root "$HOME/ClipOps-private"` afterward to open and review the imported project. Importing does not automatically publish or approve a clip.

**Notes:** On Google OAuth External / Testing, Google often expires refresh tokens after seven days for non-basic scopes. This may require signing in again. The current broad Drive readonly scope is restricted; public commercial deployment will require an appropriate consent/verification strategy. The Windows ACL and Chrome/WSL2 callback behavior are not tested here. Never use the Web OAuth JSON as a client-side JavaScript credential or share the browser's full OAuth login URL.
