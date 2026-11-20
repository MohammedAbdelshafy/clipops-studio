# ClipOps Studio — Android hybrid beta

Full desktop Studio access on Android, using the existing private Python/FFmpeg API and browser interface on a paired laptop or cloud host. This build does NOT independently run all desktop AI models or FFmpeg capabilities on the phone.

Android launcher supports secure private Tailscale Serve HTTPS pairing, two selectable independent endpoints, Android document picker for video/JSON input, and system Save As for approved MP4/SRT/VTT/ZIP downloads. The old standalone native Pocket quick-trim is preserved as an offline screen.

An independently configured Tailscale Serve processor and one-time server code are required for the full Studio. No cloud provider is deployed, public tunnel started, private footage uploaded or paid API called by building this APK. Never use Tailscale Funnel for the server.

Read docs/ANDROID_HYBRID_FULL_STUDIO.md for exact user-controlled setup, security boundaries and device acceptance.

GitHub CI produces debug-signed ClipOps-Studio-Hybrid-APK (app-debug.apk). New application ID com.mbm.clipops.studio prevents clobbering an earlier Pocket installation. Physical device QA remains necessary. Debug keystores are temporary: uninstall may be required when updating between separate CI runs. Do not distribute as a production app.
