"""Approval-verified, bounded ZIP packaging for ClipOps reviewed deliveries.

Creates a temporary ZIP on the local workstation only. Never copies original
footage into the archive or uses network services. Every included export must
have the existing ClipOps rights/QC/reviewer approval and matching file hashes.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import zipfile

MAX_CLIPS = 30
MAX_TOTAL_BYTES = 8 * 1024**3
FILES = (('export', 'clip.mp4'), ('srt', 'clip.srt'), ('vtt', 'clip.vtt'))


def bundle_approved(engine, root, project_id, destination):
    """Create one approved-only ZIP; caller owns its private temporary output."""
    directory = engine.project_dir(root, project_id)
    destination = destination.resolve()
    if destination.exists() or destination.is_symlink():
        raise ValueError('Choose a fresh temporary ZIP path')
    if destination.parent == directory or directory in destination.parents:
        raise ValueError('Keep delivery archives outside the project directory')
    with engine.lock(directory, '.worker'):
        state = engine.load_json(directory / engine.PROJECT_FILE)
        selections = [c for c in state.get('candidates', []) if c.get('review') == 'approved']
        if not selections:
            raise PermissionError('No approved clips are available for delivery')
        if len(selections) > MAX_CLIPS:
            raise ValueError('Choose no more than thirty approved clips')
        entries = []
        total = 0
        for clip in selections:
            clip_id = clip.get('id')
            if not isinstance(clip_id, str) or not clip_id.startswith('c') or len(clip_id) > 5 or not clip_id[1:].isdigit():
                raise ValueError('Invalid candidate ID in project state')
            for kind, filename in FILES:
                path = engine.approved_media(directory, clip, kind, verify=True)
                size = path.stat().st_size
                total += size
                if size <= 0 or total > MAX_TOTAL_BYTES:
                    raise ValueError('Approved delivery exceeds safe local ZIP limits')
                entries.append((clip, path, filename, f'{clip_id}/{filename}'))
        free = shutil.disk_usage(destination.parent).free
        if free < total + 64 * 1024**2:
            raise OSError('Not enough free disk space for the approved ZIP')
        receipt = []
        try:
            with zipfile.ZipFile(destination, 'x', compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
                for clip, path, name, archive_name in entries:
                    # ZIP write streams from disk in chunks; it never loads full
                    # MP4 exports into process memory.
                    archive.write(path, archive_name)
                    digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.stat().st_size < 1024**2 else engine.sha256(path)
                    expected = clip['approval']['hashes'][name]
                    if digest != expected:
                        raise PermissionError('An approved artifact changed during packaging')
                    receipt.append({'candidate_id': clip['id'], 'file': archive_name,
                                    'sha256': digest, 'bytes': path.stat().st_size,
                                    'source_range': [clip['start'], clip['end']]})
                manifest = {'format': 'clipops-approved-delivery-v1', 'project_id': project_id,
                            'clips': len(selections), 'files': receipt,
                            'review': 'Every exported file passed existing human rights/QC/hash gates'}
                archive.writestr('delivery-manifest.json', json.dumps(manifest, indent=2, ensure_ascii=False))
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
    return {'clips': len(selections), 'files': len(receipt), 'bytes': total}
