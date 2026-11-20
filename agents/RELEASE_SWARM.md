# ClipOps Studio — scoped quality-agent playbooks

These are **bounded reviewer roles** for Codex or another coding agent when a connected executor is available. They are not autonomous background workers. CI supplies the deterministic release gates. AGENTS.md, the active repository permissions, and the owner's current approvals override this file.

## Coordinator — integration owner (high reasoning)

- Check current HEAD, all ClipOps draft PR heads, worktree status, and AGENTS.md before writing.
- Work on a snapshot/review branch. No force-push, destructive cleanup, or edits to active peer branches.
- Assign the independent read-only reviews below, with one owner per file group and clear test evidence.
- Apply only reviewed, narrow patches. Integrate after comparing source provenance and exact changed files.
- No autonomous merge, deployment, background heartbeat, outreach, spending, or publishing.

## Agent 1 — Storytelling and editorial QA (medium reasoning)

- Review candidate scoring, clip boundaries, captions, audio and source-video screenshot evidence.
- Check hook/context/payoff, cutoffs, jump cuts, factual claims, subtitle contrast and safe zones.
- Review Arabic RTL, Egyptian dialect, English/Arabic switches, Franco and speaker identity manually.
- Return exact reproduction, source timestamps, and PASS/FAIL/UNVERIFIED; never claim virality.

## Agent 2 — Security and privacy (high reasoning)

- Review local origin/CSRF protection, path validation, symlinks, 20 GiB upload quotas and restart safety.
- Verify approved hash-bound delivery, protected local storage, suspicious archive/FFmpeg inputs, and no secrets.
- Confirm default deny on remote network access, paid APIs, messaging, posting, or automatic retries.
- Report proof-backed vulnerabilities with minimum safe regression; never use client footage for tests.

## Agent 3 — Reliability, media and performance (medium reasoning)

- Confirm FFmpeg/FFprobe, H.264 in branded Chrome, subtitles, worker recovery and 1080p renders.
- Run synthetic and rights-cleared long-media tests separately; report actual CPU, RAM, disk and duration.
- Verify real 15–20 GiB checksum/restart/disk-pressure tests before claiming that size production-qualified.
- Inspect any QA screenshot and listen to a source/edited audio comparison with human review.

## Deterministic release gates

1. Run Python unit + integration suite, Node JavaScript syntax, and Chrome desktop/mobile Playwright smoke.
2. Require export locked before approval, exact-output QC and SHA match after approval, and an actual MP4 download.
3. Verify approved ZIP contains MP4/SRT/VTT + manifest, not unapproved clips/source footage/customer data.
4. Generate a tracked-file-only ZIP with SHA-256 build manifest. Check the artifact from the exact commit.
5. Mark **GO** for supervised single-user local tests only after those gates pass.
6. Mark **NO-GO** for unattended public hosting/publishing until real rights-cleared 45–60 min editorial acceptance, true 15–20 GiB physical upload QA, multi-user authentication/tenant isolation, platform rights and live account integration.

## Cost and context efficiency

Use small file slices, targeted diffs and focused tests before full gates. Select the least costly capable model actually offered by the connected runtime; reserve high reasoning for security and merge conflicts. Reuse existing source, checkpoints and claims instead of regenerating apps. Report **changed/tested/blocked** with evidence and stop.
