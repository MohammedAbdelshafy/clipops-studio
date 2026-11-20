# ClipOps Studio Android — full workflow through private laptop/cloud

The installable **ClipOps Studio** Android APK opens the **same complete web Studio** already used on the desktop, via private HTTPS endpoints and Chrome Custom Tabs. It retains the offline Pocket trim/editor underneath for disconnected operation.

Choose LAPTOP (Tailscale Serve) or CLOUD (account-gated Google Cloud Shell) from inside the app. Use the exact private URL assigned by the provider, and ensure the corresponding Python/FFmpeg backend is already running. Host profiles are saved privately with no credentials, URL parameters or public services.

**Important:** full capabilities are provided by the connected backend, not ported into this APK. This build does NOT implement cross-server project synchronization, automatic failover of renders, native on-device transcription or persistent public cloud service. Cloud Shell is a temporary test fallback for small files, not a paid/prod renderer. The native Pocket backup works offline and is still limited to 3-minute trims.

For owner-only private laptop pairing and safe cloud setup, see [Hybrid Android Studio guide](../docs/HYBRID_ANDROID_STUDIO.md).

## Android test build

- Native app ID remains com.mbm.clipops.pocket for upgrade compatibility. Android 10+. Label is **ClipOps Studio**.
- Java 17, Gradle 8.13, Android Gradle Plugin 8.11.1, Kotlin 2.2.10, Media3 1.11.1, AndroidX Browser 1.10.0.
- GitHub Actions debug APK includes unit tests for source clip bounds and strict endpoint validation.
- A successful APK build does not verify that your own Windows Tailscale proxy, Cloud Shell login, customer media upload or physical Samsung codec works.
- Since GitHub debug keys may be ephemeral, uninstalling an earlier beta APK may be necessary if Android says the installed app was signed with another key. Gallery clips saved externally remain separate from the app sandbox.

No paid hosting, public deployment, account credential, asset migration or provider connection is created by installing the APK.