"""Four-step workspace acceptance in real Chrome; isolated synthetic DB, no local user data."""
import json
import socket
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'agent3_tax_compliance'
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / 'tests/e2e_v1'))
sys.path.insert(0, str(APP / 'data/local_web/browser_tools'))
import uvicorn
import test_compliance as fixtures
from playwright.sync_api import sync_playwright, expect
from src.app import create_app


def main():
    fixture = fixtures.ComplianceTests('test_reviewed_capture_real_zen_template_snapshot_replay')
    fixture.setUp()
    fixture.approved()
    output = APP / 'data/workflow_ui/browser'
    output.mkdir(parents=True, exist_ok=True)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(fixture.settings), host='127.0.0.1', port=port, log_level='error'))
    thread = threading.Thread(target=server.run, daemon=True)
    checks, errors = [], []
    try:
        with fixture.patches(), sync_playwright() as pw:
            thread.start()
            for _ in range(100):
                if server.started:
                    break
                time.sleep(.05)
            if not server.started:
                raise RuntimeError('Test server did not start')
            browser = pw.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe', headless=True)
            page = browser.new_page(viewport={'width':1440, 'height':1000})
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{port}/review')
            page.locator('#token').fill(fixture.headers['Authorization'].split(' ',1)[1])
            page.locator('#payer').fill(fixture.payer)
            page.get_by_role('button',name='Kết nối',exact=True).click()
            page.locator('[data-record="'+fixture.record_id+'"]').click()
            expect(page.locator('#fields input').first).to_be_visible()
            expect(page.locator('#page-image')).to_be_visible(timeout=15000)
            page.wait_for_function('document.getElementById("page-image").naturalWidth > 0')
            assert page.locator('#workflow-nav button').count() == 4
            assert page.locator('#workflow-nav [aria-current=step]').count() == 1
            expect(page.locator('#step-data')).to_have_attribute('aria-current','step')
            page.screenshot(path=str(output/'01_data_desktop.png'),full_page=True)
            checks.append('Four accessible steps; data/source default; one current step')
            for step in ('business','tax','explanation','data'):
                page.locator('#step-'+step).click()
                expect(page.locator('#workflow-'+step)).to_be_visible()
                assert page.locator('#workflow-nav [aria-current=step]').count() == 1
            expect(page.locator('#explanation-detail')).to_be_hidden()
            page.locator('#step-explanation').focus()
            page.keyboard.press('Enter')
            expect(page.locator('#explanation-empty')).to_be_visible()
            page.locator('#explanation-empty button').click()
            expect(page.locator('#workflow-tax')).to_be_visible()
            saved=page.request.get(f'http://127.0.0.1:{port}/v1/records/{fixture.record_id}',params={'taxpayer_id':fixture.payer},headers=fixture.headers)
            assert saved.status==200 and saved.json()['record']['revision']==2
            checks.append('Keyboard selects step; empty explanation routes to tax; navigation preserves saved revision')
            page.locator('#record-search').fill('not-in-this-loaded-list')
            expect(page.locator('#record-search-empty')).to_be_visible()
            expect(page.locator('[data-record="'+fixture.record_id+'"]').first).to_be_hidden()
            page.locator('#record-search').fill('')
            expect(page.locator('[data-record="'+fixture.record_id+'"]')).to_be_visible()
            page.locator('#upload-drawer > summary').focus()
            page.keyboard.press('Enter')
            expect(page.locator('#file')).to_be_visible()
            page.locator('#upload-drawer > summary').click()
            checks.append('Search filters loaded records without deleting them; compact upload opens by keyboard/native details')
            page.locator('#step-data').click()
            expand=page.locator('[data-item-toggle]').first
            if expand.count():
                expand.click()
                expect(expand).to_have_attribute('aria-expanded','true')
                expect(page.locator('.item-expanded .field-head').first).to_be_visible()
                expand.click()
                expect(expand).to_have_attribute('aria-expanded','false')
            checks.append('Line details expand/collapse without replacing editors or item IDs')
            field=page.get_by_label('MST người mua',exact=True)
            field.fill('1111111111')
            page.locator('#reason').fill('Workflow test: retained draft across steps')
            page.locator('#step-business').click()
            page.locator('#step-tax').click()
            page.locator('#evaluate-record').click()
            expect(page.locator('#status')).to_contain_text('Lưu hoặc bỏ bản nháp')
            page.locator('#step-data').click()
            expect(field).to_have_value('1111111111')
            expect(page.locator('#reason')).to_have_value('Workflow test: retained draft across steps')
            checks.append('Unsaved correction survives step changes and prevents tax evaluation')
            # All steps and both viewer modes must fit tablet and mobile without page overflow.
            for width in (1024,768,390):
                page.set_viewport_size({'width':width,'height':844})
                for step in ('data','business','tax','explanation'):
                    page.locator('#step-'+step).click()
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1'),(width,step)
                    expect(page.locator('#workflow-'+step)).to_be_visible()
                if width <= 920:
                    page.locator('#tab-source').click()
                    expect(page.locator('.source')).to_be_visible()
                    page.locator('#step-data').click()
                    expect(page.locator('.data-pane')).to_be_visible()
                page.screenshot(path=str(output/f'02_mobile_{width}.png'),full_page=True)
            checks.append('1024/768/390px: all steps fit, source/data tabs and action controls remain reachable')
            page.set_viewport_size({'width':1440,'height':1000})
            page.locator('#step-business').click()
            page.screenshot(path=str(output/'03_business_desktop.png'),full_page=True)
            # The audit button must reveal its panel even when invoked from another step.
            page.locator('#audit').click()
            expect(page.locator('#workflow-data')).to_be_visible()
            expect(page.locator('#audit-panel')).to_be_visible(timeout=15000)
            checks.append('Audit action routes back to data; existing history remains accessible')
            assert not errors,errors
            browser.close()
    finally:
        server.should_exit=True
        if thread.is_alive():
            thread.join(10)
        fixture.doCleanups()
    result={'result':'PASS','checks':checks,'page_errors':errors,'scope':'Real Chrome/HTTP; synthetic records; no OCR, Qwen or tax accuracy claim.'}
    (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True,indent=2))


if __name__=='__main__':
    main()
