"""Android adapter to the exact source-grounded ClipOps desktop analysis.

No network, FFmpeg subprocess or model invocation. Synthetic cues must not be
presented as a transcription of the actual source; users supply a timed transcript.
"""
import json
import math
import pilot_intelligence
import clipops_creative_review

MAX_MOBILE_ROWS = 12_000
MAX_TEXT_BYTES = 6 * 1024 * 1024


def analyze(payload, audience="general", limit=24):
    if not isinstance(payload, str) or len(payload.encode("utf-8")) > MAX_TEXT_BYTES:
        raise ValueError("Transcript file exceeds the offline mobile review limit")
    data = json.loads(payload)
    segments = data.get("segments") if isinstance(data, dict) else data
    if not isinstance(segments, list) or len(segments) > MAX_MOBILE_ROWS:
        raise ValueError("Expected a timestamped segments list (up to 12,000 rows)")
    rows = pilot_intelligence.normalize(segments)
    clean = clipops_creative_review.clean_segments(rows)
    candidates = pilot_intelligence.rank_candidates(rows, audience=audience, limit=limit)
    for i, item in enumerate(candidates, 1):
        item["id"] = f"c{i:02d}"
        item["creative_review"] = clipops_creative_review.review_candidate(clean, item)
    return json.dumps({"segments": clean, "candidates": candidates,
                       "analysis": "Exact offline desktop ranker and creative-review code",
                       "limitations": "No ASR inference, virality prediction or automatic rendering edits"},
                      ensure_ascii=False, allow_nan=False)


def sidecars(payload, start, end):
    """Return timeline-relative SRT and VTT for the requested selected video."""
    start = float(start)
    end = float(end)
    if not math.isfinite(start) or not math.isfinite(end) or not 0 <= start < end <= 7200:
        raise ValueError("Invalid source range")
    doc = json.loads(payload)
    rows = clipops_creative_review.clean_segments(doc["segments"])
    def stamp(seconds, srt):
        milliseconds = int(round(seconds * 1000))
        hh, rem = divmod(milliseconds, 3600000)
        mm, rem = divmod(rem, 60000)
        ss, ms = divmod(rem, 1000)
        return f"{hh:02d}:{mm:02d}:{ss:02d}{',' if srt else '.'}{ms:03d}"
    blocks_srt, blocks_vtt = [], ["WEBVTT", ""]
    counter = 0
    for row in rows:
        if row["start"] >= end:
            break
        a = max(start, row["start"]) - start
        b = min(end, row["end"]) - start
        if b <= a + .01:
            continue
        counter += 1
        text = row["text"].replace("-->", "→")
        time_srt = f"{stamp(a, True)} --> {stamp(b, True)}"
        time_vtt = f"{stamp(a, False)} --> {stamp(b, False)}"
        blocks_srt += [str(counter), time_srt, text, ""]
        blocks_vtt += [time_vtt, text, ""]
    if counter == 0:
        raise ValueError("No transcript cues overlap this clip")
    return json.dumps({"srt": "\n".join(blocks_srt) + "\n", "vtt": "\n".join(blocks_vtt) + "\n",
                       "cues": counter}, ensure_ascii=False)


def propose(instruction, start, end, duration):
    draft = clipops_creative_review.propose_edit(
        {"id": "mobile", "start": float(start), "end": float(end), "remove_ranges": []},
        instruction, float(duration))
    # Full desktop supports remove_ranges. Mobile's native transformer currently
    # exports a single contiguous clip. Reject unsupported edits explicitly.
    if "remove_ranges" in draft["proposed_updates"]:
        raise ValueError("Multi-cut removal needs the desktop render engine")
    return json.dumps(draft, ensure_ascii=False)
