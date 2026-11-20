# ClipOps Studio — 3D Motion + Editorial Skills + Desktop Acceptance
**November 20, 2026. Review-only.**

## Functional changes
- Same Python/FFmpeg ClipOps Studio, original media and review/approval gates.
- Project library features optional pointer-responsive **true CSS 3D depth** (perspective + rotateX/rotateY + translateZ), floating reel cards, calmer hover lift, and layered shadows. No external assets, telemetry, heavy WebGL dependency or AI calls. Video playback, editor controls, transcript and files are **not** transformed.
- Accessible `3D depth` toggle persists locally when storage is available. Disabled automatically under `prefers-reduced-motion`, narrow viewports, coarse/touch pointers and data saver. The user may switch it off at any time.
- `Creative review → Editorial skill checks` shows source-bound timing/quote verification, caption risk, and explicit `not_verified` for visual/audio quality, rights and story fidelity. The card never grants export approval.
- Reusable skills under `skills/clipops-*` are **agent guidance**, not secretly running agents. Keep cloud media and outbound publishing disabled until approved.
- Optional Microsoft Dev Tunnels no-VPN mode from parent PR #20 is for **small test clips only** (Microsoft per-user 5 GB/month transfer limit); Tailscale/Cloud Shell modes remain optional. No public or paid hosting is provisioned.

## Preserve your actual Windows work
User's Windows worktrees may have local, uncommitted modifications to Windows compatibility, Google Drive import, two-pass audio loudness, quality presets, and tests. **Before any checkout/merge on Windows**, run `git status -sb; git diff --stat; git log -1; git worktree list`. Never clean, reset, overwrite, force-push or blindly copy across worktrees. Prefer an independent new worktree with its own review branch. Main and this remote review branch alone DO NOT prove that unseen local edits are included.

## Supported desktop verification
- Python 3.12 on Windows/WSL2; FFmpeg/FFprobe with x264, ass, Fontconfig and fonts; static JavaScript parse via `node --check studio/app.js`.
- `python -m unittest discover -v` and `python -m unittest discover -s tools/transcript_brief -p 'test_*.py' -v`.
- Headless Chrome browser QA `tools/test_studio_browser.py` on generated synthetic source, which now checks desktop 3D depth hover + toggle, mobile and reduced-motion fallback, editorial skill cards and all original upload → clips → render → named human approval → MP4/SRT/VTT/ZIP download gates.
- Actual user Windows editor: verify screenshot and click/hover on true Chrome desktop. A browser fixture is not subjective visual quality proof.

## Physical test (requires permissioned source)
1. Select local owned or licensed **45–60 minute** media plus reference transcript; avoid sending full media over a 5 GB/month Dev Tunnel.
2. In ClipOps Studio: Import local source, find grounded English/Arabic moments, inspect visual transitions and editorial skill checks; compare against original audio.
3. Produce 10 candidates then choose 3, adjust timecuts, captions and speaker positions, render 1080×1920 high-quality MP4; measure measured loudness, true peak, captions, transitions, freezes, context/payoff.
4. Reviewer names the exact final output and explicitly confirms rights. Only then download MP4, SRT, VTT and ZIP. Capture SHA-256, technical QC and human creative rubric; approval must be invalidated by later edits.
5. Test actual 15–20 GiB transfer/resume separately on the workstation only, after sufficient disk space and stop/restart/cancel plan.

## Release boundary
Green CI enables supervised beta only. Do not claim Windows worktree sync, production multi-client authorization, massive Android transfer, automatic failover, Arabic/Franco ASR accuracy or real video editing excellence before physical evidence. Review PRs and merge only after conflict audit and approvals. No paid hosting, media upload to third parties, public deployment, outbound messages or live social posts.


## Existing-live-server safe test mode

On Windows, preserve the original Studio on 127.0.0.1:8765 and create an independent test worktree and private project root. The Android QA build supports an authenticated Microsoft Dev Tunnel `https://ID-8775.REGION.devtunnels.ms` to a second native Windows server bound to 127.0.0.1:8775. Pair using the local 20-minute, single-use console code; do not paste that code into chats or Git. This does not migrate or modify client projects.
