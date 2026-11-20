# ClipOps Studio hardening review

The original RC is preserved at `5b99597a1baee779ed156e6fcc38f9659726bb25`. PR #8 stacks the code on PR #5. PR #7 supplies the acceptance specification alongside it. [Implementation review](https://github.com/MohammedAbdelshafy/clipops-studio/pull/8) · [Hardening specification](https://github.com/MohammedAbdelshafy/clipops-studio/pull/7)

## Verified behavior

| Requirement | Implementation and evidence | Release gate |
| --- | --- | --- |
| Preserve and synchronize the release | Exact base SHA verified on GitHub. The 89-test baseline passed. The updated local suite passed 95 tests. Release and update trees were reviewed for private data and scanned with Gitleaks v8.30.1. | Draft review. |
| Avoid duplicating large local files | `--reference` and Studio's configured source folder bind a regular file to its observed identity and create an optional asynchronous browser proxy. An MP4 with a sparse extended box at the 20 GiB boundary opened without an original-size copy. It produced two candidates and a browser proxy. | Confirm behavior with physically allocated 15–20 GiB media on the intended disk. |
| Recover from interrupted transfer | The loopback HTTP transfer used 8 MiB tus offset/checksum chunks to send **1,283,928,385 physical encoded bytes**. The Studio process stopped midway and a new process resumed at **645,922,816 bytes**. Source SHA-256 matched at completion. The concurrent test observed 24.6 seconds for transfer, 2.4 seconds for finalization, and 38.5 MiB server process high-water memory. A 20 GiB upload reservation on the smaller runner correctly returned HTTP 507. | A physically allocated 15–20 GiB end-to-end run is unverified. The 20 GiB contract test was sparse and local. |
| Complete a real long-form run | A 51:24.625 Creative Commons recording yielded 578 timed segments and 24 candidates. Five rendered at 1080×1920. One passed all automated checks. Four were held by the two-second freeze detector. Offline tiny-model ASR took 134.0 seconds, full processing took 283.3 seconds, and peak process/child memory was 650.2 MiB. | Reviewer must compare held intervals with the original and verify the story, timing, caption text and framing. |
| Improve editorial review | Source and render comparison maps the playhead across removed ranges. In/out marks capture source milliseconds. Timed punch-ins ramp into a 2–18% zoom, and stay within one retained interval. Caption speaker edits preserve valid word timing. Editing history records recent selections. The renderer adds opt-in, rights-confirmed WAV ducking. The ranker flags context-dependent starts and last words likely to continue. | Human editorial and caption review. The earlier mixed Arabic/English synthetic result still requires reviewed captions. |
| Accessible local startup and browser workflow | `./launch-studio` opens the loopback editor. Chromium desktop and mobile exercised upload resume across page reload, caption edit, timed punch-in, comparison, playback, rights gate and approved MP4/SRT/VTT downloads. | Linux Chromium is tested. Other operating systems, browsers, accessibility audits, and distributed teams remain unverified. |
| Secure access and files | Loopback Host checks, same-origin writes, HTTP-only session cookie, CSRF, private directories, file-only decoder protocols, stable offsets, per-chunk and saved-prefix integrity, disk reservations, expiration, cancellation and media signature/probe gates. Completion atomically links the private staged media to the project. The review gate still binds export approval to the actual output bytes. | A shared-client or public upload service needs independently authorized and verified authentication, tenant isolation, encrypted storage and sandboxed media workers. GPU encoding and memory scaling on the intended workstation remain unverified. |

The recording is *Future Audiences community call 6 February 2025*, attributed to Johan (WMF), under CC BY 4.0. Frame review showed that slide text became small in the 9:16 full-scene layout. Review the landscape preset or reframe around the essential subject for slide-heavy sources. The test ran on Debian 13 with a two-CPU quota and no exposed GPU. Rights-cleared synthetic and Creative Commons test media stay out of the public Git repository. [Recording and attribution](https://commons.wikimedia.org/wiki/File:Future_Audiences_community_call_6_February_2025.webm) · [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)

## Design references

- Studio's transport implements tus offsets, SHA-256 checksums, expiry and termination with Studio-specific create/complete controls. Reviewable local uploads use one writer and 8 MiB chunks. A remote editor can use their own authenticated, loopback-bound SSH tunnel. A managed Uppy/tusd or S3 service requires approved private infrastructure. [tus protocol](https://tus.io/protocols/resumable-upload) · [Uppy tus](https://uppy.io/docs/tus/) · [OWASP upload controls](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)
- Existing competitive research covers OpusClip, Crayo and Captions. The new workflow applies the common concepts of source inspection, editable framing, exact duration control and reviewable exports. [Editor benchmark](EDITOR_BENCHMARK.md) · [FFmpeg filter reference](https://ffmpeg.org/ffmpeg-filters.html)
- WhisperX (BSD-2-Clause) documents alignment and diarization, auto-editor (Unlicense) documents timeline-driven media editing, and autoclip (MIT) documents an automated clip workflow. Clipgen had no SPDX license identifier returned by GitHub. This change uses ClipOps code and public specifications. [WhisperX](https://github.com/m-bain/whisperX) · [auto-editor](https://github.com/WyattBlue/auto-editor) · [autoclip](https://github.com/artbyjazi/autoclip) · [Clipgen](https://github.com/gnilobaiter/clipgen)

## Reproduce

```bash
./launch-studio --source-dir /absolute/path/to/footage
env CLIPOPS_ALLOW_PUBLISH=0 POSTIZ_API_KEY= GEMINI_API_KEY= python3 -m unittest discover -v
python3 tools/test_studio_browser.py --fixtures /tmp/clipops-fixtures --screenshots /tmp/clipops-evidence
python3 tools/measure_ingest.py /absolute/path/to/authorized-encoded-video.mp4 /absolute/path/to/timed-transcript.json --scratch /path/to/free/disk
```

**GO for supervised local review. NO-GO for public or unattended client ingestion and publication.**
