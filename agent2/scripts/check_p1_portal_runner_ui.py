"""Isolated regression for live runner job capture and saved-run reopening."""
import argparse
import json
from pathlib import Path
import re
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(ROOT/'tests_he'),str(ROOT/'scripts'),str(ROOT.parent)]
from web_support import WebHarness
import p1_portal_workflow as workflow
from check_he4_p1_portal import page_request


def run(output):
    from playwright.sync_api import sync_playwright,expect
    with WebHarness() as h,sync_playwright() as p:
        workflow.URL=h.h.portal_url
        browser=p.chromium.launch(channel='chrome',headless=True)
        page=browser.new_page();page.goto(h.h.portal_url+'/#data')
        page.locator('#gate-password').fill('Synthetic-Runner-2026!')
        page.locator('#gate-confirm-field input').fill('Synthetic-Runner-2026!')
        page.locator('#gate-submit').click();expect(page.locator('#intake')).to_be_visible(timeout=15000)
        snapshot=h.pair.env['queries']['C001'];job=workflow.open_job(page,'C001',snapshot,None)
        if not re.fullmatch(r'herun_[a-f0-9]{32}',job):raise AssertionError('invalid response job')
        path='/agent2/api/v1/companies/C001/he/'
        for _ in range(100):
            state=page_request(page,path+'jobs/'+job)
            if state['status']!=200:raise AssertionError('captured job inaccessible')
            if state['data']['phase']=='completed':break
            page.wait_for_timeout(200)
        else:raise AssertionError('isolated CKKS run did not complete')
        before=page_request(page,path+'runs')['data']['runs']
        if workflow.open_job(page,'C001',snapshot,job)!=job:raise AssertionError('saved run changed')
        expect(page.locator('#rows > article.transaction')).to_have_count(5,timeout=20000)
        expect(page.locator('#result-meta dd').last).to_have_text(job)
        after=page_request(page,path+'runs')['data']['runs']
        if len(before)!=len(after):raise AssertionError('reopen created duplicate job')
        report=dict(status='passed',server_response_job_capture=True,saved_run_reopen=True,no_duplicate_job=True,rows=5,scope='isolated CKKS fixture; not live P1/FHE4 acceptance',credentials_exported=False)
        output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report));browser.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();run(args.output.resolve())
