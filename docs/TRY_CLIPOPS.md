# Test ClipOps Studio locally — integrated review build

This build is an **offline-first, single-user pilot**, not a hosted multi-tenant agency app. It must run on a trusted workstation with Python 3.11+, FFmpeg/FFprobe, libass, Fontconfig, and Pillow. It does not need a paid model or API key if you provide a timestamped transcript.

## Quickest supported test: Ubuntu / Linux, including Windows WSL2 Ubuntu

1. Install the free dependencies:

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip git ffmpeg fontconfig fonts-dejavu-core fonts-liberation
```

2. Download the **verified integrated test package** from the successful GitHub Actions run for the [integration review PR](https://github.com/MohammedAbdelshafy/clipops-studio/pulls) (artifact named **ClipOps-Studio-TEST**). The package is generated *only if backend and desktop/mobile browser gates pass*. Extract `ClipOps-Studio-TEST.zip` and open the extracted `ClipOps-Studio-TEST` directory.

   Alternatively, download the exact [integration branch source archive](https://github.com/MohammedAbdelshafy/clipops-studio/archive/refs/heads/review/clipops-integrated-test-build-20261120.zip) if the CI artifact is unavailable. This source archive is NOT the tested release artifact and does not include its SHA-256 build manifest.

3. Launch from Ubuntu/WSL2 inside the extracted folder:

```bash
bash START_CLIPOPS.sh
```

   On Windows with WSL2 Ubuntu installed, you can also open PowerShell in the extracted folder and run `./START_CLIPOPS_WINDOWS.ps1`. This starts the Linux pilot; native Windows and macOS are not qualified. The first launch installs the free pinned Pillow dependency if missing. No cloud API keys are required.

Open **http://127.0.0.1:8765** on the same workstation. For WSL2, open that address in your Windows browser while the Ubuntu terminal is running. The terminal remains running until you press Ctrl+C.

4. Import a video you own or have permission to process together with a timestamped UTF-8 JSON file:

```json
{
  "segments": [
    {"start": 0.3, "end": 4.1, "text": "This is our first moment.", "speaker": "Host"},
    {"start": 4.2, "end": 8.8, "text": "And this is the next moment.", "speaker": "Guest"}
  ]
}
```

Choose **Import project**, confirm processing rights, analyze, inspect candidates, edit captions and timing, render, and review the output. Export MP4, SRT and VTT only after a named reviewer confirms editorial approval and rights.

## New source-grounded competitive review (local build only)

In **Creative review**, use **Find source moments** with English/Arabic source words. Each result shows the original timed excerpt. **Play source** listens without editing; **Preview clip boundaries** creates an unapplied proposal for the selected candidate. Only **Apply reviewed edits** changes it, invalidates any previous approval and requires rerendering and a new review. **Analyze visual scene changes** samples actual video frames with local FFmpeg and reports likely shot transitions. These are advisory frame-difference hints, not safe automatic cuts. No provider or paid model receives the media.

## Test without customer video

The optional synthetic fixture generator makes an original voiced source locally and a matching timestamped transcript (FFmpeg needs its `flite` and `librsvg` support):

```bash
python3 tools/make_fixtures.py /tmp/clipops-fixtures --only studio --espeak ''
./launch-studio --root "$HOME/ClipOps-private" --source-dir /tmp/clipops-fixtures --port 8765
```

Choose `studio.mp4` in the local source picker and upload `studio.json` as the transcript. This is a fixture for reviewing functionality, not a demonstration of Arabic transcription quality. If fixture generation is unsupported by your FFmpeg build, use any rights-cleared MP4 and a manually timed transcript instead.

## Long 15–20 GiB sources

Prefer `--source-dir /absolute/path/to/footage` on the same workstation: it references the original without copying it. Browser transfers use 8 MiB checksum-verified resumable chunks and need enough spare storage. The previous validation included sparse-size and smaller physically allocated transfers; **full 20 GiB physical upload, multi-tenant remote access, Windows native and macOS qualification remain unverified**.

## When a service or API fails

Select **Free fallbacks** in the top bar. Offline timed transcripts, local FFmpeg, export bundles and approved CSV scheduling require no paid APIs. Optional links to whisper.cpp, Kdenlive, Shotcut, GIMP and platform-native creator studios open manually. Videos are never automatically handed to third-party services.

## Security and publication

The editor binds to `127.0.0.1` and is intended for one trusted operating-system user. Do not expose port 8765 publicly, share project directories or copy customer media into this public repository. Postiz/WhatsApp/social posting is *not* automatically enabled. Check current `PILOT.md` and `docs/RC_HARDENING_RESULTS.md` before offering paid delivery.

## Functional QA checklist

- [ ] Import an authorized video and a timestamped transcript
- [ ] Search and correct transcript captions, including Arabic/English where applicable
- [ ] Inspect candidate framing, trim markers and cut intervals
- [ ] Render one 1080×1920 clip and inspect video/audio/captions
- [ ] Toggle the cinematic ambient backdrop (disabled automatically for reduced motion)
- [ ] Try **Free fallbacks** and verify external tools do not launch automatically
- [ ] Verify export stays locked until the exact render passes QC and is approved
- [ ] Download MP4, SRT and VTT; verify all remain correct after replay

The project is ready for **supervised local evaluation** when the merged build passes CI and the user completes this checklist. It is not certified for unattended public ingest or publishing.

## Integrated features to verify

- [ ] Open **Creative review**, analyze a clip, inspect exact source timestamps, and preview an edit instruction without applying it.
- [ ] Apply the reviewed edit, confirm the old delivery approval is invalidated, then rerender and reapprove.
- [ ] Export **Download approved batch ZIP**, inspect `delivery-manifest.json`, SRT, VTT and MP4, and verify source footage is excluded.
- [ ] Try **Free fallbacks** without uploading to any third-party service.
- [ ] Open the cinematic ambient preview and confirm reduced-motion preference disables it.

The CI package is a **single-user local test app**, not a standalone Windows executable or public hosted service. Editing footage requires FFmpeg and rights confirmation. Privacy and approval gates must stay enabled.

### Browser codec notes

The desktop/mobile editor tests also qualify a browser without MP4 codecs:
ClipOps transparently generates a local 540p VP8/Opus WebM **rendered preview**
only, while keeping the high-quality MP4 for human-approved downloads.
The proxy is cached inside the private project render bundle and is removed
when the render is invalidated. For long source video playback, choose a
desktop browser with working H.264 support; the proxy builder for original
source footage is a separate, explicitly requested local process.
