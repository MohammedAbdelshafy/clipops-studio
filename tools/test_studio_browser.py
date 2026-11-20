#!/usr/bin/env python3
"""Exercise the real local desk with the generated, authorized studio fixture pair."""
import argparse
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
    # Execute as a callable through the locator instead of altering the desk's CSP.
    assert page.locator('#video').evaluate('''async (video, seconds) => {
        const deadline = performance.now() + 10000;
        video.currentTime = seconds;
        while (performance.now() < deadline) {
            if (video.readyState >= 2 && Math.abs(video.currentTime - seconds) < .12) return true;
            await new Promise(resolve => setTimeout(resolve, 50));
        }
        return false;
    }''', seconds)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures', required=True, type=Path)
    parser.add_argument('--screenshots', required=True, type=Path)
    parser.add_argument('--chromium', default='/usr/bin/chromium')
    args = parser.parse_args()
    args.screenshots.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='clipops-desk-test-') as tmp, DeskServer(0, Path(tmp), pilot) as server, sync_playwright() as playwright:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        browser = playwright.chromium.launch(executable_path=args.chromium, headless=True, args=['--disable-dev-shm-usage'])
        try:
            url = f'http://127.0.0.1:{server.server_port}'
            ctx = browser.new_context(viewport={'width':1390,'height':1000}, accept_downloads=True)
            ctx.route('**/*', lambda route: route.continue_() if urlparse(route.request.url).netloc == f'127.0.0.1:{server.server_port}' else route.abort())
            page = ctx.new_page()
            errors = []
            page.on('pageerror', lambda err: errors.append(str(err)))
            page.goto(url)
            page.get_by_role('button',name='Import project').first.click()
            form = page.locator('#import-form')
            form.locator('[name="name"]').fill('The editing room')
            form.locator('[name="video"]').set_input_files(str(args.fixtures/'studio.mp4'))
            form.locator('[name="transcript"]').set_input_files(str(args.fixtures/'studio.json'))
            form.locator('[name="count"]').fill('0')
            form.locator('[name="rights"]').check()
            form.get_by_role('button',name='Import & process').click()
            expect(page.get_by_role('heading',name='The editing room', exact=True)).to_be_visible(timeout=30000)
            expect(page.locator('[data-clip]').first).to_be_visible(timeout=30000)
            job = page.url.split('/')[-1]
            clip = page.locator('[data-clip]').first.get_attribute('data-clip')
            print('Browser import and candidate selection passed', flush=True)
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
            page.get_by_role('button',name='Render batch').click()
            page.get_by_role('button',name='Render selected clips').click()
            expect(page.locator('#dialog')).not_to_be_visible()
            expect(page.locator('.monitor-head')).to_contain_text('Rendered preview',timeout=150000)
            assert abs(float(page.locator('#scrub').get_attribute('max')) - 7.45) < .06
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
            print('Rejected preapproval export, attribution, rejection, rights gate and three approved downloads passed',flush=True)
            page.get_by_role('link',name='Review desk').click()
            page.set_viewport_size({'width':390,'height':844})
            expect(page.get_by_role('heading',name='The editing room',exact=True)).to_be_visible()
            seek_preview(page, 2.2)
            page.evaluate('window.scrollTo(0, 0)')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(args.screenshots/'studio-mobile.png'))
            print('Mobile width and desktop/mobile screenshots passed',flush=True)
            assert not errors, errors
        finally:
            browser.close()
            server.shutdown()


if __name__ == '__main__':
    main()
