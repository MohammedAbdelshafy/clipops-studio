# Full ClipOps Studio Android — private hybrid laptop/cloud

Status: review-only Android build. No cloud host or paid service is provisioned.

## What you get

The Android app loads the SAME Studio HTML/JS and Python/FFmpeg review desk used on the desktop: project library, source-moment search, transcript and captions, creative suggestions, nine editing presets, visual review, FFmpeg render and quality checks, human approvals, MP4/SRT/VTT and approved ZIP export. Android's document picker selects source media and timed JSON; Save As copies approved files to phone storage. The offline Pocket quick trimmer remains available.

This is parity of the connected UI and backend, not a second on-device FFmpeg implementation. Advanced features require a reachable private host. Engine switching is explicit, without project or media synchronization. A failed laptop render does not resume automatically in the cloud.

## Laptop setup — private tailnet, no paid hosting

1. Connect the Android phone and the trusted processing machine to the SAME Tailscale tailnet. Configure restrictive tailnet ACLs. On WSL2 verify Tailscale Serve can reach the Studio process in the same OS/network namespace, or use a trusted native Ubuntu workstation.
2. Install Python 3.11+, FFmpeg, FFprobe, Pillow, Fontconfig and caption fonts on the backend. Check that the command is run from a fresh checkout of this review branch, not from an older main branch.
3. Start the backend on the workstation. Replace the origin and source directory with the EXACT private HTTPS host printed by Tailscale Serve:

    python3 studio.py --root "$HOME/ClipOps-private" --port 8765 --private-origin https://DEVICE.TAILNET.ts.net

4. In a separate backend terminal, after checking tailnet access controls, start the private Serve proxy:

    tailscale serve 8765

    tailscale serve status

Never run Tailscale Funnel. Serve URL and the --private-origin must exactly match. The server continues to bind ONLY 127.0.0.1; there is no public listener.
5. The backend prints a fresh, random one-time 16-character pairing code, valid 15 minutes. In ClipOps Android enter the same Serve URL into Laptop, enter the code from the backend console in the pairing field, then choose Connect. Do not send the code in a chat.
6. Test with a small permissioned video and reviewed timed transcript: import, analyze, find source moments, edit captions, render, review and approve, save an MP4/SRT/VTT/ZIP via Android's system document picker.

## Cloud processor

Use a separate, OWNER-APPROVED private Linux compute machine already available to you. Configure Tailscale Serve, the same Studio command with that cloud machine's HTTPS tailnet origin, and its own private project root. Enter its URL in the Android Cloud field and pair using the cloud machine's one-time code. No VM, GPU, public endpoint or paid storage is created by this PR.

The existing Google Cloud Shell private preview is temporary and unsuitable for 15–20 GiB projects. Cloud Shell Google sign-in inside Android WebView may be rejected; use Chrome for that preview if required.

## Safety and limitations

- No anonymous remote session cookies are issued in --private-origin mode. Both local browser and private phone clients must first use the one-time code. Codes are not stored in Android preferences. Retry limit: eight failed attempts. Successful codes cannot be reused.
- Tailscale Serve must remain private with ACL restrictions; *.ts.net is not itself proof that Funnel is disabled. Never enable Funnel for Studio.
- The WebView allows only exact HTTPS Cloud Shell/Tailscale origins and uses system TLS verification. External links open outside the app, no dangerous JavaScript bridge, no mixed-content or file-scheme access.
- The Android system picker supplies only user-approved content URIs. Downloads allow only same-origin approved media paths, avoid redirects and stream into user-selected files; camera/broad storage access is not requested.
- True Android WebView physical 15–20 GiB uploads, network interruption/restart, Arabic/Franco ASR quality, real customer 45–60-minute editorial acceptance and production multi-user security are NOT verified. Use the backend local-source reference for big files.
- Existing Pocket APK is a different package; this build uses com.mbm.clipops.studio, so you can keep both installed. Debug signing is ephemeral between CI runs; future APK upgrades may require uninstalling the prior debug installation.

## QA gates

Backend Python unit/integration plus Chrome desktop/mobile browser tests, Android Gradle unit and compilation, APK integrity, and actual on-device private connection tests. Green CI alone is not a production release. Do not merge, publicly deploy, spend money, send outreach or upload private client footage without relevant approval.

Official references:
https://tailscale.com/docs/features/tailscale-serve
https://developer.android.com/reference/android/webkit/WebChromeClient.FileChooserParams
https://developer.android.com/reference/android/webkit/WebSettings
