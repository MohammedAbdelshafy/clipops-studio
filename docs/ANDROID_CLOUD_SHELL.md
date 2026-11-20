# ClipOps Studio — Android, Google Cloud Shell (private test)

Use **Google Cloud Shell** on your Android phone to run the existing single-user FFmpeg editor and open it in a separate mobile Chrome tab. This is *not* a permanent public deployment. Google Cloud Shell Web Preview uses an authenticated HTTPS proxy restricted to your Google account. ClipOps still binds only to `127.0.0.1`; the new `--cloud-shell` flag strictly allows the preview host derived from Cloud Shell's own `WEB_HOST` and retains Secure, HttpOnly, SameSite=Strict cookies and CSRF validation.

## Fastest setup

1. Open [Google Cloud Shell](https://shell.cloud.google.com/) on Android and start the terminal.
2. Paste this exact command (public ClipOps source only; no keys required):

```bash
if [ -d "$HOME/clipops-phone/.git" ]; then cd "$HOME/clipops-phone" && git pull --ff-only; else git clone --depth=1 https://github.com/MohammedAbdelshafy/clipops-studio.git "$HOME/clipops-phone" && cd "$HOME/clipops-phone"; fi && bash START_CLIPOPS_CLOUD_SHELL.sh
```

3. If ffmpeg/fonts are missing, the script installs the free system dependencies; it also installs the pinned Pillow package into a private virtual environment. It does not provision a Google Cloud Run service, VM, paid API, storage bucket, or public tunnel.
4. Open the HTTPS link printed in the terminal, whose form is `https://8080-$WEB_HOST`, or tap **Web Preview → Preview on port 8080** inside Cloud Shell.
5. In ClipOps choose **Import project**, select a rights-cleared small video stored on your phone plus a timestamped JSON transcript, and render a clip. The browser sends the file only to your authenticated Cloud Shell preview workspace; never upload customer videos without their permission.

## Demo transcript

```json
{"segments":[{"start":0.2,"end":4.2,"text":"How should a creator open a good short video?","speaker":"Host"},{"start":4.3,"end":8.5,"text":"Lead with a specific promise, then deliver it.","speaker":"Host"}]}
```

Use a video containing matching dialogue and timestamps or use the included synthetic fixture from the prior ClipOps demo ZIP. Timed transcript imports must match the actual footage. An optional local transcription model requires installing weights separately and is not bundled.

## Limitations and security

- Cloud Shell is ephemeral or session-based, **not 24/7 hosting**. The editing server stops when Cloud Shell stops. This preview URL may change with the session.
- Cloud Shell storage is small; do **not** try 15–20 GB uploads there. For long videos, use the workstation release build and `--source-dir` locally; real large-file transfer remains to be qualified.
- Avoid sharing preview URLs, private upload links, Google tokens or customer footage. The GitHub repository is public, but the private media folder is not committed to Git.
- Do not run `--cloud-shell` on a public cloud VM or remove the account authentication proxy. Cloud Shell previews are suitable for supervised personal testing only.
- Do not publish the loopback service through a public tunnel, Cloud Run or `0.0.0.0` without separate authentication architecture and explicit approval.
- Codespaces is an alternative in the screenshot, but can incur usage charges outside included GitHub quotas and requires private port forwarding. This Cloud Shell route avoids creating a Codespace.
- To add a quick Android home-screen entry: open the preview in Chrome, choose menu → **Add to Home screen**. This only bookmarks the session URL; it does not keep Cloud Shell running.

## Diagnostics

- `WEB_HOST is missing`: the command is not running in an active Google Cloud Shell terminal.
- HTTP **403**: open the new Google Cloud Shell preview link, sign in to the same account, and reload the app; do not substitute `localhost:8080` in your phone browser.
- Missing Python environment: `sudo apt-get install python3-venv` (only if the first run reports it absent).
- Failed playback or render: use a small supported MP4 and FFmpeg; the UI may create a private WebM preview for browsers without H.264.
- Run server checks: `python3 -m unittest -v test_studio_preview.py test_studio.py`. Run the full suite with `python3 -m unittest discover -v`.

Sources: [Google Cloud Shell Web Preview](https://docs.cloud.google.com/shell/docs/using-web-preview), [Cloud Shell overview](https://docs.cloud.google.com/shell/docs/using-cloud-shell), [GitHub Codespaces port privacy](https://docs.github.com/en/codespaces/developing-in-a-codespace/forwarding-ports-in-your-codespace).

**Release gate:** This feature requires the dedicated backend security tests and existing media/browser CI before merging. Real user-specific Cloud Shell sign-in and preview have to be checked by the account owner.
