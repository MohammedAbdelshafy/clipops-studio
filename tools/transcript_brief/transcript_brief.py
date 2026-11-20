"""Offline transcript-to-content-brief generator. No APIs, network, or outreach."""
import argparse
import json
import re
from pathlib import Path


def generate(transcript: str, title: str = 'Untitled recording') -> dict:
    text = re.sub(r'\s+', ' ', transcript).strip()
    if len(text) < 40:
        raise ValueError('Transcript must contain at least 40 characters')
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
    if len(sentences) < 2:
        raise ValueError('Transcript must contain at least two punctuated sentences')
    candidates = sorted(enumerate(sentences), key=lambda p: (-len(re.findall(r'\b\w+\b', p[1])), p[0]))
    selected = sorted(candidates[:min(3,len(candidates))])
    highlights = [s[:240] for _,s in selected]
    return {
        'title': title,
        'source_word_count': len(text.split()),
        'summary_extracts': highlights,
        'clip_candidates': [{'hook': s[:100], 'source_excerpt': s, 'needs_editorial_review': True} for s in highlights],
        'proposed_cta': 'Review the source and approve a factual call to action.',
        'status': 'DRAFT_REVIEW_REQUIRED',
        'disclaimer': 'Extractive draft only. No timestamps, fact checking, or publishing performed.'
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument('transcript', type=Path)
    p.add_argument('--title', default='Untitled recording')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    result = generate(a.transcript.read_text(encoding='utf-8'), a.title)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
