# ClipOps Studio local video pilot

The production path runs on a single trusted workstation. ClipOps ingests an authorized video and a timed transcript, ranks moments, renders selection revisions, records technical QC, and delivers an exact approved MP4 with editable SRT and VTT. The review desk binds to loopback. Local project folders own their source, captions, brand settings, candidate decisions and render cache.

## Start the review desk

On Linux, install Python 3.11+, FFmpeg and FFprobe with libx264 and libass, Fontconfig, and DejaVu Sans and Liberation Sans fonts. On Debian or Ubuntu the media and font packages are `ffmpeg fontconfig fonts-dejavu-core fonts-liberation`. FFmpeg must provide Arabic shaping through libass with HarfBuzz and FriBidi. The tested runner used Debian and FFmpeg 7.1.5. macOS and Windows have yet to be qualified.

```bash
cd /workspace/clipops-rc
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-pilot.txt
./launch-studio --root "$PWD/out/pilot" --port 8765
```

Open `http://127.0.0.1:8765`. The launcher prints the local URL. Import MP4, MOV, MKV, or WebM with audio plus a UTF-8 JSON transcript, or configure the optional offline ASR path below. Each cue uses source-relative seconds and supports optional speaker labels and genuine word timestamps.

Add `--source-dir /absolute/path/to/footage` to let the desk open authorized files from that folder without copying them. Keep the original unchanged while the project is active. Select **Build browser preview** when a codec plays poorly in the browser. It makes a smaller local MP4 proxy, while export uses the original.

For browser uploads, progress counts checksum-verified bytes on disk. Uploads can pause and resume after a reload or Studio restart. Choose the same unchanged file to resume, then the client verifies the saved prefix before continuing. Uploading a 20 GiB file requires at least that much free space plus a small working reserve. Completed uploads transfer ownership to the project without a second full-size copy.

```json
{"segments":[{"start":0.8,"end":4.2,"text":"The opening line.","speaker":"Host"}]}
```

Optional local speech recognition uses faster-whisper and a previously downloaded multilingual CTranslate2 model directory. Install the wheel once and obtain models before loading customer media. The program uses local model paths and file-only FFmpeg inputs during processing. On this runner the prepared Python is `/workspace/clipops-asr-env/bin/python` and the model directory is `/workspace/clipops-models/tiny`.

```bash
.venv/bin/python -m pip install 'faster-whisper==1.2.1'
.venv/bin/python studio.py --root "$PWD/out/pilot" --port 8765 --model /absolute/path/to/ct2-model
```

For a prepared transcript, open the project, search or seek from a cue, review the ranked cuts against the source, and adjust boundaries, captions, framing, brand, or metadata. Select several candidates for batch rendering. Preview each finished render and inspect the QC details. A named reviewer confirms exact final content and rights before the MP4 and caption files appear in local delivery. Caption, timing, rendering or copy edits require a new approval for affected output.

Use **Review pause and filler cuts** to inspect suggestions and save intervals you have listened to. Source seconds remain visible in the edit and the playback timeline uses the shortened render duration. Audio ramps soften the joins and sidecars follow the edited timeline. Use **Render settings** for light noise reduction, a gentle push-in, or speaker-based framing with calibrated positions.

Use **Set In** and **Set Out** or **I** and **O** with the source timeline focused to capture the playhead to the nearest millisecond. **View source** and **View render** switch between the same moment before and after the edit. **Edit punch-ins** accepts timed source ranges with 1.02–1.18× zoom. The selection history records changes. Speaker correction leaves existing aligned word times in place when the spoken text and cue timing stay the same.

## Run the first authorized 45–60-minute video

From the repository, choose either command. The `--rights-confirmed` flag attests permission to process this source. It is separate from clip delivery approval. Use a private project root with mode 0700.

```bash
.venv/bin/python pilot.py --root "$PWD/out/pilot" run /absolute/path/to/source.mp4 \
  --reference --model /absolute/path/to/multilingual-ct2-model --language auto \
  --rights-confirmed --style podcast --platform shorts --candidates 24 --render-count 5
```

```bash
.venv/bin/python pilot.py --root "$PWD/out/pilot" run /absolute/path/to/source.mp4 \
  --reference --transcript /absolute/path/to/transcript.json --rights-confirmed \
  --style podcast --platform shorts --candidates 24 --render-count 5
```

A job ID prints before processing. Save the JSON output in private storage to retain the ranking and quality record. Use `--render-count 0` to choose cuts before encoding. Use `--audience education` or another supported audience to change the ranking. For local ASR, `--language en`, `ar`, `ar-EG`, and `mixed` are supported choices. Dialect and code-switching accuracy require a bilingual review. For separate speaker audio tracks, provide a JSON mapping such as `{"0":"Host","1":"Guest"}` via `--speaker-tracks`. The mixed-track route uses an optional trusted ONNX model via `--speaker-model` and the `sherpa-onnx` runtime. Check every speaker label in the final clip.

```bash
.venv/bin/python pilot.py --root "$PWD/out/pilot" resume PROJECT_ID --clips c01 c04 c09
.venv/bin/python pilot.py --root "$PWD/out/pilot" report PROJECT_ID
.venv/bin/python pilot.py --root "$PWD/out/pilot" review PROJECT_ID c01 approved --editor "Reviewer name" --rights-confirmed
.venv/bin/python pilot.py --root "$PWD/out/pilot" export PROJECT_ID c01 /absolute/path/to/new-delivery-folder
```

The CLI also supports `suggest-cuts PROJECT_ID c01` and `edit PROJECT_ID settings.json`. To remove one reviewed interval, the settings file can contain `{"candidate_id":"c01","remove_ranges":[[12.4,13.2]]}` with source-relative seconds. Render that candidate again to preview the result.

Approval applies to the rendered revision, as reviewed by a human. Review story completeness, claims, audible meaning, A/V sync by eye/ear, crop and faces, line breaks, bilingual captions, and platform UI overlap. Automated checks cover the encoded streams, alignment tolerance, duration, decoded frames, measured audio peaks, black/freeze intervals, caption timing/layout, source bounds and duplicate evidence. See the [editor benchmark and pilot rubric](docs/EDITOR_BENCHMARK.md) for hands-on review criteria.

On interruption use the same job ID with `resume`; completed bundles and ASR chunks are reused. A worker holds a nonblocking per-workspace processing lock. Per-project mutations are locked separately. For a failed QC result, inspect the report and revise the selection or settings before rendering again. Deliberate freeze frames or silence may need a different source range for the pilot gate.

## Rendering and delivery

- Export presets include Shorts, Reels, TikTok, square, and landscape. The runner produces H.264/AAC MP4 at 720p, 1080p, or source-supported 2160p. Review every alternate aspect ratio. Native source detail and safety margins depend on the footage and current platform UI.
- Presets cover business education, value-driven clips, podcasts, cinematic storytelling, Egyptian education, fashion, workshops, gaming, and minimal professional presentation. The styles control density, highlight behavior, type and color.
- The default preserve-frame layout retains on-screen context. Use center crop after previewing. Face-aware framing needs the optional local OpenCV install. Speaker and split framing can use `--speaker-positions` with normalized horizontal coordinates per known label. Framing remains an editorial decision.
- The renderer API accepts local rights-confirmed logos, B-roll and low-gain WAV accents. Its default preserves the source delivery rhythm. Studio exposes timing, captions, reviewed cuts, brand, preset, cleanup and framing controls.
- To mix a reviewed WAV bed through `pilot_edit.render`, pass `music={"path": local_wav, "gain_db": -27, "rights_confirmed": True}`. The voice lowers the bed during speech. Listen to the finished blend at normal volume.
- The score is a ranking signal across the supplied transcript. It uses timing, hook/completeness and recurring topic evidence. Copy suggestions remain editable and require verification. The product scorecard is evaluated with suitable footage and named reviewers.

## Operations and release bounds

The browser desk is a single-OS-user application. Named assignments and approval record editorial attribution. Shared agency accounts, client-relay hosting, tenant authentication, and verified platform measurement require additional engineering. Keep project storage outside public and synced directories. Source, transcript, and cached files can be removed from Studio by explicitly confirming the name or via `pilot.py purge PROJECT_ID --confirm PROJECT_ID`. Delivered copies and backups follow your retention policy.

For travel or remote editing on your own trusted workstation, Studio can be reached over a separately authenticated SSH tunnel bound to `127.0.0.1` on both ends. The host still runs the normal loopback launcher. Public listeners and shared editor accounts require a separate access design.

The delivery packet is MP4, SRT, VTT, and, through the CLI export, a JSON record with approved copy, QC and source time range. A separately authorized distribution operator can take the approved files into MBM-Social or a platform's manual editor. The legacy Postiz scheduling adapter has mock evidence and needs channel-specific authorization and validation. See the [stack verification](docs/STACK_VERIFICATION.md).

Keep the paid transcript brief, the conditional video pilot and the subscription roadmap distinct in delivery material. Real clip count, review time and technical outcome determine the video pilot scope.

## Local regression command

```bash
env CLIPOPS_ALLOW_PUBLISH=0 POSTIZ_API_KEY= GEMINI_API_KEY= \
  .venv/bin/python -m unittest discover -v
```

The synthetic evidence and measured runs are indexed in the [sprint handoff](SPRINT_HANDOFF.md).

To reproduce the local evidence, use FFmpeg with Flite and librsvg plus an optional eSpeak NG Arabic voice for the generated fixtures. For the browser journey, install Playwright and Chromium in the test environment.

```bash
python3 tools/make_fixtures.py /tmp/clipops-fixtures --hour
python3 tools/render_samples.py /tmp/clipops-fixtures evidence
python3 tools/test_studio_browser.py --fixtures /tmp/clipops-fixtures --screenshots evidence
```
