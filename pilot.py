#!/usr/bin/env python3
"""Run and review a private, resumable ClipOps project on a local workstation."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from clipops_compat import LEASE_FLAGS, NOFOLLOW, NONBLOCK, is_private_path, resource, sync_directory as _sync_directory, exclusive as _exclusive_lock
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

import pilot_edit
import pilot_intelligence
import pilot_qc

MAX_MEDIA = pilot_qc.MAX_SOURCE_BYTES
MAX_TRANSCRIPT = 24 * 1024**2
SUFFIXES = {".mp4", ".mov", ".mkv", ".webm"}
ARTIFACTS = {"preview": "clip.mp4", "export": "clip.mp4", "srt": "clip.srt", "vtt": "clip.vtt"}
PROJECT_ID = re.compile(r"[0-9a-f]{32}")
PROJECT_FILE = "project.json"
DEFAULT_ROOT = Path.home() / "ClipOps-private"


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_text(value, field, max_length, *, required=True):
    if not isinstance(value, str) or len(value) > max_length or (required and not value.strip()):
        raise ValueError(f"{field} must be text of at most {max_length} characters")
    if any(ord(char) < 32 and char not in "\t\n\r" for char in value):
        raise ValueError(f"{field} contains control characters")
    return value.strip()


def integer(value, field, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{field} must be an integer between {low} and {high}")
    return value


def number(value, field):
    if isinstance(value, bool):
        raise ValueError(f"Invalid {field}")
    try:
        result = float(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Invalid {field}") from exc
    if not math.isfinite(result):
        raise ValueError(f"Invalid {field}")
    return result


def private_root(root):
    path = Path(root).expanduser()
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise ValueError("Choose a private local directory for project storage")
    if not is_private_path(path, directory=True):
        raise ValueError("Project storage must be private to your OS account (chmod 700)")
    return path.resolve()


def project_dir(root, job_id):
    if not isinstance(job_id, str) or not PROJECT_ID.fullmatch(job_id):
        raise ValueError("Invalid project ID")
    path = private_root(root) / job_id
    if path.is_symlink() or not path.is_dir():
        raise FileNotFoundError("Project was not found")
    return path


@contextmanager
def lock(directory, filename, *, wait=False):
    """The OS releases this nonblocking lock even if a worker is killed."""
    fd = os.open(directory / filename, LEASE_FLAGS, 0o600)
    try:
        try:
            with _exclusive_lock(fd, wait=wait):
                yield
        except BlockingIOError as exc:
            raise ValueError("A worker is busy. Retry when the current operation finishes.") from exc
    finally:
        os.close(fd)


def save_json(path, data):
    with tempfile.NamedTemporaryFile("w", encoding="utf8", dir=path.parent, delete=False) as file:
        tmp = Path(file.name)
        try:
            json.dump(data, file, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
            file.flush()
            os.fsync(file.fileno())
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
    try:
        os.replace(tmp, path)
        sync_directory(path.parent)
    finally:
        tmp.unlink(missing_ok=True)


def sync_directory(path):
    _sync_directory(path)


def load_json(path, maximum=None):
    if not path.is_file() or path.is_symlink() or (maximum and path.stat().st_size > maximum):
        raise ValueError("Missing or oversized local JSON file")
    with path.open(encoding="utf-8-sig") as stream:
        return json.load(stream)


def save_state(directory, state):
    state["updated_at"] = now()
    save_json(directory / PROJECT_FILE, state)


def sha256(path):
    with path.open("rb") as file:
        digest = hashlib.sha256()
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_media(source, dest):
    with source.open("rb") as incoming, dest.open("xb") as output:
        size = os.fstat(incoming.fileno()).st_size
        if not 0 < size <= MAX_MEDIA or not stat.S_ISREG(os.fstat(incoming.fileno()).st_mode):
            raise ValueError("Source must be a regular media file of 1 byte to 20 GiB")
        if shutil.disk_usage(dest.parent).free < size + 64 * 1024**2:
            raise ValueError("Insufficient space for a private media copy and working files")
        os.chmod(dest, 0o600)
        copied = 0
        digest = hashlib.sha256()
        for chunk in iter(lambda: incoming.read(1024 * 1024), b""):
            copied += len(chunk)
            if copied > size:
                raise ValueError("Source changed during intake")
            digest.update(chunk)
            output.write(chunk)
        if copied != size:
            raise ValueError("Source changed during intake")
        return digest.hexdigest()


def file_identity(path):
    flags = os.O_RDONLY | NOFOLLOW | NONBLOCK
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
    finally:
        os.close(fd)
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_MEDIA:
        raise ValueError("Choose a regular local video up to 20 GiB")
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]


def project_source(directory, state):
    reference = state.get("source_reference")
    if not reference:
        path = directory / state["source_file"]
        if path.is_symlink() or not path.is_file():
            raise ValueError("Source is unavailable")
        return path
    path = Path(reference["path"])
    try:
        unchanged = file_identity(path) == reference["identity"]
    except (OSError, ValueError):
        unchanged = False
    if not unchanged:
        raise ValueError("The referenced original changed or moved. Import the new source as a project.")
    return path


def checked_segments(rows, duration, previous=()):
    if not isinstance(rows, list) or len(rows) > 150000:
        raise ValueError("Transcript must contain a bounded list of timed segments")
    old_text = {(item["start"], item["end"]): item["text"] for item in previous}
    result = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Invalid transcript segment")
        a, b = number(row.get("start"), "cue start"), number(row.get("end"), "cue end")
        if not 0 <= a < b <= duration + 0.15 or a >= duration:
            raise ValueError("Transcript cue extends outside source duration")
        text = " ".join(clean_text(row.get("text"), "Caption", 4096).split())
        cue = {"start": a, "end": min(b, duration), "text": text}
        if row.get("speaker") is not None:
            cue["speaker"] = clean_text(row["speaker"], "Speaker", 80)
        words = row.get("words")
        if words is not None and old_text.get((a, b), text) == text:
            if not isinstance(words, list) or len(words) > 1000:
                raise ValueError("Invalid word timing list")
            timings = []
            last = a
            for word in words:
                if not isinstance(word, dict):
                    raise ValueError("Invalid word timing")
                wa, wb = number(word.get("start"), "word start"), number(word.get("end"), "word end")
                if not last - .025 <= wa < wb <= b + .025 or wa < a - .025:
                    raise ValueError("Word timing lies outside its cue or is out of order")
                last = wb
                item = {"start": max(a, wa), "end": min(wb, cue["end"]),
                        "word": clean_text(word.get("word", word.get("text")), "Word", 256)}
                if item["end"] > item["start"]:
                    timings.append(item)
            if timings:
                cue["words"] = timings
        result.append(cue)
    return sorted(result, key=lambda item: item["start"])


def settings(style, platform, resolution, framing, brand, positions):
    if not isinstance(style, str) or not isinstance(platform, str) or style not in pilot_edit.STYLES or platform not in pilot_edit.PLATFORMS:
        raise ValueError("Unknown editing style or export preset")
    if type(resolution) is not int or resolution not in (720, 1080, 2160) or framing not in pilot_edit.FRAMINGS:
        raise ValueError("Unknown resolution or framing option")
    if not isinstance(brand, dict) or set(brand) - {"accent", "text", "background", "font"}:
        raise ValueError("Unknown brand setting")
    for key, value in brand.items():
        if key == "font":
            if value not in pilot_edit.FONTS:
                raise ValueError("Unsupported font")
        elif not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise ValueError("Brand colors require #RRGGBB")
    if not isinstance(positions, dict) or len(positions) > 16:
        raise ValueError("Speaker positions must map speaker names to normalized x coordinates")
    for speaker, x in positions.items():
        clean_text(speaker, "Speaker", 80)
        if not 0 <= number(x, "speaker position") <= 1:
            raise ValueError("Speaker position must be between 0 and 1")
    return {"style": style, "platform": platform, "resolution": resolution, "framing": framing,
            "brand": dict(brand), "speaker_positions": {speaker: float(x) for speaker, x in positions.items()}}


def store_segments(directory, rows):
    filename = f"transcript-{uuid4().hex}.json"
    save_json(directory / filename, rows)
    return filename


def create_project(source, root, *, transcript=None, model=None, rights=False, style="podcast",
                   platform="shorts", audience="general", limit=24, render_count=5, language=None,
                   name=None, job_id=None, resolution=1080, framing="contain", brand=None,
                   speaker_positions=None, speaker_tracks=None, speaker_model=None, cleanup=False, push_in=False,
                   reference=False, staged_upload=False):
    if rights is not True:
        raise ValueError("Confirm processing rights for this source before intake")
    if transcript is None and model is None:
        raise ValueError("A timestamped JSON transcript or a local speech model is required")
    prefs = settings(style, platform, resolution, framing, brand or {}, speaker_positions or {})
    if type(cleanup) is not bool or type(push_in) is not bool:
        raise ValueError("Audio cleanup and gentle push-in must be true or false")
    integer(limit, "Candidate limit", 1, 30)
    integer(render_count, "Render count", 0, 30)
    audience = clean_text(audience, "Audience", 80)
    language = None if not language else clean_text(language, "Language code", 16)
    if model is not None:
        model = Path(model).expanduser().resolve(strict=True)
        if not model.is_dir():
            raise ValueError("Speech model must be a local directory")
    if speaker_model:
        if not model or speaker_tracks:
            raise ValueError("Speaker embeddings require local ASR and a mixed track")
        speaker_model = Path(speaker_model).expanduser().resolve(strict=True)
        if not speaker_model.is_file():
            raise ValueError("Speaker model must be a local ONNX file")
    media = Path(source).expanduser()
    if media.is_symlink() or not media.is_file() or media.suffix.lower() not in SUFFIXES:
        raise ValueError("Choose a local MP4, MOV, MKV or WebM file")
    job_id = uuid4().hex if job_id is None else job_id
    if not isinstance(job_id, str) or not PROJECT_ID.fullmatch(job_id):
        raise ValueError("Invalid project ID")
    root = private_root(root)
    media = media.resolve(strict=True)
    original_identity = file_identity(media)
    if reference and staged_upload:
        raise ValueError("Choose a local reference or a completed upload")
    if staged_upload and media.parent != root / ".uploads" / job_id:
        raise ValueError("Upload must be committed in this workspace")
    with tempfile.TemporaryDirectory(dir=root, prefix=".intake-") as staging:
        directory = Path(staging) / "project"
        directory.mkdir(mode=0o700)
        file_name = "input" + media.suffix.lower()
        source_path = directory / file_name
        source_reference = None
        if reference:
            source_path = media
            source_reference = {"path": str(media), "identity": original_identity}
            source_hash = None
        elif staged_upload:
            os.link(media, source_path, follow_symlinks=False)
            source_hash = sha256(source_path)
        else:
            source_hash = copy_media(media, source_path)
        info = pilot_qc.validate_source(source_path)
        if reference and file_identity(media) != original_identity:
            raise ValueError("The original changed while opening")
        if not info.get("has_audio"):
            raise ValueError("Speech clipping requires a source audio stream")
        source_info = {key: info[key] for key in ("duration", "dimensions", "streams", "container", "mime",
                                                   "bytes", "has_audio") if key in info}
        source_info.update(name=clean_text(media.name, "Filename", 255), sha256=source_hash)
        stamp = now()
        state = {"id": job_id, "name": clean_text(name or media.stem, "Project name", 140),
                 "created_at": stamp, "source": source_info, "source_file": file_name,
                 "source_reference": source_reference, **prefs,
                 "audience": audience, "limit": limit, "render_count": render_count, "language": language,
                 "processing_rights": True, "speaker_tracks": speaker_tracks or {}, "cleanup": cleanup,
                 "push_in": push_in,
                 "model_path": str(model) if model else None, "transcript_file": None,
                 "speaker_model_path": str(speaker_model) if speaker_model else None,
                 "transcription": {}, "status": "queued", "stage": "intake", "progress": 0,
                 "candidates": [], "ranked": False, "error": None, "runs": []}
        if transcript is not None:
            payload = load_json(Path(transcript).expanduser(), MAX_TRANSCRIPT)
            rows = checked_segments(payload.get("segments") if isinstance(payload, dict) else payload,
                                    info["duration"])
            state["transcript_file"] = store_segments(directory, rows)
            state["transcription"] = {"method": "imported", "language": language or "unspecified"}
        save_state(directory, state)
        # rename refuses to replace an existing populated project, including ID races.
        directory.rename(root / job_id)
        sync_directory(root)
    return job_id


def list_projects(root):
    projects = []
    for path in private_root(root).iterdir():
        if PROJECT_ID.fullmatch(path.name) and path.is_dir() and not path.is_symlink():
            try:
                p = load_json(path / PROJECT_FILE)
            except (FileNotFoundError, ValueError):
                continue
            projects.append({**{k: p[k] for k in ("id", "name", "status", "stage", "progress", "updated_at",
                                                  "created_at", "style", "platform", "source")},
                             "candidate_count": len(p["candidates"]),
                             "approved_count": sum(c["review"] == "approved" for c in p["candidates"]),
                             "rendered_count": sum(c["rendered"] for c in p["candidates"])})
    return sorted(projects, key=lambda p: p["updated_at"], reverse=True)


def get_project(root, job_id):
    directory = project_dir(root, job_id)
    # State points to immutable transcript revisions. Retry if a simultaneous edit collected an old one.
    for attempt in range(2):
        state = load_json(directory / PROJECT_FILE)
        filename = state.pop("transcript_file")
        try:
            state["segments"] = load_json(directory / filename) if filename else []
            break
        except (ValueError, FileNotFoundError):
            if attempt:
                raise
    for key in ("source_file", "model_path", "speaker_model_path", "source_reference"):
        state.pop(key, None)
    for clip in state["candidates"]:
        for key in ("bundle", "hashes"):
            clip.pop(key, None)
    return state


def candidate(state, clip_id):
    if not isinstance(clip_id, str):
        raise ValueError("Invalid candidate ID")
    for clip in state["candidates"]:
        if clip["id"] == clip_id:
            return clip
    raise ValueError("Unknown clip candidate")


def approval_reset(clip, drop_media):
    clip.update(review="pending", approval=None)
    if drop_media:
        clip.update(rendered=False, qc=None)
        for key in ("bundle", "hashes", "render", "render_error"):
            clip.pop(key, None)


def housekeep(directory, state):
    used = {clip.get("bundle") for clip in state["candidates"]}
    for bundle in directory.glob("render-*"):
        if bundle.is_dir() and not bundle.is_symlink() and bundle.name not in used:
            shutil.rmtree(bundle)
    for item in directory.glob("transcript-*.json"):
        if item.name != state["transcript_file"]:
            item.unlink(missing_ok=True)
    for part in directory.glob(".render-*"):
        if part.is_dir() and not part.is_symlink():
            shutil.rmtree(part)


def edit_project(root, job_id, **updates):
    directory = project_dir(root, job_id)
    fields = {"segments", "style", "platform", "brand", "framing", "resolution", "speaker_positions",
              "candidate_id", "title", "description", "cta", "start", "end", "editor", "audience", "rerank",
              "cleanup", "push_in", "remove_ranges", "punch_ins", "encoder"}
    if set(updates) - fields:
        raise ValueError("Unknown project edit")
    with lock(directory, ".worker"):
        state = load_json(directory / PROJECT_FILE)
        original = json.dumps(state, sort_keys=True)
        key_settings = ("style", "platform", "resolution", "framing", "brand", "speaker_positions")
        new = settings(*(updates.get(key, state[key]) for key in key_settings))
        for key in ("cleanup", "push_in"):
            value = updates.get(key, state.get(key, False))
            if type(value) is not bool:
                raise ValueError("Audio cleanup and gentle push-in must be true or false")
            new[key] = value
        if "encoder" in updates:
            value = updates["encoder"]
            if value not in pilot_edit.ENCODERS:
                raise ValueError("Choose auto, cpu, qsv or nvenc encoder")
            new["encoder"] = value
        changed = any(state.get(k, False) != value for k, value in new.items())
        state.update(new)
        segments_changed = False
        if "segments" in updates:
            previous = load_json(directory / state["transcript_file"]) if state["transcript_file"] else []
            rows = checked_segments(updates["segments"], state["source"]["duration"], previous)
            if rows != previous:
                state["transcript_file"] = store_segments(directory, rows)
                state["transcription"]["edited"] = True
                segments_changed = True
                for clip in state["candidates"]:
                    clip["selection_edited"] = True
                    clip["preview"] = excerpt(rows, clip["start"], clip["end"])[:300]
        if changed or segments_changed:
            for clip in state["candidates"]:
                approval_reset(clip, True)
        audience = clean_text(updates.get("audience", state["audience"]), "Audience", 80)
        if audience != state["audience"] or updates.get("rerank") is True:
            state.update(audience=audience, ranked=False, candidates=[], status="queued", stage="ranking", progress=0)
        clip_fields = {"title", "description", "cta", "start", "end", "editor", "remove_ranges", "punch_ins"} & updates.keys()
        if clip_fields:
            clip = candidate(state, updates.get("candidate_id"))
            a = number(updates.get("start", clip["start"]), "clip start")
            b = number(updates.get("end", clip["end"]), "clip end")
            if not 0 <= a < b <= state["source"]["duration"] or not .25 <= b - a <= 180:
                raise ValueError("Choose a clip of 0.25–180 seconds inside the source")
            if (a, b) != (clip["start"], clip["end"]):
                rows = load_json(directory / state["transcript_file"])
                clip.update(start=a, end=b, selection_edited=True, preview=excerpt(rows, a, b)[:300],
                            remove_ranges=[], punch_ins=[])
                approval_reset(clip, True)
            if "remove_ranges" in updates:
                cuts = updates["remove_ranges"]
                if not isinstance(cuts, list) or any(not isinstance(pair, list) or len(pair) != 2 for pair in cuts):
                    raise ValueError("Use reviewed cut intervals [[start, end], ...] in source seconds")
                cuts = [[number(x, "cut timestamp") for x in pair] for pair in cuts]
                pilot_edit._keep_ranges(a, b, cuts)
                if cuts != clip.get("remove_ranges", []):
                    clip.update(remove_ranges=cuts, selection_edited=True)
                    approval_reset(clip, True)
            if "punch_ins" in updates or "remove_ranges" in updates:
                punch_ins = updates.get("punch_ins", clip.get("punch_ins", []))
                ranges = pilot_edit._keep_ranges(a, b, clip.get("remove_ranges", []))
                pilot_edit.punch_in_plan(punch_ins, ranges)
                if punch_ins != clip.get("punch_ins", []):
                    clip["punch_ins"] = punch_ins
                    approval_reset(clip, True)
            for key, limit in (("title", 240), ("description", 2000), ("cta", 500), ("editor", 100)):
                if key in updates:
                    value = clean_text(updates[key], key, limit, required=key == "title")
                    if value != clip.get(key):
                        clip[key] = value
                        approval_reset(clip, False)
        if json.dumps(state, sort_keys=True) != original:
            entry = {"at": now(), "candidate": updates.get("candidate_id"),
                     "fields": sorted(updates.keys() - {"candidate_id"})}
            if clip_fields:
                entry["selection"] = {key: clip[key] for key in ("start", "end", "remove_ranges", "punch_ins") if key in clip}
            state["edits"] = (state.get("edits", []) + [entry])[-100:]
        save_state(directory, state)
        housekeep(directory, state)
    return get_project(root, job_id)


def excerpt(rows, start, end):
    return " ".join(row["text"] for row in rows if row["start"] < end and row["end"] > start)


def suggest_cuts(root, job_id, clip_id):
    project = get_project(root, job_id)
    clip = candidate(project, clip_id)
    return pilot_edit.suggest_trims(project["segments"], clip["start"], clip["end"])


def approved_media(directory, clip, kind, verify=True):
    if not clip.get("rendered") or not clip.get("bundle"):
        raise ValueError("Render this candidate before preview or delivery")
    if kind != "preview" and (clip["review"] != "approved" or not clip.get("approval") or
                              not clip["approval"].get("rights") or not (clip.get("qc") or {}).get("passed")):
        raise ValueError("Delivery requires passing QC, a named reviewer and confirmed rights")
    artifact = ARTIFACTS[kind]
    path = directory / clip["bundle"] / artifact
    if path.parent.is_symlink() or path.is_symlink() or not path.is_file():
        raise ValueError("Render is missing. Resume the project to rebuild it.")
    if verify and kind != "preview" and sha256(path) != clip["approval"]["hashes"].get(artifact):
        raise ValueError("Approved file changed. Render and review the new revision.")
    return path


def get_media_path(root, job_id, clip_id=None, kind="preview"):
    directory = project_dir(root, job_id)
    state = load_json(directory / PROJECT_FILE)
    if kind == "source" and clip_id is None:
        source = project_source(directory, state)
        proxy = directory / "source-preview.mp4"
        return proxy if state.get("proxy_ready") and proxy.is_file() and not proxy.is_symlink() else source
    if kind not in ARTIFACTS:
        raise ValueError("Unknown media type")
    return approved_media(directory, candidate(state, clip_id), kind)


def browser_preview(root, job_id, clip_id):
    """Lazy, private WebM review proxy for browsers without MP4 decoders.

    Never alters the approved MP4, SRT, VTT, their hashes or project state.
    The reduced resolution is for viewing only. Serialized against other
    project edits, atomically installed, and never sent to another service.
    """
    directory = project_dir(root, job_id)
    # Both the cinematic layer and foreground player can ask at once. Wait for
    # one conversion and reuse it; do not return an HTTP error to the loser.
    with lock(directory, ".worker", wait=True):
        state = load_json(directory / PROJECT_FILE)
        source = approved_media(directory, candidate(state, clip_id), "preview")
        output = source.with_name("preview.webm")
        if output.is_symlink():
            raise ValueError("Browser preview is not a regular local file")
        if output.is_file():
            if output.stat().st_size > 0:
                return output
            output.unlink()
        if not shutil.which("ffmpeg"):
            raise ValueError("Local FFmpeg is required for WebM preview")
        with tempfile.TemporaryDirectory(prefix=".browser-preview-", dir=source.parent) as temp:
            draft = Path(temp) / "preview.webm"
            command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
                       "-y", "-max_alloc", "268435456", "-threads", "2",
                       "-i", str(source), "-map", "0:v:0", "-map", "0:a:0",
                       "-vf", "scale=w='min(540,iw)':h='min(540,ih)':"
                              "force_original_aspect_ratio=decrease:force_divisible_by=2,"
                              "fps=24,format=yuv420p",
                       "-c:v", "libvpx", "-deadline", "realtime", "-cpu-used", "8",
                       "-b:v", "650k", "-c:a", "libopus", "-b:a", "72k",
                       "-map_metadata", "-1", "-map_chapters", "-1",
                       "-f", "webm", str(draft)]
            duration = float((candidate(state, clip_id).get("render") or {}).get("duration") or 30)
            timeout = max(120, min(600, round(duration * 8)))
            try:
                subprocess.run(command, check=True, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=timeout)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                raise ValueError("Local WebM preview conversion failed. The MP4 export is unchanged.") from exc
            if not draft.is_file() or draft.stat().st_size == 0:
                raise ValueError("Local WebM preview was empty")
            os.chmod(draft, 0o600)
            os.replace(draft, output)
        return output


def generate_proxy(root, job_id):
    """Create an optional browser proxy without changing or copying the original container."""
    directory = project_dir(root, job_id)
    with lock(directory.parent, ".render-worker"), lock(directory, ".worker"):
        state = load_json(directory / PROJECT_FILE)
        source = project_source(directory, state)
        out = directory / "source-preview.mp4"
        if state.get("proxy_ready") and out.is_file() and not out.is_symlink():
            return
        status, stage, progress = (state[k] for k in ("status", "stage", "progress"))
        state.update(status="processing", stage="building browser preview", progress=0)
        save_state(directory, state)
        try:
            with tempfile.TemporaryDirectory(prefix=".proxy-", dir=directory) as tmp:
                preview = Path(tmp) / "source.mp4"
                command = ["ffmpeg", "-hide_banner", "-v", "error", "-nostdin", "-xerror", "-max_alloc", "268435456",
                           *pilot_qc.MEDIA_INPUT_OPTIONS, "-i", str(source), "-map", "0:V:0", "-map", "0:a:0",
                           "-vf", "scale=w='min(960,iw)':h='min(540,ih)':force_original_aspect_ratio=decrease:"
                                  "force_divisible_by=2,format=yuv420p",
                           "-map_metadata", "-1", "-map_chapters", "-1", "-c:v", "libx264", "-threads:v", "2",
                           "-preset", "veryfast", "-crf", "25", "-c:a", "aac", "-b:a", "96k",
                           "-movflags", "+faststart", str(preview)]
                result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
                                        timeout=max(90, state["source"]["duration"] * 3))
                if result.returncode:
                    raise ValueError("FFmpeg could not build a browser preview for this source")
                info = pilot_qc.validate_source(preview)
                if abs(info["duration"] - state["source"]["duration"]) > .25:
                    raise ValueError("The preview duration differs from the source")
                project_source(directory, state)
                os.chmod(preview, 0o600)
                os.replace(preview, out)
            state["proxy_ready"] = True
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Building the browser preview timed out") from exc
        finally:
            state.update(status=status, stage=stage, progress=progress)
            save_state(directory, state)


def review_clip(root, job_id, clip_id, decision, editor, rights=False):
    if decision not in ("assigned", "approved", "rejected"):
        raise ValueError("Choose assigned, approved or rejected")
    editor = clean_text(editor, "Reviewer", 100)
    directory = project_dir(root, job_id)
    with lock(directory, ".worker"):
        state = load_json(directory / PROJECT_FILE)
        clip = candidate(state, clip_id)
        if decision == "approved":
            if rights is not True or not clip.get("rendered") or not (clip.get("qc") or {}).get("passed"):
                raise ValueError("Approval requires a rendered clip, passing QC and explicit rights confirmation")
            paths = directory / clip["bundle"]
            if paths.is_symlink():
                raise ValueError("Render directory changed. Resume and review the new render.")
            for artifact, digest in clip["hashes"].items():
                path = paths / artifact
                if path.is_symlink() or not path.is_file() or sha256(path) != digest:
                    raise ValueError("Rendered media changed. Resume and review the new render.")
            clip["approval"] = {"editor": editor, "at": now(), "rights": True, "hashes": dict(clip["hashes"]),
                                "platform": state["platform"], "title": clip["title"],
                                "source_range": [clip["start"], clip["end"]]}
        else:
            clip["approval"] = None
        clip.update(editor=editor, review="pending" if decision == "assigned" else decision)
        save_state(directory, state)
    return get_project(root, job_id)


def same_content(first, second):
    # Compare full normalized source text. Candidate discovery also tests near-duplicate language.
    def terms(clip):
        return " ".join(re.findall(r"\w+", clip.casefold()))
    return bool(first and second and terms(first) == terms(second))


def unique_selection(state, rows, clip):
    text = excerpt(rows, clip["start"], clip["end"])
    for other in state["candidates"]:
        if other is clip or not other.get("rendered") or not (other.get("qc") or {}).get("passed"):
            continue
        overlap = min(other["end"], clip["end"]) - max(other["start"], clip["start"])
        shortest = min(clip["end"] - clip["start"], other["end"] - other["start"])
        if overlap > .8 * shortest or same_content(text, excerpt(rows, other["start"], other["end"])):
            return False
    return True


def cached(directory, clip):
    if not clip.get("rendered") or not clip.get("bundle") or not clip.get("qc"):
        return False
    bundle = directory / clip["bundle"]
    if bundle.is_symlink():
        return False
    return all((bundle / name).is_file() and not (bundle / name).is_symlink() and
               sha256(bundle / name) == digest for name, digest in clip["hashes"].items())


def render_candidate(directory, state, rows, clip):
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix=".render-", dir=directory) as tmp:
        # A directory rename installs the video and its two caption sidecars together.
        part = Path(tmp) / "bundle"
        part.mkdir(mode=0o700)
        out = part / "clip.mp4"
        source = project_source(directory, state)
        rendered = pilot_edit.render(source, out, clip["start"], clip["end"],
                                     rows, state["style"], state["platform"], resolution=state["resolution"],
                                     framing=state["framing"], brand=state["brand"],
                                     speaker_positions=state["speaker_positions"], cleanup=state.get("cleanup", False),
                                     remove_ranges=clip.get("remove_ranges"),
                                     push_in=state.get("push_in", False) and not clip.get("punch_ins"),
                                     punch_ins=clip.get("punch_ins"), encoder=state.get("encoder", "auto"))
        fingerprints = [(other.get("qc") or {}).get("evidence", {}).get("decoded_media_sha256")
                        for other in state["candidates"] if other is not clip and other["review"] != "rejected"
                        and (other.get("qc") or {}).get("passed")]
        qc = pilot_qc.inspect_export(out, expected_duration=rendered.get("expected_duration", clip["end"] - clip["start"]),
                                     dimensions=rendered["dimensions"], segments=rendered["captions"],
                                     source_info=state["source"], prior_fingerprints=fingerprints, require_sidecars=True)
        distinct = unique_selection(state, rows, clip)
        qc["checks"]["distinct_source_selection"] = distinct
        qc["passed"] = bool(qc["passed"] and distinct)
        project_source(directory, state)
        hashes = {name: sha256(part / name) for name in set(ARTIFACTS.values())}
        name = f"render-{clip['id']}-{uuid4().hex}"
        part.rename(directory / name)
        approval_reset(clip, True)
        fields = ("dimensions", "source_dimensions", "upscaled", "framing", "duration", "resolution",
                  "style", "platform", "warnings", "caption_mode", "framing_reason", "encoder", "audio",
                  "retained_source_ranges", "push_in", "punch_ins", "has_audio", "foreground_scale",
                  "framing_applied", "framing_details", "caption_layout", "source_detail")
        clip.update(rendered=True, bundle=name, hashes=hashes, qc=qc,
                    render={**{k: rendered[k] for k in fields if k in rendered},
                            "seconds_including_qc": round(time.monotonic() - started, 3)})


def cpu_used():
    own = resource.getrusage(resource.RUSAGE_SELF)
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    return own.ru_utime + own.ru_stime + children.ru_utime + children.ru_stime


def process_project(root, job_id, render_count=None, clip_ids=None, model=None, progress=None):
    directory = project_dir(root, job_id)
    with lock(directory.parent, ".render-worker"), lock(directory, ".worker"):
        state = load_json(directory / PROJECT_FILE)
        render_count = integer(state["render_count"] if render_count is None else render_count,
                               "Render count", 0, 30)
        if clip_ids is not None:
            if not isinstance(clip_ids, (list, tuple)) or len(clip_ids) > 30:
                raise ValueError("Choose at most 30 named candidates")
            if not state["ranked"]:
                raise ValueError("Rank candidates before choosing clip IDs")
            for clip_id in clip_ids:
                candidate(state, clip_id)
        started, cpu = time.monotonic(), cpu_used()
        stats = {"started": now(), "renders": 0, "cached": 0, "render_errors": 0}
        state.update(status="processing", error=None)
        def checkpoint(stage, percent):
            state.update(stage=stage, progress=percent)
            save_state(directory, state)
            if progress is not None:
                progress(stage, percent)
        try:
            housekeep(directory, state)
            if state["transcript_file"] is None:
                checkpoint("transcribing", 5)
                transcribe_started = time.monotonic()
                local_model = model or state["model_path"]
                if not local_model:
                    raise ValueError("Choose a local speech model or supply timestamped captions")
                def chunk_progress(done, total):
                    checkpoint(f"transcribing {done}/{total}", 5 + int(18 * done / total))
                options = {"language": state["language"], "progress": chunk_progress}
                if state.get("speaker_tracks"):
                    options["speaker_tracks"] = {int(k): v for k, v in state["speaker_tracks"].items()}
                if state.get("speaker_model_path"):
                    options["speaker_model"] = Path(state["speaker_model_path"])
                result = pilot_intelligence.transcribe_local(project_source(directory, state), Path(local_model),
                                                             directory / "asr", **options)
                project_source(directory, state)
                rows = checked_segments(result["segments"], state["source"]["duration"])
                state["transcript_file"] = store_segments(directory, rows)
                state["transcription"] = {k: result[k] for k in ("language", "languages", "speaker_method",
                    "diarization", "model", "device", "timing", "warnings", "chunk_seconds", "chunks",
                    "cached_chunks") if k in result}
                state["transcription"]["method"] = "local ASR"
                stats["transcription_wall_seconds"] = round(time.monotonic() - transcribe_started, 3)
            else:
                rows = load_json(directory / state["transcript_file"])
            if not state["ranked"]:
                checkpoint("ranking", 25)
                rank_started = time.monotonic()
                ranked = pilot_intelligence.rank_candidates(rows, limit=state["limit"], audience=state["audience"])
                state["candidates"] = [{**item, "id": f"c{idx:02d}", "review": "pending", "editor": "",
                                        "approval": None, "rendered": False, "qc": None}
                                       for idx, item in enumerate(ranked, 1)]
                state["ranked"] = True
                stats["ranking_wall_seconds"] = round(time.monotonic() - rank_started, 3)
            if clip_ids is None:
                selected = [c for c in state["candidates"] if c["review"] != "rejected"][:render_count]
            else:
                selected = [candidate(state, key) for key in dict.fromkeys(clip_ids)]
            checkpoint("rendering" if selected else "preparing review", 40)
            for index, clip in enumerate(selected, 1):
                if cached(directory, clip):
                    stats["cached"] += 1
                else:
                    try:
                        render_candidate(directory, state, rows, clip)
                        stats["renders"] += 1
                    except (ValueError, RuntimeError, OSError) as exc:
                        approval_reset(clip, True)
                        clip["render_error"] = str(exc).replace(str(directory), "[project]")[:500]
                        stats["render_errors"] += 1
                checkpoint("rendering", 40 + int(59 * index / len(selected)))
            state.update(status="review", stage="review", progress=100)
            if stats["render_errors"]:
                state["error"] = f"{stats['render_errors']} candidates could not render. See the candidate details."
                if stats["render_errors"] == len(selected):
                    state.update(status="failed", stage="rendering")
            housekeep(directory, state)
        except (Exception, KeyboardInterrupt) as exc:
            state.update(status="failed", error=str(exc).replace(str(directory), "[project]")[:700])
            if isinstance(exc, KeyboardInterrupt):
                state["error"] = "Interrupted. Resume this project to continue."
            raise
        finally:
            rss = max(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                      resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)
            stats.update(wall_seconds=round(time.monotonic() - started, 3),
                         process_and_children_cpu_seconds=round(cpu_used() - cpu, 3),
                         process_high_water_mib=round(rss / (1024**2 if sys.platform == "darwin" else 1024), 1),
                         finished=now(), status=state["status"])
            state["runs"] = (state["runs"] + [stats])[-100:]
            save_state(directory, state)
    return get_project(root, job_id)


def purge_project(root, job_id):
    directory = project_dir(root, job_id)
    with lock(directory, ".worker"):
        if load_json(directory / PROJECT_FILE).get("id") != job_id:
            raise ValueError("Project receipt does not match its storage directory")
    # Windows refuses to rename a directory while one of its files is open, so
    # the lease must be released first. The rename is atomic, so losing a race
    # against another purge simply means there is nothing left to remove.
    trash = directory.with_name(".purge-" + uuid4().hex)
    try:
        directory.rename(trash)
        shutil.rmtree(trash)
    except FileNotFoundError:
        return


def run_report(project):
    candidates = project["candidates"]
    return {
        "project": project["id"], "name": project["name"], "status": project["status"],
        "source_duration_seconds": project["source"]["duration"],
        "source_dimensions": project["source"]["dimensions"],
        "style": project["style"], "platform": project["platform"], "audience": project["audience"],
        "transcription": project["transcription"], "transcript_segments": len(project["segments"]),
        "candidate_count": len(candidates), "rendered_count": sum(c["rendered"] for c in candidates),
        "qc_pass_count": sum(bool((c.get("qc") or {}).get("passed")) for c in candidates),
        "approved_count": sum(c["review"] == "approved" for c in candidates),
        "candidates": candidates, "processing_runs": project["runs"],
        "error": project["error"],
    }


def cli(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="Use an owned 0700 directory")
    actions = parser.add_subparsers(dest="command", required=True)
    run = actions.add_parser("run", help="Intake, transcribe or import, rank, render and check")
    run.add_argument("source", type=Path)
    inputs = run.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--transcript", type=Path)
    inputs.add_argument("--model", type=Path)
    run.add_argument("--language", default=None)
    run.add_argument("--name")
    run.add_argument("--rights-confirmed", action="store_true")
    run.add_argument("--reference", action="store_true", help="Read the unchanged local original without copying it")
    run.add_argument("--style", choices=pilot_edit.STYLES, default="podcast")
    run.add_argument("--platform", choices=pilot_edit.PLATFORMS, default="shorts")
    run.add_argument("--framing", choices=("contain", "crop", "faces", "speaker", "split"), default="contain")
    run.add_argument("--resolution", type=int, choices=(720, 1080, 2160), default=1080)
    run.add_argument("--brand", type=Path, help="JSON file with font and color settings")
    run.add_argument("--speaker-positions", type=Path, help="JSON mapping speaker labels to normalized x positions")
    run.add_argument("--speaker-tracks", type=Path, help="JSON mapping zero-based audio track indexes to labels")
    run.add_argument("--speaker-model", type=Path, help="Optional local speaker embedding model for mixed audio")
    run.add_argument("--cleanup", action="store_true", help="Enable light speech noise reduction")
    run.add_argument("--push-in", action="store_true", help="Use a gentle push-in throughout the edit")
    run.add_argument("--audience", default="general")
    run.add_argument("--candidates", type=int, default=24)
    run.add_argument("--render-count", type=int, default=5, help="Use 0 to review candidates before rendering")
    actions.add_parser("list", help="List local projects")
    resume = actions.add_parser("resume", help="Continue a project or render selected candidate IDs")
    resume.add_argument("project")
    resume.add_argument("--model", type=Path)
    resume.add_argument("--render-count", type=int)
    resume.add_argument("--clips", nargs="+")
    report = actions.add_parser("report", help="Print candidates, QC, and processing measurements as JSON")
    report.add_argument("project")
    edit = actions.add_parser("edit", help="Apply a local JSON edit, including reviewed cut intervals")
    edit.add_argument("project")
    edit.add_argument("settings", type=Path)
    cuts = actions.add_parser("suggest-cuts", help="Show possible pauses and filler in a candidate")
    cuts.add_argument("project")
    cuts.add_argument("clip")
    approve = actions.add_parser("review", help="Record a named decision about an exact clip")
    approve.add_argument("project")
    approve.add_argument("clip")
    approve.add_argument("decision", choices=("assigned", "approved", "rejected"))
    approve.add_argument("--editor", required=True)
    approve.add_argument("--rights-confirmed", action="store_true")
    export = actions.add_parser("export", help="Copy reviewed MP4 and caption sidecars to a new directory")
    export.add_argument("project")
    export.add_argument("clip")
    export.add_argument("output", type=Path)
    purge = actions.add_parser("purge", help="Delete private project media, transcript, caches and review record")
    purge.add_argument("project")
    purge.add_argument("--confirm", required=True, help="Repeat the exact project ID")
    opts = parser.parse_args(argv)

    def progress(stage, percent):
        print(f"{percent:3d}% {stage}", file=sys.stderr, flush=True)

    try:
        if opts.command == "run":
            job = create_project(
                opts.source, opts.root, transcript=opts.transcript, model=opts.model, rights=opts.rights_confirmed,
                reference=opts.reference,
                language=opts.language, name=opts.name, style=opts.style, platform=opts.platform, audience=opts.audience,
                limit=opts.candidates, render_count=opts.render_count, resolution=opts.resolution,
                framing=opts.framing, brand=load_json(opts.brand, 8192) if opts.brand else None,
                speaker_positions=load_json(opts.speaker_positions, 8192) if opts.speaker_positions else None,
                speaker_tracks=load_json(opts.speaker_tracks, 8192) if opts.speaker_tracks else None,
                speaker_model=opts.speaker_model, cleanup=opts.cleanup, push_in=opts.push_in,
            )
            print(f"Project {job}", file=sys.stderr, flush=True)
            result = run_report(process_project(opts.root, job, progress=progress))
        elif opts.command == "resume":
            result = run_report(process_project(opts.root, opts.project, opts.render_count, opts.clips,
                                                opts.model, progress))
        elif opts.command == "list":
            result = list_projects(opts.root)
        elif opts.command == "report":
            result = run_report(get_project(opts.root, opts.project))
        elif opts.command == "edit":
            changes = load_json(opts.settings, MAX_TRANSCRIPT)
            if not isinstance(changes, dict):
                raise ValueError("Edits require a JSON object")
            result = run_report(edit_project(opts.root, opts.project, **changes))
        elif opts.command == "suggest-cuts":
            result = suggest_cuts(opts.root, opts.project, opts.clip)
        elif opts.command == "review":
            project = review_clip(opts.root, opts.project, opts.clip, opts.decision, opts.editor, opts.rights_confirmed)
            result = candidate(project, opts.clip)
        elif opts.command == "export":
            directory = project_dir(opts.root, opts.project)
            with lock(directory, ".worker"):
                clip = candidate(load_json(directory / PROJECT_FILE), opts.clip)
                files = [approved_media(directory, clip, kind) for kind in ("export", "srt", "vtt")]
                out = opts.output.expanduser()
                if not out.parent.is_dir() or out.exists() or out.is_symlink():
                    raise ValueError("Choose a new output directory under an existing parent")
                with tempfile.TemporaryDirectory(dir=out.parent, prefix=".export-") as tmp:
                    package = Path(tmp) / "package"
                    package.mkdir(mode=0o700)
                    for path in files:
                        shutil.copyfile(path, package / path.name)
                    manifest = {key: clip[key] for key in ("id", "title", "description", "cta", "start", "end",
                                                          "approval", "render", "qc")}
                    save_json(package / "delivery.json", manifest)
                    package.rename(out)
            result = {"project": opts.project, "clip": opts.clip, "directory": str(out)}
        else:
            if opts.confirm != opts.project:
                raise ValueError("Confirmation must match the project ID")
            purge_project(opts.root, opts.project)
            result = {"purged": opts.project}
    except KeyboardInterrupt:
        parser.exit(130, "Interrupted. Use resume with the project ID to continue.\n")
    except (ValueError, RuntimeError, OSError, KeyError) as exc:
        parser.exit(2, f"ClipOps error: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(cli())
