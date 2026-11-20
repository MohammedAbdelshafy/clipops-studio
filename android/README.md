# ClipOps Pocket — native Android offline beta

This is a real installable Android application, **not** a Termux script or a WebView shortcut.

- Native Android Media3 player and on-device Transformer. Android 10+. Compiled against Android API 36.
- Pick a video using Android's document picker, preview, mark in/out, select original/vertical/square framing, render a <=180-second clip, save to Movies/ClipOps, share using Android's share sheet.
- Entire trim pipeline is **offline**. No INTERNET permission, no accounts, no telemetry, no paid providers, no upload.
- Cropping modes use fit/padding to preserve content rather than pretending to do automatic speaker tracking.
- Source video remains unchanged; final clip appears in device gallery only after a complete successful export.

**Deliberate scope:** This APK does NOT yet port the desktop Python/FFmpeg ranker, AI transcription, multi-speaker effects, 15–20 GiB processing guarantees, brand templates, or full batch factory. Those remain in the desktop/local-first ClipOps Studio, separately available in GitHub. The Hatchable ClipOps Content Studio is a separate hosted *transcript-drafting* companion, not the native renderer.

Build on GitHub Actions `ClipOps Pocket Android APK` (Java 17 / Gradle 8.13 / AGP 8.11.1 / Media3 1.11.1). Artifacts are unsigned-for-release but debug-signed for internal installation. This APK has not been accepted on a real physical device until you test it. A Google Play release needs a secure production keystore, store policy review, and user approval.

## Install (Android)

1. Download `ClipOps-Pocket-APK` from a successful Actions run, extract its ZIP to obtain `app-debug.apk`.
2. Tap the APK on your own device; enable *Install unknown apps* only for the download source when Android asks. Don't sideload from unknown links.
3. Open **ClipOps Pocket** icon; select a small, rights-cleared MP4; set a short interval; tap **Export MP4**.
4. Confirm the clip exists in **Gallery > Movies > ClipOps**, preview it and use **Share clip**.

No Termux, Cloud Shell, or paid API is needed for these native features.
