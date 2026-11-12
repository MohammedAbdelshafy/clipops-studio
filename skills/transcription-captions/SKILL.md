---
name: clipops-transcription-captions
description: Transcribe media with local faster-whisper, create timed subtitles, and review captions before rendering.
---
# ClipOps Transcription + Captions

1. Ensure you own or may transcribe the footage. Avoid sensitive or client recordings without permission.
2. Install optional `faster-whisper` only when needed. First use of a model name may download weights; to stay offline, use a preinstalled local model path.
3. Run `python3 clipops.py transcribe video.mp4 --out out/transcript.json --model small`. Confirm model language (Arabic/English) and punctuation manually.
4. Output schema: `{"segments":[{"start":0.0,"end":1.2,"text":"..."}]}`; times are seconds relative to source beginning.
5. Generate subtitles with `python3 clipops.py captions out/transcript.json --out out/subs.srt --words 6` or `.vtt`. For burned-in captions, pass transcript JSON to `clip --captions` so clip offsets are handled.
6. QA proper nouns, silence hallucination, speaker changes, translation accuracy and RTL shaping. Word timings are not proof of correctness.

References: https://github.com/SYSTRAN/faster-whisper/blob/master/README.md ; https://ffmpeg.org/ffmpeg-filters.html
