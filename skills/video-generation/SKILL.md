---
name: clipops-video-generation
description: Turn an approved scene brief into a reproducible portrait promo using the ClipOps FFmpeg text-card renderer.
---
# ClipOps Video Generation

1. Confirm rights to input text, brand identity and any optional font. Read `README_NEW.md` / current root README for supported commands.
2. Create `examples/promo.json`-compatible JSON: `background: #RRGGBB`, `scenes: [{text,seconds}]` (1-20 scenes, 0.5-20 sec each).
3. Run `python3 clipops.py promo brief.json --out out/promo.mp4`. Requires local FFmpeg and a supported font. No paid model calls.
4. Run `python3 clipops.py qc out/promo.mp4` and visually review readable text. Handle Arabic with an appropriately licensed font and manual QA; do not claim automatic RTL perfection.
5. Do not confuse these deterministic text cards with AI video generation, scene animation, talking avatars or uncommitted Remotion functionality.

References: https://ffmpeg.org/ffmpeg-filters.html ; https://ffmpeg.org/documentation.html
