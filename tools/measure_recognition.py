#!/usr/bin/env python3
"""Measure local speech recognition against the generated ClipOps reference cues."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys
import tempfile
from time import monotonic

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pilot_intelligence import transcribe_local


def tokens(text):
    return re.findall(r"[^\W_]+", text.casefold())


def edit_distance(reference, hypothesis):
    row = list(range(len(hypothesis) + 1))
    for i, token in enumerate(reference, 1):
        next_row = [i]
        for j, heard in enumerate(hypothesis, 1):
            next_row.append(min(next_row[-1] + 1, row[j] + 1, row[j - 1] + (token != heard)))
        row = next_row
    return row[-1]


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("source", type=Path)
    cli.add_argument("reference", type=Path)
    cli.add_argument("model", type=Path)
    cli.add_argument("--language", default="auto")
    cli.add_argument("--speaker-model", type=Path)
    options = cli.parse_args()
    reference = json.loads(options.reference.read_text(encoding="utf-8"))
    if reference.get("synthetic") is not True:
        raise ValueError("Benchmark expects the generated fixture reference")
    started = monotonic()
    with tempfile.TemporaryDirectory(prefix="clipops-asr-check-") as work:
        observed = transcribe_local(options.source, options.model, Path(work), language=options.language,
                                   speaker_model=options.speaker_model)
    rows = observed.pop("segments")
    expected = tokens(" ".join(row["text"] for row in reference["segments"]))
    actual = tokens(" ".join(row["text"] for row in rows))
    if not expected:
        raise ValueError("Include reference speech")
    edits = edit_distance(expected, actual)
    print(json.dumps({
        "fixture": options.source.name, "model": options.model.name, "language_option": options.language,
        "reference_words": len(expected), "edits": edits, "word_error_rate": round(edits / len(expected), 4),
        "tokenization": "Unicode word tokens, case folded, punctuation ignored",
        "elapsed_s": round(monotonic() - started, 3),
        "words_with_timestamps": sum(len(row.get("words", [])) for row in rows),
        "speaker_segment_counts": dict(Counter(row.get("speaker", "unassigned") for row in rows)),
        "metadata": observed, "observed_segments": rows,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
