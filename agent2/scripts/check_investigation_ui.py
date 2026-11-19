"""Real isolated Portal, saved pipeline results and persistent reviews; no live state edits."""
import argparse
import json
from pathlib import Path
import sys
import threading
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(ROOT/'tests_he'),str(ROOT.parent)]
from test_portal_auth import PortalHarness,portal
import test_release_shadow_plan as support
from sme_fraud.pipeline_release import ReleaseService
from sme_fraud.pipeline_release_store import ReleaseStore
from sme_fraud.case_queue_store import CaseQueueStore
from sme_fraud.analysis_resources import AnalysisResources
from sme_fraud.review_server import make_server

def run(output):
    from playwright.sync_api import sync_playwright,expect
    output.mkdir(parents=True,exist_ok=False);checks=[];errors=[];report={}
    support.ShadowPlanTests.setUpClass()
    try:
        f=support.ShadowPlanTests.fixture
        with PortalHarness() as h,sync_playwright() as p:
            svc=ReleaseService(ReleaseStore(h.root/'releases.db',b'w'*32),f.snapshots,AnalysisResources(f.models.path),CaseQueueStore(h.root/'cases.db'))
            results={}
            for company in ('C001','C002'):
                scope=f.company_ctx[company]['scope'];sid=f.company_ctx[company]['manifests']['sealed_future_test']['snapshot_id']
                reg=svc.register_plan(scope,support.ShadowPlanTests.packages[company],'register-investigation-'+company)
                b=svc.prepare(scope,sid,'Investigation UI '+company,'prepare-investigation-'+company,plan_id=reg['plan_id'])
                g=svc.qualify(scope,b['bundle_id'],'staging');assert g['technical_ready']
                a=svc.approve(scope,b['bundle_id'],g['gate_id'],'staging','Synthetic isolated investigation UI acceptance')
                svc.switch(scope,dict(bundle_id=b['bundle_id'],gate_id=g['gate_id'],approval_id=a['approval_id'],lane='staging',expected_revision=0,reason='Synthetic workflow acceptance',action='activate'),'activate-investigation-'+company)
                results[company]=svc.run(scope,'investigation-ui-'+company,'staging',sid,svc._snapshot(scope,sid)[1]['source']['as_of'])
            h.agent.shutdown();h.agent.server_close();h.agent=make_server(0,h.authorizer,f.snapshots,svc.resources,case_queue_store=svc.case_queue,release_service=svc)
            h.agent.daemon_threads=False
            portal.CFG['agents']['agent2']['port']=h.agent.server_port;t=threading.Thread(target=h.agent.serve_forever,daemon=True);t.start();h.threads.append(t)
            browser=p.chromium.launch(channel='chrome',headless=True);page=browser.new_page(viewport=dict(width=1440,height=1000),locale='vi-VN')
            page.on('pageerror',lambda e:errors.append(str(e)));page.add_init_script('sessionStorage.setItem("kt-session",'+json.dumps(h.token)+');')
            try:
                page.goto(h.portal_url+'/agent2/#company=C001')
                expect(page.locator('#rows .tx-row')).not_to_have_count(0,timeout=30000)
                first=page.locator('#rows .tx-row').first;tid=first.get_attribute('data-transaction');rid=first.get_attribute('data-review')
                status,queue=h.request(h.url('pipeline-workspace/investigation'));assert status==200,queue
                expected=next(r for r in queue['rows'] if r['review_id']==rid and r['transaction_id']==tid)
                assert expected['score'] is not None
                first.click();expect(page.locator('#preview')).to_contain_text('không phải xác suất gian lận')
                page.screenshot(path=str(output/'01-queue.png'),full_page=True)
                checks.append('Queue reads saved real pipeline scores, sorted priorities, statuses and source-bound explanations')
                before_count=len(svc.store.list(f.company_ctx['C001']['scope'],'observation'))
                page.locator('#open-investigation').click();expect(page.locator('#investigation')).to_be_visible(timeout=20000)
                expect(page.locator('#detail-title')).to_contain_text(tid);expect(page.locator('#graph .node')).not_to_have_count(0)
                initial=page.locator('#graph .node').count()
                visible=set(page.locator('#graph .node').evaluate_all('(nodes)=>nodes.map(n=>n.dataset.node)'))
                status,dto=h.request(h.url('pipeline-workspace/runs/'+expected['run_id']+'/investigation/'+tid+'/reviews/'+rid));assert status==200,dto
                expansion=next((e['source'] if e['source'] in visible else e['target'] for e in dto['graph']['edges'] if (e['source'] in visible)!=(e['target'] in visible)),None)
                assert expansion, 'Graph fixture must contain a genuine second hop'
                page.locator('#graph [data-node="'+expansion+'"]').click(force=True)
                assert page.locator('#graph .node').count()>initial
                page.locator('#expand-node').click()
                expect(page.locator('#graph .edge')).not_to_have_count(0)
                page.locator('#graph .edge').first.focus()
                page.locator('#graph .edge').first.press('Enter')
                expect(page.locator('#relation-evidence')).to_contain_text('Căn cứ của liên kết')
                expect(page.locator('#relation-evidence')).to_contain_text('Chưa xác minh chứng từ gốc')
                assert len(svc.store.list(f.company_ctx['C001']['scope'],'observation'))==before_count
                page.screenshot(path=str(output/'02-investigation.png'),full_page=True)
                checks.append('Node expansion and selected-edge evidence work without new scoring/fitting; graph uses frozen source identities')
                page.locator('[data-tab="related"]').click();expect(page.locator('#related')).to_be_visible()
                page.locator('[data-tab="evidence"]').click();expect(page.locator('#evidence details')).not_to_have_count(0)
                page.locator('[data-tab="explanation"]').click();expect(page.locator('#explanation')).to_contain_text('Điểm luật trước phối hợp')
                checks.append('Related records, source evidence, saved score components and model/source trace are reachable')
                page.locator('#start').click();expect(page.locator('#save')).to_be_enabled(timeout=15000)
                page.reload();expect(page.locator('#investigation')).to_be_visible(timeout=30000)
                expect(page.locator('#review-status')).to_have_text('Đang kiểm tra')
                expect(page.locator('#save')).to_be_enabled(timeout=15000)
                page.locator('#file').set_input_files(dict(name='supporting-evidence.pdf',mimeType='application/pdf',buffer=b'%PDF-1.4\nIndependent review evidence'))
                page.locator('#attach').click();expect(page.locator('#attachment-status')).to_contain_text('Đã lưu tệp',timeout=15000)
                expect(page.locator('#save')).to_be_enabled()
                page.locator('#outcome').select_option('inconclusive');page.locator('#notes').fill('Đã đối chiếu bản ghi nguồn; còn thiếu chứng từ gốc để xác nhận.')
                page.locator('#action').fill('Yêu cầu kế toán cung cấp hóa đơn gốc và xác nhận người nhận tiền.')
                page.locator('#missing').fill('Hóa đơn gốc và phê duyệt thanh toán.')
                def lose_response(route):route.fetch();route.abort()
                page.route('**/investigation/*/reviews/*/save',lose_response,times=1)
                page.locator('#save').click();expect(page.locator('#save-status')).to_contain_text('Mất phản hồi',timeout=15000)
                page.locator('#save').click();expect(page.locator('#save-status')).to_contain_text('phiên bản 1',timeout=15000)
                page.reload();expect(page.locator('#investigation')).to_be_visible(timeout=30000)
                expect(page.locator('#notes')).to_have_value('Đã đối chiếu bản ghi nguồn; còn thiếu chứng từ gốc để xác nhận.')
                expect(page.locator('#review-status')).to_have_text('Cần bổ sung bằng chứng')
                page.locator('[data-tab="history"]').click();expect(page.locator('#history')).to_contain_text('Kết quả phiên bản 1')
                with page.expect_download() as dl:page.locator('#attachment-list button').first.click()
                dl.value.save_as(str(output/'downloaded-evidence.pdf'));assert (output/'downloaded-evidence.pdf').read_bytes()==b'%PDF-1.4\nIndependent review evidence'
                checks.append('Start survives reload; attachment round-trip, conclusion, audit and response-loss retry persist exactly one review revision')
                page.locator('#back').click();expect(page.locator('#queue')).to_be_visible(timeout=15000)
                page.locator('#status').select_option('waiting_evidence');expect(page.locator('#rows')).to_contain_text(tid)
                page.locator('#status').select_option('');page.locator('#rows .tx-row').first.click();page.locator('#open-investigation').click();expect(page.locator('#investigation')).to_be_visible()
                page.locator('#notes').fill('Nội dung đang soạn chưa lưu');page.once('dialog',lambda d:d.dismiss());page.locator('#back').click()
                expect(page.locator('#notes')).to_have_value('Nội dung đang soạn chưa lưu')
                page.once('dialog',lambda d:d.accept());page.locator('#back').click();expect(page.locator('#queue')).to_be_visible(timeout=15000)
                page.locator('#company').select_option('C002');expect(page.locator('#rows .tx-row')).not_to_have_count(0,timeout=20000)
                assert 'C001_TEST' not in page.locator('#rows').inner_text(), 'Rows from previous company remained visible'
                page.reload();expect(page.locator('#company')).to_have_value('C002',timeout=20000)
                checks.append('Filters, unsaved-edit guard and company reload preserve isolation')
                path=h.url('pipeline-workspace/runs/'+expected['run_id']+'/investigation/'+tid+'/reviews/'+rid,'C002')
                assert h.request(path)[0]==404
                assert h.request(h.url('pipeline-workspace/investigation'),token=False)[0]==401
                page.set_viewport_size(dict(width=390,height=844));assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
                page.screenshot(path=str(output/'03-mobile.png'),full_page=True)
                assert not errors,errors
                checks.append('Portal denies unauthenticated and cross-company reads; mobile 390px fits; no JavaScript errors')
                report=dict(status='pass',checks=checks,synthetic_data=True,actual_fhe=False,live_state_changed=False)
            except Exception as e:
                report=dict(status='fail',checks=checks,error=str(e),browser_errors=errors);page.screenshot(path=str(output/'failure.png'),full_page=True);raise
            finally:
                (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');browser.close()
    finally:support.ShadowPlanTests.tearDownClass()
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    print(json.dumps(run(parser.parse_args().output.resolve()),ensure_ascii=True,indent=2))
