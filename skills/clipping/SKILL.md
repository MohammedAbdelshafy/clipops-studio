---
name: clipops-clipping
description: Convert an authorized source video into reviewed, captioned vertical clips with FFmpeg.
---
# ClipOps Clipping

1. Verify media rights, file duration and audio/video streams with `python3 clipops.py inspect source.mp4`.
2. Use `suggest` on a reviewed transcript to generate *candidate* timestamps. Results are heuristic, not professional creative judgment.
3. Choose start/end after reviewing the source content. Use `clip source.mp4 --start 12 --end 37 --fit blur --captions out/transcript.json --out out/clip.mp4`. Use `--fit crop` only after checking speaker framing; blur is safe for off-center speakers.
4. Run `qc` and manually review crop, voice synchrony, hook quality, font placement, client branding, music rights and end frame.
5. Require explicit signoff before scheduling or publishing a customer video. Do not process someone else's material without permission.

Reference: https://ffmpeg.org/ffmpeg-filters.html ; MBM-Social `Factories/ClipFactory/clip_generator.py`.
