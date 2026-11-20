#!/usr/bin/env python3
"""Package a source-complete, private test build from tracked Git files only."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EXTENSIONS = {'.py', '.js', '.css', '.html', '.md', '.txt', '.json', '.yaml', '.yml', '.svg', '.woff2'}
ROOT_FILES = {'launch-studio', 'START_CLIPOPS.sh', 'START_CLIPOPS_WINDOWS.ps1',
              'START_CLIPOPS_CLOUD_SHELL.sh',
              'requirements-pilot.txt', 'requirements-visual-optional.txt', 'README.md', 'AGENTS.md', 'CONTEXT.md',
              'PILOT.md', 'VIDEO_WORKFLOW.md', 'MARKET_READY_QUALITY.md', 'SPRINT_HANDOFF.md'}
DIRECTORIES = {'studio', 'docs', 'tools', 'agents', 'skills', 'examples'}
MAX_ASSET = 16 * 1024 * 1024
ARCHIVE_PREFIX = 'ClipOps-Studio-TEST'


def tracked_files():
    paths = subprocess.check_output(['git', '-C', str(ROOT), 'ls-files', '-z']).decode().split('\0')
    for name in paths:
        if not name:
            continue
        p = Path(name)
        if (p.is_absolute() or '..' in p.parts or p.name.startswith('.env')
                or p.name.startswith('id_rsa') or p.suffix.lower() in
                {'.mp4','.mov','.mkv','.webm','.mp3','.wav','.key','.pem','.p12','.sqlite3','.db'}):
            continue
        if len(p.parts) == 1:
            permitted = p.suffix.lower() == '.py' or name in ROOT_FILES
        else:
            permitted = p.parts[0] in DIRECTORIES and p.suffix.lower() in EXTENSIONS
        if not permitted:
            continue
        source = ROOT / p
        if source.is_symlink() or not source.is_file() or source.stat().st_size > MAX_ASSET:
            raise ValueError(f'Unsafe or oversized tracked release file: {name}')
        yield name, source


def package(target):
    dest = Path(target).expanduser().resolve()
    if ROOT == dest.parent or ROOT in dest.parents:
        raise ValueError('Write packages outside the tracked source checkout')
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        raise ValueError('Refusing to overwrite an existing test archive')
    revision = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    indexed = []
    try:
        with zipfile.ZipFile(dest, 'x', zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
            for name, source in sorted(tracked_files()):
                data = source.read_bytes()
                archive.writestr(f'{ARCHIVE_PREFIX}/{name}', data)
                indexed.append({'path': name, 'size_bytes': len(data),
                                'sha256': hashlib.sha256(data).hexdigest()})
            if not any(x['path'] == 'studio.py' for x in indexed):
                raise RuntimeError('Missing Studio application backend')
            for need in ['studio/app.js', 'studio/index.html', 'studio/studio.css',
                         'pilot.py', 'pilot_edit.py', 'START_CLIPOPS.sh']:
                if not any(x['path'] == need for x in indexed):
                    raise RuntimeError(f'Missing required build component: {need}')
            manifest = {'type': 'local-review-only', 'revision': revision, 'files': indexed,
                        'privacy': 'No source videos, uploads, customer data, credentials or active API tokens included',
                        'warning': 'No executables or media codecs bundled; install free local system prerequisites.'}
            archive.writestr(f'{ARCHIVE_PREFIX}/BUILD_MANIFEST.json',
                             json.dumps(manifest, indent=2, ensure_ascii=False))
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
    return {'archive': str(dest), 'revision': revision, 'files': len(indexed),
            'sha256': hashlib.sha256(dest.read_bytes()).hexdigest()}


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python tools/package_test_build.py /tmp/clipops-studio-test.zip')
    print(json.dumps(package(sys.argv[1]), indent=2))
