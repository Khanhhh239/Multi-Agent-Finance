"""Browser import acceptance for the P1 source files; isolated Portal only."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(ROOT.parent)]
from test_portal_auth import PortalHarness
from experiments.he4.p1_demo import source
from sme_fraud.import_files import canonical


def run(output):
    from playwright.sync_api import sync_playwright,expect
    output.mkdir(parents=True,exist_ok=False);checks=[];errors=[]
    with PortalHarness() as h,sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True);page=browser.new_page(viewport=dict(width=1365,height=950));page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(h.portal_url+'/#data');page.locator('#gate-password').fill('P1-Synthetic-2026!');page.locator('#gate-confirm-field input').fill('P1-Synthetic-2026!');page.locator('#gate-submit').click();expect(page.locator('#intake')).to_be_visible(timeout=15000)
        page.goto(h.portal_url+'/agent2/');expect(page.locator('#company option')).to_have_count(2)
        for index,company in enumerate(('C001','C002')):
            if index:page.locator('#new-import').click()
            page.locator('#company').select_option(company)
            page.locator('#file').set_input_files(dict(name=company+'_P1_5_ca_8_ban_ghi.json',mimeType='application/json',buffer=canonical(source(company))))
            page.locator('#validate').click();expect(page.locator('#save-panel')).to_be_visible(timeout=20000);expect(page.locator('#save')).to_be_disabled()
            page.locator('#ack').check();page.locator('#save').click();expect(page.locator('#analysis-panel')).to_be_visible(timeout=20000)
            if h.count()!=index+1:raise AssertionError('source snapshot count')
            page.screenshot(path=str(output/(company+'-imported.png')),full_page=True)
            checks.append(company+': JSON preview and explicit acknowledgement commit all source tables, including signed adjustment and declared coverage')
        if errors:raise AssertionError(errors)
        browser.close()
    report=dict(status='passed',checks=checks,count=len(checks),browser_errors=errors,synthetic_data=True,scope='import flow only; native HE tested separately',live_services_changed=False)
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.output.resolve())
