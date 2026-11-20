"""Offline intake and quality checks for the local ClipOps video pilot."""
from __future__ import annotations

import html
import json
import math
from fractions import Fraction
import os
from pathlib import Path
import re
import subprocess
import threading
import time
import unicodedata

MAX_SOURCE_BYTES = 20 * 1024**3
MAX_SOURCE_SECONDS = 3 * 3600
MAX_EXPORT_SECONDS = 180
MAX_PIXELS = 8192 * 4320
MEDIA_INPUT_OPTIONS = (
    "-protocol_whitelist", "file", "-format_whitelist", "mov,matroska,webm",
    "-max_streams", "32", "-threads", "2", "-max_pixels", str(MAX_PIXELS),
)
PROBE_ENTRIES = (
    "format=format_name,duration:format_tags=major_brand:"
    "stream=index,codec_type,codec_name,width,height,pix_fmt,color_transfer,color_space,color_primaries,sample_aspect_ratio,"
    "avg_frame_rate,start_time,duration,nb_frames,channels,sample_rate:"
    "stream_side_data=rotation:stream_disposition=attached_pic"
)

MANUAL_REVIEW = [
    "Watch the opening and closing cut in source context. Verify the speaker's meaning and the hook.",
    "Watch at phone size. Verify eyes, faces, product details and caption placement throughout the edit.",
    "Listen against the speaker's lips, music and original speech. Stream timestamps alone cannot confirm lip sync.",
    "Read the captions against the audio, including names, Arabic shaping, punctuation and code-switches.",
    "Compare image detail, color, crop and motion with the original. Encoding cannot establish recovered detail.",
    "Compare similar takes across the batch. Confirm source, brand, music and insert rights before delivery.",
]


def _run(command, timeout):
    """Bound diagnostic output as well as wall time for untrusted media headers."""
    try:
        proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError as exc:
        raise RuntimeError(f"{command[0]} must be installed locally") from exc
    deadline = time.monotonic() + timeout
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    errors = []

    def drain(name):
        try:
            stream = proc.stdout if name == "stdout" else proc.stderr
            while True:
                chunk = os.read(stream.fileno(), 65536)
                if not chunk:
                    break
                output = buffers[name]
                if len(output) + len(chunk) > 2 * 1024**2:
                    raise ValueError("Media diagnostics exceeded the local inspection limit")
                output.extend(chunk)
        except BaseException as exc:
            errors.append(exc)

    # select() only accepts sockets on Windows; threads drain pipes on every OS.
    readers = [threading.Thread(target=drain, args=(name,), daemon=True)
               for name in ("stdout", "stderr")]
    for reader in readers:
        reader.start()
    try:
        code = proc.wait(timeout=max(.01, deadline - time.monotonic()))
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"{command[0]} exceeded its inspection deadline") from exc
    finally:
        if proc.poll() is None:
            proc.kill()
    for reader in readers:
        reader.join(timeout=max(.01, deadline - time.monotonic()))
    if proc.stdout:
        proc.stdout.close()
    if proc.stderr:
        proc.stderr.close()
    if errors:
        raise errors[0]
    return subprocess.CompletedProcess(command, code, *(buffers[k].decode("utf-8", "replace")
                                                         for k in ("stdout", "stderr")))


def _number(value):
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _frame_rate(stream):
    try:
        return float(Fraction(stream.get("avg_frame_rate", "0")))
    except (TypeError, ValueError, ZeroDivisionError, OverflowError):
        return 0.


def validate_source(path: str | Path) -> dict:
    """Accept self-contained local media from a supported container family.

    File extensions, signatures and FFprobe's selected demuxer must agree.
    The media bytes are never copied into the returned metadata.
    """
    source = Path(path).expanduser()
    if not source.is_file():
        raise ValueError("Source must be a regular local file")
    size = source.stat().st_size
    if not 0 < size <= MAX_SOURCE_BYTES:
        raise ValueError("Source exceeds the 20 GiB intake limit or is empty")
    suffix = source.suffix.lower()
    if suffix not in {".mp4", ".m4v", ".mov", ".webm", ".mkv"}:
        raise ValueError("Use an MP4, MOV, M4V, MKV or WebM source")
    with source.open("rb") as stream:
        signature = stream.read(512)
    is_ebml = signature.startswith(b"\x1a\x45\xdf\xa3")
    is_bmff = signature[4:8] in (b"ftyp", b"moov", b"mdat", b"free", b"wide", b"skip")
    if suffix in (".webm", ".mkv"):
        # The EBML header identifies the particular document type (Matroska/WebM).
        doctype = re.search(rb"\x42\x82([\x81-\xfe])(webm|matroska)", signature)
        if not is_ebml or not doctype or (suffix == ".webm" and doctype[2] != b"webm"):
            raise ValueError("Matroska/WebM file header does not match the extension")
        container = "webm" if doctype[2] == b"webm" else "matroska"
        mime = "video/webm" if container == "webm" else "video/x-matroska"
    else:
        if not is_bmff:
            raise ValueError("ISO media file header does not match the extension")
        container, mime = "mp4", "video/mp4"

    probe = _run(["ffprobe", "-v", "error", "-max_alloc", "268435456", *MEDIA_INPUT_OPTIONS,
                  "-show_entries", PROBE_ENTRIES, "-of", "json", str(source.resolve())], 40)
    if probe.returncode or probe.stderr.strip():
        raise ValueError("FFprobe could not read the local media cleanly")
    info = json.loads(probe.stdout)
    fmt, streams = info["format"], info.get("streams", [])
    detected = fmt.get("format_name", "").split(",")
    if ("matroska" if is_ebml else "mov") not in detected:
        raise ValueError("Detected container disagrees with file signature")
    if is_bmff and (fmt.get("tags", {}).get("major_brand") == "qt  " or
                    (signature[4:8] != b"ftyp" and suffix == ".mov")):
        container, mime = "mov", "video/quicktime"
    seconds = _number(fmt.get("duration"))
    if seconds is None or not 0 < seconds <= MAX_SOURCE_SECONDS:
        raise ValueError("A finite media duration up to 3 hours is required")
    videos = [s for s in streams if s["codec_type"] == "video"]
    if len(videos) != 1 or videos[0].get("disposition", {}).get("attached_pic"):
        raise ValueError("Supply one video track without attached cover pictures")
    video = videos[0]
    width, height = video.get("width", 0), video.get("height", 0)
    if min(width, height) < 2 or max(width, height) > 8192 or width * height > MAX_PIXELS:
        raise ValueError("Unsupported source dimensions")
    if not 0 < _frame_rate(video) <= 240:
        raise ValueError("Source frame rate must be measurable and at most 240 fps")
    aspect = video.get("sample_aspect_ratio", "1:1")
    try:
        aspect_ratio = Fraction(aspect.replace(":", "/")) if aspect not in ("0:1", "N/A") else Fraction(1)
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError("Unsupported pixel aspect ratio") from exc
    display_width = width * aspect_ratio
    if not (1 / 8 <= aspect_ratio <= 8 and display_width <= 8192 and display_width * height <= MAX_PIXELS):
        raise ValueError("Square-pixel source geometry exceeds the local intake limits")
    audio = [s for s in streams if s["codec_type"] == "audio"]
    if any(not (1 <= s.get("channels", 0) <= 16 and 0 < int(s.get("sample_rate", 0)) <= 192000)
           for s in audio):
        raise ValueError("Unsupported audio channel count or sampling rate")
    rotation = next((s["rotation"] for s in video.get("side_data_list", []) if "rotation" in s), 0) % 360
    if rotation not in (0, 90, 180, 270):
        raise ValueError("Normalize the source's arbitrary display rotation before intake")
    dims = [height, width] if rotation in (90, 270) else [width, height]
    return {"duration": seconds, "dimensions": dims, "coded_dimensions": [width, height],
            "rotation": rotation, "sample_aspect_ratio": aspect,
            "container": container, "mime": mime, "streams": streams, "bytes": size,
            "has_audio": bool(audio), "fps": _frame_rate(video)}


def _stream_delta(video, audio, end=False):
    v, a = _number(video.get("start_time")), _number(audio.get("start_time"))
    if v is None or a is None:
        return None
    if end:
        vd, ad = _number(video.get("duration")), _number(audio.get("duration"))
        if vd is None or ad is None:
            return None
        v, a = v + vd, a + ad
    return round(abs(v - a), 4)


def _caption_report(cues, duration, dimensions):
    width, height = dimensions
    previous = 0.
    invalid_times, overflow = [], []
    measured = 0
    for i, cue in enumerate(cues):
        start, end = _number(cue.get("start")), _number(cue.get("end"))
        if (start is None or end is None or start < previous - 0.001 or start < 0 or
                end <= start or end > duration + 0.001 or not str(cue.get("text", "")).strip()):
            invalid_times.append(i + 1)
        if end is not None:
            previous = end
        lines = cue.get("lines") or str(cue.get("text", "")).splitlines()
        widths, available = cue.get("line_widths"), _number(cue.get("max_width"))
        measured_width = widths is not None and available is not None
        block_height, max_height = _number(cue.get("block_height")), _number(cue.get("max_height"))
        fits_height = (max_height is not None and block_height is not None and
                       0 < block_height <= max_height <= math.ceil(height * .22))
        if (not isinstance(lines, list) or not 1 <= len(lines) <= 3 or
                (len(lines) == 3 and not (measured_width and fits_height)) or
                ("block_height" in cue and not fits_height)):
            overflow.append(i + 1)
            continue
        if measured_width:
            measured += 1
            values = [_number(v) for v in widths] if isinstance(widths, (list, tuple)) else []
            if (not 0 < available <= width or len(values) != len(lines) or
                    any(v is None or v <= 0 or v > available + 1 for v in values)):
                overflow.append(i + 1)
        else:
            # A generous fallback detects obvious errors when pixel metrics were not supplied.
            # Combining marks have zero columns. Pixel fit still needs visual verification.
            for line in lines:
                columns = sum(0 if unicodedata.combining(c) else 2 if unicodedata.east_asian_width(c)
                              in ("F", "W") else 1 for c in str(line))
                if columns > 48:
                    overflow.append(i + 1)
                    break
    return {"caption_timing": bool(cues) and not invalid_times,
            "caption_line_bounds": bool(cues) and not overflow}, {
        "count": len(cues), "cues_with_measured_widths": measured,
        "timing_failures": invalid_times, "line_bound_failures": overflow}


def _check_sidecar(path, cues):
    """Compare the editor-delivered sidecar bytes to the clip's rendered cues."""
    from clipops import sec_to_stamp

    if not path.is_file() or path.is_symlink() or path.stat().st_size > 2 * 1024**2:
        return False
    vtt = path.suffix == ".vtt"
    expected = ["WEBVTT", ""] if vtt else []
    for index, cue in enumerate(cues, 1):
        if not vtt:
            expected.append(str(index))
        try:
            left = sec_to_stamp(float(cue["start"]), vtt)
            right = sec_to_stamp(float(cue["end"]), vtt)
        except (ValueError, OverflowError, TypeError, KeyError):
            return False
        lines = cue.get("lines") or str(cue.get("text", "")).splitlines()
        expected.extend([f"{left} --> {right}", *(html.escape(str(line), quote=False) for line in lines), ""])
    try:
        actual = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        return False
    return actual.rstrip("\n") == "\n".join(expected).rstrip("\n")


def _scan(path, has_audio, secs):
    # Decode *every* frame before measuring motion. Downsample for detector cost;
    # fingerprint the decoded picture and mono PCM to ignore container metadata.
    cmd = ["ffmpeg", "-nostdin", "-nostats", "-hide_banner", "-loglevel", "info",
           "-xerror", "-max_error_rate", "0", "-max_alloc", "268435456", *MEDIA_INPUT_OPTIONS,
           "-err_detect", "explode", "-i", str(Path(path).resolve()), "-map", "0:V:0",
           "-filter_threads", "1", "-vf",
           "scale=192:192:force_original_aspect_ratio=decrease:force_divisible_by=2,"
           "blackdetect=d=0:pix_th=0.10:pic_th=0.98,freezedetect=n=-58dB:d=2,format=gray",
           "-fps_mode", "passthrough", "-c:v", "rawvideo", "-threads:v", "1"]
    if has_audio:
        cmd += ["-map", "0:a:0", "-af", "ebur128=peak=true:framelog=verbose,"
                "astats=measure_perchannel=none:measure_overall=Number_of_samples,aresample=8000",
                "-ac", "1", "-c:a", "pcm_s16le"]
    result = _run([*cmd, "-progress", "pipe:1", "-f", "hash", "-hash", "sha256", "pipe:1"],
                  max(45, round(secs * 6) + 15))
    output, diag = result.stdout, result.stderr
    digest = re.search(r"(?m)^SHA256=([a-f0-9]{64})$", output)
    frames = re.findall(r"(?m)^frame=(\d+)$", output)
    black = [{"start": float(start), "end": float(end), "duration": float(span)}
             for start, end, span in re.findall(r"black_start:([\d.]+) black_end:([\d.]+) black_duration:([\d.]+)", diag)]
    freezes = [float(s) for s in re.findall(r"lavfi\.freezedetect\.freeze_start: ([\d.]+)", diag)]
    peak = re.findall(r"Peak:\s+([-\d.inf]+) dBFS", diag)
    loudness = re.findall(r"I:\s+([-\d.inf]+) LUFS", diag)
    samples = re.findall(r"Number of samples:\s+(\d+)", diag)
    return {"decoded": result.returncode == 0 and bool(digest and frames and "progress=end" in output),
            "decoded_frames": int(frames[-1]) if frames else 0,
            "decoded_audio_samples": int(samples[-1]) if samples else 0,
            "decoded_media_sha256": digest[1] if digest else None, "black_intervals": black,
            "freeze_starts_s": freezes, "true_peak_dbtp": _number(peak[-1]) if peak else None,
            "integrated_lufs": _number(loudness[-1]) if loudness else None}


def inspect_export(path: str | Path, expected_duration: float, dimensions, segments=None,
                   source_info=None, *, prior_fingerprints=(), require_sidecars=False) -> dict:
    """Return only technical gate status. Editorial approval is always a separate action.

    segments are clip-relative rendered caption cues. prior_fingerprints contains
    decoded_media_sha256 values from other exports intended to be distinct.
    """
    checks, evidence = {}, {}
    report = {"passed": False, "checks": checks, "evidence": evidence, "manual_review": list(MANUAL_REVIEW)}
    try:
        media = validate_source(path)
        checks["readable_container"] = True
    except (ValueError, OSError, RuntimeError):
        checks["readable_container"] = False
        return report
    seconds = media["duration"]
    video = next(s for s in media["streams"] if s["codec_type"] == "video")
    audio = next((s for s in media["streams"] if s["codec_type"] == "audio"), {})
    expected = _number(expected_duration)
    tolerance = max(0.10, 2 / media["fps"])
    evidence.update(duration_s=seconds, dimensions=media["dimensions"], fps=media["fps"],
                    streams=[s["codec_type"] for s in media["streams"]], source_bounds="unavailable")
    checks.update(
        export_duration=0 < seconds <= MAX_EXPORT_SECONDS and expected is not None and
                        0 < expected <= MAX_EXPORT_SECONDS and abs(seconds - expected) <= tolerance,
        export_dimensions=media["dimensions"] == list(dimensions) and media["rotation"] == 0,
        mp4_container=media["container"] == "mp4",
        h264_420=video["codec_name"] == "h264" and video["pix_fmt"] == "yuv420p",
        square_pixels=video.get("sample_aspect_ratio", "1:1") in ("1:1", "N/A"),
        standard_fps=1 <= media["fps"] <= 120,
        delivery_streams=sorted(evidence["streams"]) == ["audio", "video"],
        aac_audio=audio.get("codec_name") == "aac" and audio.get("sample_rate") in ("44100", "48000")
                  and audio.get("channels") in (1, 2))
    start_delta = _stream_delta(video, audio)
    end_delta = _stream_delta(video, audio, end=True)
    evidence.update(av_start_delta_s=start_delta, av_end_delta_s=end_delta, timing_tolerance_s=tolerance)
    checks["av_start_alignment"] = start_delta is not None and start_delta <= tolerance
    checks["av_end_alignment"] = end_delta is not None and end_delta <= tolerance
    if segments is not None:
        cap_checks, cap_evidence = _caption_report(segments, expected if expected is not None else seconds,
                                                   media["dimensions"])
        checks.update(cap_checks)
        evidence["captions"] = cap_evidence
        sidecars = [Path(path).with_suffix(suffix) for suffix in (".srt", ".vtt")]
        if require_sidecars or any(item.exists() for item in sidecars):
            checks["editable_sidecars_match"] = all(_check_sidecar(item, segments) for item in sidecars)
    else:
        checks["caption_evidence_available"] = False
    if source_info:
        src_dims = sorted(source_info["dimensions"])
        out_dims = sorted(media["dimensions"])
        evidence.update(source_bounds="probed", source_dimensions=source_info["dimensions"],
                        source_fewer_pixels=src_dims[0] * src_dims[1] < out_dims[0] * out_dims[1])
        checks["source_duration_bound"] = seconds <= source_info["duration"] + tolerance
        checks["source_supported_4k"] = max(out_dims) <= 1920 or all(s >= o for s, o in zip(src_dims, out_dims))
    if seconds > MAX_EXPORT_SECONDS:
        return report
    try:
        scan = _scan(path, bool(audio), seconds)
    except (ValueError, OSError, RuntimeError):
        checks["full_decode"] = False
        return report
    evidence.update(scan)
    checks["full_decode"] = scan["decoded"] and scan["decoded_frames"] > 0
    frame_count = _number(video.get("nb_frames"))
    checks["video_frame_count"] = frame_count is not None and scan["decoded_frames"] == frame_count
    audio_duration = _number(audio.get("duration"))
    sample_rate = _number(audio.get("sample_rate"))
    sample_secs = scan["decoded_audio_samples"] / sample_rate if sample_rate else 0.
    evidence["decoded_audio_duration_s"] = round(sample_secs, 4)
    checks["audio_sample_duration"] = audio_duration is not None and abs(sample_secs - audio_duration) <= tolerance
    checks["no_black_run"] = all(b["duration"] < 0.30 for b in scan["black_intervals"])
    checks["no_freeze_2s"] = not scan["freeze_starts_s"]
    peak = scan["true_peak_dbtp"]
    checks["audible_signal"] = peak is not None and peak > -60
    checks["true_peak_headroom"] = peak is not None and peak <= -0.1
    checks["distinct_decoded_media"] = bool(scan["decoded_media_sha256"]) and scan["decoded_media_sha256"] not in prior_fingerprints
    report["passed"] = all(checks.values())
    return report
