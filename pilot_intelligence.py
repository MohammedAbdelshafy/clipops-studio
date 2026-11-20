"""Offline transcript analysis and chunked local speech recognition for ClipOps Studio."""
from __future__ import annotations

from collections import Counter
from itertools import groupby
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unicodedata
import wave

from clipops_compat import replace_file, serialised


# These are transcript signals that an editor can inspect. Scores are editorial
# sort keys. They are deliberately independent of views or channel analytics.
SIGNALS = {
    "question": ("why", "how", "what if", "ever wondered", "ليه", "ازاي", "لماذا", "كيف", "ماذا لو"),
    "lesson": ("step", "learn", "because", "example", "here is how", "here's how", "first", "خطوة", "مثال", "السبب", "لان", "علشان", "عشان", "اولا"),
    "contrast": ("instead", "but", "myth", "mistake", "actually", "however", "غلط", "بالعكس", "بس", "لكن", "الحقيقة"),
    "story": ("i remember", "when i", "we started", "one day", "at first", "لما", "فاكر", "كنت", "في يوم", "اول مرة"),
    "emotion": ("afraid", "surprised", "proud", "scared", "failed", "shocked", "خايف", "خفت", "اتفاجئت", "فخور", "فشلت", "صدمة"),
    "business": ("client", "customer", "price", "profit", "revenue", "founder", "عميل", "العميل", "تسعير", "ربح", "شركة"),
    "fashion": ("fabric", "stitch", "fit", "silhouette", "cotton", "قماش", "مقاس", "قطن", "خياطة"),
    "gaming": ("level", "boss", "combo", "game", "round", "لعبة", "جولة", "مرحلة"),
}
REASONS = {
    "question": "The opening poses a question.", "lesson": "The excerpt includes an explanation or example.",
    "contrast": "The speaker states a contrast or corrects an assumption.", "story": "A first-person event introduces a story.",
    "emotion": "The speaker names an emotional response.", "business": "The excerpt mentions a business decision.",
    "fashion": "The excerpt discusses a garment or its construction.", "gaming": "The excerpt describes gameplay.",
}
AUDIENCES = {"general": (), "education": ("lesson", "question"), "business": ("business", "contrast"),
             "podcast": ("story", "emotion"), "fashion": ("fashion",), "gaming": ("gaming",),
             "storytelling": ("story", "emotion"), "workshop": ("lesson", "business")}
STOP = set("a an the and for with this that you your our when how why from have had they about then can what into were who would been their was are which will but because there one only just هنا من في علي الي عن او انا هو هي اللي ان ايه كان بس ليه ازاي فيه دي ده مش مع كان عشان لما التي الذي كل اذا".split())
PUNCT_END = re.compile(r"[.!?؟…][\"'»”’)]*$", re.UNICODE)
TOKEN = re.compile(r"[^\W_]+", re.UNICODE)
ARABIC = re.compile(r"[\u0621-\u064a]")
FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ـ": ""})


def _tokens(text):
    clean = "".join(ch for ch in unicodedata.normalize("NFKC", text.casefold()).translate(FOLD)
                    if unicodedata.category(ch) != "Mn")
    return TOKEN.findall(clean)


def _marker_variants(marker):
    tokens = _tokens(marker)
    if len(tokens) != 1 or not ARABIC.search(tokens[0]):
        return (" ".join(tokens),)
    token = tokens[0]
    # Recognize the definite article and attached conjunctions in the signal
    # dictionary without stemming user text, quotes or displayed topic terms.
    forms = {token, token if token.startswith("ال") else "ال" + token}
    return tuple(sorted(forms | {prefix + form for form in forms for prefix in ("و", "ف")}))


SIGNAL_MARKERS = {kind: tuple(variant for marker in markers for variant in _marker_variants(marker))
                  for kind, markers in SIGNALS.items()}


def _bounded_text(value, maximum, field):
    if not isinstance(value, str) or len(value) > maximum or not value.strip():
        raise ValueError(f"Invalid transcript {field}")
    return " ".join(value.split())


def _time(value):
    if isinstance(value, bool):
        raise ValueError("Invalid transcript timestamp")
    t = float(value)
    if not math.isfinite(t) or t < 0:
        raise ValueError("Transcript times must be finite nonnegative seconds")
    return t


def normalize(segments):
    """Validate legacy word rows and sentence rows with optional aligned words."""
    if not isinstance(segments, list) or len(segments) > 200_000:
        raise ValueError("Expected a list of up to 200,000 timestamped rows")
    result = []
    word_count = 0
    for raw in segments:
        if not isinstance(raw, dict):
            raise ValueError("Expected a timestamped transcript row")
        a, b = _time(raw['start']), _time(raw['end'])
        if b <= a:
            raise ValueError("Transcript end must follow start")
        row = {"start": a, "end": b, "text": _bounded_text(raw.get('text'), 8192, 'text')}
        if raw.get('speaker') is not None:
            row['speaker'] = _bounded_text(raw['speaker'], 100, 'speaker')
        if raw.get('words'):
            words = raw['words']
            if not isinstance(words, list) or len(words) > 4096:
                raise ValueError("Invalid transcript word list")
            word_count += len(words)
            if word_count > 250_000:
                raise ValueError("Transcript word limit exceeded")
            row['words'] = []
            last = a
            for word in words:
                if not isinstance(word, dict):
                    raise ValueError("Invalid transcript word")
                x, y = _time(word['start']), _time(word['end'])
                if x < last - 0.002 or y <= x or y > b + 0.002:
                    raise ValueError("Word bounds must fit their sentence in chronological order")
                # Accept the native faster-whisper field and the pilot field.
                row['words'].append({'start': max(a, x), 'end': min(b, y),
                                     'text': _bounded_text(word.get('text', word.get('word')), 1024, 'word')})
                last = x
        result.append(row)
    return sorted(result, key=lambda s: (s['start'], s['end']))


def _utterances(segments, max_seconds):
    """Use punctuation, speaker changes and actual gaps as boundaries. No invented times."""
    rows = []
    for s in normalize(segments):
        if s.get('words') and ''.join(s['text'].split()) == ''.join(''.join(w['text'].split()) for w in s['words']):
            rows.extend({**w, 'speaker': s.get('speaker')} for w in s['words'])
        else:
            rows.append(s)
    turns, buffer = [], []

    def flush():
        if buffer:
            turns.append({'start': buffer[0]['start'], 'end': max(w['end'] for w in buffer),
                          'text': ' '.join(w['text'] for w in buffer), 'speaker': buffer[0].get('speaker')})
            buffer.clear()

    for row in sorted(rows, key=lambda s: s['start']):
        if buffer and (len(buffer) >= 32 or row.get('speaker') != buffer[-1].get('speaker') or
                       row['start'] - buffer[-1]['end'] > 0.8 or
                       row['end'] - buffer[0]['start'] > min(10, max_seconds)):
            flush()
        buffer.append(row)
        if PUNCT_END.search(row['text']) or len(row['text'].split()) >= 5:
            flush()
    flush()
    return turns


def _excerpt(text, length):
    if len(text) <= length:
        return text
    piece = text[:length - 1].rsplit(' ', 1)[0]
    return (piece or text[:length - 1]) + '…'


def _candidate(group, frequency, audience, min_seconds, max_seconds, next_turn=None):
    first, last = group[0], group[-1]
    a, b = first['start'], max(s['end'] for s in group)
    span = b - a
    text = ' '.join(s['text'] for s in group)
    tokens = _tokens(text)
    if len(tokens) < max(3, int(span * .22)):
        return None
    body = ' ' + ' '.join(tokens) + ' '
    opening = ' ' + ' '.join(_tokens(first['text'])[:15]) + ' '
    signals = []
    for name, markers in SIGNAL_MARKERS.items():
        target = opening if name in ('question', 'story') else body
        if any(f' {marker} ' in target for marker in markers):
            signals.append(name)
    if ('?' in first['text'] or '؟' in first['text']) and 'question' not in signals:
        signals.append('question')
    terms = set(tokens) - STOP
    questions = sum('?' in s['text'] or '؟' in s['text'] for s in group)
    answered = 'question' in signals and len(group) > 1 and not re.search(r'[?؟]$', last['text'])
    story_break = bool(next_turn and re.search(r'[?؟]$', next_turn['text']))
    coverage = min(1.0, sum(s['end'] - s['start'] for s in group) / span)
    closure = bool(PUNCT_END.search(last['text'])) and last['text'].rstrip()[-1] not in '?؟'
    lead_in = any(opening.startswith(x) for x in (
        ' and so ', ' and then ', ' that one ', ' so on the ', ' as i mentioned ',
        ' like i said ', ' as we discussed ', ' وده ', ' ودي ', ' زي ما قولنا '))
    unfinished = tokens[-1] in {'and', 'or', 'but', 'because', 'علشان', 'عشان', 'لكن', 'او'}
    target = min(max_seconds, max(min_seconds, 29))
    components = {
        'structure': 14 + 8 * closure - 9 * lead_in - 7 * unfinished,
        'focused_exchange': 5 * answered + 4 * (story_break and closure) - 5 * max(0, questions - 1),
        'signals': min(30, 8 * len(signals)),
        'speech_coverage': round(14 * coverage),
        'specificity': min(12, len(terms)) + (4 if any(t.isdigit() for t in tokens) else 0),
        'audience_fit': 8 if set(signals).intersection(AUDIENCES[audience]) else 0,
        'duration_fit': round(10 * max(0.0, 1 - abs(span - target) / target)),
    }
    rationale = [REASONS[s] for s in signals]
    if answered:
        rationale.append('A statement follows the opening question in this excerpt.')
    if story_break and closure:
        rationale.append('The next transcript turn begins a new question.')
    if closure:
        rationale.append('Ends at transcript sentence punctuation.')
    if not rationale:
        rationale.append('Contiguous speech provides a possible excerpt for review.')
    if components['audience_fit']:
        rationale.append(f'Transcript markers match the {audience} brief.')
    if lead_in:
        rationale.append('Opening refers back to earlier context. Review the preceding sentence.')
    if unfinished:
        rationale.append('The last words suggest a continued thought. Review the next sentence.')
    # Across the whole transcript, downweight terms that recur in many turns.
    # Preserve the speaker's words in title and copy so facts remain traceable.
    topics = sorted(terms, key=lambda t: (frequency[t], -len(t), t))[:5]
    is_arabic = sum(bool(ARABIC.search(t)) for t in tokens) > len(tokens) / 2
    cta = ('جرّب الخطوة وشارك النتيجة.' if is_arabic else 'Try the example and share what you learn.') if 'lesson' in signals else (
        'ما رأيك؟' if is_arabic else 'What is your take?')
    item = {'start': a, 'end': b, 'score': max(0, min(100, sum(components.values()))), 'score_components': components,
            'score_type': 'editorial_heuristic', 'rationale': rationale, 'signals': signals, 'topics': topics,
            'title': _excerpt(first['text'], 80), 'description': _excerpt(text, 260), 'cta': cta,
            'preview': _excerpt(text, 180), 'audience': audience}
    return item, terms or set(tokens), set(zip(tokens, tokens[1:], tokens[2:]))


def _same_excerpt(one, two):
    a, terms_a, phrases_a = one
    b, terms_b, phrases_b = two
    overlap = min(a['end'], b['end']) - max(a['start'], b['start'])
    if overlap > 0.15 * min(a['end'] - a['start'], b['end'] - b['start']):
        return True
    lexical = len(terms_a & terms_b) / max(1, len(terms_a | terms_b))
    phrasal = len(phrases_a & phrases_b) / max(1, min(len(phrases_a), len(phrases_b)))
    return (lexical >= .82 and phrasal >= .35) or phrasal >= .78


def rank_candidates(segments, limit=24, audience='general', min_seconds=12, max_seconds=55):
    """Find contiguous source excerpts and suppress overlaps and repeated takes across the film."""
    audience = str(audience).lower()
    if audience not in AUDIENCES:
        raise ValueError('Audience must be one of ' + ', '.join(AUDIENCES))
    if not isinstance(limit, int) or not 1 <= limit <= 100 or not (0 < min_seconds <= max_seconds <= 180):
        raise ValueError('Invalid clip count or time range')
    turns = _utterances(segments, max_seconds)
    if not turns:
        return []
    frequency = Counter(token for t in turns for token in set(_tokens(t['text'])))
    pool = []
    for i, first in enumerate(turns):
        best = None
        end = first['start']
        for j in range(i, min(i + 48, len(turns))):
            turn = turns[j]
            # A sizeable gap is a break in the material. Extending a candidate
            # through it simply to achieve a requested duration loses context.
            if turn['start'] - end > 3 or turn['end'] - first['start'] > max_seconds:
                break
            end = max(end, turn['end'])
            if end - first['start'] < min_seconds:
                continue
            candidate = _candidate(turns[i:j + 1], frequency, audience, min_seconds, max_seconds,
                                   turns[j + 1] if j + 1 < len(turns) else None)
            if candidate and (best is None or candidate[0]['score'] > best[0]['score']):
                best = candidate
        if best:
            pool.append(best)
    duration = max(t['end'] for t in turns) - turns[0]['start']
    bin_width = max(max_seconds, duration / min(8, limit))
    def chapter(row):
        return int((row['start'] - turns[0]['start']) / bin_width)
    used, chosen = Counter(), []
    while pool and len(chosen) < limit:
        # Similar-quality choices from a different part of the program surface
        # earlier. Never fill an empty period with synthetic suggestions.
        index = max(range(len(pool)), key=lambda i: (pool[i][0]['score'] - 4 * used[chapter(pool[i][0])], -pool[i][0]['start']))
        pick = pool.pop(index)
        item = pick[0]
        used[chapter(item)] += 1
        chosen.append(item)
        pool = [other for other in pool if not _same_excerpt(pick, other)]
    return sorted(chosen, key=lambda s: (-s['score'], s['start']))

# Allow ordinary standalone media containers. Playlists, concat scripts, data
# references and network protocols are outside the local pilot's intake model.
INPUT_OPTIONS = ['-protocol_whitelist', 'file', '-format_whitelist', 'mov,mp4,m4a,3gp,3g2,mj2,matroska,webm,avi,wav,flac,mp3,ogg,aac']
LANGUAGE = {None: None, 'auto': None, 'mixed': None, 'ar-eg': 'ar', 'egyptian': 'ar', 'en': 'en', 'ar': 'ar'}


def _probe_audio(src):
    proc = subprocess.run(['ffprobe', '-v', 'error', *INPUT_OPTIONS, '-select_streams', 'a',
                           '-show_entries', 'format=duration:stream=index', '-of', 'json', str(src)],
                          capture_output=True, timeout=40)
    if proc.returncode:
        raise ValueError('Unable to probe local media for speech recognition')
    info = json.loads(proc.stdout)
    duration = float(info.get('format', {}).get('duration', 0))
    if not info.get('streams') or not 0 < duration <= 7200:
        raise ValueError('Speech recognition requires an audio stream and up to two hours of media')
    return duration, len(info['streams'])


def _fingerprint(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(2 ** 20), b''):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path, value):
    # Unique temp names let simultaneous workers converge on complete files.
    with serialised(path):
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as f:
            staging = Path(f.name)
            try:
                json.dump(value, f, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
                f.flush()
                os.fsync(f.fileno())
            except BaseException:
                staging.unlink(missing_ok=True)
                raise
        try:
            replace_file(staging, path)
        finally:
            staging.unlink(missing_ok=True)


def _audio(src, index, start, end, output, pcm=False):
    args = ['ffmpeg', '-nostdin', '-hide_banner', '-v', 'error', '-xerror', '-y', *INPUT_OPTIONS,
            '-ss', f'{start:.6f}', '-i', str(src), '-map', f'0:a:{index}', '-vn', '-sn', '-dn',
            '-t', f'{end - start:.6f}', '-af', 'aresample=16000:async=1:first_pts=0',
            '-ar', '16000', '-ac', '1', '-c:a', 'pcm_s16le', '-f', 's16le' if pcm else 'wav', str(output)]
    proc = subprocess.run(args, capture_output=True, timeout=max(60, int(end - start) * 2))
    if proc.returncode:
        raise ValueError('Local audio decoding failed')


def _load_speech_model(model, device):
    try:
        import ctranslate2
        import onnxruntime
        onnxruntime.disable_telemetry_events()
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError('Install the optional faster-whisper package in this Python environment') from exc
    options = dict(local_files_only=True, cpu_threads=2, num_workers=1)
    if device in ('auto', 'cuda') and ctranslate2.get_cuda_device_count() > 0:
        try:
            return WhisperModel(str(model), device='cuda', compute_type='float16', **options), 'cuda'
        except RuntimeError:
            if device == 'cuda':
                raise
    elif device == 'cuda':
        raise ValueError('Requested CUDA device is unavailable')
    return WhisperModel(str(model), device='cpu', compute_type='int8', **options), 'cpu'


def _decode_piece(recognizer, wav, language, offset, start, end, speaker):
    # FFmpeg already decoded this private mono 16 kHz PCM chunk. Feeding the
    # samples directly also avoids another container parser and decode pass.
    import numpy as np
    with wave.open(str(wav), 'rb') as handle:
        if (handle.getnchannels(), handle.getframerate(), handle.getsampwidth()) != (1, 16000, 2):
            raise ValueError('Unexpected audio chunk format')
        audio = np.frombuffer(handle.readframes(handle.getnframes()), dtype='<i2').astype(np.float32) / 32768
    iterable, info = recognizer.transcribe(audio, language=language, task='transcribe',
        word_timestamps=True, vad_filter=True, multilingual=language is None, beam_size=3,
        condition_on_previous_text=False)
    rows = []
    for segment in iterable:
        words = []
        for word in getattr(segment, 'words', None) or []:
            if word.start is None or word.end is None:
                continue
            a, b = offset + word.start, offset + word.end
            midpoint = (a + b) / 2
            label = word.word.strip()
            if label and b > a and start <= midpoint < end:
                a = max(start, a, words[-1]['end'] if words else start)
                b = min(end, b)
                if b > a:
                    words.append({'start': a, 'end': b, 'text': label})
        if words:
            row = {'start': words[0]['start'], 'end': words[-1]['end'],
                   'text': ' '.join(w['text'] for w in words), 'words': words}
        elif not getattr(segment, 'words', None):
            a, b = offset + segment.start, offset + segment.end
            if not (start <= (a + b) / 2 < end and b > a and segment.text.strip()):
                continue
            row = {'start': max(start, a), 'end': min(end, b), 'text': segment.text.strip()}
        else:
            continue
        if speaker:
            row['speaker'] = speaker
        rows.append(row)
    return {'language': info.language, 'segments': normalize(rows)}


def _append_piece(rows, piece, boundary):
    # Both overlapping decoders can claim the same word near the midpoint.
    # Join only matching tokens clipped on *both* sides of the exact seam.
    # Natural repetition away from a chunk boundary is preserved.
    if not rows or not piece or not rows[-1].get('words') or not piece[0].get('words'):
        rows.extend(piece)
        return
    previous, following = rows[-1], piece[0]
    left, right = previous['words'][-1], following['words'][0]
    if (abs(left['end'] - boundary) < 1e-6 and abs(right['start'] - boundary) < 1e-6 and
            _tokens(left['text']) and _tokens(left['text']) == _tokens(right['text'])):
        left['end'] = right['end']
        previous['end'] = right['end']
        # The last decode often holds the final punctuation for this word.
        left['text'] = right['text'] if PUNCT_END.search(right['text']) else left['text']
        previous['text'] = ' '.join(w['text'] for w in previous['words'])
        following['words'] = following['words'][1:]
        if following['words']:
            following['start'] = following['words'][0]['start']
            following['text'] = ' '.join(w['text'] for w in following['words'])
        else:
            piece = piece[1:]
    rows.extend(piece)


def _read_piece(path):
    try:
        if path.stat().st_size > 16 * 1024**2:
            return None
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data.get('language'), str):
            return None
        return {**data, 'segments': normalize(data['segments'])}
    except (OSError, ValueError, TypeError, AttributeError, KeyError):
        return None


def _speaker_windows(segments):
    items = [word for row in segments for word in (row.get('words') or [row])]
    windows, group = [], []
    for word in items:
        if group and (word['start'] - group[-1]['end'] > .6 or word['end'] - group[0]['start'] > 4 or
                      (group[-1]['end'] - group[0]['start'] >= 1.4 and PUNCT_END.search(group[-1]['text']))):
            windows.append(group)
            group = []
        group.append(word)
    if group:
        windows.append(group)
    return windows


def _speaker_labels(src, duration, segments, model, directory):
    """Cluster speech windows by voice; short/ambiguous/overlapped turns need an editor."""
    import numpy as np
    try:
        import sherpa_onnx
    except ImportError as exc:
        raise RuntimeError('Install the optional sherpa-onnx package for mixed-track speaker estimation') from exc
    config = sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(model), provider='cpu', num_threads=1)
    if not config.validate():
        raise ValueError('Invalid local speaker embedding model')
    extractor = sherpa_onnx.SpeakerEmbeddingExtractor(config)
    windows = _speaker_windows(segments)
    vectors = []
    with tempfile.TemporaryDirectory(dir=directory, prefix='voices-') as temp:
        audio_path = Path(temp) / 'voice.pcm'
        _audio(src, 0, 0.0, duration, audio_path, pcm=True)
        if not audio_path.stat().st_size:
            return segments, []
        signal = np.memmap(audio_path, dtype='<i2', mode='r')
        try:
            for words in windows:
                a, b = words[0]['start'], words[-1]['end']
                samples = np.asarray(signal[int(a * 16000):int(b * 16000)], dtype=np.float32) / 32768
                if len(samples) < 16000 * .65:
                    vectors.append(None)
                    continue
                stream = extractor.create_stream()
                stream.accept_waveform(sample_rate=16000, waveform=samples)
                stream.input_finished()
                vec = np.asarray(extractor.compute(stream), dtype=np.float32) if extractor.is_ready(stream) else None
                norm = np.linalg.norm(vec) if vec is not None else 0.0
                vectors.append(vec / norm if norm > .00001 else None)
        finally:
            del signal
    centers, counts = [], []
    for vec in vectors:
        if vec is None:
            continue
        scores = [float(c @ vec) for c in centers]
        if not scores or (max(scores) < .60 and len(centers) < 16):
            centers.append(vec.copy())
            counts.append(1)
        else:
            index = int(np.argmax(scores))
            summed = centers[index] * counts[index] + vec
            centers[index] = summed / max(float(np.linalg.norm(summed)), .00001)
            counts[index] += 1
    assigned = {}
    turns = []
    for group, vec in zip(windows, vectors):
        scores = sorted(((float(c @ vec), i) for i, c in enumerate(centers)), reverse=True) if vec is not None else []
        if not scores or scores[0][0] < .45 or (len(scores) > 1 and scores[0][0] - scores[1][0] < .05):
            continue
        label = f'Speaker {scores[0][1] + 1}'
        for w in group:
            assigned[id(w)] = label
        turns.append({'start': group[0]['start'], 'end': group[-1]['end'], 'speaker': label})
    tagged = []
    for row in segments:
        raw = row.get('words')
        if not raw:
            tagged.append({**row, **({'speaker': assigned[id(row)]} if id(row) in assigned else {})})
            continue
        for speaker, word_iter in groupby(raw, key=lambda word: assigned.get(id(word))):
            words = list(word_iter)
            tag = {'start': words[0]['start'], 'end': words[-1]['end'], 'text': ' '.join(w['text'] for w in words), 'words': words}
            if speaker:
                tag['speaker'] = speaker
            tagged.append(tag)
    return tagged, turns


def transcribe_local(source, model, work, language=None, *, chunk_seconds=240, device='auto',
                     speaker_tracks=None, speaker_model=None, progress=None):
    """Transcribe local media. Completed chunks are reusable after an interrupted run.

    With isolated microphones, speaker_tracks maps zero-based audio stream indices to
    reviewed labels. A speaker_model instead enables exploratory mixed-track diarization.
    All models must already be installed locally; this function performs no downloads.
    """
    src, model, work = Path(source).resolve(strict=True), Path(model).resolve(strict=True), Path(work)
    if not src.is_file() or not model.is_dir():
        raise ValueError('Expected a local source file and CTranslate2 model directory')
    required = ('model.bin', 'config.json', 'tokenizer.json')
    if not all((model / name).is_file() for name in required):
        raise ValueError('Local model requires model.bin, config.json and tokenizer.json')
    key = str(language).lower() if language is not None else None
    if key not in LANGUAGE or not isinstance(chunk_seconds, int) or not 10 <= chunk_seconds <= 600 or device not in ('cpu', 'auto', 'cuda'):
        raise ValueError('Invalid language, device or chunk length')
    lang = LANGUAGE[key]
    duration, stream_count = _probe_audio(src)
    tracks = speaker_tracks or {0: None}
    if not isinstance(tracks, dict) or len(tracks) > 8 or any(type(i) is not int or not 0 <= i < stream_count for i in tracks):
        raise ValueError('Isolated microphone mapping requires valid audio stream indices')
    if speaker_tracks:
        tracks = {i: _bounded_text(name, 80, 'speaker label') for i, name in tracks.items()}
        if len(set(tracks.values())) != len(tracks) or speaker_model:
            raise ValueError('Use distinct labels for isolated tracks, or one mixed-track speaker model')
    if speaker_model:
        speaker_model = Path(speaker_model).resolve(strict=True)
        if not speaker_model.is_file():
            raise ValueError('Expected a local speaker embedding model file')
    # Content hashes also invalidate cache after in-place file/model edits. Hash
    # optional vocabulary and feature configs when provided by converted models.
    from importlib.metadata import PackageNotFoundError, version
    try:
        runtime = [version('faster-whisper'), version('ctranslate2'), version('onnxruntime')]
    except PackageNotFoundError as exc:
        raise RuntimeError('Install optional faster-whisper for local transcription') from exc
    signature = {'schema': 3, 'source': _fingerprint(src), 'files': {n: _fingerprint(model / n)
        for n in (*required, 'preprocessor_config.json', 'vocabulary.txt', 'vocabulary.json') if (model / n).is_file()},
        'language': lang, 'chunk_seconds': chunk_seconds, 'tracks': sorted(tracks.items()), 'device': device, 'runtime': runtime}
    cache = work / hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()
    cache.mkdir(mode=0o700, parents=True, exist_ok=True)
    rows, languages, devices, chunks = [], Counter(), set(), math.ceil(duration / chunk_seconds)
    recognizer = None
    cached = 0
    warnings = ['Review names, timing, Egyptian dialect and code-switching against the source audio.']
    for stream_index, speaker in sorted(tracks.items()):
        stream_rows = []
        for i in range(chunks):
            part = cache / f'track-{stream_index}-chunk-{i}.json'
            data = _read_piece(part)
            if data is None:
                if recognizer is None:
                    recognizer, engine_device = _load_speech_model(model, device)
                a, b = i * chunk_seconds, min(duration, (i + 1) * chunk_seconds)
                # Overlap provides linguistic context at boundaries. Retain each
                # word only in the chunk owning its source-time midpoint.
                left, right = max(0.0, a - 3), min(duration, b + 3)
                with tempfile.TemporaryDirectory(dir=cache, prefix='audio-') as tmp:
                    wave = Path(tmp) / 'chunk.wav'
                    _audio(src, stream_index, left, right, wave)
                    try:
                        data = _decode_piece(recognizer, wave, lang, left, a, b, speaker)
                    except RuntimeError:
                        if engine_device != 'cuda' or device != 'auto':
                            raise
                        recognizer, engine_device = _load_speech_model(model, 'cpu')
                        data = _decode_piece(recognizer, wave, lang, left, a, b, speaker)
                    data['device'] = engine_device
                _atomic_json(part, data)
            else:
                cached += 1
            _append_piece(stream_rows, data['segments'], i * chunk_seconds)
            if data['segments']:
                languages[data['language']] += sum(s['end'] - s['start'] for s in data['segments'])
            devices.add(data.get('device', 'unknown'))
            if progress:
                progress((sorted(tracks).index(stream_index) * chunks + i + 1), len(tracks) * chunks)
        rows.extend(stream_rows)
    rows.sort(key=lambda row: (row['start'], row['end']))
    turns = []
    if speaker_model and rows:
        # Keep embeddings ephemeral. Only anonymous time spans and labels persist.
        rows, turns = _speaker_labels(src, duration, rows, speaker_model, cache)
        warnings.append('Mixed-track speakers are acoustic estimates. Check short, overlapping and ambiguous turns.')
    if speaker_tracks:
        warnings.append('Speaker labels use the supplied isolated microphone mapping. Check bleed and track ownership.')
    method = 'isolated_audio_tracks' if speaker_tracks else ('speaker_embeddings' if speaker_model else 'unassigned')
    return {'segments': rows, 'language': lang or (languages.most_common(1)[0][0] if languages else None),
            'languages': list(languages), 'speaker_method': method, 'diarization': {'method': method, 'turns': turns},
            'model': model.name, 'device': ', '.join(sorted(devices)), 'timing': 'source-relative seconds',
            'warnings': warnings, 'chunk_seconds': chunk_seconds, 'chunks': chunks * len(tracks), 'cached_chunks': cached}
