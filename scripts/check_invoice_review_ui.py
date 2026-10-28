"""Read-only UI check on an existing report over HTTP; no OCR or label writes."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'agent3_tax_compliance'
sys.path.insert(0, str(APP / 'data/local_web/browser_tools'))
from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    report = args.report.resolve()
    if not report.is_relative_to(ROOT) or not report.is_file():
        raise ValueError('Select an existing report inside the workspace')
    output = APP / 'data/invoice_review_ui'; output.mkdir(exist_ok=True)
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = report if self.path == '/review.html' else report.with_name('review.before_ui_fix.html') if self.path == '/old.html' else None
            if path is None or not path.is_file():
                self.send_error(404); return
            content = path.read_bytes()
            self.send_response(200); self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(content))); self.end_headers(); self.wfile.write(content)
        def log_message(self, *args): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    checks = []; errors = []; measurements = {}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe', headless=True)
            context = browser.new_context(viewport={'width': 1440, 'height': 1000})
            page = context.new_page(); page.on('pageerror', lambda error: errors.append(str(error)))
            base = f'http://127.0.0.1:{server.server_port}'
            if report.with_name('review.before_ui_fix.html').exists():
                page.goto(base + '/old.html')
                measurements['before'] = page.evaluate('({nodes:document.querySelectorAll("*").length,images:document.images.length,loaded:[...document.images].filter(i=>i.complete&&i.naturalWidth>0).length})')
            errors.clear()
            started = time.perf_counter(); page.goto(base + '/review.html')
            expect(page.locator('#source-title')).to_contain_text('Trang')
            page.wait_for_function('document.querySelector(".source img")?.naturalWidth>0')
            count = page.locator('#case-select option').count()
            measurements['after'] = page.evaluate('({nodes:document.querySelectorAll("*").length,images:document.images.length,loaded:[...document.images].filter(i=>i.complete&&i.naturalWidth>0).length})')
            measurements['open_seconds'] = time.perf_counter() - started
            assert measurements['after']['images'] == 1
            assert measurements['after']['nodes'] < 800
            checks.append('HTTP preview loads an embedded source image and mounts only one invoice')
            for index in range(count):
                page.locator('#case-select').select_option(str(index))
                page.wait_for_function('document.querySelector(".source img")?.naturalWidth>0')
                assert page.locator('.source img').count() == 1
                assert page.locator('input[type=text]').count() <= 13
                assert page.locator('*').count() < 800
                if page.locator('#page-next').is_enabled():
                    before = page.locator('.source img').get_attribute('src')
                    page.locator('#page-next').click()
                    page.wait_for_function('document.querySelector(".source img")?.naturalWidth>0')
                    assert before != page.locator('.source img').get_attribute('src')
            checks.append(f'All {count} invoices and continuation pages load without growing the DOM')
            page.locator('#case-select').select_option('0')
            row = page.locator('tr[data-field="invoice.number"]')
            row.locator('input[type=text]').fill('UI-TEST-ONLY')
            if count > 1:
                page.locator('#next').click(); page.locator('#previous').click()
            expect(page.locator('tr[data-field="invoice.number"] input[type=text]')).to_have_value('UI-TEST-ONLY')
            expect(page.locator('#save-state')).to_contain_text('đã lưu', timeout=10000)
            page.reload()
            expect(page.locator('tr[data-field="invoice.number"] input[type=text]')).to_have_value('UI-TEST-ONLY')
            checks.append('Draft values survive invoice navigation and refresh in an isolated browser profile')
            assert page.evaluate("formatted('totals.gross','9007199254740993.01')") == '9.007.199.254.740.993,01'
            assert page.evaluate("formatted('items.1.vat_rate','0.08')") == '8%'
            assert page.evaluate("formatted('items.1.vat_rate','0')") == '0%'
            checks.append('Money and VAT display preserve exact decimal strings')
            page.locator('#tab-items').click()
            assert page.locator('input[type=text]').count() <= 6
            page.locator('#tab-issues').click(); assert page.locator('input[type=text]').count() == 0
            page.locator('#tab-info').click()
            page.locator('#zoom-in').click()
            assert page.locator('#image-canvas').evaluate('(n)=>n.style.width') == '125%'
            page.locator('#fit').click()
            checks.append('Tabs and zoom work without rebuilding all invoice editors')
            for width in (1440, 390):
                page.set_viewport_size({'width': width, 'height': 1000})
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                page.screenshot(path=str(output / f'review-{width}.png'), full_page=True)
            checks.append('Desktop and mobile fit the viewport without horizontal page overflow')
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown(); server.server_close(); thread.join(5)
    result = {'result': 'PASS', 'checks': checks, 'measurements': measurements, 'page_errors': errors,
              'scope': 'Existing invoice outputs read only; HTTP, isolated Chrome profile, no OCR or capture mutation'}
    (output / 'result.json').write_bytes((json.dumps(result, indent=2) + '\n').encode())
    print(json.dumps(result, indent=2))


if __name__ == '__main__': main()
