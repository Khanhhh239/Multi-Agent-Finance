"""Real Chrome acceptance against an isolated local_web database.

Requires local tooling in agent3_tax_compliance/data/local_web/browser_tools.
Uses synthetic invoices only; never run against the user's demo/production DB.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
LOCAL=ROOT/'agent3_tax_compliance/data/local_web'
sys.path.insert(0,str(LOCAL/'browser_tools'))
from playwright.sync_api import sync_playwright,expect


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://127.0.0.1:8765')
    parser.add_argument('--real',type=Path,help='Optional public CyberBill pilot PDF; still use isolated database')
    args=parser.parse_args();token=json.loads((LOCAL/'credentials.json').read_text())['token']
    output=LOCAL/'browser_evidence';output.mkdir(parents=True,exist_ok=True)
    findings=[];errors=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
        context=browser.new_context(viewport={'width':1366,'height':900})
        def login(page):
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(args.url+'/review')
            page.locator('#token').fill(token)
            page.locator('#connect-form button[type=submit]').click()
            expect(page.locator('#connection-panel')).to_be_hidden()
        page=context.new_page();page.goto(args.url+'/review')
        page.screenshot(path=str(output/'01_welcome.png'),full_page=True)
        login(page)
        page.locator('#file').set_input_files(str(ROOT/'agent3_tax_compliance/tests/fixtures/ocr/functional_set_v1/syn-02-pdf_text.pdf'))
        page.locator('#upload-submit').click()
        expect(page.locator('#workspace')).to_be_visible(timeout=180000)
        expect(page.locator('#page-image')).to_be_visible()
        page.wait_for_function('document.getElementById("page-image").naturalWidth > 0')
        findings.append('Upload enqueues job; actual local worker automatically reaches review')
        expect(page.locator('.items-table')).to_be_visible()
        page.screenshot(path=str(output/'02_desktop.png'),full_page=True)
        gross=page.get_by_label('Tổng thanh toán',exact=True)
        original=gross.input_value()
        gross.locator('xpath=ancestor::div[contains(@class,"field")][1]').get_by_role('button',name='Xem nguồn').click()
        expect(gross).to_have_value(original)
        expect(page.locator('#overlay rect').first).to_be_visible()
        page.locator('#zoom-in').click();expect(page.locator('#zoom-label')).to_have_text('125%')
        findings.append('Evidence highlights and zoom; inspecting a candidate does not edit input')
        gross.fill('1.234,56');page.locator('#reason').fill('Browser acceptance: exact Vietnamese decimal input')
        page.locator('#save').click();expect(page.locator('#record-summary')).to_contain_text('Bản 2',timeout=15000)
        expect(page.get_by_label('Tổng thanh toán',exact=True)).to_have_value('1.234,56')
        findings.append('Decimal comma/grouping input saves and reloads exactly')
        record_id=page.locator('.record-button.active').get_attribute('data-record')
        second=context.new_page();login(second)
        second.locator('[data-record="'+record_id+'"]').click();expect(second.locator('#workspace')).to_be_visible()
        page.get_by_label('MST người mua',exact=True).fill('1111111111')
        page.locator('#reason').fill('Browser acceptance: preserve conflicting draft')
        second.get_by_label('MST người bán',exact=True).fill('2222222222')
        second.locator('#reason').fill('Browser acceptance: concurrent reviewer')
        second.locator('#save').click();expect(second.locator('#record-summary')).to_contain_text('Bản 3',timeout=15000)
        page.locator('#save').click();expect(page.locator('#conflict-panel')).to_be_visible(timeout=15000)
        expect(page.locator('#conflict-panel')).to_contain_text('1111111111')
        page.get_by_role('button',name='Áp dụng lại trường này').click();page.locator('#save').click()
        expect(page.locator('#record-summary')).to_contain_text('Bản 4',timeout=15000)
        findings.append('Concurrent correction keeps draft and requires explicit reapply before saving')
        page.screenshot(path=str(output/'03_review_saved.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        page.locator('#tab-source').click();expect(page.locator('.source')).to_be_visible();expect(page.locator('.data-pane')).to_be_hidden()
        page.screenshot(path=str(output/'04_mobile_source.png'),full_page=True)
        page.locator('#tab-data').click();expect(page.locator('.data-pane')).to_be_visible()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'),'Mobile body overflows horizontally'
        page.screenshot(path=str(output/'05_mobile_data.png'),full_page=True)
        findings.append('Mobile tabs work; no horizontal body overflow at 390px')
        page.locator('#audit').click();expect(page.locator('#audit-readable')).to_contain_text('Browser acceptance')
        with page.expect_download() as download:page.locator('#export').click()
        data=json.loads(Path(download.value.path()).read_text(encoding='utf-8'))
        assert data['record']['revision']==4 and data['record']['totals']['gross']['value']=='1234.56'
        findings.append('Readable history and JSON export reflect saved revision and exact decimals')
        page.set_viewport_size({'width':1366,'height':900})
        page.get_by_label('Tổng thanh toán',exact=True).locator('xpath=ancestor::div[contains(@class,"field")][1]').get_by_role('button',name='Xem nguồn').click()
        expect(page.locator('#candidates .candidate').first).to_be_visible()
        other=page.locator('.record-button:not(.active)')
        (other.first if other.count() else page.locator('.record-button').first).click()
        expect(page.locator('#candidates .candidate')).to_have_count(0)
        expect(page.locator('#raw-value')).to_contain_text('Chọn “Xem nguồn”')
        findings.append('Opening a saved record clears stale candidates and source text')
        if args.real:
            page.set_viewport_size({'width':1366,'height':900})
            page.locator('#file').set_input_files(str(args.real.resolve()))
            page.locator('#upload-submit').click()
            expect(page.locator('#record-title')).to_have_text('Hóa đơn 3',timeout=240000)
            expect(page.get_by_label('MST người bán',exact=True)).to_have_value('3702790298')
            expect(page.locator('.items-table tbody tr')).to_have_count(1)
            page.screenshot(path=str(output/'06_real_cyberbill_desktop.png'),full_page=True)
            findings.append('Public CyberBill PDF runs through actual OCR worker and opens with correct seller tax ID and one item row')
        assert not errors,errors
        (output/'result.json').write_text(json.dumps({'result':'PASS','checks':findings,'page_errors':errors},indent=2),encoding='utf-8')
        browser.close()
    print(json.dumps({'result':'PASS','checks':len(findings)},indent=2))


if __name__=='__main__':main()
