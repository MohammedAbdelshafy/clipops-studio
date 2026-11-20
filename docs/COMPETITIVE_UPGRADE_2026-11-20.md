# ClipOps Studio — competitive editing upgrades (local review candidate)

This is a **local-only source tree based on verified main `e93f9d54`**. It has not been published, pushed, merged or deployed. It preserves all old draft PRs.

## Implemented

1. **Find source moments** in the Creative review tab: prompt with exact topics, words, or quotes in English or Arabic, inspect real timestamped dialogue, play the original, and preview new in/out boundaries. Only clicking **Apply reviewed edits** changes the selected candidate; the existing renderer, QC and approval invalidation apply. This is transparent local lexical matching, not a claim to OpusClip-style multimodal AI or semantic text understanding.
2. **Inspect visual transitions** for the selected clip. FFmpeg samples 4 fps at 320px width, uses the frame-difference scene detector, and reports source-relative transition times. Nothing is cut or exported automatically. Scan caps: 180-second range and 45-second timeout. Results are advisory because frame differences miss action/silent highlights and can report camera cuts irrelevant to editorial meaning.
3. Optional PySceneDetect 0.7.3 dependency pinned in `requirements-visual-optional.txt` for later full-scene/shot experimentation; **not installed as part of the shipped workflow**, because this runner had no network access. The standard feature needs only existing FFmpeg.

## Operating boundaries

- No new cloud API, uploaded video, paid model, platform posting or auto-approval.
- No arbitrary URL media retrieval; source files are already authorized and accessed via the existing project source gate.
- Prompt matches cannot claim semantic relevance, only source token coincidence. Confirm source, fact meaning and context before applying.
- Visual analysis is a blocking on-demand bounded operation. For large or highly compressed 4K media it may time out; the rest of the Studio still works. A durable background worker would be the next improvement before enabling scans across all candidates.
- All source editing uses the existing safe proposal → reviewed edit → new render → QC → named approval → delivery.

## Next feature milestones (not shipped)

- Add multimodal source index (shot thumbnails, local speech embeddings, detected object/actions) after choosing an offline model and GPU budget; measure retrieval precision against a human-labeled set.
- Correct Egyptian Arabic/English/Franco ASR with a human-labeled benchmark. WhisperX word alignment is optional and **does not fix bad words**.
- Multi-shot story assembly with versioned EDL and clear scene/quote provenance.
- Client brand kits, motion/caption previews, licensed cutaway library and side-by-side reference clips.
- Full-length 45–60-minute client test, 15–20GiB real upload/resume, multi-user auth, and mobile device QA before commercial production.

## Verification

Run locally:
```
python -m unittest discover -q
node --check studio/app.js
python -m unittest -q test_competitive_upgrades.py
```

No claims about improved views, human acceptance, or superior competitive output until blind editorial comparison on the same authorized footage.
