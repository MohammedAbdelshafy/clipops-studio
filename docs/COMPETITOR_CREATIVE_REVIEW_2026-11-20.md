# ClipOps Studio — competitor-inspired feature parity (20 November 2026)

**Branch:** `review/clipops-creative-review-20261120`, based on the synced release candidate in draft PR #8. **Review-only: not merged or deployed.**

## Sources and scope

- Jimmy Walsh, [I Tried Every FREE AI Clipping Tool](https://www.youtube.com/watch?v=6yzsJZ7rrP4), 16 November 2026. Opinions and free-plan limitations in this video are observations, not independently verified lasting guarantees.
- Official product references: [NXTCLIP](https://nxtclip.com), [Maveform](https://www.maveform.com), [OpusClip](https://www.opus.pro), and [Short.now](https://short.now).
- Reuse ideas and openly documented techniques; **do not copy proprietary interfaces, code, branding, media, or protected assets.** Validate any open-source license before integrating.

## Added in this branch

1. **Creative review tab:** source-grounded opening-hook suggestion and timestamped, verbatim quote bank for the selected candidate; never fabricated dialogue.
2. **Editorial warnings:** potential mid-cue starts/ends, overlapping cues, high speech density, speaker transitions, and a conservative English/Arabic profanity lexicon. **Flags are suggestions; nothing is censored or deleted automatically.**
3. **Bounded editing assistant:** supports `start MM:SS; end MM:SS; title: Text; cta: Text; remove MM:SS to MM:SS` with an explicit preview. Unsupported/ambiguous commands fail closed.
4. **Approval preservation:** generating a proposal has zero edit, media, upload, or publication side effects. Clicking *Apply reviewed edits* routes changes through the existing project edit API, which invalidates affected approvals and requires rerendering and renewed review.
5. **Read-only CLI:** `python3 clipops_creative_review.py /private/clipops-root/PROJECT_ID` emits a JSON report. Its input is limited to that project's `project.json` and an immutable `transcript-<id>.json` revision. Redirect stdout only to a trusted/private file if retaining the report.
6. **Focused tests:** `python3 -m unittest -v test_clipops_creative_review.py` and HTTP endpoint regressions in `test_studio.py`.

## Feature matrix: preserve what already exists, prioritize actual gaps

| Inspiration | ClipOps capability / decision | Status |
|---|---|---|
| NXTCLIP conversational edits | Explicit, review-only structured edit proposals; future opt-in language-model parser must output the same validated schema | **Added limited version** |
| Maveform quote library / source provenance | Timestamped quotes with speaker and original dialogue | **Added** |
| OpusClip hooks / editorial scoring | Existing ranked clips with reasons; new source-only hook cards, without fictitious viral likelihood | **Existing + added** |
| BudgetPixel and Clypse profanity handling | Manual review flags now; later add reversible bleep/mute/blur with preview and licensing/platform policies | **Added flags; effects pending** |
| Clypse speaker-colored captions | Existing speaker labels, layouts and correction; add per-speaker caption styling with readable contrast and bilingual QA | **Pending** |
| Maveform many clips / multiple models | Existing 24 suggested candidates, up to 30, local ASR; compare local model options only with user-approved resource budget | **Mostly existing** |
| Vizard / OpusClip caption designer | Existing nine editing presets and editable transcript; enhance live caption preview, preset thumbnails and reusable client templates | **Existing + pending UX** |
| Short.now project overview | Existing source timestamps, candidate explanations, status and QC; export a human-readable project brief | **Mostly existing** |
| Zora-Labs ZIP batch download | Create approval-gated ZIP with MP4, SRT, VTT, source ranges and SHA-256 manifest | **Pending** |
| OpusClip B-roll and animated graphics | Existing cutaways, overlays and accent transitions; add searchable licensed asset library, provenance, motion templates and human approval | **Partly existing** |
| NXTCLIP watermark-free delivery | ClipOps renders native deliverables without imposed vendor watermark; verify any third-party assets/voices separately | **Existing local design** |
| External tool monthly credit limits | Keep local processing usable without per-clip SaaS limits; track hardware, electricity and model licensing as real costs | **Architecture principle** |
| Browser links / YouTube imports | Local footage stays private; remote URL intake only after rights checks, allowlisting, SSRF prevention, and consent | **Not enabled** |
| CapCut as manual fallback | Permit local manual editing/export path and interoperability, avoid dependency on competitor service availability | **Pending integration** |
| Background completion notification | Local notification only, no email/SMS without explicit opt-in; persist reliable job status | **Pending** |

## Next engineering slices (not claimed to ship in this branch)

**P0 / before paid customer trial:** run the full regression suite, browser E2E of the new tab and edit preview, a real rights-cleared hour-long bilingual video, and the actual 15–20 GiB resume/restart/disk-pressure test. Verify caption quality by sight, audio sync by ear, Arabic/Franco transcription, and exact invalidation of prior approvals. Run static/security checks and make a draft PR go green before any merge.

**P1 / professional quality:** add speaker-specific caption palettes with colorblind-safe fallbacks, user-adjustable timing and live preview; manual profanity bleep/mute/blur with reversible edit decisions; ZIP delivery manifest; local completion notification; client brand kits and batch export profiles; local library of licensed B-roll; title and description variants grounded in source, not generated factual claims.

**P2 / advanced editing:** optional model-backed chat instructions behind a pluggable *local-first* provider layer; semantic similarity and duplicate detection; visual scene/face tracking with explicit consent; auto-suggested punch-ins and animation presets; adaptive caption emphasis and Arabic shaping; real edit retention and watch-time outcome analytics where consent and connected channel data exist.

## Verification and operational bounds

- The new **offline helper** passed 7 local unit tests on 20 November 2026. JavaScript syntax was checked against the GitHub branch content. Full integration/CI and customer-footage acceptance remain to be verified.
- Earlier PR #8 reported 89 tests for its own synced release candidate; that number is **not evidence** that this branch's new integration passed.
- Review labels and source quotes are aids for editors, never substitute for checking meaning, permissions, profanity context, quality or factual accuracy.
- No cloud credentials, automatic social publishing, remote media uploads, or destructive changes are authorized by this change.
