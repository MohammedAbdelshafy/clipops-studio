#!/usr/bin/env python3
"""ClipOps Studio: local video intake, transcripts, captions, render, QC and scheduling.

No requests leave the machine unless `publish --live` is explicitly invoked,
and the job is approved. Optional faster-whisper downloads its model only when
transcription is requested. Standard library + installed FFmpeg for basic use.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from urllib import request
from uuid import uuid4


def run(command: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    p = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    if p.returncode:
        raise RuntimeError(f"{command[0]} failed ({p.returncode}): {p.stderr[-1300:]}")
    return p


def media_info(path: str | Path) -> dict:
    p = Path(path).expanduser().resolve(strict=True)
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration,size:stream=codec_name,codec_type,width,height", "-of", "json", str(p)]
    info = json.loads(run(cmd).stdout)
    if not any(s.get("codec_type") == "video" for s in info.get("streams", [])):
        raise ValueError("Input has no video stream")
    info["file"] = str(p)
    return info


def duration(info: dict) -> float:
    return float(info["format"]["duration"])


def require_local_file(path: str | Path, suffixes: tuple[str, ...] = ()) -> Path:
    p = Path(path).expanduser().resolve(strict=True)
    if not p.is_file() or (suffixes and p.suffix.lower() not in suffixes):
        raise ValueError(f"Invalid local input file: {p}")
    return p


def sec_to_stamp(seconds: float, vtt: bool = False) -> str:
    ms = max(0, int(round(seconds * 1000)))
    hh, ms = divmod(ms, 3600000)
    mm, ms = divmod(ms, 60000)
    ss, ms = divmod(ms, 1000)
    return f"{hh:02}:{mm:02}:{ss:02}{'.' if vtt else ','}{ms:03}"


def normalize_segments(items: list[dict]) -> list[dict]:
    result = []
    for item in items:
        start, end = float(item["start"]), float(item["end"])
        text = re.sub(r"\s+", " ", str(item["text"])).strip()
        if start < 0 or end <= start or not text:
            raise ValueError("Segments need nonempty text and strictly increasing positive timing")
        result.append({"start": start, "end": end, "text": text})
    result.sort(key=lambda x: x["start"])
    return result


def segments_from(path: str | Path) -> list[dict]:
    content = json.loads(require_local_file(path, (".json",)).read_text(encoding="utf-8"))
    if isinstance(content, dict):
        content = content["segments"]
    return normalize_segments(content)


def subtitle_text(segments: list[dict], vtt: bool = False, start: float = 0, end: float | None = None) -> str:
    lines = ["WEBVTT", ""] if vtt else []
    count = 0
    for seg in segments:
        a, b = max(start, seg["start"]), min(end if end is not None else float("inf"), seg["end"])
        if b <= a:
            continue
        count += 1
        if not vtt:
            lines.append(str(count))
        lines.append(f"{sec_to_stamp(a - start, vtt)} --> {sec_to_stamp(b - start, vtt)}")
        # Avoid injection of additional SRT cue boundaries from raw source text.
        lines.append(re.sub(r"[\r\n]+", " ", seg["text"]))
        lines.append("")
    return "\n".join(lines) + "\n"


def transcribe(media: str, output: str, model_name: str = "small", language: str | None = None) -> dict:
    require_local_file(media)
    try:
        from faster_whisper import WhisperModel  # optional, may download model
    except ImportError as e:
        raise RuntimeError("Install optional dependency: pip install faster-whisper") from e
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    iterable, info = model.transcribe(media, word_timestamps=True, vad_filter=True, language=language)
    segments = []
    for segment in iterable:
        words = getattr(segment, "words", None)
        if words:
            for word in words:
                if word.start is not None and word.end is not None and word.end > word.start:
                    segments.append({"start": word.start, "end": word.end, "text": word.word.strip()})
        else:
            segments.append({"start": segment.start, "end": segment.end, "text": segment.text.strip()})
    # Word-level segments are useful for adjustable caption grouping and highlight selection.
    data = {"source": str(Path(media).resolve()), "language": info.language, "segments": normalize_segments(segments)}
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"path": output, "language": info.language, "segments": len(data["segments"])}


def caption_groups(segments: list[dict], max_words: int = 7, max_seconds: float = 3.2) -> list[dict]:
    if max_words < 1 or max_seconds <= 0:
        raise ValueError("max_words and max_seconds must be positive")
    groups: list[dict] = []
    words: list[str] = []
    first = last = 0.0
    for seg in segments:
        if words and (len(words) >= max_words or seg["end"] - first > max_seconds or seg["start"] - last > 1.25):
            groups.append({"start": first, "end": last, "text": " ".join(words)})
            words = []
        if not words:
            first = seg["start"]
        words.append(seg["text"])
        last = seg["end"]
    if words:
        groups.append({"start": first, "end": last, "text": " ".join(words)})
    return groups


def suggest_clips(segments: list[dict], min_seconds: float = 10, max_seconds: float = 55, limit: int = 5) -> list[dict]:
    """Transparent keyword heuristic; editor approval required. Not a virality predictor."""
    if min_seconds <= 0 or max_seconds < min_seconds or limit < 1:
        raise ValueError("Invalid duration or limit")
    markers = ("how to", "mistake", "secret", "never", "best", "why", "important", "learn", "tip", "problem", "solution", "because", "imagine", "don't", "stop")
    results = []
    for i, first in enumerate(segments):
        end_index = i
        while end_index + 1 < len(segments) and segments[end_index]["end"] - first["start"] < min_seconds:
            end_index += 1
        while end_index < len(segments) and segments[end_index]["end"] - first["start"] <= max_seconds:
            clip_segments = segments[i : end_index + 1]
            full = " ".join(x["text"] for x in clip_segments)
            span = clip_segments[-1]["end"] - first["start"]
            if span >= min_seconds:
                beginning = " ".join(x["text"] for x in clip_segments[: min(14, len(clip_segments))]).lower()
                hits = sum(m in beginning for m in markers)
                score = round(min(100, 40 + 15 * hits + min(len(full.split()), 60) / 6), 2)
                results.append({"start": round(first["start"], 2), "end": round(clip_segments[-1]["end"], 2), "score": score, "preview": full[:180]})
                break  # shortest sufficient window per start
            end_index += 1
    results.sort(key=lambda x: (-x["score"], x["start"]))
    chosen = []
    for candidate in results:
        if all(max(0, min(candidate["end"], other["end"]) - max(candidate["start"], other["start"])) < (candidate["end"] - candidate["start"]) * .5 for other in chosen):
            chosen.append(candidate)
        if len(chosen) >= limit:
            break
    return chosen


def render_clip(media: str, output: str, start: float, end: float, captions: str | None = None, fit: str = "blur", width: int = 720, height: int = 1280) -> dict:
    src = require_local_file(media)
    info = media_info(src)
    if start < 0 or end <= start or end > duration(info) + 0.15:
        raise ValueError("Clip timestamps outside source video")
    if fit not in ("blur", "crop") or width <= 0 or height <= 0 or width % 2 or height % 2:
        raise ValueError("Fit must be blur/crop and output dimensions must be positive even numbers")
    out = Path(output).expanduser().resolve()
    if out == src:
        raise ValueError("Output must not overwrite the source")
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="clipops-") as tmp:
        wd = Path(tmp)
        # Local files, no arbitrary shell, no remote URLs.
        if fit == "crop":
            vf = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"
        else:
            vf = (f"split=2[fg][bg];[bg]scale={width}:{height}:force_original_aspect_ratio=increase,"
                  f"crop={width}:{height},boxblur=20:2[blur];[fg]scale={width}:{height}:"
                  f"force_original_aspect_ratio=decrease[front];[blur][front]overlay=(W-w)/2:(H-h)/2")
        if captions:
            segs = caption_groups(segments_from(captions))
            (wd / "captions.srt").write_text(subtitle_text(segs, start=start, end=end), encoding="utf-8")
            vf += ",subtitles=filename=captions.srt:force_style='FontName=DejaVu Sans,FontSize=21,Outline=2,Alignment=2,MarginV=60'"
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(start), "-i", str(src), "-t", str(end-start), "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out)]
        run(cmd, wd)
    quality = media_info(out)
    return {"file": str(out), "duration": duration(quality), "fit": fit, "captions": bool(captions), "quality": quality["streams"]}


def promo(brief_path: str, output: str, width: int = 720, height: int = 1280) -> dict:
    """FFmpeg text-card promo from user-supplied brief, with no generative API cost."""
    config = json.loads(require_local_file(brief_path, (".json",)).read_text(encoding="utf-8"))
    scenes = config.get("scenes")
    if not isinstance(scenes, list) or not scenes or len(scenes) > 20:
        raise ValueError("Promo brief requires 1-20 scenes")
    if width <= 0 or height <= 0 or width % 2 or height % 2:
        raise ValueError("Dimensions must be positive even numbers")
    out = Path(output).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    font = config.get("font") or "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    font = require_local_file(font)
    color = config.get("background", "#172033")
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise ValueError("background must be #RRGGBB")
    with tempfile.TemporaryDirectory(prefix="clipops-promo-") as d:
        wd = Path(d)
        clips = []
        for i, scene in enumerate(scenes):
            text = str(scene.get("text", "")).strip()
            seconds = float(scene.get("seconds", 2))
            if not text or len(text) > 160 or not (0.5 <= seconds <= 20):
                raise ValueError("Each scene needs text up to 160 chars and duration 0.5-20 sec")
            text_file = wd / f"text{i}.txt"
            text_file.write_text(text, encoding="utf-8")
            part = wd / f"card{i}.mp4"
            draw = f"drawtext=fontfile={font}:textfile={text_file.name}:fontcolor=white:fontsize={max(20, width//15)}:box=1:boxcolor=black@0.40:boxborderw=24:x=(w-text_w)/2:y=(h-text_h)/2"
            run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"color=c=0x{color[1:]}:s={width}x{height}:r=25", "-t", str(seconds), "-vf", draw, "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", str(part)], wd)
            clips.append(part)
        joined = wd / "joined.txt"
        # Fixed trusted generated paths in temp directory; no user path escaping needed.
        joined.write_text("".join(f"file '{p.name}'\n" for p in clips), encoding="utf-8")
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "1", "-i", joined.name, "-c", "copy", "-movflags", "+faststart", str(out)], wd)
    return {"file": str(out), "scenes": len(scenes), "duration": duration(media_info(out))}


SCHEMA = """CREATE TABLE IF NOT EXISTS jobs (
 id TEXT PRIMARY KEY, file TEXT NOT NULL, platform TEXT NOT NULL, integration_id TEXT NOT NULL,
 title TEXT NOT NULL, caption TEXT NOT NULL, scheduled_utc TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'draft', rights_confirmed INTEGER NOT NULL DEFAULT 0,
 response_json TEXT, updated_utc TEXT NOT NULL);"""


@contextmanager
def connect(db: str):
    p = Path(db).expanduser().resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    try:
        con.row_factory = sqlite3.Row
        con.execute(SCHEMA)
        with con:
            yield con
    finally:
        con.close()


def iso_utc(date_text: str) -> str:
    dt = datetime.fromisoformat(date_text.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Schedule timestamp must include timezone offset (e.g. +02:00 or Z)")
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def add_job(db: str, file: str, platform: str, integration_id: str, title: str, caption: str, when: str) -> dict:
    media = require_local_file(file, (".mp4",))
    media_info(media)
    if platform not in ("youtube", "instagram", "tiktok", "linkedin", "facebook"):
        raise ValueError("Unsupported platform")
    if not integration_id or not title.strip() or not caption.strip():
        raise ValueError("Integration, title and caption required")
    job = {"id": uuid4().hex[:14], "file": str(media), "platform": platform, "integration_id": integration_id, "title": title, "caption": caption, "scheduled_utc": iso_utc(when), "status": "draft"}
    with connect(db) as con:
        con.execute("INSERT INTO jobs(id,file,platform,integration_id,title,caption,scheduled_utc,status,updated_utc) VALUES(:id,:file,:platform,:integration_id,:title,:caption,:scheduled_utc,:status,:updated)", {**job, "updated": iso_utc(datetime.now(timezone.utc).isoformat())})
    return job


def approve_job(db: str, job_id: str, rights: bool = False) -> None:
    if not rights:
        raise ValueError("Approval requires confirming rights to source media (--rights-confirmed)")
    with connect(db) as con:
        cur = con.execute("UPDATE jobs SET status='approved', rights_confirmed=1, updated_utc=? WHERE id=? AND status='draft'", (iso_utc(datetime.now(timezone.utc).isoformat()), job_id))
        if cur.rowcount != 1:
            raise ValueError("Job is missing or not a draft")


def qc_media(path: str | Path) -> dict:
    info = media_info(path)
    videos = [s for s in info["streams"] if s.get("codec_type") == "video"]
    s = videos[0]
    w, h = s.get("width", 0), s.get("height", 0)
    checks = {"valid_duration": 0.2 <= duration(info) <= 180,
              "h264_video": s.get("codec_name") == "h264",
              "vertical_video": h > w and w >= 180 and h >= 320,
              "nonempty": Path(info["file"]).stat().st_size > 1000}
    return {"file": info["file"], "passed": all(checks.values()), "checks": checks,
            "duration": duration(info), "dimensions": [w, h]}


def list_jobs(db: str) -> list[dict]:
    with connect(db) as con:
        return [dict(row) for row in con.execute("SELECT * FROM jobs ORDER BY scheduled_utc, id")]


def postiz_publish(job: dict, api_key: str, base_url: str = "https://api.postiz.com/public/v1") -> dict:
    """Send one approved, previously vetted job to Postiz scheduler (network action)."""
    if base_url.rstrip("/") != "https://api.postiz.com/public/v1":
        raise ValueError("Only the official Postiz cloud API is supported in this release")
    if job["platform"] == "tiktok":
        raise RuntimeError("TikTok requires channel-specific privacy settings; finish in Postiz UI")
    file_path = require_local_file(job["file"], (".mp4",))
    # multipart/form-data upload, using explicit byte lengths, no third-party dependencies
    boundary = "clipops" + uuid4().hex
    data = file_path.read_bytes()
    if len(data) > 300 * 1024 * 1024:
        raise ValueError("Uploads above 300 MB require another transfer method")
    start = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"clip.mp4\"\r\n"
             "Content-Type: video/mp4\r\n\r\n").encode()
    payload = start + data + f"\r\n--{boundary}--\r\n".encode()
    upload = request.Request(base_url + "/upload", payload, {"Authorization": api_key, "Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST")
    with request.urlopen(upload, timeout=120) as resp:
        attached = json.load(resp)
    if not attached.get("id") or not attached.get("path"):
        raise RuntimeError("Postiz upload did not return a media id and path")
    settings = {"__type": job["platform"]}
    if job["platform"] == "youtube":
        settings.update({"title": job["title"], "type": "unlisted", "selfDeclaredMadeForKids": "no", "tags": []})
    elif job["platform"] == "instagram":
        settings["post_type"] = "post"  # Single video creates a Reel; Postiz enum has post/story
    post = {
        "type": "schedule", "date": job["scheduled_utc"], "shortLink": False, "tags": [],
        "posts": [{"integration": {"id": job["integration_id"]},
                   "value": [{"content": html.escape(job["caption"]), "image": [{"id": attached["id"], "path": attached["path"]}]}], "settings": settings}]
    }
    req = request.Request(base_url + "/posts", json.dumps(post).encode(), {"Authorization": api_key, "Content-Type": "application/json"}, method="POST")
    with request.urlopen(req, timeout=120) as resp:
        created = json.load(resp)
    return {"postiz": created, "uploaded_media": attached}


def dispatch(db: str, job_id: str, live: bool = False) -> dict:
    with connect(db) as con:
        row = con.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if row is None:
        raise ValueError("Unknown job")
    job = dict(row)
    if job["status"] != "approved" or not job["rights_confirmed"]:
        raise ValueError("Job must be approved with media-rights confirmation")
    if datetime.fromisoformat(job["scheduled_utc"].replace("Z", "+00:00")) <= datetime.now(timezone.utc):
        raise ValueError("Schedule is in the past; choose a future time and create a new job")
    if not live:
        return {"dry_run": True, "job": job, "would_schedule_with": "Postiz"}
    if os.environ.get("CLIPOPS_ALLOW_PUBLISH") != "1":
        raise RuntimeError("Set CLIPOPS_ALLOW_PUBLISH=1 and provide --live for outbound scheduling")
    api_key = os.environ.get("POSTIZ_API_KEY")
    if not api_key:
        raise RuntimeError("POSTIZ_API_KEY not configured")
    # Claim before network call to prevent duplicate scheduling if a timeout occurs.
    with connect(db) as con:
        c = con.execute("UPDATE jobs SET status='submitting' WHERE id=? AND status='approved'", (job_id,))
        if c.rowcount != 1:
            raise ValueError("Job already claimed or changed")
    try:
        result = postiz_publish(job, api_key)
    except Exception as exc:
        with connect(db) as con:
            con.execute("UPDATE jobs SET status='needs_manual_review',response_json=? WHERE id=?", (json.dumps({"error": str(exc)[:500]}), job_id))
        raise
    with connect(db) as con:
        con.execute("UPDATE jobs SET status='submitted_to_postiz',response_json=? WHERE id=?", (json.dumps(result), job_id))
    return {"id": job_id, "status": "submitted_to_postiz", "response": result}


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("inspect", help="ffprobe media and report properties"); p.add_argument("file")
    p = sub.add_parser("transcribe", help="optional local faster-whisper transcript"); p.add_argument("file"); p.add_argument("--out", required=True); p.add_argument("--model", default="small"); p.add_argument("--language")
    p = sub.add_parser("captions", help="generate SRT or VTT from timestamped JSON"); p.add_argument("transcript"); p.add_argument("--out", required=True); p.add_argument("--words", type=int, default=7)
    p = sub.add_parser("suggest", help="editor-reviewed clip candidates from transcript"); p.add_argument("transcript"); p.add_argument("--out", required=True); p.add_argument("--min", type=float, default=10); p.add_argument("--max", type=float, default=55)
    p = sub.add_parser("clip", help="cut/vertical-fit/caption a video"); p.add_argument("file"); p.add_argument("--out", required=True); p.add_argument("--start", type=float, required=True); p.add_argument("--end", type=float, required=True); p.add_argument("--captions"); p.add_argument("--fit", choices=["blur", "crop"], default="blur")
    p = sub.add_parser("promo", help="render a text-scene promotional video"); p.add_argument("brief"); p.add_argument("--out", required=True)
    p = sub.add_parser("qc", help="validate rendered output"); p.add_argument("file")
    p = sub.add_parser("queue", help="create a reviewable Postiz schedule draft"); p.add_argument("file"); p.add_argument("--db", default="clipops_queue.sqlite3"); p.add_argument("--platform", required=True); p.add_argument("--integration", required=True); p.add_argument("--title", required=True); p.add_argument("--caption", required=True); p.add_argument("--when", required=True)
    p = sub.add_parser("approve", help="approve the exact draft and confirm media rights"); p.add_argument("id"); p.add_argument("--db", default="clipops_queue.sqlite3"); p.add_argument("--rights-confirmed", action="store_true")
    p = sub.add_parser("jobs", help="list local queue"); p.add_argument("--db", default="clipops_queue.sqlite3")
    p = sub.add_parser("publish", help="send approved job to Postiz for scheduled posting"); p.add_argument("id"); p.add_argument("--db", default="clipops_queue.sqlite3"); p.add_argument("--live", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.cmd in ("inspect", "qc"):
            result = qc_media(args.file) if args.cmd == "qc" else media_info(args.file)
        elif args.cmd == "transcribe":
            result = transcribe(args.file, args.out, args.model, args.language)
        elif args.cmd == "captions":
            segs = caption_groups(segments_from(args.transcript), max_words=args.words)
            vtt = args.out.lower().endswith(".vtt")
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_text(subtitle_text(segs, vtt=vtt), encoding="utf-8")
            result = {"file": args.out, "cues": len(segs)}
        elif args.cmd == "suggest":
            candidates = suggest_clips(segments_from(args.transcript), args.min, args.max)
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_text(json.dumps(candidates, indent=2), encoding="utf-8")
            result = {"file": args.out, "candidates": candidates}
        elif args.cmd == "clip":
            result = render_clip(args.file, args.out, args.start, args.end, args.captions, args.fit)
        elif args.cmd == "promo":
            result = promo(args.brief, args.out)
        elif args.cmd == "queue":
            result = add_job(args.db, args.file, args.platform, args.integration, args.title, args.caption, args.when)
        elif args.cmd == "approve":
            approve_job(args.db, args.id, args.rights_confirmed); result = {"id": args.id, "status": "approved"}
        elif args.cmd == "jobs":
            result = list_jobs(args.db)
        elif args.cmd == "publish":
            result = dispatch(args.db, args.id, args.live)
        else:
            raise ValueError("Unknown command")
    except (ValueError, RuntimeError, FileNotFoundError, OSError, KeyError) as exc:
        parser.exit(2, f"ClipOps error: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(cli())
