"""Real-browser CSV/XLSX import and precise source error presentation."""
import argparse
import io
import json
from pathlib import Path
import sys
from openpyxl import load_workbook

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(ROOT.parent)]
from test_portal_auth import PortalHarness
from sme_fraud.tabular_templates import sample


def run(output):
    from playwright.sync_api import sync_playwright,expect
    output.mkdir(parents=True,exist_ok=False);checks=[];errors=[]
    with PortalHarness() as h,sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True);page=browser.new_page(viewport=dict(width=1365,height=950));page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(h.portal_url+'/#data');page.locator('#gate-password').fill('Tabular-Synthetic-2026!');page.locator('#gate-confirm-field input').fill('Tabular-Synthetic-2026!');page.locator('#gate-submit').click();expect(page.locator('#intake')).to_be_visible(timeout=15000)
        page.goto(h.portal_url+'/agent2/');expect(page.locator('#company option')).to_have_count(2)
        with page.expect_download() as downloaded:page.get_by_role('link',name='Mẫu Excel',exact=True).click()
        if not downloaded.value.suggested_filename.endswith('.xlsx'):raise AssertionError('sample download')
        checks.append('download synthetic Excel template through Portal')
        page.locator('#file').set_input_files(dict(name='demo.xlsx',mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer=sample(h.data,'xlsx')))
        page.locator('#validate').click();expect(page.locator('#save-panel')).to_be_visible();expect(page.locator('#save')).to_be_disabled();page.locator('#ack').check();page.locator('#save').click();expect(page.locator('#analysis-panel')).to_be_visible();assert h.count()==1
        checks.append('XLSX upload preview explicit acknowledgement commit creates one immutable snapshot')
        page.locator('#new-import').click();book=load_workbook(io.BytesIO(sample(h.data,'xlsx')));sheet=book['transactions'];names=[c.value for c in sheet[1]];sheet.cell(2,names.index('record_id')+1).value=None;raw=io.BytesIO();book.save(raw)
        page.locator('#file').set_input_files(dict(name='bad.xlsx',mimeType='application/octet-stream',buffer=raw.getvalue()));page.locator('#validate').click();expect(page.locator('#errors')).to_contain_text('Sheet transactions');expect(page.locator('#errors')).to_contain_text('Dòng 2');expect(page.locator('#save-panel')).to_be_hidden();assert h.count()==1
        checks.append('missing transaction ID shows actual Excel sheet and row and cannot save')
        page.screenshot(path=str(output/'excel-error.png'),full_page=True)
        page.locator('#file').set_input_files(dict(name='demo.csv',mimeType='text/csv',buffer=sample(h.data,'csv')));page.locator('#validate').click();expect(page.locator('#save-panel')).to_be_visible();page.locator('#ack').check();page.locator('#save').click();expect(page.locator('#analysis-panel')).to_be_visible();assert h.count()==2
        checks.append('CSV upload normalizes to validated contract without losing source snapshot separation')
        if errors:raise AssertionError(errors)
        browser.close()
    report=dict(status='passed',checks=checks,count=len(checks),browser_errors=errors,synthetic_only=True,live_services_changed=False)
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.output.resolve())
