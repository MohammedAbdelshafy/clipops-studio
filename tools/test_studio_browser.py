#!/usr/bin/env python3
"""Exercise the real local desk with the generated, authorized studio fixture pair."""
import argparse
from base64 import b64encode
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import threading
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures', required=True, type=Path)
    parser.add_argument('--screenshots', required=True, type=Path)
    parser.add_argument('--chromium', default=None, help='Optional Chrome/Chromium executable; branded Chrome supports H.264 playback')
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
            part = ctx.request.patch(uploader,data=block,headers={**headers,'Upload-Offset':'0',
                'Content-Type':'application/offset+octet-stream',
                'Upload-Checksum':'sha256 '+b64encode(sha256(block).digest()).decode()})
            assert part.status == 204
            form.locator('[name="video"]').evaluate('async (field,id) => localStorage.setItem(await fileKey(field.files[0]),id)', upload_id)
            page.reload()
            page.get_by_role('button',name='Import project').first.click()
            form = page.locator('#import-form')
            form.locator('[name="video"]').set_input_files(str(source))
            form.locator('[name="rights"]').check()
            form.get_by_role('button',name='Import & process').click()
            expect(page.get_by_role('heading',name='The editing room', exact=True)).to_be_visible(timeout=30000)
            expect(page.locator('[data-clip]').first).to_be_visible(timeout=30000)
            job = page.url.split('/')[-1]
            assert job == upload_id
            clip = page.locator('[data-clip]').first.get_attribute('data-clip')
            print('Browser import and candidate selection passed', flush=True)
            page.get_by_role('button', name='Creative review').click()
            page.get_by_role('button', name='Analyze this clip').click()
            expect(page.get_by_role('heading', name='Verbatim quote bank')).to_be_visible()
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
            page.get_by_label('Reviewed source intervals').fill('3.45, 3.67')
            page.get_by_role('button',name='Save reviewed cuts').click()
            expect(page.get_by_role('status').last).to_have_text('Reviewed cuts saved.')
            page.get_by_role('button',name='Edit punch-ins').click()
            page.get_by_label('Timed punch-ins').fill('4.2, 6.0, 1.08')
            page.get_by_role('button',name='Save punch-ins').click()
            expect(page.get_by_role('status').last).to_have_text('Punch-ins saved.')
            page.get_by_role('button',name='Render batch').click()
            page.get_by_role('button',name='Render selected clips').click()
            expect(page.locator('#dialog')).not_to_be_visible()
            expect(page.locator('.monitor-head')).to_contain_text('Rendered preview',timeout=150000)
            motion = page.get_by_role('button', name='Toggle cinematic video backdrop')
            expect(motion).to_have_attribute('aria-pressed', 'true')
            expect(page.locator('.ambient-preview')).to_have_count(1)
            motion.click()
            expect(motion).to_have_attribute('aria-pressed', 'false')
            expect(page.locator('.ambient-preview')).to_have_count(0)
            motion.click()
            expect(page.locator('.ambient-preview')).to_have_count(1)
            assert abs(float(page.locator('#scrub').get_attribute('max')) - 7.45) < .06
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
