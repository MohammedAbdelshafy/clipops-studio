# ClipOps Studio

Read `CONTEXT.md`, `PILOT.md` and `docs/TRY_CLIPOPS.md` before changing the local pilot. Use the existing `pilot*.py`, `studio.py`, `studio/`, and `studio_uploads.py` rather than recreating parallel implementations. Keep `batch_images.py` and the original tests intact.

Run `python -m unittest discover -v`, `node --check studio/app.js` and the existing real browser smoke test for UI changes. Measure representative footage and use human editorial acceptance before claiming commercial production readiness. The Remotion layout in `README.md` is historical roadmap, not implemented code.

The review desk is loopback-only and single-user. Customer material remains private. Publishing defaults to a dry run and requires rights confirmation plus a specific explicit opt-in. Never equate an upstream platform API submission with confirmed publication.

If a provider, quota or external API fails, use only the existing authorized **offline/manual** fallback routes (`free_fallbacks.py`), not a silent new cloud upload, duplicate dispatch, paid API or external notification. Record status and honor the original privacy/permission boundary.
