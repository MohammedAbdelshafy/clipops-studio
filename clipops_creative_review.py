#!/usr/bin/env python3
"""Offline, source-grounded creative review for ClipOps Studio.

This is an advisory layer: it neither modifies projects nor renders, uploads,
or publishes media. Suggested edits must be reviewed and applied through the
existing ClipOps edit/approval workflow.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import re

MAX_TRANSCRIPT_BYTES = 24 * 1024**2
MAX_SEGMENTS = 150_000
MAX_CANDIDATES = 100
# Deliberately small, conservative starter lexicon. Never auto-censor.
REVIEW_WORDS = frozenset({'fuck', 'fucking', 'shit', 'bitch', 'asshole', 'خرا', 'احا', 'متناك'})
TOKEN = re.compile(r'[^\W_]+', re.UNICODE)
TRANSCRIPT = re.compile(r'transcript-[0-9a-f]{32}\.json\Z')
TIME = re.compile(r'\d+(?::[0-5]\d){0,2}(?:\.\d{1,3})?\Z')


def bounded_number(value, label):
    if isinstance(value, bool):
        raise ValueError(f'{label} must be finite')
    try:
        n = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f'{label} must be finite') from exc
    if not math.isfinite(n):
        raise ValueError(f'{label} must be finite')
    return n


def clean_segments(rows):
    if not isinstance(rows, list) or len(rows) > MAX_SEGMENTS:
        raise ValueError('Invalid or oversized transcript')
    result = []
    for item in rows:
        if not isinstance(item, dict):
            raise ValueError('Invalid transcript cue')
        a, b = bounded_number(item.get('start'), 'start'), bounded_number(item.get('end'), 'end')
        if a < 0 or b <= a:
            raise ValueError('Invalid transcript cue range')
        text = ' '.join(str(item.get('text', '')).split())
        if not text or len(text) > 4096:
            raise ValueError('Invalid transcript text')
        speaker = item.get('speaker') or ''
        if not isinstance(speaker, str) or len(speaker) > 80:
            raise ValueError('Invalid speaker label')
        result.append({'start': a, 'end': b, 'text': text, 'speaker': speaker})
    return sorted(result, key=lambda r: (r['start'], r['end']))


def review_terms(text):
    return sorted({word.lower() for word in TOKEN.findall(text) if word.lower() in REVIEW_WORDS})


def quotes_in(rows, start, end, maximum=8):
    """Return contiguous verbatim source spans, never generated speech."""
    if not 1 <= maximum <= 50:
        raise ValueError('Invalid quote limit')
    active = [r for r in rows if r['start'] < end and r['end'] > start]
    output, block = [], []

    def emit():
        if not block:
            return
        text = ' '.join(r['text'] for r in block)
        if len(TOKEN.findall(text)) >= 4:
            output.append({'start': block[0]['start'], 'end': block[-1]['end'],
                           'speaker': block[0]['speaker'] or None, 'verbatim': text[:700],
                           'review_terms': review_terms(text)})
        block.clear()

    for row in active:
        if block and (row['speaker'] != block[-1]['speaker'] or row['start'] - block[-1]['end'] > 1.25
                      or row['end'] - block[0]['start'] > 11 or len(TOKEN.findall(' '.join(r['text'] for r in block))) > 42):
            emit()
        block.append(row)
        if re.search(r'[.!?؟…]["\'»”’)]*\Z', row['text']):
            emit()
    emit()
    return sorted(output, key=lambda q: (-int('?' in q['verbatim'] or '؟' in q['verbatim']),
                                         -len(TOKEN.findall(q['verbatim'])), q['start']))[:maximum]


def review_candidate(rows, clip, *, max_quotes=8):
    if not isinstance(clip, dict):
        raise ValueError('Invalid candidate')
    start, end = bounded_number(clip.get('start'), 'clip start'), bounded_number(clip.get('end'), 'clip end')
    if not 0 <= start < end or end - start > 180:
        raise ValueError('Invalid clip range')
    selected = [r for r in rows if r['start'] < end and r['end'] > start]
    dialogue = ' '.join(r['text'] for r in selected)
    warnings = []
    if not selected:
        warnings.append('No timed transcript cues overlap this clip')
    else:
        if selected[0]['start'] < start - 0.05:
            warnings.append('Start intersects a transcript cue: review the opening word')
        if selected[-1]['end'] > end + 0.05:
            warnings.append('End intersects a transcript cue: review the final word')
        for left, right in zip(selected, selected[1:]):
            if right['start'] < left['end'] - 0.1:
                warnings.append('Overlapping cues: review caption synchronization')
                break
        rate = len(TOKEN.findall(dialogue)) / max(end - start, 0.001)
        if rate > 3.8:
            warnings.append('Dense speech: review caption grouping and safe zones')
        if len({r['speaker'] for r in selected if r['speaker']}) > 1:
            warnings.append('Multiple speakers: review caption colors and framing')
    flagged = review_terms(dialogue)
    if flagged:
        warnings.append('Possible profanity: manual review, never auto-delete source audio')
    quotes = quotes_in(selected, start, end, maximum=max_quotes)
    hook = next((q for q in quotes if '?' in q['verbatim'] or '؟' in q['verbatim']),
                quotes[0] if quotes else None)
    return {'candidate_id': clip.get('id'), 'source_range': [start, end],
            'original_editorial_score': clip.get('score'),
            'hook_source': hook, 'quote_bank': quotes,
            'possible_profanity': flagged, 'warnings': warnings,
            'speaker_counts': dict(sorted(Counter(r['speaker'] for r in selected if r['speaker']).items()))}


def parse_time(token):
    if not TIME.fullmatch(token):
        raise ValueError('Use seconds, MM:SS, or HH:MM:SS for timestamps')
    parts = token.split(':')
    if len(parts) > 3:
        raise ValueError('Invalid timestamp')
    result = 0.0
    for component in parts:
        result = 60 * result + float(component)
    return result


def propose_edit(clip, instruction, source_duration):
    """Parse a tightly bounded command into a PROPOSAL, not an applied edit.

    Supported syntax: start 00:12; end 00:43; title: Text; cta: Text;
    remove 00:20 to 00:21. Unsupported natural language is rejected.
    """
    if not isinstance(instruction, str) or not instruction.strip() or len(instruction) > 1000:
        raise ValueError('Provide a short supported edit instruction')
    commands = [p.strip() for p in instruction.split(';')]
    if len(commands) > 8 or not all(commands):
        raise ValueError('Provide at most eight complete edit commands')
    changes, removals = {}, []
    duration = bounded_number(source_duration, 'source duration')
    for command in commands:
        if match := re.fullmatch(r'(start|end)\s+(\S+)', command, flags=re.IGNORECASE):
            field = match[1].lower()
            if field in changes:
                raise ValueError('Duplicate edit field')
            changes[field] = parse_time(match[2])
        elif match := re.fullmatch(r'(title|cta):\s*(.{1,500})', command, flags=re.IGNORECASE):
            field = match[1].lower()
            if field in changes or not match[2].strip():
                raise ValueError('Duplicate or empty edit field')
            changes[field] = match[2].strip()
        elif match := re.fullmatch(r'remove\s+(\S+)\s+to\s+(\S+)', command, flags=re.IGNORECASE):
            removals.append([parse_time(match[1]), parse_time(match[2])])
        else:
            raise ValueError('Unsupported command. Use start, end, title:, cta:, or remove X to Y')
    start = changes.get('start', bounded_number(clip.get('start'), 'clip start'))
    end = changes.get('end', bounded_number(clip.get('end'), 'clip end'))
    if not 0 <= start < end <= duration or not .25 <= end - start <= 180:
        raise ValueError('Clip boundary outside source or permitted clip length')
    if removals:
        existing = clip.get('remove_ranges', [])
        if not isinstance(existing, list) or len(existing) > 100:
            raise ValueError('Invalid existing removed ranges')
        if 'start' in changes or 'end' in changes:
            if existing:
                raise ValueError('Review existing cuts before changing clip boundaries')
        for pair in existing:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                raise ValueError('Invalid existing cut')
        ranges = sorted([list(x) for x in existing] + removals)
        prev = start
        total = 0.0
        for a, b in ranges:
            a, b = bounded_number(a, 'removed start'), bounded_number(b, 'removed end')
            if a < prev or b <= a or b > end:
                raise ValueError('Removed ranges must be nonoverlapping and inside this clip')
            prev = b
            total += b - a
        if end - start - total < .25:
            raise ValueError('Removal would leave an unusably short clip')
        changes['remove_ranges'] = ranges
    return {'candidate_id': clip.get('id'), 'proposed_updates': changes,
            'applied': False, 'requires_review': True,
            'note': 'Apply through ClipOps edit controls, rerender, then reapprove the exact output.'}


def project_review(project_dir, maximum=8):
    """Read only the project's own JSON and immutable transcript revision."""
    root = Path(project_dir).expanduser().resolve(strict=True)
    state_path = root / 'project.json'
    if not root.is_dir() or state_path.is_symlink() or not state_path.is_file() or state_path.stat().st_size > 4 * 1024**2:
        raise ValueError('Invalid local project')
    state = json.loads(state_path.read_text(encoding='utf-8'))
    name = state.get('transcript_file')
    if not isinstance(name, str) or not TRANSCRIPT.fullmatch(name):
        raise ValueError('Project must have a valid immutable transcript revision')
    transcript = root / name
    if transcript.is_symlink() or not transcript.is_file() or transcript.stat().st_size > MAX_TRANSCRIPT_BYTES:
        raise ValueError('Invalid local transcript file')
    rows = clean_segments(json.loads(transcript.read_text(encoding='utf-8')))
    clips = state.get('candidates', [])
    if not isinstance(clips, list) or len(clips) > MAX_CANDIDATES:
        raise ValueError('Invalid candidate list')
    return {'project': state.get('id'), 'analysis': 'offline_source_grounded_review',
            'candidate_reviews': [review_candidate(rows, clip, max_quotes=maximum) for clip in clips],
            'privacy': 'Local review only; no automatic editing, media upload, or publishing.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project_dir', help='Existing private ClipOps project folder')
    parser.add_argument('--quotes', type=int, default=8, help='Maximum source quotes per candidate (1–50)')
    args = parser.parse_args(argv)
    print(json.dumps(project_review(args.project_dir, args.quotes), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
