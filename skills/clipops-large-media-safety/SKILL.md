---
name: clipops-large-media-safety
description: Audit and plan secure local-first ingestion, restartable transfer, checksums, disk protection, and bounded optional Gemini proxy analysis for 15–20 GB video files in ClipOps.
---

# ClipOps Large Media Safety

Use when designing or reviewing media intake (including Android laptop/cloud hybrid). Prefer existing code in ClipOps; do not claim large-file support from a small fixture.

## Procedure
1. Identify current session/auth model, paths, upload protocol, size limits, filesystem and drive quotas, private endpoint, and resume semantics.
2. Default to keeping 15–20 GB originals on a private local/workstation volume with sufficient free space plus reserve. No cloud transfer without explicit opt-in.
3. For any resumable transfer, require bounded chunks, idempotent offsets, per-upload randomized IDs, upload ownership, authenticated resume, expiring leases, byte caps, size reservations, and final SHA-256 validation.
4. Reject path traversal, symlink/reparse-point escapes, mismatched offsets, non-private paths, unapproved MIME/containers, duplicate conflicting chunks, and inconsistent resumes. Enforce CSRF/origin on browser endpoints.
5. Track states: NEW -> RECEIVING -> VERIFYING -> SCANNED -> READY -> PROCESSING -> REVIEW -> APPROVED -> EXPORTED, with explicit failure/cancel paths and a recovery journal.
6. Generate independent small FFmpeg proxies / transcript segments for optional cloud model review. **Do not submit a 15–20 GB original through Gemini Files API**.
7. Document known Google API constraints: Google Files API input comparison states 2 GB per file, 20 GB per project, 48h retention; Cloud Storage URI registration is 2 GB per file. Verify limits again immediately before enabling a model adapter.
8. Preserve full-resolution source for final FFmpeg cuts, caption burn-in, audio loudness and QC.

## Test gates
- Synthetic boundary/offset/tamper/restart tests; interrupted transfer; low disk; cancellation and cleanup; 20 GiB sparse-file planning (not evidence of a real 20 GiB data transfer).
- A genuine 15–20 GiB end-to-end transfer on the authorized target device before calling feature validated.
- Verify original and final SHA-256 where applicable, ffprobe codec/dimensions, private HTTP/session access, and no outbound network calls while cloud use is disabled.

## Boundaries
Never change ACLs, expose Cloud Shell or Tailscale Funnel, allocate paid GCP resources, or send customer media without separate authorization.
