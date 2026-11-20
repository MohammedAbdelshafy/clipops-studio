---
name: clipops-agentops-release
description: Execute review-only release quality gates for ClipOps desktop and Android, including FFmpeg regression, subtitles, security controls, optional AI evaluation, and evidence-based go/no-go decisions.
---

# ClipOps AgentOps Release Gate

Use before proposing a ClipOps PR, APK, customer pilot, publishing integration, or infrastructure change.

## Procedure
1. Record exact repository/branch/commit; detect any uncommitted local work and avoid overwriting it.
2. Identify changed code paths and select narrow tests first, then full Python and Android suites at a release milestone.
3. Verify local-first FFmpeg output: actual MP4 playability, H.264/AAC or target codec, 1080x1920 requested dimensions, black frame/frozen frame checks, audio clipping/loudness, timing and legible multilingual SRT/VTT.
4. Verify creative fidelity: in/out boundaries, quoted words, no misleading hard cuts, speaker framing and hook quality from source timestamps.
5. Verify security: authenticated sessions, CSRF/origin, no anonymous private video exposure, no bypassable approval gate, no absolute filesystem escape, no token/media logging, no publish when default policy forbids it.
6. Verify 20 GiB upload claims only against actual large transfer evidence; keep separate results for sparse-file tests, small fixtures, and real-device transfers.
7. Evaluate optional model suggestions against held-out annotated excerpts; record factual grounding, false-positive hooks, manual acceptance, latency and estimated cost. The free local path must remain functional.
8. Produce a go/no-go report with precise test commands, evidence IDs, commit SHA, failures and next smallest safe tests.

## Output contract
- Statuses must be VERIFIED, UNVERIFIED, or FAILED. No pass-by-assumption.
- Create review assets only. No merge, public deployment, publishing, paid API call, media upload, or outreach without owner approval.
- Call out missing real-media test evidence explicitly.
