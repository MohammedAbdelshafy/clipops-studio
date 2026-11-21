#!/usr/bin/env python3
"""Exercise the real local desk with the generated, authorized studio fixture pair."""
import argparse
from base64 import b64encode
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import re
import threading
import time
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pilot
from studio import DeskServer


def seek_preview(page, seconds):
    """Verify a decoded seek and expose the media element's real state on failure."""
    # Execute through the locator, not by weakening the application's CSP.
    diagnostic = page.locator('#video').evaluate('''async (video, seconds) => {
        const deadline = performance.now() + 20000;
        video.pause();
        while (performance.now() < deadline && video.readyState === 0 && !video.error) {
            await new Promise(resolve => setTimeout(resolve, 50));
        }
        if (!video.error && video.readyState > 0) video.currentTime = seconds;
        while (performance.now() < deadline && !video.error) {
            if (!video.seeking && video.readyState >= 2 &&
                Math.abs(video.currentTime - seconds) < .12) return {passed: true};
            await new Promise(resolve => setTimeout(resolve, 50));
        }
        return {passed: false, src: new URL(video.currentSrc || video.src).pathname,
          readyState: video.readyState, networkState: video.networkState,
          errorCode: video.error?.code ?? null, errorMessage: video.error?.message ?? '',
          duration: video.duration, currentTime: video.currentTime,
          seekable: video.seekable.length ? [video.seekable.start(0), video.seekable.end(video.seekable.length-1)] : [],
          buffered: video.buffered.length ? [video.buffered.start(0), video.buffered.end(video.buffered.length-1)] : [],
          seeking: video.seeking, paused: video.paused};
    }''', seconds)
    assert diagnostic["passed"], f"Foreground browser preview failed to decode/seek: {diagnostic}"


def wait_for_upload_and_project(page, ctx, url, upload_id, source, chunk_bytes, headers, chunk_seconds):
    """Wait on observable upload progress, then on the real project page.

    The forced 256 KiB test chunk makes a ~44 MiB fixture ~175 round-trips.
    A flat timeout ignores both that workload and a stalled transfer, so the
    budget is derived from the measured first-chunk cost and the actual chunk
    count, and progress is checked against the server's tus offset. Both the
    overall deadline and the no-progress deadline are bounded.
    """
    total = source.stat().st_size
    chunks = -(-total // chunk_bytes)
    per_chunk = min(1.5, max(0.08, chunk_seconds * 3))
    budget_ms = int(min(8 * 60_000, max(30_000, chunks * per_chunk * 1000 + 20_000)))
    stall_s = max(15.0, per_chunk * 8)
    deadline = time.monotonic() + budget_ms / 1000
    last_offset = 0
    last_progress = time.monotonic()
    last_stage = 'starting'
    last_chunk = 0
    while time.monotonic() < deadline:
        try:
            last_stage = page.locator('#upload-message').text_content(timeout=500) or last_stage
        except Exception:
            pass
        # Browser progress is authoritative: the server may retire the tus
        # session as soon as /complete finishes, so HEAD can legitimately 404.
        shown = re.search(r'(\d+) of (\d+) MiB confirmed', last_stage)
        upload_finished = 'Verifying' in last_stage or 'opening the project' in last_stage
        if shown:
            shown_bytes = int(shown.group(1)) * 1024 * 1024
            if shown_bytes > last_offset:
                last_offset = shown_bytes
                last_chunk = -(-last_offset // chunk_bytes)
                last_progress = time.monotonic()
        if upload_finished:
            last_progress = time.monotonic()
        if page.get_by_role('heading', name='The editing room', exact=True).is_visible() and \
                page.locator('[data-clip]').count() > 0:
            expect(page.get_by_role('heading', name='The editing room', exact=True)).to_be_visible(timeout=5000)
            expect(page.locator('[data-clip]').first).to_be_visible(timeout=5000)
            return budget_ms, int((deadline - time.monotonic()) * 1000), chunks
        try:
            reply = ctx.request.head(url + '/api/uploads/' + upload_id, headers=headers, timeout=5000)
            if reply.status == 200:
                offset = int(reply.headers.get('Upload-Offset', '0'))
                if offset > last_offset:
                    last_offset = offset
                    last_chunk = -(-offset // chunk_bytes)
                    last_progress = time.monotonic()
                elif offset < total and not upload_finished and time.monotonic() - last_progress > stall_s:
                    raise AssertionError(
                        f'Upload stalled at chunk {last_chunk}/{chunks} '
                        f'({last_offset}/{total} bytes); last stage: {last_stage!r}')
            elif reply.status not in (404, 410):
                raise AssertionError(f'Upload status check returned HTTP {reply.status}; last stage: {last_stage!r}')
        except AssertionError:
            raise
        except Exception as exc:
            last_stage = f'status check error: {exc}'
            if time.monotonic() - last_progress > stall_s:
                raise AssertionError(
                    f'Upload status unavailable for {stall_s:.0f}s at chunk {last_chunk}/{chunks}; '
                    f'last stage: {last_stage!r}') from exc
        page.wait_for_timeout(250)
    raise AssertionError(
        f'Upload/project deadline {budget_ms}ms exhausted at chunk {last_chunk}/{chunks} '
        f'({last_offset}/{total} bytes); last stage: {last_stage!r}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures', required=True, type=Path)
    parser.add_argument('--screenshots', required=True, type=Path)
    parser.add_argument('--chromium', default=None, help='Optional Chrome/Chromium executable; branded Chrome supports H.264 playback')
    parser.add_argument('--no-route-filter', action='store_true', help='Leave browser network unmodified')
    parser.add_argument('--upload-only', action='store_true', help='Stop after upload and project validation')
    args = parser.parse_args()
    args.screenshots.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='clipops-desk-test-') as tmp, DeskServer(0, Path(tmp), pilot) as server, sync_playwright() as playwright:
        server.upload_store.chunk = 256 * 1024
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        import shutil
        executable = args.chromium or shutil.which('google-chrome') or shutil.which('google-chrome-stable') or shutil.which('chromium')
        if args.chromium and not Path(args.chromium).is_file():
            raise RuntimeError('The explicitly requested Chrome executable is missing')
        browser = playwright.chromium.launch(executable_path=executable, headless=True, args=['--disable-dev-shm-usage'])
        try:
            url = f'http://127.0.0.1:{server.server_port}'
            ctx = browser.new_context(viewport={'width':1390,'height':1000}, accept_downloads=True)
            if not args.no_route_filter:
                ctx.route('**/*', lambda route: route.continue_() if urlparse(route.request.url).netloc == f'127.0.0.1:{server.server_port}' else route.abort())
            page = ctx.new_page()
            errors = []
            page.on('pageerror', lambda err: errors.append(str(err)))
            page.goto(url)
            page.get_by_role('button',name='Free fallbacks').click()
            expect(page.get_by_role('dialog')).to_be_visible()
            expect(page.get_by_role('dialog')).to_contain_text('whisper.cpp')
            expect(page.get_by_role('dialog')).to_contain_text('YouTube Studio')
            page.get_by_role('button',name='Close dialog').click()
            page.get_by_role('button',name='Import project').first.click()
            form = page.locator('#import-form')
            form.locator('[name="name"]').fill('The editing room')
            form.locator('[name="video"]').set_input_files(str(args.fixtures/'studio.mp4'))
            form.locator('[name="transcript"]').set_input_files(str(args.fixtures/'studio.json'))
            form.locator('[name="count"]').fill('0')
            form.locator('[name="rights"]').check()
            # Simulate a prior browser session with a successfully committed first chunk.
            source = args.fixtures/'studio.mp4'
            upload_id = 'e' * 32
            session = ctx.request.get(url + '/api/session').json()
            headers = {'Origin':url,'X-ClipOps-CSRF':session['csrf'],'Tus-Resumable':'1.0.0'}
            metadata = {'filename':source.name,'name':'The editing room','rights':True,'render_count':0,
                        'transcript':json.loads((args.fixtures/'studio.json').read_text())}
            created = ctx.request.post(url + '/api/uploads', headers=headers,
                                       data={'id':upload_id,'size':source.stat().st_size,'metadata':metadata})
            assert created.status == 201, created.text()
            with source.open('rb') as stream:
                block = stream.read(session['chunk_bytes'])
            uploader = url + created.headers['location']
            chunk_started = time.monotonic()
            part = ctx.request.patch(uploader,data=block,headers={**headers,'Upload-Offset':'0',
                'Content-Type':'application/offset+octet-stream',
                'Upload-Checksum':'sha256 '+b64encode(sha256(block).digest()).decode()})
            chunk_seconds = time.monotonic() - chunk_started
            assert part.status == 204
            form.locator('[name="video"]').evaluate('async (field,id) => localStorage.setItem(await fileKey(field.files[0]),id)', upload_id)
            page.reload()
            page.get_by_role('button',name='Import project').first.click()
            form = page.locator('#import-form')
            form.locator('[name="video"]').set_input_files(str(source))
            form.locator('[name="rights"]').check()
            form.get_by_role('button',name='Import & process').click()
            budget, remaining, chunks = wait_for_upload_and_project(
                page, ctx, url, upload_id, source, session['chunk_bytes'], headers, chunk_seconds)
            print(f'Upload/project wait: {chunks} chunks, first chunk {chunk_seconds:.3f}s, '
                  f'budget {budget}ms, {remaining}ms unused, route_filter={not args.no_route_filter}', flush=True)
            if args.upload_only:
                print('Upload-only validation passed', flush=True)
                return
            job = page.url.split('/')[-1]
            assert job == upload_id
            clip = page.locator('[data-clip]').first.get_attribute('data-clip')
            print('Browser import and candidate selection passed', flush=True)
            page.get_by_role('button', name='Creative review').click()
            page.get_by_role('button', name='Analyze this clip').click()
            expect(page.get_by_role('heading', name='Verbatim quote bank')).to_be_visible()
            page.locator('#moment-form input[name="query"]').fill('biography')
            page.get_by_role('button',name='Find source moments').click()
            expect(page.get_by_role('heading',name='Found source moments')).to_be_visible()
            expect(page.locator('.review-block li').filter(has_text='biography').first).to_be_visible()
            page.get_by_role('button',name='Preview clip boundaries').first.click()
            expect(page.get_by_role('heading',name='Edit preview — not applied')).to_be_visible()
            page.get_by_role('button',name='Analyze visual scene changes').click()
            expect(page.get_by_role('heading',name='Visual transitions in selected clip')).to_be_visible(timeout=45000)
            print('Competitor upgrade: grounded moment search, non-mutating preview and local visual scene review passed',flush=True)
            page.locator('#creative-form textarea').fill('title: A reviewable opening; cta: Check the original')
            page.get_by_role('button', name='Preview safe edit').click()
            expect(page.get_by_role('heading', name='Edit preview — not applied')).to_be_visible()
            print('Creative quote bank and non-mutating edit preview passed', flush=True)
            page.get_by_role('button',name='Transcript & captions').click()
            page.get_by_role('searchbox',name='Search transcript').fill('biography')
            expect(page.locator('.cue')).to_have_count(1)
            page.locator('[data-edit-cue]').first.click()
            caption = page.locator('#cue-form textarea')
            caption.fill(caption.input_value() + ' Cut to the answer.')
            page.get_by_role('button',name='Save caption').click()
            expect(page.locator('#dialog')).not_to_be_visible()
            expect(page.locator('.cue p')).to_contain_text('Cut to the answer')
            page.get_by_role('button',name='Render settings').click()
            settings = page.locator('#settings-form')
            settings.locator('[name="resolution"]').select_option('720')
            settings.locator('[name="accent"]').fill('#B4DF87')
            settings.get_by_role('button',name='Save render settings').click()
            expect(page.get_by_role('status').last).to_have_text('Render settings saved.')
            page.get_by_role('button',name='Clip details').click()
            detail = page.locator('#details-form')
            detail.locator('[name="title"]').fill('Why did our best interview lose its audience?')
            detail.locator('[name="description"]').fill('An opening question sets the context for the answer.')
            detail.locator('[name="start"]').fill('0.33')
            detail.locator('[name="end"]').fill('8.0')
            detail.get_by_role('button',name='Save clip edits').click()
            expect(page.get_by_role('status').last).to_have_text('Clip edits saved.')
            page.get_by_role('button',name='Review pause and filler cuts').click()
            # Synthetic captions have cue timings, not per-word timings. A cut
            # inside speech is correctly forbidden, so select a measured silence
            # between two source cues rather than defeating the speech guard.
            source_cues = metadata['transcript']['segments']
            gaps = [(a['end'], b['start']) for a, b in zip(source_cues, source_cues[1:])
                    if a['end'] >= .33 and b['start'] <= 8.0
                    and b['start'] - a['end'] >= .30]
            assert gaps, 'Synthetic test needs a genuine source pause within the selected clip'
            pause_start, pause_end = gaps[0]
            cut_start, cut_end = round(pause_start + .06, 3), round(pause_start + .24, 3)
            assert cut_end < pause_end - .025, 'Cut must stay in confirmed silence'
            page.get_by_label('Reviewed source intervals').fill(f'{cut_start:.3f}, {cut_end:.3f}')
            page.get_by_role('button',name='Save reviewed cuts').click()
            expect(page.get_by_role('status').last).to_have_text('Reviewed cuts saved.')
            page.get_by_role('button',name='Edit punch-ins').click()
            page.get_by_label('Timed punch-ins').fill('0.80, 1.20, 1.08')
            page.get_by_role('button',name='Save punch-ins').click()
            expect(page.get_by_role('status').last).to_have_text('Punch-ins saved.')
            page.get_by_role('button',name='Render batch').click()
            page.get_by_role('button',name='Render selected clips').click()
            expect(page.locator('#dialog')).not_to_be_visible()
            try:
                expect(page.locator('.monitor-head')).to_contain_text('Rendered preview', timeout=150000)
            except AssertionError as exc:
                # Preserve the actual async render failure in CI logs. The
                # preview header alone says nothing about why it remained on
                # the original footage for the duration of this smoke test.
                with server.lock:
                    worker_error = server.worker_errors.get(job)
                    worker_active = job in server.active
                statuses = page.get_by_role('status').all_text_contents()
                monitor = page.locator('.monitor-head').inner_text()
                project_state = server.details(job)
                candidates = [(c['id'], c.get('rendered'), c.get('render_error'))
                              for c in project_state.get('candidates', [])[:3]]
                raise AssertionError(
                    f'Edit render unavailable: project={job!r}, active={worker_active}, '
                    f'worker_error={worker_error!r}, monitor={monitor!r}, '
                    f'project_status={project_state.get("status")!r}, '
                    f'project_error={project_state.get("error")!r}, '
                    f'candidates={candidates!r}, '
                    f'ui_statuses={statuses[-4:]!r}, page_errors={errors[-4:]!r}'
                ) from exc
            motion = page.get_by_role('button', name='Toggle cinematic video backdrop')
            expect(motion).to_have_attribute('aria-pressed', 'true')
            expect(page.locator('.ambient-preview')).to_have_count(1)
            motion.click()
            expect(motion).to_have_attribute('aria-pressed', 'false')
            expect(page.locator('.ambient-preview')).to_have_count(0)
            motion.click()
            expect(page.locator('.ambient-preview')).to_have_count(1)
            edited_length = 8.0 - .33 - (cut_end - cut_start)
            assert abs(float(page.locator('#scrub').get_attribute('max')) - edited_length) < .06
            page.get_by_role('button',name='View source').click()
            expect(page.locator('.monitor-head')).to_contain_text('Source preview')
            expect(page.locator('.ambient-preview')).to_have_count(0)
            page.get_by_role('button',name='View render').click()
            expect(page.locator('.monitor-head')).to_contain_text('Rendered preview')
            expect(page.locator('.ambient-preview')).to_have_count(1)
            seek_preview(page, 2.2)
            page.evaluate('window.scrollTo(0, 0)')
            page.screenshot(path=str(args.screenshots/'studio-desktop.png'))
            page.get_by_role('button',name='Play preview').click()
            assert page.locator('#video').evaluate('''async video => {
                const deadline = performance.now() + 5000;
                while (performance.now() < deadline && video.currentTime <= 2.4) {
                    await new Promise(resolve => setTimeout(resolve, 50));
                }
                return video.currentTime > 2.4;
            }''')
            page.get_by_role('button',name='Pause preview').click()
            print('Search, caption edit, brand settings, trimmed interval, internal cut, batch render and playback passed',flush=True)
            req = ctx.request
            denied = req.get(f'{url}/media/{job}/{clip}/export')
            assert denied.status in (400,403), denied.status
            page.get_by_role('button',name='Review & delivery').click()
            expect(page.get_by_text('Technical QC passed')).to_be_visible(timeout=15000)
            review = page.locator('#review-form')
            review.locator('[name="editor"]').fill('Fixture reviewer')
            review.get_by_role('button',name='Assign editor').click()
            expect(page.get_by_role('status').last).to_have_text('Editor assigned.')
            review.get_by_role('button',name='Reject clip').click()
            expect(page.locator('.review-block .badge').first).to_have_text('Rejected')
            review.get_by_role('button',name='Approve for delivery').click()
            expect(page.get_by_role('status').last).to_contain_text('Confirm editorial review')
            review.locator('[name="rights"]').check()
            review.get_by_role('button',name='Approve for delivery').click()
            expect(page.locator('.review-block .badge').first).to_have_text('Approved')
            page.get_by_role('link',name='Export center').click()
            expect(page.get_by_role('heading',name='Approved clips')).to_be_visible()
            for kind, label in [('export','MP4'),('srt','SRT'),('vtt','VTT')]:
                with page.expect_download() as download:
                    page.get_by_role('link',name=label).click()
                assert download.value.failure() is None
                assert download.value.path().stat().st_size > 0
            with page.expect_download() as batch:
                page.get_by_role('link', name='Download approved batch ZIP').click()
            assert batch.value.failure() is None
            import zipfile
            with zipfile.ZipFile(batch.value.path()) as package:
                files = set(package.namelist())
                assert 'delivery-manifest.json' in files and any(name.endswith('/clip.mp4') for name in files)
                assert all('input' not in name.lower() for name in files)
            print('Approval-verified MP4/SRT/VTT batch ZIP passed',flush=True)
            print('Rejected preapproval export, attribution, rejection, rights gate and three approved downloads passed',flush=True)
            page.get_by_role('link',name='Review desk').click()
            page.set_viewport_size({'width':390,'height':844})
            expect(page.get_by_role('heading',name='The editing room',exact=True)).to_be_visible()
            expect(page.locator('.ambient-preview')).to_have_count(0)
            expect(page.get_by_role('button', name='Toggle cinematic video backdrop')).to_be_disabled()
            seek_preview(page, 2.2)
            page.evaluate('window.scrollTo(0, 0)')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(args.screenshots/'studio-mobile.png'))
            print('Mobile width and desktop/mobile screenshots passed',flush=True)
            reduced = browser.new_context(reduced_motion='reduce')
            try:
                reduced_page = reduced.new_page()
                reduced_page.goto(url)
                reduced_page.goto(url + '/#desk/' + job)
                reduced_button = reduced_page.get_by_role('button', name='Toggle cinematic video backdrop')
                expect(reduced_button).to_be_disabled()
                expect(reduced_page.locator('.ambient-preview')).to_have_count(0)
            finally:
                reduced.close()
            print('Ambient preview toggle and reduced-motion fallback passed',flush=True)
            assert not errors, errors
        finally:
            browser.close()
            server.shutdown()


if __name__ == '__main__':
    main()
