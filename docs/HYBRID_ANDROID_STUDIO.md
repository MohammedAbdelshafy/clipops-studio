# ClipOps Studio — hybrid Android with desktop feature access

**Status:** private, supervised test architecture. Full Studio UI and rendering are served unchanged by the existing desktop Python + FFmpeg engine through a user-authorized HTTPS proxy. Offline Pocket trimming remains available inside the Android app. This is not an independent native port of every desktop algorithm.

**Privacy:** no public hosting, no media copied between engines, no payments or API keys, no auto-publishing, no automatic failover. The laptop and cloud workspaces are separate and switching profiles does not synchronize projects, transcripts, approvals, or jobs.

## A. Laptop backend: Tailscale Serve (preferred for large videos)

1. Install Tailscale on the laptop and phone, sign in, and verify both are on the same trusted tailnet. Limit your tailnet ACL so only the owner can access the ClipOps service. Enable HTTPS certificates; do not enable Funnel.
2. In the existing ClipOps source checkout on Linux or Windows WSL2, install the Python 3.11+, FFmpeg, fonts and Pillow prerequisites listed in docs/TRY_CLIPOPS.md.
3. Run in the source directory: **bash START_CLIPOPS_TAILNET.sh laptop.your-tailnet.ts.net owner@example.com**. Replace the hostname and owner email with the exact values shown in your Tailscale account. This keeps ClipOps bound to 127.0.0.1 and blocks any client without the forwarded matching Tailscale-User-Login identity, including initial GET requests.
4. In a separate terminal on the SAME host with access to the server's localhost port, run: **tailscale serve 8765**. Use Serve only, never **tailscale funnel**. Verify its output shows the expected private https://laptop.your-tailnet.ts.net address. If Tailscale runs on Windows and ClipOps runs in WSL2, first verify Windows-to-WSL localhost forwarding; if that does not work, configure Serve on the Linux host where localhost is actually reachable.
5. In the Android ClipOps Studio app paste the exact private HTTPS URL under **LAPTOP**, tap **Open FULL Studio on laptop**. Chrome Custom Tab provides the original Studio project library, clip ranking, captions, source-moment search, creative review, render queue, approval and verified exports.

## B. Private cloud fallback: Google Cloud Shell

1. Sign in to Google Cloud Shell in Chrome on your Android phone and start its terminal; run the existing START_CLIPOPS_CLOUD_SHELL.sh from this repository.
2. Copy the exact private HTTPS address printed by Cloud Shell, of the form https://8080-...cloudshell.dev, into the Android app under CLOUD and open it.
3. Chrome handles your existing Google account sign-in. Embedded WebView login is deliberately not used. Cloud Shell expires and has small storage/CPU resources: use synthetic/small tests only. Do not ingest 15–20 GiB or assume uninterrupted rendering.

## Offline backup and parity boundary

The APK includes the previous on-device Media3 import/trim/export Pocket tools if no private backend is reachable. These native-only tools do not provide transcript ranking, captions, scene detection, 20 GiB ingestion or approved batch exports. **Those desktop features become available only when the matching private backend is running and reachable.**

The app validates the two HTTPS URL profiles and rejects arbitrary public domains, http, credentials, query strings, URL paths and fragments. It saves only the hostnames in Android private preferences. It does not automatically transfer projects, retry uploads, promote renders or switch servers after failure.

## Acceptance required before unrestricted delivery

- Confirm the owner can open the private laptop URL through Tailscale Android; confirm another tailnet user gets HTTP 403 even for GET /.
- Open the Cloud Shell URL while authenticated as the owner, then verify unrelated Google accounts cannot enter.
- From Android, test the same real (rights-cleared) import -> ranked candidates -> transcript correction -> render -> human review -> MP4/SRT/VTT/ZIP download path as desktop. Confirm the browser can resume a synthetic interrupted upload without duplicate jobs.
- Test the Windows WSL2 + Tailscale port forwarding on the actual laptop, and verify original-source read-only paths. No client footage should be uploaded to arbitrary services.
- Run human editorial QA on an authorized hour-long mixed-language recording and physical 15–20 GiB transfer/resume on the actual workstation. Neither is proven by an APK build.
- Multi-editor login, server-side tenancy, durable cloud compute, secure cross-engine sync and paid/public deployment remain blocked pending separate design, security acceptance and explicit owner approval.

References: https://tailscale.com/docs/features/tailscale-serve ; https://developer.chrome.com/docs/android/custom-tabs/guide-get-started ; https://docs.cloud.google.com/shell/docs/using-web-preview