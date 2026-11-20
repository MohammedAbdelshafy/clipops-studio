"""Read-only, offline-first alternatives for optional ClipOps dependencies.

No provider calls, credentials, file uploads, subprocess execution or automatic
publication. External links are manual options initiated by the editor.
"""
from __future__ import annotations

import shutil

ROUTES = (
    ("speech", "import_transcript", "Import a reviewed timed transcript", "local",
     "Import JSON segments with start, end and text. No API or local model needed.", None),
    ("speech", "faster_whisper", "Installed local faster-whisper", "local_optional",
     "Supply an existing CTranslate2 model folder; audio stays on your computer.", None),
    ("speech", "whisper_cpp", "whisper.cpp (external local tool)", "manual_external",
     "Free offline transcription after installation. Review and adapt timestamps before ClipOps import.",
     "https://github.com/ggml-org/whisper.cpp"),
    ("editing", "ffmpeg", "ClipOps offline FFmpeg renderer", "local_optional",
     "Use built-in review and approved export with installed FFmpeg and FFprobe.", None),
    ("editing", "kdenlive", "Kdenlive", "manual_external",
     "Free desktop editor. Export approved media from ClipOps before manually editing.",
     "https://kdenlive.org/en/"),
    ("editing", "shotcut", "Shotcut", "manual_external",
     "Free open-source desktop editor for manual finishing.", "https://shotcut.org/"),
    ("distribution", "clipops_export", "Export approved MP4, SRT and VTT", "local",
     "Use the Export center and the offline CSV schedule generator. Nothing is sent automatically.", None),
    ("distribution", "youtube_studio", "YouTube Studio", "manual_external",
     "Upload manually after rights review and choose appropriate visibility.",
     "https://studio.youtube.com/"),
    ("distribution", "tiktok_studio", "TikTok Studio", "manual_external",
     "Manually upload or manage clips with the channel owner's account and approval.",
     "https://www.tiktok.com/tiktokstudio"),
    ("distribution", "meta_business", "Meta Business Suite", "manual_external",
     "Manually post or schedule approved content where the account supports it.",
     "https://business.facebook.com/"),
    ("assets", "local_assets", "Use licensed local assets", "local",
     "Reuse authorized photos, logos, audio and owned graphics from your workstation.", None),
    ("assets", "gimp", "GIMP", "manual_external",
     "Free desktop image editor when a generation API is unavailable.", "https://www.gimp.org/"),
    ("intake", "source_reference", "Open a trusted local source folder", "local",
     "Use --source-dir to reference originals without a duplicate 15–20 GiB browser upload.", None),
    ("intake", "resumable_upload", "Resume the local browser upload", "local",
     "Resume checksum-verified chunks with the same unchanged source.", None),
)
GROUPS = ("intake", "speech", "editing", "assets", "distribution")


def free_routes(*, local_model=False, category=None):
    """Report possible manual actions; never infer remote account availability."""
    if category is not None and category not in GROUPS:
        raise ValueError("Unknown workflow")
    installed = {"ffmpeg": bool(shutil.which("ffmpeg") and shutil.which("ffprobe")),
                 "faster_whisper": bool(local_model)}
    rows = []
    for group, identifier, title, mode, description, url in ROUTES:
        if category is not None and group != category:
            continue
        if url is not None and not url.startswith("https://"):
            raise ValueError("Unsafe external option URL")
        rows.append({"workflow": group, "id": identifier, "title": title,
                     "mode": mode, "description": description, "url": url,
                     "available_here": installed.get(identifier, mode == "local"),
                     "automatic": False, "requires_approval": mode == "manual_external"})
    return {"routes": rows, "workflows": GROUPS, "network_requests": 0,
            "policy": "Only the editor decides when to open another tool. No automatic upload, publication or retry of a possibly submitted post."}
