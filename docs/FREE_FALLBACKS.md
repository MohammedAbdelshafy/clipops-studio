# ClipOps free fallback routes — offline-first

Open **Free fallbacks** in the Studio top bar when an optional API, model, quota or app is unavailable. This read-only local directory never uploads media, publishes, spends, sends outreach or exposes credentials. External websites only open when the editor chooses to open them.

| Interrupted step | Built-in fallback | Other manual free tools |
| --- | --- | --- |
| Large media import | `--source-dir` avoids a second 15–20 GiB copy; browser uploads resume with checksums | Keep customer originals private |
| Speech API | Import a timed JSON transcript or use an existing local faster-whisper model | Offline whisper.cpp |
| Editing or rendering | Local FFmpeg and ClipOps review/QC | Kdenlive; Shotcut |
| Image generation | Use owned, licensed images and local artwork | GIMP |
| Postiz API | Export already approved MP4, SRT, VTT. A separate offline schedule CSV is available from `export_schedule.py` | YouTube Studio; TikTok Studio; Meta Business Suite |

**Publishing uncertainty:** If a Postiz request times out, it may have been received. The queue already marks that job `needs_manual_review`. Verify provider status before retrying, to avoid duplicate publication. The CSV schedule generator includes approved pending jobs only.

**No automatic API hopping:** ClipOps does not silently upload customer videos to a free-tier service, bypass quotas or authorization, or assume a paid option is free. Availability and features on public services may change. This is a manual fail-safe, not a hosted provider federation.

**YCloud:** Not configured as a ClipOps video-processing or publishing substitute. Future WhatsApp work requires the approved server-side secret boundary and separate permission for outbound messages.

Run `python -m unittest discover -v` for backend checks. The GitHub Actions workflow additionally exercises desktop/mobile Playwright interactions and generates its own authorized synthetic video fixture. Tests must pass before merging into `main`.
