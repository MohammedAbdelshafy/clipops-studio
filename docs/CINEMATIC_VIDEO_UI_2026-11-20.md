# Cinematic video backdrop — local preview UI

This review-branch change adapts the motion-design ideas shown in the 2026-11-20 user reference video (OriginKit-style visual motion, reusable UI principles). It does **not** copy the video's footage, third-party components, or unlicensed assets.

## Design and behavior

- The library gets a responsive, original motion-gradient hero and decorative reel silhouettes; the import and project navigation remain intact.
- The **review desk** gets a cinematic stage around its existing player. Only a **locally rendered clip preview** can become the muted, blurred, looping backdrop. It never uses the original 15–20 GiB media as a background source.
- A visible, accessible **Ambient video** toggle lets the editor disable it. The preference stays in this browser only as an on/off flag (no source paths or customer content).
- Reduced-motion OS settings and browser data-saver settings disable the backdrop. If autoplay is blocked, editing and foreground playback continue normally over a static gradient. Background video is never an exported effect.
- Background requests stay on the existing authenticated, same-origin local /media route; no stock videos, CDNs, third-party trackers, dependencies, network uploads, or new publishing permissions.
- The established review, rights, technical QC and export gates are unchanged.

## Verification and remaining tests

The draft PR adds browser checks for on/off, source-versus-render behavior, and reduced-motion fallback in \`tools/test_studio_browser.py\`. CI runs \`node --check studio/app.js\` and the existing Python regression suites. A real browser journey requires local generated fixtures and Playwright; use:

\`\`\`bash
python3 -m unittest discover -v
python3 tools/make_fixtures.py /tmp/clipops-fixtures
python3 tools/test_studio_browser.py --fixtures /tmp/clipops-fixtures --screenshots /tmp/clipops-ui-evidence
\`\`\`

No production deployment, external outreach, automatic publishing or customer-media import is part of this change. This is a **draft review branch** stacked on PR #8, not a merge into the default branch.
