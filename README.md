# ClipOps Studio v0.1

> **Repo-state note (2026-10-06):** this checkout ships only the overnight
> image batch lane — `batch_images.py` (+ `test_batch_images.py`, 34 hermetic
> tests). The Remotion video-pipeline sections below (`template/`,
> `generate-video.mjs`, `workflow/`, `out/`) describe a **planned component
> that is not committed to this repo yet** — it is a roadmap, not shipped
> code. Past-tense "verified" claims under those sections refer to the
> 2026-10-04 spike environment, not to files in this checkout.

**Agent-native video-as-code pipeline (planned).** You don't edit timelines
— an agent writes a 7-stage plan (analysis → brand → script → motion →
build → choreography → review), each stage leaving a readable, editable,
overrulable markdown artifact. The video itself is a data structure
(`props.json`) rendered by a Remotion template. Pattern ported from
remocn-studio, proven in the 2026-10-04 spike.

**Status:** the video pipeline below is **planned** (spike-verified
2026-10-04 in a separate environment — the Remotion project is not in this
repo). What ships here today is the overnight image batch lane
(`batch_images.py`), dry-run capable with no key.

## Planned pipeline: layout (not in this repo yet)

> The tree below is the planned Remotion video pipeline — none of these
> paths exist in this checkout. Kept for reference until the pipeline is
> committed or this section is trimmed.

```
clipops-studio/
  template/               Remotion project (the renderer)
    src/Promo.tsx         Scene-schema + 5 animated scene kinds
    src/Root.tsx          Composition (dynamic duration via calculateMetadata)
    src/index.ts          registerRoot
    remotion.config.ts    Browser executable (CLIPOPS_BROWSER override)
    props.json            The per-video prompt file (written by generator)
    package.json          Pins: remotion@4.0.520, zod@4.4.3 (do not downgrade zod —
                          4.0.520 hard-requires zod 4.x)
    tsconfig.json
  generate-video.mjs      Brief JSON → props.json → remotion render → out/<slug>/<slug>.mp4
  workflow/
    WORKFLOW.md           How to run the 7-stage chain (subagents or solo)
    stages/               7 ready-to-use subagent prompts:
      analysis.md → brand.md → script.md → motion.md →
      build.md → choreography.md → review.md
  out/<slug>/             Per-video artifacts:
    brief.json, analysis.md … review.md, <slug>.mp4
```

## Quick start

> The Remotion block below is planned (see note at top). The batch lane
> block after it is what ships in this repo.

```bash
cd ~/workspace/clipops-studio/template && bun install   # once
cd ~/workspace/clipops-studio
node generate-video.mjs brief.json
```

`brief.json` example:

```json
{
  "product": "P4 Lead Cleaner",
  "tagline": "Dead lists in; Verified leads out; 48 hours",
  "price": "$499",
  "priceNote": "First 1,000 rows free",
  "cta": "Reply CLEAN for your free sample",
  "brandColor": "#7c3aed"
}
```

No `scenes` given → the generator auto-builds: title → bullets → price → cta.
Pass explicit `scenes[]` for full control (kinds: `title|bullets|price|logo|cta`,
each `{kind, lines[1-5], durationInFrames[15-300]}`).

## Full pipeline (planned — not in this repo yet)

Follow `workflow/WORKFLOW.md`: run the 7 stage prompts as sequential subagents
into `out/<slug>/`. Only a Stage-7 **APPROVE** goes to render.

## Render host requirement (planned pipeline)

Frame capture needs a real, working Chrome/Chromium. Set:

```bash
export CLIPOPS_BROWSER=/path/to/working/chrome
```

Known-bad: this VM's `/opt/meta-chromium/chrome` (Chromium 152) cannot load
any page in this environment (verified: `data:`, `file://`, `http://127.0.0.1`
all produce no output), so `remotion render` fails at frame capture with
`net::ERR_BLOCKED_BY_LOCAL_NETWORK_ACCESS_CHECKS`. **Bundling reaches 100%**
— the failure is the browser environment, not the project. Render on any host
with working Chrome (Playwright's bundled Chromium, chrome-for-testing, or
plain Google Chrome). Expected render for a 3–7s 720p promo: <60s end-to-end.

## What was verified on 2026-10-04 (spike environment — not this repo)

- `bun install`: 242 packages, clean.
- `node generate-video.mjs` with a P4 brief: `props.json` written and valid,
  `remotion render` **bundling reached 100%**.
- mp4 frame capture: blocked by the browser environment (above). Not claimed.
- Plan correction: the spike plan assumed `bunx` on PATH — it is not in this
  environment. `generate-video.mjs` now shells out to the template's own
  `node_modules/.bin/remotion` binary (deterministic, no PATH dependency).
- All 7 stage prompts reviewed as complete, self-contained subagent
  instructions with inputs, outputs, and acceptance criteria.

## The $299 offer (planned pipeline scope — not yet shippable from this repo)

- Up to **10 short-form promo videos** (720p, 3–7s each) via the 7-stage pipeline.
- You review the stage artifacts (script, brand, motion) **before** render —
  2 revision rounds included.
- Delivered: mp4 files + the Remotion project + all 7 stage docs per video,
  so you own the pipeline, not just the output.
- Turnaround: 48 hours per batch of 5.
- What it is not: no live-action filming, no licensed music/stock, no
  platform upload management. Renders happen on a working host (ours).

## Design decisions (planned pipeline)

- **Video as data, not timeline.** `props.json` is the video. Swap values, get
  a different video, never touch code.
- **Template frozen by default.** Only Stage 5 may edit template code, only
  for flagged gaps, only additive. The five scene kinds cover promos; new
  kinds are a scoped change, not a rewrite.
- **Artifacts are the product.** The 7 markdown files are what make this
  sellable: the client sees and overrules decisions before render, and the
  pipeline is auditable.
- **Not ported** (per plan): no desktop app, no editor UI, no preview server.
  Headless generation + mp4 is the product.

## Overnight image batch lane (Gemini Batch API)

`batch_images.py` — stdlib-only client that submits image-generation jobs to
the Gemini **Batch** API at 50% pricing and collects per-key results. Built
for overnight FanForge/ClipOps asset runs (product shots, ad creatives,
thumbnails) while the video pipeline handles motion.

- **Model:** `gemini-3-pro-image`. **Pricing (Batch, verified 2026-10-05):**
  $0.067 per 1K/2K image, $1.00/1M text input, $6.00/1M thinking+text output
  → **$0.0732 per 2K image** at default token assumptions. (4K Batch pricing
  is unverified — `estimate_cost` refuses it rather than inventing a number.)
- **Limits:** 24h turnaround target · job **expires at 48h** with no results ·
  results kept 6 weeks.
- **Auth:** the stored `custom.gemini` connector (live since 2026-10-05 —
  verified end-to-end against the real API) with `GEMINI_API_KEY` /
  `GOOGLE_API_KEY` env as fallback. With neither, the client runs in
  **dry-run mode**: it builds the exact JSONL payload and the cost estimate
  with zero network I/O. Keys are never printed or logged.
- **Transport:** batch endpoints verified against the official Batch API guide
  (ai.google.dev/api/batch-mode, 2026-10-05): `POST
  /v1beta/models/{model}:batchGenerateContent` → poll `GET
  /v1beta/batches/{id}` → download the output JSONL → parse per key. The
  Files API upload/download adapter is marked `NEEDS_LIVE_VERIFICATION` —
  run one live dry-run before first paid use.

```bash
cd ~/workspace/clipops-studio
python3 batch_images.py --prompt "product photo of a red sneaker" \
  --prompt "hero banner, neon gym" --name "fanforge-overnight"
# dry-run without a key: prints the JSONL path + cost plan, touches nothing
GEMINI_API_KEY=... python3 batch_images.py --file prompts.txt --name "run-1"
python3 -m unittest test_batch_images -v   # 34 hermetic tests
```

Lifecycle API: `GeminiBatchClient().run_overnight(prompts, name)` →
`create_batch` → `wait` (raises `BatchExpired`/`BatchFailed`) →
`download_results` → `{key: {ok, response|error}}`. Corrupt output lines are
recorded under `_failed_lines`, never fatal.
