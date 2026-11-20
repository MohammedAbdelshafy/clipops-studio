"""Non-destructive, on-demand local visual transition hints using installed FFmpeg.

A histogram-based scene score is not semantic video understanding. Never apply
scene cuts automatically: a hard camera cut can be the correct editorial choice.
"""
from __future__ import annotations

import math
from pathlib import Path
import re
import subprocess

SHOWINFO = re.compile(r'\[Parsed_showinfo_\d+[^\]]*\].*?pts_time:\s*([0-9]+(?:\.[0-9]+)?)')


def scene_review(source, start, end, *, threshold=0.30):
    if isinstance(start, bool) or isinstance(end, bool):
        raise ValueError('Invalid scene review time interval')
    try:
        start, end = float(start), float(end)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError('Invalid scene review time interval') from exc
    if not math.isfinite(start) or not math.isfinite(end) or start < 0 or not .25 <= end - start <= 180:
        raise ValueError('Scene reviews must cover at most 180 seconds of real media')
    if not isinstance(threshold, (float, int)) or isinstance(threshold, bool) or not .18 <= threshold <= .65:
        raise ValueError('Invalid visual change threshold')
    path = Path(source)
    if path.is_symlink() or not path.is_file() or path.suffix.lower() not in {'.mp4', '.mov', '.mkv', '.webm'}:
        raise ValueError('Select an available local video source')
    # Only local input. Frame resizing occurs after local media decode; capped
    # scan time and frame rate keep this an explicit per-clip review operation.
    filtergraph = f"setpts=PTS-STARTPTS,fps=4,scale=320:-2,select='gt(scene,{float(threshold):.3f})',showinfo"
    command = ['ffmpeg', '-nostdin', '-hide_banner', '-v', 'info',
               '-protocol_whitelist', 'file', '-ss', f'{start:.3f}', '-i', str(path),
               '-t', f'{end-start:.3f}', '-an', '-vf', filtergraph,
               '-fps_mode', 'vfr', '-f', 'null', '-']
    try:
        run = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, timeout=45, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError('Local scene analysis unavailable or exceeded the 45-second limit') from exc
    if run.returncode != 0:
        raise ValueError('Unable to inspect visual changes in the local media')
    local = []
    for match in SHOWINFO.finditer(run.stderr.decode('utf-8', 'replace')):
        moment = float(match[1])
        if .10 < moment < end-start-.10 and (not local or moment - local[-1] > .35):
            local.append(moment)
        if len(local) >= 64:
            break
    # Source-relative timestamps are calculated from the requested trim start.
    return {'source_range': [start, end], 'scene_boundaries': [round(start + t, 3) for t in local],
            'method': 'local_ffmpeg_frame_change', 'threshold': round(float(threshold), 3),
            'sample_rate_fps': 4, 'advisory_only': True,
            'warning': 'Visual changes are sampled frame differences, not safe automatic clip boundaries. Review every cut and speaker switch.'}
