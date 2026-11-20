---
name: clipops-editorial-intelligence
description: Review ClipOps transcript and source-grounded scene evidence to rank short-form hooks, clip boundaries, captions, and creative risks without changing source footage or approving exports.
---

# ClipOps Editorial Intelligence

Use for **reviewing** a long-form recording to propose short clips. Work on the existing ClipOps Studio pipeline; never silently replace its renderer, provenance, approval model, or creative-review tools.

## Inputs
- Source identity (private ID and SHA-256, not raw private footage in a prompt).
- Word-level timestamps, language, speaker metadata, scene-cut evidence, transcript confidence.
- User goals, platform/aspect ratio, target duration, customer voice/brand.
- Rights/consent status and whether any optional cloud analysis was expressly authorized.

## Procedure
1. Check that timestamps are ordered and within source duration. Flag missing, overlapping, low-confidence, or unsupported material.
2. Generate 3–10 independently source-grounded candidate ranges. Preserve exact spoken language; don't invent quotes, claims, or dialogue.
3. Score each 0–5: first-3-second hook, standalone clarity, payoff, visual context, retention/pacing, ethical/brand fit. Report **each score plus evidence**, not a magic virality probability.
4. For bilingual Arabic/English or Franco-Arabic, validate words and captions against the original audio; never auto-translate without an explicit request.
5. Recommend optional safe cuts, b-roll, framing, subtitles, and transitions. Never erase an essential qualifier or change speaker meaning.
6. Return a structured proposal with clip_id, source_start, source_end, exact_quote, evidence, score_components, cautions, and review_required=true.
7. Route proposals through existing ClipOps human approval -> original-media FFmpeg render -> independent QC; do not trigger publish, remote upload, or irreversible edits.

## Fail closed
- No direct editing tool invocation, publishing, rights assumptions, invented testimonials, or unsanctioned cloud media upload.
- Distinguish transcription uncertainty from verified facts.
- If source timecodes are missing, output a question/evidence gap instead of precise cuts.
- Agent recommendations are advisory; the owner's reviewed action is the only approval signal.

## Evaluation
- 100% proposed ranges must lie within source duration; zero fabricated transcript quotations.
- Verify captions against audio on a multilingual sample; confirm original image quality on final render.
- Track human acceptance, edit-revision rate, caption-word error rate, render failures, and time-per-approved-clip.
