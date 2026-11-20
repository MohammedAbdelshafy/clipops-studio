# ClipOps Studio Android — private Microsoft Dev Tunnels (no Tailscale)

**Purpose:** An optional temporary remote connection from the normal Android ClipOps Studio APK to the **existing** Python/FFmpeg Studio running on your trusted laptop, with no VPN, no domain registration, no public deployment, and no paid hosting created by this repository.

## Why only for small tests

Microsoft Dev Tunnels is a **developer preview** product, not a commercial media transport. Microsoft's documented quota is **5 GB per user per month**, and **16 MB maximum HTTP request body** for web forwarding. ClipOps uses 8 MiB resumable chunks and fits the *per-request* cap, but a real **15–20 GiB** source would exceed the *entire monthly* bandwidth limit. Do not use Dev Tunnels for your long-form production source transfers; keep those on the actual workstation's local storage and use direct local source references. For large-file production, consider a separately approved Cloudflare Access/Tunnel deployment or a private peer-to-peer networking solution. Never enable anonymous tunnel access.

## Set up (two laptop terminals, one phone)

1. On Windows, install the official CLI using PowerShell:

   `winget install Microsoft.devtunnel`

   Sign in with your own Microsoft **or GitHub** account:

   `devtunnel user login`

   This is a human browser authorization step and must be completed by the account owner.

2. Keep the Windows PowerShell terminal open and host **only** the local ClipOps port, without any anonymous flags:

   `devtunnel host -p 8765`

   The CLI displays a browser-friendly HTTPS address of the form **https://TUNNELID-8765.REGION.devtunnels.ms/**. **Copy that exact -8765 hostname**; do not use the alternate :8765 URL or the inspection hostname. Do not add `--allow-anonymous`, `--tenant`, `--organization` or share access tokens. Microsoft authenticates the tunnel to the account that created it by default.

3. On the **same Windows computer**, start your existing ClipOps Python backend from a separate WSL2 Ubuntu terminal (Python 3.11+, FFmpeg, fonts and Pillow as described in `docs/TRY_CLIPOPS.md`):

   `bash START_CLIPOPS_DEVTUNNEL.sh "https://TUNNELID-8765.REGION.devtunnels.ms"`

   This sets `CLIPOPS_ALLOW_PUBLISH=0` and uses `studio.py --devtunnel-url`. The local server still listens on **127.0.0.1:8765 only**. It prints a **one-time 32-character pairing code**, valid for 20 minutes and at most eight wrong attempts. Keep this code on the laptop terminal; do not put it in chat, Git, screenshots, browser URL parameters, or logs.

4. On Windows, verify it can reach **http://127.0.0.1:8765**; the private pairing page should appear. WSL2 localhost forwarding is environment-dependent: if Windows cannot reach WSL2, fix that connection or run Dev Tunnels on the Linux host. Do not bind ClipOps to `0.0.0.0` as a workaround.

5. On Android, open the new **ClipOps Studio** APK. Under **NO VPN · Microsoft Dev Tunnel**, paste the exact browser-friendly HTTPS URL, tap **Open FULL Studio without Tailscale**, and sign in with the **same Microsoft or GitHub account** in Chrome. Follow Microsoft's first-visit security interstitial if shown. On the private ClipOps pairing page, enter the one-time code from your laptop terminal.

6. The full desktop Studio interface now runs through Chrome Custom Tabs: upload a **small authorized video** with timed JSON, review source moments, transcripts/captions, render locally on the laptop, approve outputs and download from the phone. Files and render jobs stay on the laptop. Offline Pocket works without any connection.

7. Stop the tunnel using **Ctrl+C** in its Windows terminal. Microsoft states temporary tunnels are deleted when their host command exits. The app's saved URL is now stale; reconnect with a new address if you start a new temporary tunnel.

## Security model

- The Microsoft relay authenticates your Microsoft/GitHub account. The ClipOps backend **additionally requires a one-use, random, time-limited code** before issuing **any** remote session cookie or serving static app scripts, the project API or media files. It maintains Secure/HttpOnly/SameSite cookies and same-origin CSRF checks for edits/renders.
- The backend accepts only the exact configured `id-8765.region.devtunnels.ms` HTTPS origin and stays bound to `127.0.0.1`. Local and Cloud Shell/Tailscale behavior remains unchanged in their own modes.
- This is temporary access, **not** a 24/7 cloud host, not cross-engine storage sync, not automatic failover, and not a multi-client production application. Connection over a tunnel sends traffic through Microsoft's relay infrastructure even though your files remain hosted locally.
- Never use the tunnel inspector for client footage, never enable `--allow-anonymous`, and never share the pairing code. Exposed video data must be rights-cleared and owner-approved.

## Real acceptance checks still required

- Verify only the tunnel owner's Microsoft/GitHub account reaches the pairing form.
- Verify no user can retrieve `/app.js`, `/api/projects`, or `/media/*` without the one-time pairing cookie; verify a used code is rejected.
- Verify Chrome on the actual Android phone can complete Microsoft login then POST the pairing form and retain Secure cookies.
- Test a small MP4 + reviewed transcript through import/candidate search/render/approval/download and retry a synthetic interrupted upload.
- Measure transferred bytes and refuse production media beyond the documented 5 GB per-user monthly Dev Tunnels quota.

Official sources:
- https://learn.microsoft.com/en-us/azure/developer/dev-tunnels/get-started
- https://learn.microsoft.com/en-us/azure/developer/dev-tunnels/security
- https://learn.microsoft.com/en-us/azure/developer/dev-tunnels/cli-commands
- https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/azure-subscription-service-limits
