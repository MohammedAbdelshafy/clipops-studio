"""Offline, source-evidence checks for ClipOps' optional editorial skill card.

This module NEVER approves clips, edits, renders, sends network traffic or
predicts performance. Human review is required irrespective of the findings.
"""
from __future__ import annotations

import math

SKILL_ID = 'clipops-editorial-intelligence'


def _second(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _span(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    start, end = (_second(x) for x in value)
    if start is None or end is None or not 0 <= start < end:
        return None
    return start, end


def _grounded_quote(quote, rows):
    if not isinstance(quote, dict):
        return False
    stamp = _span([quote.get('start'), quote.get('end')])
    spoken = quote.get('verbatim')
    if not stamp or not isinstance(spoken, str) or not spoken or len(spoken) > 700:
        return False
    included = [row for row in rows if row['start'] >= stamp[0] - .001 and row['end'] <= stamp[1] + .001]
    return bool(included) and ' '.join(row['text'] for row in included).startswith(spoken)


def review_skill_checks(rows, review, source_duration=None):
    """Return an advisory evidence card from an existing ClipOps creative review.

    `rows` are already validated transcript cues from clean_segments().
    Never infer clip meaning, image content, audio quality, or rights from text.
    """
    if not isinstance(review, dict) or not isinstance(rows, list):
        raise ValueError('Expected validated transcript and creative review')
    clip_span = _span(review.get('source_range'))
    duration = _second(source_duration) if source_duration is not None else None
    if source_duration is not None and (duration is None or duration <= 0):
        raise ValueError('Invalid source duration')
    checks = []

    def record(key, label, status, detail):
        checks.append({'key': key, 'label': label, 'status': status, 'detail': detail})

    if clip_span is None:
        record('source_bounds', 'Source time bounds', 'needs_review', 'The candidate has invalid source time bounds.')
    elif duration is None:
        record('source_bounds', 'Source time bounds', 'not_verified', 'Source duration was not supplied for cross-checking.')
    elif clip_span[1] > duration + .001:
        record('source_bounds', 'Source time bounds', 'needs_review', 'Candidate extends beyond the recorded source duration.')
    else:
        record('source_bounds', 'Source time bounds', 'verified', 'Candidate timestamps are inside the reported source duration.')

    hook = review.get('hook_source')
    valid_hook = _grounded_quote(hook, rows)
    hook_stamp = _span([hook.get('start'), hook.get('end')]) if isinstance(hook, dict) else None
    within_clip = bool(clip_span and hook_stamp and hook_stamp[0] >= clip_span[0] - .001 and hook_stamp[1] <= clip_span[1] + .001)
    record('hook_grounding', 'Hook grounded in transcript', 'verified' if valid_hook and within_clip else 'needs_review',
           'Hook is a source-aligned transcript excerpt within the candidate.' if valid_hook and within_clip
           else 'No complete, source-grounded hook lies entirely within the selected clip; verify by listening.')

    quoted = review.get('quote_bank', [])
    quote_ok = (isinstance(quoted, list) and bool(quoted) and bool(clip_span)
                and all(_grounded_quote(item, rows) and
                        (qspan := _span([item['start'], item['end']])) is not None
                        and qspan[0] >= clip_span[0] - .001 and qspan[1] <= clip_span[1] + .001
                        for item in quoted))
    record('quote_ranges', 'Quoted words inside clip', 'verified' if quote_ok else 'needs_review',
           'Every listed source quote is transcript-grounded and inside selected boundaries.' if quote_ok
           else 'Some source quotes extend outside clip boundaries or were not verifiable.')

    warnings = review.get('warnings', [])
    if not isinstance(warnings, list):
        warnings = []
    risk_terms = ('intersects a transcript cue', 'overlapping cues', 'dense speech')
    timing_risk = any(isinstance(w, str) and any(term in w.lower() for term in risk_terms) for w in warnings)
    record('caption_timing', 'Caption timing risk', 'needs_review' if timing_risk else 'not_verified',
           'Detected boundary/overlap/density warning; inspect word-level caption timing.' if timing_risk
           else 'No structural cue warning detected; audio-to-caption alignment remains untested.')

    record('visual_audio', 'Visual framing and sound', 'not_verified',
           'A transcript cannot establish visual framing, speaker identity, audio clarity or export quality.')
    record('story_rights', 'Story fidelity and media rights', 'not_verified',
           'A human must verify complete meaning, omitted context, consent and rights before approval.')
    return {'skill_id': SKILL_ID, 'method': 'offline_source_evidence', 'checks': checks,
            'requires_human_review': True, 'grants_export_approval': False,
            'network_or_model_calls': False,
            'note': 'Structural evidence only, NOT a virality score or a substitute for watching and listening.'}
