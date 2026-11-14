"""Isolated Portal trial using archived native outputs, without new HE compute."""
import argparse,json,sqlite3,sys
from contextlib import closing
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(ROOT/'tests_he'),str(ROOT.parent)]
from web_support import WebHarness
from comparison_support import seed_run


def run(output):
    from playwright.sync_api import sync_playwright,expect
    output.mkdir(parents=True,exist_ok=False);checks=[];errors=[]
    with WebHarness() as f,sync_playwright() as p:
        runs={c:seed_run(f,c,'selection-browser-'+c) for c in ('C001','C002')}
        browser=p.chromium.launch(channel='chrome',headless=True);page=browser.new_page(viewport=dict(width=1440,height=1050),locale='vi-VN');page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(f.h.portal_url+'/#data');page.locator('#gate-password').fill('Synthetic-Workspace-2026!');page.locator('#gate-confirm-field input').fill('Synthetic-Workspace-2026!');page.locator('#gate-submit').click();expect(page.locator('#intake')).to_be_visible(timeout=15000)
        for company in ('C001','C002'):
            page.goto(f.h.portal_url+'/agent2/workspace#company='+company+'&run='+runs[company]);expect(page.locator('#ws-cases > button')).to_have_count(8,timeout=20000);expect(page.locator('#ws-compare')).to_be_enabled(timeout=20000)
            expect(page.locator('#ws-detail')).to_contain_text('Chọn một giao dịch để rà')
            if company=='C001':
                intercepted=[]
                def lost_reply(route):
                    if route.request.method!='POST':route.continue_();return
                    intercepted.append(route.request.post_data_json)
                    if len(intercepted)==1:route.fetch();route.abort('failed')
                    else:route.continue_()
                page.route('**/workspace/runs/*/comparison',lost_reply);page.locator('#ws-compare').click();expect(page.locator('#ws-compare')).to_be_enabled();page.locator('#ws-compare').click()
            else:page.locator('#ws-compare').click()
            expect(page.locator('#ws-comparison')).to_contain_text('ML thêm 2 giao dịch; thay 0 giao dịch',timeout=15000);expect(page.locator('#ws-compare')).to_be_hidden()
            if company=='C001':
                page.unroute('**/workspace/runs/*/comparison',lost_reply)
                if len(intercepted)!=2 or intercepted[0]!=intercepted[1]:raise AssertionError('plan retry body changed')
                with closing(sqlite3.connect(f.node.jobs.store.path.with_name('comparisons.sqlite3'))) as conn:
                    if conn.execute('SELECT count(*) FROM plans WHERE run_id=?',(runs[company],)).fetchone()[0]!=1:raise AssertionError('duplicate plan')
                checks.append('lost plan response retries same protocol and stores one immutable plan')
            expect(page.locator('#ws-comparison')).to_contain_text('Chỉ luật P1 · 3/5 giao dịch');expect(page.locator('#ws-comparison')).to_contain_text('Luật P1 + ML · 5/5 giao dịch');expect(page.locator('#ws-comparison')).to_contain_text('P1 không áp dụng cho loại giao dịch này');expect(page.locator('#ws-comparison')).to_contain_text('Chưa đánh giá')
            with page.expect_download() as download:page.locator('#ws-comparison-export').click()
            path=output/(company+'-comparison-before.json');download.value.save_as(path);before=json.loads(path.read_text('utf-8'))
            checks.append(company+': same-run budget cap, baseline underfill, ML additions and unknown metrics shown')
            page.locator('#ws-comparison details[open]').first.get_by_role('button',name='P1_T04',exact=False).click();expect(page.locator('#ws-detail h2')).to_contain_text('P1_T04');page.locator('#ws-start').click();expect(page.locator('#ws-save')).to_be_enabled();page.locator('#ws-outcome').select_option('inconclusive');page.locator('#ws-explanation').fill('Kiểm thử UI mô phỏng: chưa đối chiếu chứng từ gốc.');page.locator('#ws-action').fill('Đề nghị kế toán bổ sung căn cứ điều chỉnh.');page.locator('#ws-missing').fill('Chứng từ điều chỉnh gốc.');page.locator('#ws-save').click();expect(page.locator('#ws-detail')).to_contain_text('Đã lưu kết quả phiên bản 1',timeout=10000)
            page.locator('#ws-comparison-refresh').click();page.reload();expect(page.locator('#ws-comparison')).to_contain_text('ML thêm 2 giao dịch; thay 0 giao dịch',timeout=20000)
            with page.expect_download() as download:page.locator('#ws-comparison-export').click()
            path=output/(company+'-comparison-after.json');download.value.save_as(path);after=json.loads(path.read_text('utf-8'))
            if before['plan_id']!=after['plan_id'] or before['plan_sha256']!=after['plan_sha256']:raise AssertionError('review/reload changed plan')
            if after['combined']['metrics']['reviewed']!=1 or after['combined']['metrics']['inconclusive']!=1 or after['combined']['metrics']['declared_precision_resolved'] is not None:raise AssertionError('inconclusive treated as false/zero-precision')
            checks.append(company+': supplementary candidate opens real review, server feedback updates metrics while plan survives reload')
            page.screenshot(path=str(output/(company+'-comparison.png')),full_page=True)
        if errors:raise AssertionError(errors)
        page.locator('#ws-company').select_option('C001');expect(page.locator('#ws-home')).to_be_visible(timeout=20000);expect(page.locator('#ws-comparison')).to_be_empty();checks.append('company switch clears prior comparison')
        browser.close()
    report=dict(status='passed',checks=checks,count=len(checks),browser_errors=errors,servers='isolated real Portal/node/snapshot/review stores',archived_native_results=True,new_native_computation=False,live_services_changed=False,human_business_feedback=False)
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(dict(status='passed',checks=len(checks))))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();run(args.output.resolve())
