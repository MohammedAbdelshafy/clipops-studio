# ClipOps Studio — desktop integration & evidence audit
**As of November 20, 2026.** Target: `MohammedAbdelshafy/clipops-studio`; `main` after merge of PR #16: `9e5e55b7cb34307dd80096b8c8cfa44eed635e7a`. This file is a release/evidence checklist, not a substitute for running the desktop app on the user's Windows laptop.

## Reconciled and in main — verified

| Scope / source | Current desktop implementation | Evidence |
| --- | --- | --- |
| PR #8 local video pilot / 20 GiB **configured cap** | Private local intake, 8 MiB checksummed resumable upload, source directory reference, proxy, FFmpeg pipeline, local edit state | `studio_uploads.py`, `pilot.py`, `docs/RC_HARDENING_RESULTS.md`; physical 20 GiB transfer **not verified** |
| PR #9 UI and PR #11 offline fallback | Cinematic/reduced-motion desk, desktop and mobile browser UX, manual/offline fallback links, browser-compatible preview | `studio/`, `free_fallbacks.py`, `test_studio.py`, `tools/test_studio_browser.py`; cinematic `studio/index.html` and `studio/studio.css` content hashes match PR #9 |
| PR #10 creative editor and batch delivery | Source-based quotes/hooks, warnings and previewable edit commands, manual approval, output-hash-bound MP4/SRT/VTT and approved-only ZIP | `clipops_creative_review.py` and `studio_delivery.py` blob hashes match PR #10 source; approval and HTTP regression tests |
| PR #6 standalone transcript brief | Local no-cloud text briefing utility and its tests exist under `tools/transcript_brief/` | Exact tool and test blob hashes match PR #6; CI runs four focused tests |
| PR #12/#13/#14 integration and playback | Combined Studio, safe build packaging, Chrome H.264/WebM playback fallback, optional Google-account-gated Cloud Shell preview | Merged PRs #12/#13/#14. Cloud Shell is **not a persistent production renderer** |
| **PR #16 (merged Nov 20)** | English/Arabic source-moment lexical search, reference timestamps, local FFmpeg scene-change suggestions, nonmutating previews, verified editing/approval flow | [CI run 44743357972](https://github.com/MohammedAbdelshafy/clipops-studio/actions/runs/44743357972) green: **125 repository tests + 4 brief tests**, Chrome desktop/mobile, ZIP package |

**Release disposition:** `GO` for supervised, trusted-workstation desktop evaluation with **reviewed transcripts** and permissioned videos. `NO-GO` for unattended paid customer delivery, public service, high-volume multi-user uploads or automatic publishing. Green synthetic CI does not establish subjective editing quality.

## Preserve concurrent work: no blind branch merges

- Open legacy draft PRs **#5–#10** remain for provenance. Main already contains verified functional slices from #6, #8, #9 and #10. They have diverged histories or older base branches, so direct merges risk replacing newer code and causing conflicts. **Do not close, delete or force-push them** while other chats may be using them.
- `review/clipops-android-shared-intelligence-20261120` is a separate **Android-only** research branch, intentionally not included in desktop release. Pocket remains a companion, not parity.
- Separate ongoing Drive integration and Windows portability work was reported in another Codex session (`review/clipops-drive-integration-audit-20261120`), but **that branch is not present in GitHub's branch list** at this audit. Local reported results (26 focused passes, one skip, two Windows test defects; historically 28 larger-suite failures) are **not independently revalidated here**. Preserve that worktree; do not invent a remote merge or overwrite its uncommitted files.
- GitHub issues API returned **no open issue objects** for this repo at audit time; the acceptance tasks below are the explicit current checklist.

## Outstanding TODOs — exact acceptance gates

| Priority | Status | Work to perform on the real desktop release | Evidence necessary before declaring complete |
| --- | --- | --- | --- |
| P0 | **Blocked: local work missing** | Recover the *actual* Windows/Codex Drive connector changes and fix the two platform-specific tests. Build authenticated import only after reconciling local edits and user permissions. | Clean, new non-destructive review branch, exact changed paths/SHA, focused and broad test reports; no Drive tokens in Git; OAuth + real transfer separately approved |
| P0 | **Unverified on target PC** | Windows WSL2 startup, FFmpeg/font/codec support, paths, local read/write/cache, 1080p render, browser playback, approved ZIP. | Video and caption exports inspected on the actual Windows laptop, with runtime logs and snapshots |
| P0 | **Not accepted** | Genuine permissioned 45–60 min editorial test, from import through 10 shortlisted candidates to 3 approved high-quality 1080×1920 clips. | Human scoring of hook/context/payoff, crop, lip sync, true peak, caption safe areas, freezes, editor time and clip identity; separate QC vs creative acceptance |
| P0 | **Not physically tested at 20 GiB** | True ~15–20 GiB local/remote resume across browser/server/network interruption, checksum conflicts, disk headroom, and cancellations. Do not equate sparse and 1.28 GiB tests with full 20 GiB. | Physically allocated input, SHA-256, recovery offsets, RAM/disk/time, failure conditions, no duplicate ingest, input preserved |
| P0 | **Not accepted** | Egyptian Arabic, English and Franco/code-switch speech recognition and word timing on human-transcribed samples. | Separate WER and caption-timing reference metrics, correct names, RTL/BiDi and speech-cut comparison. Historical synthetic mixed WER was poor; human correction remains mandatory |
| P1 | **Not implemented** | Versioned edit decision list, multi-shot storytelling assembly, explicit undo/review after trim, and opt-in licensed B-roll with provenance. | Exact sourced frames, approval invalidation, rollback and render/QC tests |
| P1 | **Partly implemented** | Extend optional visual and transcript search to a queued/indexed multimodal approach with cache, safe cancellation and bounded concurrency. | Measure result precision on human labels; no unsupported virality/semantic claims |
| P1 | **Not production ready** | Multi-editor/client authorization, role and tenant isolation, secure media storage, untrusted FFmpeg sandboxing and release risk triage. | Security threat model, tenant/cross-project negative tests, vulnerability triage and deployment-specific approvals |
| P2 | **Deferred until desktop passes** | Native Android parity and optional Hatchable/AppDeploy management interface. | No change to desktop engine or media privacy; deployment only with explicit approval |
| P2 | **Not verified** | GitHub default-branch CI and desktop source package on fresh merge. | Desktop offline, Chrome E2E and package jobs green at exact merged SHA (new workflow `push: main` gate) |

## Safe continuation instructions

1. Before touching any laptop worktree run `git status -sb`, `git diff`, `git log -1`, `git branch -vv`; never reset, clean or force-push unknown edits. Use a separate worktree/review branch.
2. Reconcile each task against the exact GitHub `main` SHA; focus on modified files, not a new app implementation. Check source privacy/secrets before public repo commits.
3. Preserve single-user local bind and approval gates. No unsolicited network uploads, customer outreach, live Postiz/Publora dispatch, paid model calls, public services, or merging unverified local changes.
4. Run focused unit/integration tests, full suite, desktop/mobile browser smoke and package checks. Use [quality-agent rubric](../agents/RELEASE_SWARM.md); a checklist is **not** evidence that autonomous agents ran.
5. For each P0 test capture exact inputs (permissioned only), runtime, logs, observed output, screenshots, technical/QC and human editorial approval. Only then advance from supervised desktop beta to client delivery readiness.

The Android native APK is intentionally **not** the desktop editing factory. It remains in this public repository as a separate `android/` project; future efforts should prioritize desktop QA, not phone parity.
