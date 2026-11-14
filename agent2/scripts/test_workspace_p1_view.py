"""Render archived native HE4 results in an isolated authenticated work area.

Reuses public synthetic CR-043 evidence; does not compute new ciphertext.
"""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(ROOT/'tests_he'),str(ROOT.parent)]
from web_support import WebHarness
from experiments.he_inference.registry_demo import commit

def run(output):
    from playwright.sync_api import sync_playwright,expect
    output.mkdir(parents=True,exist_ok=False);checks=[];errors=[]
    evidence=ROOT.parent/'Agent2_Spec_v2_1/evidence/HE/p1_portal_recheck_20261113'
    with WebHarness() as f,sync_playwright() as p:
        runs={}
        for company in ('C001','C002'):
            scope=f.h.authorizer.authorize('Bearer '+f.h.token,company)
            source=json.loads((evidence/(company+'-source.json')).read_text('utf-8'))
            sid=commit(f.h.store,scope,source,'workspace-p1-'+company)
            result=json.loads((evidence/(company+'-result.json')).read_text('utf-8'))
            job=f.node.jobs.store.create(scope,'workspace-p1-view-'+company,dict(snapshot_id=sid,as_of=result['as_of'],artifact_id=f.pair.env['artifacts'][company]))
            _,data=f.node.jobs.store.get(scope,job);result.update(snapshot_id=sid,run_id=job);data['result']=result;f.node.jobs.store.save(scope,job,data,'completed');runs[company]=job
        browser=p.chromium.launch(channel='chrome',headless=True);page=browser.new_page(viewport=dict(width=1440,height=1050),locale='vi-VN');page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(f.h.portal_url+'/#data');page.locator('#gate-password').fill('Synthetic-Workspace-2026!');page.locator('#gate-confirm-field input').fill('Synthetic-Workspace-2026!');page.locator('#gate-submit').click();expect(page.locator('#intake')).to_be_visible(timeout=15000)
        for company,invoice,cumulative,adjustment in [('C001','10.000.000','12.000.000','-4.000.000'),('C002','30.000.000','36.000.000','-12.000.000')]:
            page.goto(f.h.portal_url+'/agent2/workspace#company='+company+'&run='+runs[company]);expect(page.locator('#ws-cases > button')).to_have_count(8,timeout=20000)
            page.locator('#ws-cases > button').nth(2).click();expect(page.locator('#ws-detail')).to_contain_text(cumulative);expect(page.locator('#ws-detail')).to_contain_text(invoice)
            page.get_by_text('Liên kết giữa các đối tượng',exact=True).click();expect(page.locator('#ws-detail')).to_contain_text('Cùng tài khoản ngân hàng')
            page.screenshot(path=str(output/(company+'-P1-review.png')),full_page=True)
            page.locator('#ws-cases > button').nth(3).click();expect(page.locator('#ws-detail h2')).to_contain_text('Giao dịch P1_T04');expect(page.locator('#ws-detail h2')).to_contain_text(adjustment)
            page.locator('#ws-cases > button').nth(6).click();expect(page.locator('#ws-detail')).to_contain_text('Nhóm thanh toán cùng thời điểm');page.get_by_text('Chứng từ và nguồn đối chiếu',exact=True).click();expect(page.locator('#ws-detail')).to_contain_text('P1_A_P1_T06')
            page.locator('#ws-cases > button').nth(7).click();expect(page.locator('#ws-detail')).to_contain_text('Chưa đủ nguồn để kết luận')
            checks.append(company+': eight archived native results, P1 money, adjustment, peer evidence, bank graph link and missing-history explanation')
        if errors:raise AssertionError(errors)
        browser.close()
    value=dict(status='passed',checks=checks,browser_errors=errors,archived_native_results=True,new_native_computation=False,servers='isolated Portal/node',live_services_changed=False,human_feedback_written=False)
    (output/'report.json').write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(dict(status='passed',checks=len(checks))))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();run(args.output.resolve())
