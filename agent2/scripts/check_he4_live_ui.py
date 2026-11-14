"""User signs into a visible Portal window; no password/token is exported.

After login, test only the two explicitly prepared simulated evaluation sets.
No business conclusion, model activation or role change is performed.
"""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def run(output):
    from playwright.sync_api import sync_playwright,expect
    output.mkdir(parents=True,exist_ok=False);checks=[];errors=[]
    manifest=json.loads((ROOT/'.runtime/he-company-demo/prepared.json').read_bytes())
    companies=manifest['companies']
    if not isinstance(companies,list) or {r['company_id'] for r in companies}!={'C001','C002'}:raise ValueError('expected prepared two-company demo')
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=False);page=browser.new_page(viewport=dict(width=1365,height=950));page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto('http://127.0.0.1:8800/#data');print(json.dumps(dict(stage='waiting_for_user_login',password_read=False)),flush=True)
        try:
            # The user may return in a later turn. Do not destroy their login
            # window merely because an earlier acceptance wait expired.
            page.locator('#intake').wait_for(state='visible',timeout=0)
            print(json.dumps(dict(stage='authenticated')),flush=True)
            for company in companies:
                code=company['company_id'];page.goto('http://127.0.0.1:8800/agent2/encrypted-analysis');page.locator('#company').select_option(code)
                expect(page.locator('#dataset option')).not_to_have_count(0);page.locator('#dataset').select_option(company['evaluation_snapshot_id']);expect(page.locator('#run')).to_be_enabled(timeout=30000);page.locator('#run').click()
                expect(page.locator('#rows .transaction')).to_have_count(5,timeout=30*60*1000);run_id=page.locator('#result-meta dd').last.inner_text()
                expect(page.locator('#result-meta dd').first).to_have_text(code)
                for label in ('Đối chiếu thanh toán','So sánh với lịch sử doanh nghiệp','Quan hệ giữa các đối tượng','Phân tích bất thường'):
                    expect(page.locator('#rows .transaction').first).to_contain_text(label)
                expect(page.locator('#review-cases article')).to_have_count(5,timeout=30000)
                page.reload();expect(page.locator('#rows .transaction')).to_have_count(5,timeout=30000);expect(page.locator('#result-meta dd').last).to_have_text(run_id)
                page.screenshot(path=str(output/(code+'.png')),full_page=True)
                checks.append(dict(company_id=code,row_count=5,reload_same_run=True,review_cases=5));print(json.dumps(dict(stage='completed',company=code)),flush=True)
            if errors:raise AssertionError(errors)
            report=dict(status='passed',authenticated_live_portal=True,actual_fhe=True,simulated_data=True,user_entered_password=True,password_exported=False,checks=checks,human_reviews_created=False,browser_errors=errors)
            (output/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
        finally:browser.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.output.resolve())
