"""Local ClipOps editorial rendering. All edit times are seconds, all asset paths local.

render() uses source timestamps for transcript, speaker labels and reviewed remove_ranges.
Cutaway at/until and returned captions are relative to the edited output. Optional logo
and cutaway assets require explicit rights confirmation. All outputs belong in a private
per-job directory. Callers should promote the completed directory as a unit.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
import html
import json
import logging
import math
import os
from pathlib import Path
import re
import statistics
import subprocess
import tempfile
import unicodedata
import wave

from clipops import sec_to_stamp


@dataclass(frozen=True)
class Style:
    name: str
    font: str
    accent: str
    background: str
    words: int
    font_fraction: float
    highlight: bool


STYLES = {
    "business": Style("Business education", "DejaVu Sans", "#8EE3C6", "#101C20", 6, .057, True),
    "value": Style("Value-driven", "DejaVu Sans", "#FFCF57", "#191922", 4, .067, True),
    "podcast": Style("Premium podcast", "DejaVu Sans", "#E8BC8B", "#171B25", 7, .054, True),
    "cinematic": Style("Cinematic storytelling", "DejaVu Serif", "#E7CEB4", "#181919", 8, .052, False),
    "egyptian": Style("Egyptian education", "DejaVu Sans", "#8EDFC9", "#112026", 5, .061, True),
    "fashion": Style("Fashion campaign", "DejaVu Serif", "#F5BCCD", "#201B25", 4, .058, False),
    "workshop": Style("Founder workshop", "Liberation Sans", "#ADDAF1", "#15212B", 7, .060, True),
    "gaming": Style("Gaming and entertainment", "DejaVu Sans", "#BBED77", "#19182A", 4, .064, True),
    "minimal": Style("Minimal professional", "Liberation Sans", "#F2F2ED", "#1B2024", 8, .054, False),
}
# Aspect ratio, left/right safe margin, bottom safe margin.
PLATFORMS = {
    "shorts": ((9, 16), .115, .225),
    "reels": ((9, 16), .125, .25),
    "tiktok": ((9, 16), .15, .245),
    "square": ((1, 1), .09, .12),
    "landscape": ((16, 9), .08, .10),
}
FONTS = ("DejaVu Sans", "DejaVu Serif", "Liberation Sans", "Noto Sans Arabic")
FRAMINGS = ("contain", "crop", "faces", "speaker", "split")


def _number(value, name):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number")
    try:
        result = float(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    return result


def _local_run(args, *, cwd=None, timeout=90, binary=False):
    try:
        result = subprocess.run(args, cwd=cwd, capture_output=True, timeout=timeout,
                                stdin=subprocess.DEVNULL, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{args[0]} exceeded its local time budget") from exc
    if result.returncode:
        error = result.stderr.decode("utf-8", "replace")[-1000:]
        raise RuntimeError(f"{args[0]} failed ({result.returncode}): {error}")
    return result.stdout if binary else result.stdout.decode("utf-8", "replace")


# Encoder selection. "auto" probes hardware with a real encoded frame (an FFmpeg
# encoder listing is not evidence that the GPU can actually use it) and always
# keeps libx264 CPU as the last resort.
ENCODERS = ("auto", "cpu", "qsv", "nvenc")
HARDWARE_ENCODERS = ("nvenc", "qsv")
_ENCODER_PROBES = {
    "nvenc": ("h264_nvenc", ["-preset", "p5"]),
    "qsv": ("h264_qsv", ["-global_quality", os.environ.get("CLIPOPS_QSV_QUALITY", "20")]),
}
# Quality settings: NVENC keeps its original CQ=20 VBR behaviour; QSV uses CQP 20
# to match libx264 CRF 20. QSV quality is tunable via CLIPOPS_QSV_QUALITY.
_ENCODER_ARGS = {
    "nvenc": ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "20", "-b:v", "0"],
    "qsv": ["-c:v", "h264_qsv", "-global_quality", os.environ.get("CLIPOPS_QSV_QUALITY", "20")],
    "cpu": ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"],
}
_ENCODER_LOG = logging.getLogger("clipops.encoder")


@lru_cache(maxsize=None)
def _encoder_available(encoder):
    """Return True only after a one-frame encode actually succeeds on this GPU."""
    codec, options = _ENCODER_PROBES[encoder]
    try:
        _local_run(["ffmpeg", "-v", "error", "-nostdin", "-f", "lavfi", "-i", "color=s=192x128",
                    "-frames:v", "1", "-c:v", codec, *options, "-f", "null", "-"], timeout=15)
    except RuntimeError:
        return False
    return True


def _nvenc_available():
    """Backwards-compatible wrapper around the shared hardware probe."""
    return _encoder_available("nvenc")


def _select_encoder(requested):
    """Resolve an encoder mode to ffmpeg codec args, a display name and a trace.

    The trace is structured diagnostics: every probe and its outcome is recorded
    so the desktop app can show why an encoder was chosen or skipped.
    """
    if requested not in ENCODERS:
        raise ValueError("Choose auto, cpu, qsv or nvenc encoder")
    cpu = _ENCODER_ARGS["cpu"]
    if requested == "cpu":
        return list(cpu), "libx264", [{"mode": "cpu", "status": "requested"}]
    # Measured on this host (2026-11-20, 10 s 720p end-to-end render with six
    # caption segments): libx264 8.48 s, h264_qsv 10.88 s. Auto therefore keeps
    # the original NVENC-then-CPU policy so a working QSV probe cannot silently
    # slow every job. Set CLIPOPS_AUTO_QSV=1 to add QSV to auto after measuring
    # your own workload; explicit encoder="qsv" always works without the opt-in.
    auto_qsv = os.environ.get("CLIPOPS_AUTO_QSV", "") == "1"
    if requested == "auto":
        candidates = ("nvenc", "qsv") if auto_qsv else ("nvenc",)
    else:
        candidates = (requested,)
    trace = []
    for name in candidates:
        ok = _encoder_available(name)
        trace.append({"mode": name, "status": "available" if ok else "unavailable"})
        if ok:
            return list(_ENCODER_ARGS[name]), name, trace
    trace.append({"mode": "cpu", "status": "fallback"})
    return list(cpu), "libx264", trace


def _brand(brand, style):
    brand = dict(brand or {})
    unknown = brand.keys() - {"font", "accent", "text", "background", "logo", "rights_confirmed"}
    if unknown:
        raise ValueError("Unknown brand setting")
    settings = {"font": style.font, "accent": style.accent, "text": "#FFFFFF",
                "background": style.background, **brand}
    if settings["font"] not in FONTS:
        raise ValueError("Unsupported brand typeface")
    for key in ("accent", "text", "background"):
        if not isinstance(settings[key], str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", settings[key]):
            raise ValueError(f"{key} must be #RRGGBB")
    if settings.get("logo") and settings.get("rights_confirmed") is not True:
        raise ValueError("A local logo requires explicit rights confirmation")
    return settings


def _clean_text(value):
    if not isinstance(value, str):
        raise ValueError("Caption text must be a string")
    value = "".join(" " if unicodedata.category(c) == "Cc" else c for c in value)
    return " ".join(value.split())


def _visible_rows(segments, start, end):
    """Prefer reviewed text if the source transcript's word list is stale."""
    result = []
    for segment in segments:
        a, b = _number(segment["start"], "cue start"), _number(segment["end"], "cue end")
        if a < 0 or b <= a:
            raise ValueError("Invalid source caption interval")
        if b <= start or a >= end:
            continue
        text = _clean_text(segment["text"])
        if not text:
            continue
        words = segment.get("words", [])
        if words and "".join(text.split()) == "".join(
                _clean_text(w.get("word", w.get("text", ""))).replace(" ", "") for w in words):
            items = []
            for word in words:
                word_start = _number(word["start"], "word start")
                word_end = _number(word["end"], "word end")
                label = _clean_text(word.get("word", word.get("text", "")))
                if not (a - .05 <= word_start < word_end <= b + .05):
                    raise ValueError("Word timing lies outside its source segment")
                if label and word_end > start and word_start < end:
                    items.append((max(a, word_start), min(b, word_end), label, True))
        else:
            items = [(a, b, text, len(text.split()) == 1)]
        for left, right, label, timed in items:
            result.append({"start": max(start, left) - start, "end": min(end, right) - start,
                           "text": label, "timed": timed, "speaker": segment.get("speaker")})
    return sorted(result, key=lambda row: row["start"])


def _phrases(rows, max_words):
    phrases = []
    group = []

    def flush():
        if group:
            phrases.append({"start": group[0]["start"], "end": max(x["end"] for x in group),
                            "text": " ".join(x["text"] for x in group),
                            "words": list(group) if all(x["timed"] for x in group) else []})
            group.clear()

    for item in rows:
        if group and (not item["timed"] or not group[0]["timed"]
                      or item["speaker"] != group[0]["speaker"] or len(group) >= max_words
                      or item["start"] - group[-1]["end"] > .60
                      or item["end"] - group[0]["start"] > 3.6
                      or re.search(r"[.!?؟…]$", group[-1]["text"])):
            flush()
        group.append(item)
    flush()
    # Simultaneous speech uses a single readable block. Overlapping karaoke events would collide.
    result = []
    for phrase in phrases:
        if result and phrase["start"] < result[-1]["end"]:
            prior = result[-1]
            prior.update(end=max(prior["end"], phrase["end"]),
                         text=prior["text"] + " " + phrase["text"], words=[])
        else:
            result.append(phrase)
    return result


@lru_cache(maxsize=12)
def _font_path(family):
    if os.name == "nt":
        from clipops_compat import font_path
        path = font_path(family)
        if path and Path(path).is_file():
            return path
        raise RuntimeError("A local caption font is required")
    path = _local_run(["fc-match", "--format=%{file}", family + ":style=Bold"]).strip()
    if not path or not Path(path).is_file():
        raise RuntimeError("A local caption font and Fontconfig are required")
    return path


@lru_cache(maxsize=128)
def _font(family, size):
    try:
        from PIL import ImageFont
    except ImportError as exc:
        raise RuntimeError("Install Pillow for measured caption layout") from exc
    return ImageFont.truetype(_font_path(family), size)


def _fit_text(text, family, base, minimum, max_width, max_height):
    # Reserve outline and shaping tolerance; exact line widths are recorded for QC.
    for size in range(base, minimum - 1, -2):
        font = _font(family, size)
        lines = []
        line = ""
        for word in text.split():
            tentative = (line + " " + word).strip()
            if line and font.getlength(tentative) > max_width * .95:
                lines.append(line)
                line = word
            else:
                line = tentative
        if line:
            lines.append(line)
        widths = [math.ceil(font.getlength(part)) for part in lines]
        # Short phrases fit in two lines. A coarse sentence with one source interval can use
        # a third line at a slightly smaller size rather than inventing word timestamps.
        allowed_lines = 3 if size <= base * .86 else 2
        ascent, descent = font.getmetrics()
        block_height = (ascent + descent) * len(lines) + 2 * math.ceil(size * .055)
        if (len(lines) <= allowed_lines and max(widths, default=0) <= max_width * .95
                and block_height <= max_height):
            return size, lines, widths, block_height
    raise ValueError("Caption exceeds its safe area at readable size. Split the source cue at reviewed timestamps.")


def _ass_color(rgb):
    return rgb[5:7] + rgb[3:5] + rgb[1:3]


def _ass_stamp(seconds):
    cs = max(0, round(seconds * 100))
    hours, cs = divmod(cs, 360000)
    minutes, cs = divmod(cs, 6000)
    sec, cs = divmod(cs, 100)
    return f"{hours}:{minutes:02}:{sec:02}.{cs:02}"


def _ass_escape(text):
    # libass supports literal braces via backslash. A word joiner preserves a literal
    # backslash before N/n/h and prevents a transcript from inserting line/space commands.
    return text.replace("\\", "\\\u2060").replace("{", r"\{").replace("}", r"\}")


def _caption_files(directory, segments, ranges, style, platform, dimensions, brand, center_band=False):
    width, height = dimensions
    short_side = min(width, height)
    base = round(short_side * style.font_fraction)
    horizontal = math.ceil(width * PLATFORMS[platform][1])
    bottom = math.ceil(height * PLATFORMS[platform][2])
    max_width = width - 2 * horizontal
    max_height = math.floor(height * .22)
    panel = brand["background"]
    events = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}", f"PlayResY: {height}",
        "ScaledBorderAndShadow: yes", "WrapStyle: 2", "YCbCr Matrix: TV.709",
        "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,"
        "Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,"
        "Alignment,MarginL,MarginR,MarginV,Encoding",
        f"Style: Body,{brand['font']},{base},&H00{_ass_color(brand['text'])},"
        f"&H00{_ass_color(brand['accent'])},&H10{_ass_color(panel)},&H65000000,"
        f"-1,0,0,0,100,100,0,0,1,{max(2, round(base*.055))},1,2,{horizontal},{horizontal},{bottom},1",
        "[Events]", "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text"
    ]
    srt = []
    vtt = ["WEBVTT", ""]
    captions = []
    elapsed = 0.0
    for left, right in ranges:
        for cue in _phrases(_visible_rows(segments, left, right), style.words):
            size, lines, widths, block_height = _fit_text(
                cue["text"], brand["font"], base, round(short_side * .034), max_width, max_height)
            a = round(elapsed + cue["start"], 3)
            b = round(elapsed + cue["end"], 3)
            if b <= a:
                continue
            timed = cue["words"] if style.highlight else []
            tokens = [w for line in lines for w in line.split()]
            if len(tokens) != len(timed):
                timed = []
            captions.append({"start": a, "end": b, "text": cue["text"], "lines": lines,
                             "line_widths": widths, "max_width": max_width,
                             "block_height": block_height, "max_height": max_height,
                             "font_size": size, "timing": "word-highlight" if timed else "phrase"})
            safe_lines = [html.escape(line, quote=False) for line in lines]
            srt += [str(len(captions)), f"{sec_to_stamp(a)} --> {sec_to_stamp(b)}", *safe_lines, ""]
            vtt += [f"{sec_to_stamp(a, True)} --> {sec_to_stamp(b, True)}", *safe_lines, ""]
            cuts = {a, b}
            for word in timed:
                cuts.update((max(a, min(b, elapsed + word["start"])), max(a, min(b, elapsed + word["end"]))))
            points = sorted(cuts)
            for begin, finish in zip(points, points[1:]):
                if _ass_stamp(begin) == _ass_stamp(finish):
                    continue
                mid = (begin + finish) / 2 - elapsed
                active = next((i for i, word in enumerate(timed) if word["start"] <= mid < word["end"]), None)
                spans = []
                index = 0
                for line in lines:
                    pieces = []
                    for token in line.split():
                        value = _ass_escape(token)
                        if index == active:
                            value = (r"{\1c&H" + _ass_color(brand["accent"]) + "&}" + value
                                     + r"{\1c&H" + _ass_color(brand["text"]) + "&}")
                        pieces.append(value)
                        index += 1
                    spans.append(" ".join(pieces))
                placement = rf"\an5\pos({width//2},{height//2})" if center_band else ""
                body = r"{\fs" + str(size) + placement + "}" + r"\N".join(spans)
                events.append(f"Dialogue: 0,{_ass_stamp(begin)},{_ass_stamp(finish)},Body,,0,0,0,,{body}")
        elapsed += right - left
    for name, lines in (("captions.ass", events), ("captions.srt", srt), ("captions.vtt", vtt)):
        (directory / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return captions


def _keep_ranges(start, end, remove_ranges):
    keep = []
    cursor = start
    cuts = remove_ranges or []
    if len(cuts) > 12:
        raise ValueError("Up to 12 reviewed cuts per clip")
    for a, b in sorted((_number(a, "cut start"), _number(b, "cut end")) for a, b in cuts):
        if not cursor <= a < b <= end:
            raise ValueError("Reviewed cuts must be disjoint and within the source selection")
        if a > cursor:
            keep.append((cursor, a))
        cursor = b
    if cursor < end:
        keep.append((cursor, end))
    if not keep or min(b - a for a, b in keep) < .25:
        raise ValueError("Reviewed cut leaves less than 0.25 s of retained footage")
    return keep


def punch_in_plan(punch_ins, ranges):
    """Convert reviewed source-time accents to nonoverlapping edited intervals."""
    if not isinstance(punch_ins, list) or len(punch_ins) > 8:
        raise ValueError("Choose up to eight punch-ins")
    plan = []
    for item in punch_ins:
        if not isinstance(item, dict) or set(item) != {"start", "end", "scale"}:
            raise ValueError("Punch-ins require start, end and scale")
        start, end, scale = (_number(item[key], key) for key in ("start", "end", "scale"))
        if end - start < .4 or not 1.02 <= scale <= 1.18:
            raise ValueError("Use at least 0.4 seconds and a scale from 1.02 to 1.18")
        elapsed = 0.
        for left, right in ranges:
            if left <= start < end <= right:
                plan.append((elapsed + start - left, elapsed + end - left, scale))
                break
            elapsed += right - left
        else:
            raise ValueError("Each punch-in must fit inside one retained source interval")
    plan.sort()
    if any(one[1] > two[0] for one, two in zip(plan, plan[1:])):
        raise ValueError("Punch-ins must not overlap")
    return plan


def _guard_cut_words(segments, ranges, start, end):
    boundaries = [t for interval in ranges for t in interval if start < t < end]
    if not boundaries:
        return
    for item in _visible_rows(segments, start, end):
        for t in boundaries:
            if item["start"] + start + .025 < t < item["end"] + start - .025:
                raise ValueError("Review cuts at word boundaries; split an untimed source cue before trimming it")


def suggest_trims(segments, start, end):
    """Offer pauses and isolated filler words for review. Nothing is removed automatically."""
    rows = _visible_rows(segments, start, end)
    result = []
    last_end = None
    for row in rows:
        if last_end is not None and row["start"] - last_end >= 1.5:
            result.append({"start": round(start + last_end + .25, 3),
                           "end": round(start + row["start"] - .25, 3),
                           "reason": "Transcript gap; listen for breaths, music and intentional pauses"})
        if row["timed"] and row["text"].casefold().strip(" .,?!؟،") in {"um", "uh", "umm", "uhh", "اممم", "أمم"}:
            result.append({"start": round(start + row["start"], 3), "end": round(start + row["end"], 3),
                           "reason": "Isolated filler; confirm meaning by ear"})
        last_end = max(last_end or 0, row["end"])
    return result


def _anchors(positions):
    result = {}
    if positions:
        if not isinstance(positions, dict) or len(positions) > 16:
            raise ValueError("Expected a speaker-to-position map")
        for name, value in positions.items():
            position = _number(value, "speaker center")
            if not 0 <= position <= 1:
                raise ValueError("Speaker centers must be between 0 and 1")
            result[name] = position
    return result


def _speaker_points(segments, start, end, anchors):
    rows = sorted((s for s in segments if s["end"] > start and s["start"] < end), key=lambda s: s["start"])
    if not rows or any(s.get("speaker") not in anchors for s in rows):
        return []
    points = [(0.0, anchors[rows[0]["speaker"]])]
    previous_end = rows[0]["end"]
    for row in rows:
        x = anchors[row["speaker"]]
        if x != points[-1][1]:
            if row["start"] + .15 < previous_end:
                return []  # Cross-talk has no single active speaker.
            points.append((max(0, row["start"] - start), x))
        previous_end = max(previous_end, row["end"])
    return points if len(points) <= 64 else []


def _face_layout(source, options, start, end):
    """Sample authorized footage locally. Preserve context on ambiguous or intermittent detections."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return "contain", [], "OpenCV unavailable; full frame retained"
    detector = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    if detector.empty():
        return "contain", [], "Local face detector unavailable; full frame retained"
    fps = min(2, 32 / (end - start))
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-filter_threads", "1",
           "-ss", str(start), "-t", str(end - start), *options, "-i", str(source), "-map", "0:V:0",
           "-an", "-vf", f"fps={fps:.6f},scale=320:240:force_original_aspect_ratio=decrease,"
           "pad=320:240:(ow-iw)/2:(oh-ih)/2,setsar=1", "-pix_fmt", "gray",
           "-threads", "1", "-frames:v", "32", "-f", "rawvideo", "pipe:1"]
    samples = _local_run(cmd, binary=True, timeout=120)
    frame_size = 320 * 240
    count = len(samples) // frame_size
    if not count:
        return "contain", [], "No sampled faces; full frame retained"
    heights = []
    for i in range(count):
        frame = np.frombuffer(samples, dtype=np.uint8, count=frame_size, offset=i * frame_size).reshape(240, 320)
        faces = detector.detectMultiScale(frame, scaleFactor=1.10, minNeighbors=5, minSize=(22, 22))
        heights.append(sorted((x + w / 2) / 320 for x, _y, w, _h in faces))
    pairs = [f for f in heights if len(f) == 2 and f[1] - f[0] > .20]
    if len(pairs) >= count * .85:
        centers = [statistics.median(p[side] for p in pairs) for side in (0, 1)]
        return "split", [(0, x) for x in centers], f"Two recurring face positions across {len(pairs)}/{count} samples"
    singles = [(i / fps, row[0]) for i, row in enumerate(heights) if len(row) == 1]
    if len(singles) < count * .85 or any(len(row) > 1 for row in heights):
        return "contain", [], "Ambiguous face evidence; full frame retained"
    # Smooth short changes; limit motion to keep cuts and detection jitter out of focus moves.
    smooth = [(0, singles[0][1])]
    for i, (at, _) in enumerate(singles[1:], start=1):
        x = statistics.median(item[1] for item in singles[max(0, i-2):i+1])
        if abs(smooth[-1][1] - x) > .05:
            smooth.append((at, x))
    return "faces", smooth, f"One recurring face across {len(singles)}/{count} samples"


def _framing(mode, source, metadata, options, start, end, segments, speaker_positions):
    if mode not in FRAMINGS:
        raise ValueError("Unsupported framing")
    anchors = _anchors(speaker_positions)
    width, height = metadata["dimensions"]
    if mode == "faces":
        # The detector uses horizontal screen coordinates only; full frame is safe for tall footage.
        if width / height < 4 / 3:
            return "contain", [], "Full portrait retained"
        return _face_layout(source, options, start, end)
    if mode == "speaker":
        points = _speaker_points(segments, start, end, anchors)
        if points:
            return "speaker", points, "Source speaker timestamps and reviewed horizontal positions"
        return "contain", [], "Missing or ambiguous speaker positions; full frame retained"
    if mode == "split":
        if len(anchors) != 2:
            raise ValueError("Split layout needs two reviewed speaker positions")
        if abs(max(anchors.values()) - min(anchors.values())) < .15:
            raise ValueError("Split layout needs two distinct positions")
        return mode, [(0, x) for x in sorted(anchors.values())], "Two reviewed speaker positions"
    return mode, [], "Full scene" if mode == "contain" else "Editor-selected center crop"


def _focus_expression(points):
    # Coordinates were parsed to finite floats; the filtergraph never interpolates source text.
    focus = f"{points[0][1]:.5f}" if points else ".5"
    if points:
        for at, x in points[1:]:
            focus = f"if(gte(t,{at:.3f}),{x:.5f},{focus})"
    return f"'max(0,min(iw-ow,iw*({focus})-ow/2))'"


def _picture_filters(width, height, mode, points, brand, same_aspect, band=0):
    def fill(w, h, focus):
        return (f"scale={w}:{h}:force_original_aspect_ratio=increase:force_divisible_by=2,"
                f"crop={w}:{h}:x={_focus_expression(focus)},setsar=1")
    # Normalize pixel aspect before calculating the crop, also after FFmpeg's display rotation.
    source = "[0:V:0]scale='max(2,2*round(iw*sar/2))':ih,setsar=1"
    if same_aspect and mode != "split":
        return [source + f",scale={width}:{height},setsar=1[framed]"]
    if mode == "contain":
        # Blur a small copy first to bound work even for 4K canvases.
        return [source + ",split[front][back]",
                f"[back]scale={width//4}:{height//4}:force_original_aspect_ratio=increase,"
                f"crop={width//4}:{height//4},boxblur=10:2,eq=brightness=-0.09:saturation=0.65,"
                f"scale={width}:{height},setsar=1,drawbox=color=0x{brand['background'][1:]}@0.38:"
                "x=0:y=0:w=iw:h=ih:t=fill[matte]",
                f"[front]scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2,"
                "setsar=1[sharp]",
                "[matte][sharp]overlay=(W-w)/2:(H-h)/2,setsar=1[framed]"]
    if mode == "split":
        # Limit each panel to its side of the midpoint between the two reviewed centers.
        # This excludes the edges of the opposite face and retains extra headroom.
        pane = (height - band) // 4 * 2
        span = abs(points[1][1] - points[0][1])
        filters = [source + ",split[one][two]"]
        for i, (label, pane_height) in enumerate((("one", pane), ("two", height-band-pane))):
            focus = _focus_expression(points[i:i+1])
            filters.append(f"[{label}]crop=w='max(2,2*trunc(iw*{span:.5f}/2))':h=ih:x={focus},"
                           f"scale={width}:{pane_height}:force_original_aspect_ratio=increase:force_divisible_by=2,"
                           f"crop={width}:{pane_height}:y='(ih-oh)*0.25',setsar=1[pane{i}]")
        if band:
            filters.append(f"[pane0]pad={width}:{pane+band}:0:0:color=0x{brand['background'][1:]}[withband]")
            filters.append("[withband][pane1]vstack,setsar=1[framed]")
        else:
            filters.append("[pane0][pane1]vstack,setsar=1[framed]")
        return filters
    return [source + "," + fill(width, height, points) + "[framed]"]


def _cut_filters(ranges, start, end, has_audio):
    if ranges == [(start, end)]:
        return [], "framed", "0:a:0"
    count = len(ranges)
    filters = []
    if count > 1:
        filters.append(f"[framed]split={count}" + "".join(f"[pv{i}]" for i in range(count)))
        if has_audio:
            filters.append(f"[0:a:0]asplit={count}" + "".join(f"[pa{i}]" for i in range(count)))
    labels = []
    for i, (left, right) in enumerate(ranges):
        a, b = left - start, right - start
        video = f"pv{i}" if count > 1 else "framed"
        filters.append(f"[{video}]trim=start={a:.6f}:end={b:.6f},setpts=PTS-STARTPTS[v{i}]")
        labels.append(f"[v{i}]")
        if has_audio:
            audio = f"pa{i}" if count > 1 else "0:a:0"
            filters.append(f"[{audio}]atrim=start={a:.6f}:end={b:.6f},asetpts=PTS-STARTPTS,"
                           f"afade=t=in:d=0.008,afade=t=out:st={max(0,b-a-.008):.6f}:d=0.008[a{i}]")
            labels.append(f"[a{i}]")
    target = "[picture][sound]" if has_audio else "[picture]"
    filters.append("".join(labels) + f"concat=n={count}:v=1:a={int(has_audio)}" + target)
    return filters, "picture", "sound"


def _prepare_logo(path, directory, width):
    from PIL import Image, ImageOps
    logo = Path(path).expanduser().resolve(strict=True)
    if not logo.is_file() or logo.suffix.lower() != ".png" or logo.stat().st_size > 8 * 1024**2:
        raise ValueError("Logo must be a local PNG up to 8 MiB")
    with Image.open(logo, formats=("PNG",)) as img:
        if img.width * img.height > 8_000_000:
            raise ValueError("Logo dimensions exceed the pixel budget")
        resized = ImageOps.contain(img.convert("RGBA"), (round(width * .16), round(width * .095)))
        resized.save(directory / "logo.png", "PNG")


def _add_art(filters, command, picture, width, height, duration, cutaways, brand, directory, options):
    from pilot_qc import validate_source
    assets = cutaways or []
    if len(assets) > 4:
        raise ValueError("Up to four reviewed cutaways per clip")
    previous_end = 0
    for index, asset in enumerate(assets, start=1):
        if asset.get("rights_confirmed") is not True:
            raise ValueError("Every cutaway needs explicit rights confirmation")
        at = _number(asset["at"], "cutaway start")
        until = _number(asset["until"], "cutaway end")
        offset = _number(asset.get("source_start", 0), "cutaway source start")
        if not previous_end <= at < until <= duration or offset < 0:
            raise ValueError("Cutaways must be disjoint and within edited duration")
        path = Path(asset["path"]).expanduser().resolve(strict=True)
        info = validate_source(path)
        if offset + until - at > info["duration"] + .005:
            raise ValueError("Cutaway exceeds its source duration")
        previous_end = until
        command.extend(["-ss", str(offset), "-t", str(until-at), *options, "-i", str(path)])
        filters.append(f"[{index}:V:0]scale={width}:{height}:force_original_aspect_ratio=decrease:"
                       f"force_divisible_by=2,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:"
                       f"color=0x{brand['background'][1:]},setsar=1,setpts=PTS-STARTPTS+{at}/TB[art{index}]")
        filters.append(f"[{picture}][art{index}]overlay=eof_action=pass:repeatlast=0:"
                       f"enable='gte(t,{at})*lt(t,{until})'[cutaway{index}]")
        picture = f"cutaway{index}"
    if brand.get("logo"):
        _prepare_logo(brand["logo"], directory, width)
        command.extend(["-protocol_whitelist", "file", "-f", "image2", "-pattern_type", "none",
                        "-framerate", "1", "-i", "logo.png"])
        index = len(assets) + 1
        filters.append(f"[{picture}][{index}:v:0]overlay=x={width*.065:.1f}:y={height*.085:.1f}[branded]")
        picture = "branded"
    return picture


def _mix_accents(filters, command, sound, accents, duration, first_index):
    if len(accents) > 4:
        raise ValueError("Up to four reviewed sound accents per clip")
    for index, accent in enumerate(accents, start=first_index):
        if accent.get("rights_confirmed") is not True:
            raise ValueError("Every sound accent needs explicit rights confirmation")
        at = _number(accent["at"], "accent start")
        gain = _number(accent.get("gain_db", -20), "accent gain")
        if not 0 <= at < duration or not -48 <= gain <= -12:
            raise ValueError("Sound accents must be within the clip and attenuated by 12–48 dB")
        path = Path(accent["path"]).expanduser().resolve(strict=True)
        if not path.is_file() or path.suffix.lower() != ".wav" or path.stat().st_size > 6 * 1024**2:
            raise ValueError("Sound accent must be a local PCM WAV up to 6 MiB")
        try:
            with wave.open(str(path), "rb") as asset:
                rate = asset.getframerate()
                length = asset.getnframes() / rate
                if not (8000 <= rate <= 96000 and 0 < length <= 4 and 1 <= asset.getnchannels() <= 2):
                    raise ValueError("Sound accent must be up to four seconds, mono/stereo, at 8–96 kHz")
        except (EOFError, wave.Error, ZeroDivisionError) as exc:
            raise ValueError("Sound accent has an invalid PCM WAV header") from exc
        length = min(length, duration - at)
        command.extend(["-protocol_whitelist", "file", "-format_whitelist", "wav",
                        "-t", str(length), "-i", str(path)])
        delay = round(at * 1000)
        filters.append(f"[{index}:a:0]volume={gain:.2f}dB,afade=t=out:"
                       f"st={max(0,length-.03):.6f}:d=0.03,adelay={delay}:all=1[accent{index}]")
        filters.append(f"[{sound}][accent{index}]amix=inputs=2:duration=first:normalize=0[mixed{index}]")
        sound = f"mixed{index}"
    return sound


def _duck_music(filters, command, voice, music, duration, index):
    if not isinstance(music, dict) or music.get("rights_confirmed") is not True:
        raise ValueError("Confirm rights for the local music bed")
    gain = _number(music.get("gain_db", -24), "music gain")
    if not -40 <= gain <= -18:
        raise ValueError("Music bed gain must be between -40 and -18 dB")
    path = Path(music["path"]).expanduser().resolve(strict=True)
    if not path.is_file() or path.suffix.lower() != ".wav" or path.stat().st_size > 128 * 1024**2:
        raise ValueError("Choose a local PCM WAV music bed of up to 128 MiB")
    try:
        with wave.open(str(path), "rb") as stream:
            rate = stream.getframerate()
            if not 8000 <= rate <= 96000 or not 1 <= stream.getnchannels() <= 2 or not stream.getnframes():
                raise ValueError("Choose a nonempty mono or stereo PCM WAV at 8–96 kHz")
    except (EOFError, wave.Error) as exc:
        raise ValueError("The music bed does not have a valid PCM WAV header") from exc
    command.extend(["-protocol_whitelist", "file", "-format_whitelist", "wav", "-stream_loop", "-1",
                    "-t", str(duration), "-i", str(path)])
    fade = min(.35, duration / 5)
    filters.extend([
        f"[{voice}]aresample=48000,aformat=channel_layouts=stereo,asplit[dialogue][music-key]",
        f"[{index}:a:0]aresample=48000,aformat=channel_layouts=stereo,volume={gain:.2f}dB,"
        f"afade=t=in:d={fade:.4f},afade=t=out:st={duration-fade:.4f}:d={fade:.4f}[music-bed]",
        "[music-bed][music-key]sidechaincompress=threshold=0.025:ratio=8:attack=20:release=280[ducked]",
        "[dialogue][ducked]amix=inputs=2:duration=first:normalize=0[with-music]",
    ])
    return "with-music"


def render(source: Path, output: Path, start: float, end: float, segments: list, style="podcast",
           platform="shorts", *, resolution=1080, framing="contain", brand=None,
           speaker_positions=None, cleanup=False, remove_ranges=None, cutaways=None, push_in=False,
           sound_accents=None, encoder="auto", punch_ins=None, music=None):
    """Render local H.264/AAC plus editable clip-relative SRT and WebVTT.

    remove_ranges are explicit editorial decisions in absolute source time. Set push_in for
    one gentle four-percent push across the finished clip. Wordless sections stay caption-free.
    """
    from pilot_qc import MEDIA_INPUT_OPTIONS, validate_source
    src = Path(source).expanduser().resolve(strict=True)
    out = Path(output).expanduser().resolve()
    if out == src or out.suffix.lower() != ".mp4":
        raise ValueError("Choose a new MP4 output distinct from the source")
    if style not in STYLES or platform not in PLATFORMS or resolution not in (720, 1080, 2160):
        raise ValueError("Unsupported style, platform or resolution")
    if encoder not in ENCODERS:
        raise ValueError("Choose auto, cpu, qsv or nvenc encoder")
    if type(push_in) is not bool or type(cleanup) is not bool:
        raise ValueError("push_in and cleanup must be booleans")
    profile = STYLES[style]
    brand = _brand(brand, profile)
    metadata = validate_source(src)
    if any(s.get("color_transfer") in {"smpte2084", "arib-std-b67"} for s in metadata["streams"]
           if s.get("codec_type") == "video"):
        raise ValueError("This SDR renderer needs an approved SDR conversion of HDR footage")
    start, end = _number(start, "clip start"), _number(end, "clip end")
    if start < 0 or end > metadata["duration"] + .005 or not .25 <= end - start <= 180:
        raise ValueError("Render interval must lie within the source and last 0.25–180 s")
    end = min(end, metadata["duration"])
    ranges = _keep_ranges(start, end, remove_ranges)
    punch_plan = punch_in_plan(punch_ins or [], ranges)
    if punch_plan and push_in:
        raise ValueError("Choose timed punch-ins or a continuous push-in for this clip")
    _guard_cut_words(segments, ranges, start, end)
    length = sum(b - a for a, b in ranges)
    aspect = PLATFORMS[platform][0]
    width, height = (resolution * axis // min(aspect) for axis in aspect)
    source_width, source_height = metadata["dimensions"]
    options = list(MEDIA_INPUT_OPTIONS)
    mode, points, evidence = _framing(framing, src, metadata, options, start, end, segments, speaker_positions)
    target_height = height / 2 if mode == "split" else height
    visible_width = source_width * abs(points[1][1] - points[0][1]) if mode == "split" else source_width
    factor = (min if mode == "contain" else max)(width/visible_width, target_height/source_height)
    factor *= max((step[2] for step in punch_plan), default=1.04 if push_in else 1)
    if resolution == 2160 and (min(source_width, source_height) < 2160
                              or max(source_width, source_height) < max(width, height) or factor > 1.001):
        raise ValueError("4K requires source-supported pixels for this layout")
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".clipops-render-", dir=out.parent) as temp:
        directory = Path(temp)
        captions = _caption_files(directory, segments, ranges, profile, platform, (width, height),
                                  brand, center_band=mode == "split")
        band = 0
        if mode == "split" and captions:
            band = 2 * math.ceil((max(c["block_height"] for c in captions) + height * .026) / 2)
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-max_alloc", "268435456", "-filter_complex_threads", "1",
               "-ss", str(start), "-t", str(end-start), *options, "-i", str(src)]
        same_aspect = abs(source_width / source_height - width / height) < .001
        filters = _picture_filters(width, height, mode, points, brand, same_aspect, band)
        audio = metadata["has_audio"]
        cuts, picture, sound = _cut_filters(ranges, start, end, audio)
        filters.extend(cuts)
        video = next(s for s in metadata["streams"] if s["codec_type"] == "video")
        try:
            fps = Fraction(video.get("r_frame_rate", video.get("avg_frame_rate", "0/1")))
        except (ValueError, ZeroDivisionError, TypeError):
            fps = Fraction(0)
        if cuts:
            # Normalize sub-frame PTS at edit joins before muxing. This avoids
            # an ambiguous end edit in MP4, which can hide the last frame.
            rate = fps if 8 <= fps <= 60 else Fraction(30)
            filters.append(f"[{picture}]fps={rate}:start_time=0:round=near[editclock]")
            picture = "editclock"
        if push_in or punch_plan:
            if not 8 <= fps <= 60:
                raise ValueError("A measured 8–60 fps source rate is required for a push-in")
            clock = f"on/{float(fps):.6f}"
            if punch_plan:
                accents = [f"{scale-1:.5f}*clip(min(({clock}-{a:.6f})/0.16,({b:.6f}-{clock})/0.16),0,1)"
                           for a, b, scale in punch_plan]
                zoom = "1+" + "+".join(accents)
            else:
                zoom = f"1+0.04*min(1,{clock}/{length:.6f})"
            filters.append(f"[{picture}]zoompan=z='{zoom}':"
                           f"x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s={width}x{height}:fps={fps}[zoomed]")
            picture = "zoomed"
        picture = _add_art(filters, cmd, picture, width, height, length, cutaways, brand, directory, options)
        finish = "ass=filename=captions.ass:shaping=complex," if captions else ""
        filters.append(f"[{picture}]{finish}format=yuv420p[outv]")
        if sound_accents:
            if not audio:
                raise ValueError("Sound accents require source audio for the mix")
            sound = _mix_accents(filters, cmd, sound, sound_accents, length,
                                 1 + len(cutaways or []) + bool(brand.get("logo")))
        if music is not None:
            if not audio:
                raise ValueError("Ducking a music bed requires an audible source dialogue track")
            sound = _duck_music(filters, cmd, sound, music, length,
                                1 + len(cutaways or []) + bool(brand.get("logo")) + len(sound_accents or []))
        if audio:
            treatment = "highpass=f=65,afftdn=nr=6:nf=-45," if cleanup else ""
            # Reconcile the samples with the edit clock before encoding. In a
            # concatenated cut, fractional frame boundaries can otherwise
            # produce overlapping decoded audio timestamps after resampling.
            filters.append(f"[{sound}]{treatment}loudnorm=I=-16:TP=-1.5:LRA=9,"
                           "aresample=48000:async=1:first_pts=0,asetpts=N/SR/TB[outa]")
        cmd += ["-filter_complex", ";".join(filters), "-map", "[outv]"]
        if audio:
            cmd += ["-map", "[outa]", "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "192k"]
        cmd += ["-map_metadata", "-1", "-map_chapters", "-1", "-t", str(length), "-threads", "2"]
        cpu = _ENCODER_ARGS["cpu"]
        encoding, used_encoder, trace = _select_encoder(encoder)
        _ENCODER_LOG.info("encoder_selection=%s", json.dumps(
            {"requested": encoder, "chosen": used_encoder, "probes": trace}))
        finish = ["-pix_fmt", "yuv420p", "-movflags", "+faststart", "render.mp4"]
        timeout = max(120, round(length * (15 if resolution == 2160 else 8)))
        try:
            _local_run(cmd + encoding + finish, cwd=directory, timeout=timeout)
        except RuntimeError:
            if encoding == cpu:
                raise
            _ENCODER_LOG.warning("encoder_fallback from=%s to=libx264", used_encoder)
            trace.append({"mode": used_encoder, "status": "runtime_failed"})
            used_encoder = "libx264"
            encoding = cpu
            _local_run(cmd + encoding + finish, cwd=directory, timeout=timeout)
        # Publish the media last; the project layer atomically promotes a fully QC'd artifact directory.
        for filename, target in (("captions.srt", out.with_suffix(".srt")),
                                 ("captions.vtt", out.with_suffix(".vtt")), ("render.mp4", out)):
            os.chmod(directory / filename, 0o600)
            os.replace(directory / filename, target)
    return {"file": str(out), "srt": str(out.with_suffix(".srt")), "vtt": str(out.with_suffix(".vtt")),
            "start": start, "end": end, "duration": round(length, 6), "expected_duration": round(length, 6),
            "style": style, "platform": platform, "resolution": resolution,
            "dimensions": [width, height], "source_dimensions": [source_width, source_height],
            "upscaled": factor > 1.001, "foreground_scale": round(factor, 4), "framing": mode,
            "framing_reason": evidence, "requested_framing": framing, "captions": captions,
            "caption_mode": sorted({cue["timing"] for cue in captions}), "encoder": used_encoder,
            "encoder_requested": encoder, "encoder_probes": trace,
            "retained_source_ranges": ranges, "has_audio": audio, "push_in": push_in,
            "punch_ins": punch_plan,
            "cutaway_count": len(cutaways or []), "sound_accent_count": len(sound_accents or []),
            "music_ducking": music is not None}
