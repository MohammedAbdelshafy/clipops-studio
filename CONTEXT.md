---
type: repository
status: active-local-pilot
owner_repo: MohammedAbdelshafy/clipops-studio
product_name: ClipOps Studio
source_of_truth: https://github.com/MohammedAbdelshafy/clipops-studio
---

# ClipOps Studio context

The production candidate is a **single-user, local-first review desk**, not a public hosted agency editing service. The implemented pipeline is: authorized local input or resumable transfer → reviewed timed transcript or preinstalled offline ASR → ranked candidates → editable selections and captions → FFmpeg render and QC → exact-output human approval → MP4/SRT/VTT export. Optional social scheduling remains a separately gated action.

## Code and tests

- `pilot.py`, `pilot_edit.py`, `pilot_intelligence.py`, `pilot_qc.py`: local media and approval workflow.
- `studio.py`, `studio/`, `studio_uploads.py`: loopback browser UI and resumable import.
- `free_fallbacks.py`: read-only, non-automatic alternatives to optional APIs and tools.
- `clipops.py`: legacy video CLI and opt-in Postiz connector.
- `batch_images.py`: original image batch service preserved.
- `test_*.py`, `tools/test_studio_browser.py`: unit, integration and real-browser smoke coverage.

## Operational limits

Use rights-cleared local media. Keep `CLIPOPS_ALLOW_PUBLISH=0` by default. Confirm named approval of exact rendered bytes before delivery. Do not silently retry uncertain Postiz submissions, send personal data to external apps, or activate paid providers on API failure. Use manual export and the free fallback directory instead.

[Try ClipOps](docs/TRY_CLIPOPS.md) · [Pilot instructions](PILOT.md) · [Fallback directory](docs/FREE_FALLBACKS.md) · [Measured release gates](docs/RC_HARDENING_RESULTS.md).

The Remotion generator in the README remains **historical roadmap**, not part of the implemented FFmpeg pilot.
