# Google-inspired Agent Skills integration — 20 November 2026

## Scope and current status

This review branch integrates **one real offline source-evidence skill card** into the existing Studio Creative Review screen, preserving the original ClipOps review, upload, editing and approval paths. It adds three reusable local `SKILL.md` instructions as agent playbooks, **not as remotely running AI agents**. No Gemini/ADK runtime SDK, cloud inference, paid Google product, or third-party media upload has been enabled.

## Changed code

- `clipops_skill_checks.py`: read-only deterministic editorial evidence checks; checks source duration, full-in-clip quotes, transcript anchoring and caption-timing risk; explicitly marks visual/audio, meaning, permissions, rights, and performance forecasts as **unverified**.
- `studio.py`: adds the `editorial_skill_review` property to existing authenticated `GET /api/projects/{id}/{clip_id}/creative`, after the pre-existing `clipops_creative_review.review_candidate` calculation. Existing GET session checks are unchanged.
- `studio/app.js`: displays this advisory scorecard in **Creative review**; escapes text for safe insertion. The edit and export approval controls remain unchanged.
- `test_clipops_skill_checks.py`: tests timing and quote integrity, Arabic transcript content, tampered quote rejection, unverifiable cases, invalid input, and no implicit approvals.
- `test_studio.py`: HTTP regression ensures the card appears and cannot approve or call models.
- `skills/clipops-{editorial-intelligence,large-media-safety,agentops-release}/SKILL.md`: reusable instructions with minimal frontmatter, designed for progressively loaded skills.

## How to inspect

1. In the existing single-user Studio, open a project with an authorized video and timestamped transcript.
2. Select a clip, choose **Creative review**, then **Analyze this clip**.
3. Review source quotation(s), potential cut risks and **Editorial skill checks**.
4. Manually play original source, inspect visuals and captions, check rights, then explicitly apply an edit/rerender/reapprove using the existing ClipOps controls. The skill card never approves anything.

## Safety and claims

- A **verified** skill check means only that a deterministic structural property of the supplied transcript and metadata has been checked. It is not a verified audio transcription, a human-safe cut, a confirmed factual claim, a rights clearance, or predictive virality.
- No raw customer media leaves the laptop because of this integration. Other existing optional integrations retain their own owner approvals.
- Keep `CLIPOPS_ALLOW_PUBLISH=0`, `GEMINI_API_KEY=` and `POSTIZ_API_KEY=` when testing the local-only mode.
- Google guidance inspires the structured skill format and traceable specialist workflow; Google has not certified this implementation.
- Skill descriptions are small for metadata-only context; their instructions can be loaded only by an explicit agent runner. Runtime `clipops_skill_checks.py` does not interpret Markdown or invoke a model.

## Test commands

```bash
python -m unittest -v test_clipops_skill_checks.py test_clipops_creative_review.py test_studio.py
python -m unittest discover -v
node --check studio/app.js
```

The existing GitHub Actions release gate also covers backend, synthetic local FFmpeg rendering and Playwright browser smoke. Read CI status for the exact review SHA before claiming green integration.

## Still required for production readiness

- Genuine authorized 45–60 minute English/Arabic source; editorial human benchmark and cut-quality scores, plus any transcript word-error measurements with reference labels.
- Genuine 15–20 GiB upload/resume under interrupted transfers and disk-pressure on the intended laptop/phone.
- Physical Android pairing and hybrid engine test.
- No merges, pushes to default, deployments, external media sends, paid API calls, outreach or publishing without owner approval.

## Official references

- https://developers.googleblog.com/developers-guide-to-building-adk-agents-with-skills/
- https://google.github.io/agents-cli/reference/skills/
- https://docs.cloud.google.com/storage/docs/resumable-uploads
