#!/usr/bin/env python3
"""Single-user ClipOps review desk. All requests and media stay on loopback."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from http.cookies import SimpleCookie, CookieError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import tempfile
import threading
from urllib.parse import urlsplit

from studio_uploads import UploadStore, UploadError, TUS, EMPTY_RECEIPT, expires, checksum
from free_fallbacks import free_routes

ASSETS = Path(__file__).resolve().parent / 'studio'
STATIC = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
          '/studio.css': ('studio.css', 'text/css; charset=utf-8'), '/Inter-latin.woff2': ('Inter-latin.woff2', 'font/woff2')}
LEGACY_MEDIA = 6 * 1024**3
MAX_JSON = 16 * 1024**2
ID = r'[0-9a-f]{32}'
CLIP = r'c[0-9]{2,4}'
MEDIA_TYPES = {'.mp4': 'video/mp4', '.mov': 'video/quicktime', '.mkv': 'video/x-matroska', '.webm': 'video/webm',
               '.srt': 'application/x-subrip', '.vtt': 'text/vtt; charset=utf-8'}
VIDEO_TYPES = {key: value for key, value in MEDIA_TYPES.items() if key not in ('.srt', '.vtt')}
PUBLIC_FIELDS = ('id', 'name', 'status', 'stage', 'progress', 'style', 'platform', 'audience', 'resolution', 'framing',
                 'brand', 'cleanup', 'push_in', 'speaker_positions', 'candidate_count', 'rendered_count',
                 'approved_count', 'created_at', 'updated_at', 'error', 'proxy_ready', 'edits')
CLIP_FIELDS = ('id', 'start', 'end', 'score', 'rationale', 'title', 'description', 'cta', 'preview', 'review', 'editor',
               'rendered', 'render_error', 'selection_edited', 'remove_ranges', 'punch_ins')


class RequestError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def project_view(project, detail):
    result = {k: project[k] for k in PUBLIC_FIELDS if k in project}
    src = project.get('source', {})
    result['source'] = {k: src[k] for k in ('name', 'duration', 'dimensions') if k in src}
    if detail:
        result['segments'] = project.get('segments', [])
        clips = []
        for source in project.get('candidates', []):
            clip = {k: source[k] for k in CLIP_FIELDS if k in source}
            quality = source.get('qc') or {}
            clip['qc'] = {k: quality[k] for k in ('passed', 'checks', 'manual_review', 'dimensions') if k in quality} or None
            rendering = source.get('render') or {}
            clip['render'] = {k: rendering[k] for k in ('duration', 'framing', 'framing_reason', 'dimensions',
                                                        'upscaled', 'encoder', 'retained_source_ranges') if k in rendering}
            clips.append(clip)
        result['candidates'] = clips
    return result


class DeskServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port, root, engine, model=None, source_dir=None):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.engine = engine
        self.model = Path(model).expanduser().resolve(strict=True) if model else None
        self.source_dir = Path(source_dir).expanduser().resolve(strict=True) if source_dir else None
        if self.source_dir and not self.source_dir.is_dir():
            raise ValueError("The source folder must be a local directory")
        self.upload_store = UploadStore(self.root)
        self.uploads = threading.BoundedSemaphore(1)
        self.slots = threading.BoundedSemaphore(6)
        self.lock = threading.RLock()
        self.active = set()
        self.worker_errors = {}
        self.session = secrets.token_urlsafe(32)
        self.csrf = secrets.token_urlsafe(32)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='clipops-render')
        super().__init__(('127.0.0.1', port), DeskHandler)
        self.hosts = {f'127.0.0.1:{self.server_port}', f'localhost:{self.server_port}'}
        self.cookie_name = f'clipops_{self.server_port}'

    def queue_job(self, project_id, count, clip_ids=None, proxy=False):
        with self.lock:
            if project_id in self.active:
                raise RequestError(409, 'This project already has a job running.')
            if not self.slots.acquire(blocking=False):
                raise RequestError(429, 'The render queue is full. Try again after a job finishes.')
            self.worker_errors.pop(project_id, None)
            self.active.add(project_id)
            self.executor.submit(self._process, project_id, count, clip_ids, proxy)

    def _process(self, project_id, count, clip_ids, proxy):
        try:
            if proxy:
                self.engine.generate_proxy(self.root, project_id)
            else:
                self.engine.process_project(self.root, project_id, render_count=count, clip_ids=clip_ids, model=self.model)
        except Exception as exc:
            with self.lock:
                self.worker_errors[project_id] = self.safe_message(exc)
        finally:
            with self.lock:
                self.active.discard(project_id)
                self.slots.release()

    def safe_message(self, exc):
        message = str(exc).splitlines()[0][:320] if str(exc).strip() else 'The operation failed.'
        for private_path in (self.root, self.model, self.source_dir):
            if private_path:
                message = message.replace(str(private_path), '[local storage]')
        return message

    def details(self, project_id):
        project = project_view(self.engine.get_project(self.root, project_id), True)
        with self.lock:
            project['busy'] = project_id in self.active
            if project_id in self.worker_errors:
                project['error'] = self.worker_errors[project_id]
        return project

    def server_close(self):
        super().server_close()
        self.executor.shutdown(wait=True)


class DeskHandler(BaseHTTPRequestHandler):
    server: DeskServer
    server_version = 'ClipOps'
    sys_version = ''

    def setup(self):
        super().setup()
        self.connection.settimeout(45)

    def log_message(self, format, *args):
        # Request URLs can identify customer projects. The UI reports job errors.
        pass

    def _headers(self, status, mime, length, extra=()):
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(length))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
        self.send_header('Content-Security-Policy', "default-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        for name, value in extra:
            self.send_header(name, value)
        self.end_headers()

    def _json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, allow_nan=False).encode()
        self._headers(status, 'application/json; charset=utf-8', len(body))
        if self.command != 'HEAD':
            self.wfile.write(body)

    def _validate_request(self, path):
        hosts = self.headers.get_all('Host', [])
        if len(hosts) != 1 or hosts[0] not in self.server.hosts:
            raise RequestError(403, 'Use the local Studio address shown at startup.')
        if self.headers.get('Sec-Fetch-Site') == 'cross-site' and not (path == '/' and self.command == 'GET'):
            raise RequestError(403, 'This route is available only inside Studio.')
        if path in STATIC and self.command in ('GET', 'HEAD'):
            return
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie', ''))
        except CookieError:
            pass
        token = cookie.get(self.server.cookie_name)
        if not token or not secrets.compare_digest(token.value, self.server.session):
            raise RequestError(403, 'Open Studio in a local browser to begin a session.')
        if self.command in ('POST', 'PATCH', 'DELETE'):
            if self.headers.get('Origin') != 'http://' + hosts[0] or not secrets.compare_digest(self.headers.get('X-ClipOps-CSRF', ''), self.server.csrf):
                raise RequestError(403, 'This request requires an active Studio session. Reload the page.')

    def _length(self, maximum):
        raw = self.headers.get_all('Content-Length', [])
        if self.headers.get('Transfer-Encoding') or len(raw) != 1 or not re.fullmatch(r'[0-9]{1,14}', raw[0]):
            raise RequestError(411, 'A single byte length is required.')
        length = int(raw[0])
        if length < 1 or length > maximum:
            raise RequestError(413, 'The request exceeds the local size limit or is empty.')
        return length

    def _read_json(self):
        if self.headers.get_content_type() != 'application/json':
            raise RequestError(415, 'This action requires JSON.')
        value = json.loads(self.rfile.read(self._length(MAX_JSON)))
        if not isinstance(value, dict):
            raise RequestError(400, 'Expected a JSON object.')
        return value

    def _get(self, path):
        if path in STATIC:
            filename, mime = STATIC[path]
            content = (ASSETS / filename).read_bytes()
            extra = [('Set-Cookie', f'{self.server.cookie_name}={self.server.session}; HttpOnly; SameSite=Strict; Path=/')] if path == '/' else []
            self._headers(200, mime, len(content), extra)
            if self.command != 'HEAD':
                self.wfile.write(content)
        elif path == '/api/session':
            self._json({'csrf': self.server.csrf, 'local_model': bool(self.server.model), 'upload_limit': self.server.upload_store.capacity, 'chunk_bytes': self.server.upload_store.chunk,
                        'local_sources': bool(self.server.source_dir)})
        elif path == '/api/fallbacks':
            self._json(free_routes(local_model=self.server.model is not None))
        elif path == '/api/local-sources' and self.server.source_dir:
            from itertools import islice

            files = (p.name for p in self.server.source_dir.iterdir()
                     if p.suffix.lower() in VIDEO_TYPES and not p.is_symlink() and p.is_file())
            self._json(sorted(islice(files, 200)))
        elif path == '/api/projects':
            self._json([project_view(p, False) for p in self.server.engine.list_projects(self.server.root)])
        elif match := re.fullmatch(rf'/api/projects/({ID})', path):
            self._json(self.server.details(match[1]))
        elif match := re.fullmatch(rf'/api/projects/({ID})/({CLIP})/cuts', path):
            self._json(self.server.engine.suggest_cuts(self.server.root, match[1], match[2]))
        elif match := re.fullmatch(rf'/media/({ID})/(source|({CLIP})/(preview|webm|export|srt|vtt))', path):
            kind = match[4] or 'source'
            if kind == 'webm':
                file = self.server.engine.browser_preview(self.server.root, match[1], match[3])
            else:
                file = self.server.engine.get_media_path(self.server.root, match[1], clip_id=match[3], kind=kind)
            self._file(Path(file), kind, match[3])
        else:
            raise RequestError(404, 'Route not found.')

    def _file(self, path, kind, clip_id):
        size = path.stat().st_size
        start, end = 0, size - 1
        extra = [('Accept-Ranges', 'bytes')]
        status = 200
        if byte_range := self.headers.get('Range'):
            match = re.fullmatch(r'bytes=(\d{0,16})-(\d{0,16})', byte_range)
            if match and any(match.groups()):
                first, last = match.groups()
                start = int(first) if first else max(0, size - int(last))
                end = min(int(last), size - 1) if first and last else size - 1
            if not match or not any(match.groups()) or start > end or start >= size:
                self._headers(416, 'text/plain', 0, [('Content-Range', f'bytes */{size}')])
                return
            status = 206
            extra.append(('Content-Range', f'bytes {start}-{end}/{size}'))
        if kind in ('export', 'srt', 'vtt'):
            extra.append(('Content-Disposition', f'attachment; filename="{clip_id}{path.suffix.lower()}"'))
        self._headers(status, MEDIA_TYPES.get(path.suffix.lower(), 'application/octet-stream'), max(0, end - start + 1), extra)
        if self.command == 'HEAD':
            return
        with path.open('rb') as media:
            media.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                block = media.read(min(256 * 1024, remaining))
                if not block:
                    break
                self.wfile.write(block)
                remaining -= len(block)

    def _import_metadata(self, meta):
        if not isinstance(meta, dict) or meta.get('rights') is not True:
            raise RequestError(400, 'Confirm your rights to process the footage.')
        filename = meta.get('filename', '')
        if (not isinstance(filename, str) or not 1 <= len(filename) <= 180 or
                Path(filename).name != filename or '\\' in filename or any(ord(c) < 32 for c in filename)):
            raise RequestError(400, 'Invalid video filename.')
        suffix = Path(filename).suffix.lower()
        if suffix not in VIDEO_TYPES:
            raise RequestError(415, 'Choose an MP4, MOV, MKV or WebM source.')
        media_type = meta.get('mime') or 'application/octet-stream'
        compatible = {VIDEO_TYPES[suffix], 'application/octet-stream'}
        if suffix == '.mov':
            compatible.add('video/mp4')
        if media_type not in compatible:
            raise RequestError(415, 'The selected file type does not match its video extension.')
        transcript = meta.get('transcript')
        if transcript is None and self.server.model is None:
            raise RequestError(400, 'Choose a timestamped transcript or start Studio with --model.')
        if transcript is not None and not isinstance(transcript, (dict, list)):
            raise RequestError(400, 'Choose a timestamped JSON transcript.')
        count = meta.get('render_count', 5)
        if type(count) is not int or not 0 <= count <= 30:
            raise RequestError(400, 'Choose between zero and 30 initial renders.')
        name = meta.get('name') or Path(filename).stem
        if not isinstance(name, str) or not name.strip() or len(name) > 140:
            raise RequestError(400, 'Enter a project name of at most 140 characters.')
        return {'filename': filename, 'name': name.strip(), 'transcript': transcript,
                'render_count': count, 'style': meta.get('style', 'podcast'),
                'platform': meta.get('platform', 'shorts')}

    def _create_job(self, media, work, spec, **options):
        transcript = None
        if spec['transcript'] is not None:
            from pilot import save_json
            transcript = work / 'timed-transcript.json'
            save_json(transcript, spec['transcript'])
        return self.server.engine.create_project(media, self.server.root, transcript=transcript, model=self.server.model,
                rights=True, name=spec['name'], render_count=spec['render_count'],
                style=spec['style'], platform=spec['platform'], **options)

    def _import_result(self, project_id, count):
        try:
            self.server.queue_job(project_id, count)
        except (RequestError, UploadError) as exc:
            self._json({'id': project_id, 'message': str(exc)}, 201)
            return
        self._json({'id': project_id}, 201)

    def _upload_route(self, path):
        store = self.server.upload_store
        verb = self.command
        version = [('Tus-Resumable', TUS)]
        if path == '/api/uploads' and verb == 'POST':
            payload = self._read_json()
            spec = self._import_metadata(payload.get('metadata'))
            key = payload.get('id')
            if not isinstance(key, str):
                raise RequestError(400, 'Upload ID is required.')
            state = store.begin(key, payload.get('size'), spec)
            self._headers(201, 'text/plain', 0, version + [
                ('Location', '/api/uploads/' + key), ('Upload-Offset', str(state['offset'])),
                ('Upload-Expires', expires(state))])
            return
        match = re.fullmatch(rf'/api/uploads/({ID})(/complete)?', path)
        if not match:
            raise RequestError(404, 'Unknown upload route.')
        key, complete = match.groups()
        if complete and verb == 'POST':
            project, count = store.finish(key, self.server.root,
                                          lambda file, work, spec: self._create_job(
                                              file, work, spec, job_id=key, staged_upload=True))
            # A replay after completion returns the existing project without starting a new render.
            details = self.server.engine.get_project(self.server.root, project)
            if details['status'] == 'queued':
                self._import_result(project, count)
            else:
                self._json({'id': project}, 201)
            return
        if complete or verb not in ('HEAD', 'PATCH', 'DELETE'):
            raise RequestError(405, 'Use HEAD, PATCH or DELETE on the upload itself.')
        if self.headers.get('Tus-Resumable') != TUS:
            raise RequestError(412, 'Use Tus-Resumable 1.0.0 for upload requests.')
        status = 204
        if verb == 'DELETE':
            store.cancel(key)
            self._headers(status, 'text/plain', 0, version)
            return
        if verb == 'PATCH':
            if self.headers.get_content_type() != 'application/offset+octet-stream':
                raise RequestError(415, 'Use application/offset+octet-stream for chunks.')
            offsets = self.headers.get_all('Upload-Offset', [])
            hashes = self.headers.get_all('Upload-Checksum', [])
            if len(offsets) != 1 or not re.fullmatch(r'[0-9]{1,12}', offsets[0]) or len(hashes) != 1:
                raise RequestError(400, 'A byte offset and a checksum are required.')
            length = self._length(store.chunk)
            if not self.server.uploads.acquire(blocking=False):
                raise RequestError(429, 'Another upload is writing. Retry this chunk.')
            try:
                state = store.append(key, int(offsets[0]), length, checksum(hashes[0]), self.rfile)
            finally:
                self.server.uploads.release()
        else:
            status = 200
            state = store.inspect(key)
        self._headers(status, 'text/plain', 0, version + [
            ('Upload-Offset', str(state['offset'])), ('Upload-Length', str(state['size'])),
            ('Upload-Expires', expires(state)), ('Upload-Receipt', state.get('receipt', EMPTY_RECEIPT))])

    def _local_import(self):
        if not self.server.source_dir:
            raise RequestError(404, 'Configure a trusted local source folder first.')
        spec = self._import_metadata(self._read_json())
        media = self.server.source_dir / spec['filename']
        if media.is_symlink() or not media.is_file():
            raise RequestError(404, 'Choose a regular file in the configured source folder.')
        with tempfile.TemporaryDirectory(dir=self.server.root, prefix='.local-intake-') as scratch:
            job = self._create_job(media, Path(scratch), spec, reference=True)
        self._import_result(job, spec['render_count'])

    def _upload(self):
        if self.headers.get_content_type() != 'application/octet-stream':
            raise RequestError(415, 'Use the Studio import form to upload video.')
        length = self._length(LEGACY_MEDIA + MAX_JSON)
        header = self.headers.get('X-ClipOps-Metadata-Length', '')
        if not re.fullmatch(r'\d{1,8}', header) or not 1 <= int(header) < length or int(header) > MAX_JSON:
            raise RequestError(400, 'Invalid upload metadata length.')
        if length - int(header) > LEGACY_MEDIA:
            raise RequestError(413, 'Video exceeds the local size limit.')
        if not self.server.uploads.acquire(blocking=False):
            raise RequestError(429, 'Another import is in progress.')
        try:
            meta = self._import_metadata(json.loads(self.rfile.read(int(header))))
            filename, count = meta['filename'], meta['render_count']
            remaining = length - int(header)
            if shutil.disk_usage(self.server.root).free < 2 * remaining + 64 * 1024**2:
                raise RequestError(507, 'Local storage needs space for the upload and private project copy.')
            with tempfile.TemporaryDirectory(dir=self.server.root, prefix='.ingest-') as directory:
                tmp = Path(directory)
                # Create the transcript separately to avoid any name collision with the video.
                source = tmp / filename
                with source.open('xb') as out:
                    while remaining:
                        block = self.rfile.read(min(1024 * 1024, remaining))
                        if not block:
                            raise RequestError(400, 'The upload ended before the video was complete.')
                        out.write(block)
                        remaining -= len(block)
                transcript = None
                if meta.get('transcript') is not None:
                    transcript = tmp / 'timed-transcript.json'
                    transcript.write_text(json.dumps(meta['transcript'], ensure_ascii=False), encoding='utf-8')
                project_id = self.server.engine.create_project(source, self.server.root, transcript=transcript, model=self.server.model,
                    rights=True, name=meta['name'], render_count=count, style=meta.get('style', 'podcast'), platform=meta.get('platform', 'shorts'))
            try:
                self.server.queue_job(project_id, count)
            except RequestError as exc:
                # The source is already safe. Keep a successfully imported job resumable.
                self._json({'id': project_id, 'message': str(exc)}, 201)
                return
            self._json({'id': project_id}, 201)
        finally:
            self.server.uploads.release()

    def _post(self, path):
        if path == '/api/import-local':
            self._local_import()
            return
        if path == '/api/import':
            self._upload()
            return
        match = re.fullmatch(rf'/api/projects/({ID})/(edit|review|render|proxy|purge)', path)
        if not match:
            raise RequestError(404, 'Route not found.')
        project_id, action = match.groups()
        data = self._read_json()
        with self.server.lock:
            if project_id in self.server.active:
                raise RequestError(409, 'Wait for the current job to finish.')
            engine, root = self.server.engine, self.server.root
            if action == 'edit':
                allowed = {'segments', 'style', 'platform', 'brand', 'resolution', 'framing', 'candidate_id', 'title',
                           'editor', 'start', 'end', 'description', 'cta', 'remove_ranges', 'cleanup', 'push_in',
                           'speaker_positions', 'audience', 'punch_ins'}
                if not data or set(data) - allowed:
                    raise RequestError(400, 'Unknown or missing editable field.')
                engine.edit_project(root, project_id, **data)
            elif action == 'review':
                if data.get('decision') not in ('assigned', 'approved', 'rejected') or not re.fullmatch(CLIP, str(data.get('clip_id', ''))):
                    raise RequestError(400, 'Choose a candidate and a valid review decision.')
                engine.review_clip(root, project_id, data['clip_id'], data['decision'], data.get('editor', ''), rights=data.get('rights') is True)
            elif action == 'render':
                project = engine.get_project(root, project_id)
                count, ids = data.get('render_count', 5), data.get('clip_ids')
                if type(count) is not int or not 0 <= count <= 30:
                    raise RequestError(400, 'Choose between zero and 30 renders.')
                if ids is not None:
                    available = {c['id'] for c in project.get('candidates', [])}
                    if not isinstance(ids, list) or not ids or len(ids) > 30 or not all(isinstance(i, str) and i in available for i in ids):
                        raise RequestError(400, 'Choose candidates from this project.')
                    if len(set(ids)) != len(ids) or count != len(ids):
                        raise RequestError(400, 'Choose each candidate once.')
                self.server.queue_job(project_id, count, ids)
            elif action == 'proxy':
                engine.get_project(root, project_id)
                self.server.queue_job(project_id, 0, proxy=True)
            elif action == 'purge':
                project = engine.get_project(root, project_id)
                if data.get('confirm_name') != project['name']:
                    raise RequestError(400, 'Type the project name to confirm deletion.')
                engine.purge_project(root, project_id)
                self.server.worker_errors.pop(project_id, None)
        self._json({'ok': True}, 202 if action in ('render', 'proxy') else 200)

    def _handle(self):
        try:
            path = urlsplit(self.path).path
            self._validate_request(path)
            if path == '/api/uploads' or path.startswith('/api/uploads/'):
                self._upload_route(path)
            elif self.command == 'POST':
                self._post(path)
            elif self.command in ('PATCH', 'DELETE'):
                raise RequestError(405, 'This route does not support the request method.')
            else:
                self._get(path)
        except (BrokenPipeError, ConnectionResetError, socket.timeout):
            self.close_connection = True
        except (RequestError, UploadError) as exc:
            self._json({'error': str(exc)}, exc.status)
        except FileNotFoundError:
            self._json({'error': 'This project or artifact is unavailable.'}, 404)
        except PermissionError:
            self._json({'error': 'This artifact requires approval and a passing technical check.'}, 403)
        except (ValueError, KeyError, TypeError, RuntimeError) as exc:
            self._json({'error': self.server.safe_message(exc)}, 400)
        except OSError:
            self._json({'error': 'Local storage is unavailable. Check disk space and project access.'}, 500)

    do_GET = _handle
    do_HEAD = _handle
    do_POST = _handle
    do_PATCH = _handle
    do_DELETE = _handle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path, help='Private local project directory')
    parser.add_argument('--port', default=8765, type=int)
    parser.add_argument('--source-dir', type=Path, help='Optional trusted folder for direct, read-only import')
    parser.add_argument('--open', action='store_true', help='Open the local studio in the default browser')
    parser.add_argument('--model', type=Path, help='Optional local faster-whisper model directory')
    args = parser.parse_args()
    import pilot
    os.umask(0o077)
    with DeskServer(args.port, args.root, pilot, model=args.model, source_dir=args.source_dir) as server:
        print(f'ClipOps Studio is ready at http://127.0.0.1:{server.server_port}', flush=True)
        if args.open:
            import webbrowser
            opener = threading.Thread(target=webbrowser.open, args=(f'http://127.0.0.1:{server.server_port}',), daemon=True)
            opener.start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
