"""Real isolated Portal: bundle run -> accountant review -> persisted JSON/CSV."""
import argparse
from pathlib import Path
import sys
import threading
import json
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(ROOT/'tests_he'),str(ROOT.parent)]
from test_portal_auth import PortalHarness,portal
import test_release_shadow_plan as support
from sme_fraud.pipeline_release import ReleaseService
from sme_fraud.pipeline_release_store import ReleaseStore
from sme_fraud.case_queue_store import CaseQueueStore
from sme_fraud.analysis_resources import AnalysisResources
from sme_fraud.review_server import make_server
from sme_fraud.import_files import canonical,digest


def run(output):
    from playwright.sync_api import sync_playwright,expect
    output.mkdir(parents=True,exist_ok=False);checks=[];errors=[];report={}
    support.ShadowPlanTests.setUpClass()
    try:
        f=support.ShadowPlanTests.fixture
        with PortalHarness() as h,sync_playwright() as p:
            svc=ReleaseService(ReleaseStore(h.root/'releases.db',b'w'*32),f.snapshots,AnalysisResources(f.models.path),CaseQueueStore(h.root/'cases.db'))
            runs={};datasets={};bundles={}
            for company in ('C001','C002'):
                scope=f.company_ctx[company]['scope'];sid=f.company_ctx[company]['manifests']['sealed_future_test']['snapshot_id']
                package=support.ShadowPlanTests.packages[company];reg=svc.register_plan(scope,package,'register-review-'+company)
                b=svc.prepare(scope,sid,'Business review '+company,'prepare-review-'+company,plan_id=reg['plan_id'])
                g=svc.qualify(scope,b['bundle_id'],'staging');assert g['technical_ready']
                a=svc.approve(scope,b['bundle_id'],g['gate_id'],'staging','Synthetic business review flow approval')
                svc.switch(scope,dict(bundle_id=b['bundle_id'],gate_id=g['gate_id'],approval_id=a['approval_id'],lane='staging',expected_revision=0,reason='Synthetic workflow acceptance',action='activate'),'activate-review-'+company)
                datasets[company]=sid;bundles[company]=b['bundle_id']
            h.agent.shutdown();h.agent.server_close();h.agent=make_server(0,h.authorizer,f.snapshots,svc.resources,case_queue_store=svc.case_queue,release_service=svc)
            portal.CFG['agents']['agent2']['port']=h.agent.server_port;t=threading.Thread(target=h.agent.serve_forever,daemon=True);t.start();h.threads.append(t)
            browser=p.chromium.launch(channel='chrome',headless=True);page=browser.new_page(viewport=dict(width=1440,height=1050),locale='vi-VN')
            page.on('pageerror',lambda e:errors.append(str(e)));page.add_init_script('sessionStorage.setItem("kt-session",'+json.dumps(h.token)+');')
            try:
                for company in ('C001','C002'):
                    page.goto(h.portal_url+'/agent2/#company='+company)
                    expect(page.locator('#bw-company')).to_have_value(company,timeout=30000);expect(page.locator('#bw-snapshot')).to_be_enabled(timeout=30000)
                    page.locator('#bw-snapshot').select_option(datasets[company])
                    if company=='C001':
                        # Lose the response only AFTER backend commit, then retry
                        # from the same operator control and persistent request ID.
                        def lose_response(route):route.fetch();route.abort()
                        page.route('**/pipeline-workspace/runs',lose_response)
                        page.locator('#bw-analyze').click();expect(page.locator('#bw-notice')).to_contain_text('Mất kết nối',timeout=30000)
                        page.unroute('**/pipeline-workspace/runs',lose_response)
                        expect(page.locator('#bw-analyze')).to_be_enabled(timeout=10000)
                    page.locator('#bw-analyze').click();expect(page.locator('#bw-report')).to_be_visible(timeout=30000)
                    rid=page.locator('#bw-run').input_value();assert rid
                    expect(page.locator('#bw-baseline')).to_contain_text('35 luật')
                    assert 'Giữ cảnh báo P1' not in page.locator('body').inner_text()
                    status,r=h.request(h.url('pipeline-workspace/runs/'+rid,company));assert status==200,r;runs[company]=r
                    assert r['snapshot_id']==datasets[company] and r['bundle_id']==bundles[company]
                    scope=f.company_ctx[company]['scope'];observations=svc.store.list(scope,'observation');assert len(observations)==1
                    assert svc.case_queue.get_queue_state(scope,mode='active')['items']==[]
                    checks.append(dict(id=company+'-OPERATOR-RUN',status='pass',observed='Operator selects immutable snapshot and executes approved bundle through scoring, coalescing, shadow queue, review packet; response-loss retry creates one logical run'))
                    expect(page.locator('#bw-run')).to_have_value(rid);expect(page.locator('#bw-cases button')).to_have_count(3)
                    for key in ('snapshot_id','run_id','bundle_id'):expect(page.locator('#bw-meta')).to_contain_text(runs[company][key])
                    assert 'ecod' not in page.locator('body').inner_text().lower()
                    page.locator('#bw-cases button').first.click();expect(page.locator('#bw-detail')).to_be_visible()
                    page.locator('#bw-start').click();expect(page.locator('#bw-save')).to_be_enabled(timeout=10000)
                    page.locator('#bw-outcome').select_option('inconclusive');page.locator('#bw-explanation').fill('Nguồn mô phỏng; đã xem bản ghi, chưa có chứng từ gốc.')
                    page.locator('#bw-action').fill('Yêu cầu kế toán bổ sung bản gốc để đối chiếu.');page.locator('#bw-missing').fill('Thiếu hóa đơn gốc và xác nhận ngân hàng.')
                    if company=='C001':
                        attachment=output/'synthetic-only.pdf';attachment.write_bytes(b'%PDF-1.4 synthetic UI attachment, not an original invoice')
                        page.locator('#bw-upload').set_input_files(attachment)
                        expect(page.locator('#bw-detail')).to_contain_text('synthetic-only.pdf',timeout=10000)
                    page.locator('#bw-save').click();expect(page.locator('#bw-detail')).to_contain_text('phiên bản 1',timeout=20000)
                    checks.append(dict(id=company+'-REVIEW',status='pass',observed='Accountant/director use business DTO, inspect source, start server timer, save inconclusive; no algorithm fields'))
                    expect(page.locator('#bw-task-create')).to_be_enabled(timeout=10000)
                    page.locator('#bw-task-title').fill('Bổ sung chứng từ nguồn '+company)
                    page.locator('#bw-task-todo').fill('Bổ sung hóa đơn gốc và xác nhận thanh toán.')
                    page.locator('#bw-task-reason').fill('Nguồn mô phỏng, chưa đủ căn cứ đối chiếu.')
                    page.locator('#bw-task-assignee').select_option('ke_toan_cong_no')
                    page.locator('#bw-task-due').fill('2026-12-10T17:00')
                    if company=='C001':
                        page.route('**/reviews/*/tasks',lose_response)
                        page.locator('#bw-task-create').click()
                        expect(page.locator('#bw-detail')).to_contain_text('Mất kết nối',timeout=15000)
                        page.unroute('**/reviews/*/tasks',lose_response)
                    page.locator('#bw-task-create').click()
                    expect(page.locator('#bw-task-list [data-task]')).to_have_count(1,timeout=15000)
                    checks.append(dict(id=company+'-CASE-TASK',status='pass',observed='Create department-assigned task with explicit due date from admitted case; C001 response-loss retry retains one task and immutable snapshot/run/bundle binding'))
                    page.reload();expect(page.locator('#bw-report')).to_be_visible(timeout=30000);page.locator('#bw-cases button').first.click()
                    expect(page.locator('#bw-outcome')).to_have_value('inconclusive');expect(page.locator('#bw-explanation')).to_have_value('Nguồn mô phỏng; đã xem bản ghi, chưa có chứng từ gốc.')
                    expect(page.locator('#bw-missing')).to_have_value('Thiếu hóa đơn gốc và xác nhận ngân hàng.')
                    expect(page.locator('#bw-task-list [data-task]')).to_have_count(1,timeout=15000)
                    with page.expect_download() as dl:page.locator('#bw-json').click()
                    dest=output/(company+'-business-report.json');dl.value.save_as(str(dest));saved=json.loads(dest.read_bytes())
                    assert all(saved[k]==runs[company][k] for k in ('snapshot_id','run_id','bundle_id'))
                    assert saved['summary']['reviewed_cases']==1 and saved['summary']['verified_fraud_precision'] is None and saved['training_eligible'] is False
                    task=saved['cases'][0]['tasks'][0]
                    assert all(task['source_binding'][k]==saved[k] for k in ('snapshot_id','run_id','bundle_id'))
                    assert task['generates_ml_label'] is False and task['mutates_case_status'] is False
                    # Export exact server bytes: JSON parse/stringify in JS can
                    # turn Python 0.0 into 0 and invalidate the report checksum.
                    checksum=saved.pop('report_sha256');assert checksum==digest(canonical(saved))
                    with page.expect_download() as dl:page.locator('#bw-csv').click()
                    dl.value.save_as(str(output/(company+'-business-report.csv')))
                    checks.append(dict(id=company+'-RELOAD-EXPORT',status='pass',observed='Reload restores feedback and source; JSON/CSV bind same snapshot/run/bundle; metrics remain declared, not verified fraud accuracy'))
                page.screenshot(path=str(output/'desktop.png'),full_page=True);page.set_viewport_size(dict(width=390,height=844))
                assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+2')
                page.screenshot(path=str(output/'mobile.png'),full_page=True)
                checks.append(dict(id='BUSINESS-MOBILE',status='pass',observed='Business review page fits mobile viewport'))
                # Same-document hash navigation must replace the report/packet too.
                page.goto(h.portal_url+'/agent2/pipeline-workspace#company=C001&run='+runs['C001']['run_id'])
                expect(page.locator('#bw-company')).to_have_value('C001',timeout=20000);expect(page.locator('#bw-meta')).to_contain_text(runs['C001']['bundle_id'],timeout=20000)
                assert runs['C002']['bundle_id'] not in page.locator('#bw-meta').inner_text()
                checks.append(dict(id='BUSINESS-COMPANY-ROUTING',status='pass',observed='Hash navigation keeps company isolation; old company report removed'))
                # Real outer Portal route/reload must restore the new workspace,
                # not the previous HE/P1 screen or C001 when C002 was selected.
                page.locator('#bw-company').select_option('C002')
                expect(page.locator('#bw-run')).to_be_enabled(timeout=15000)
                page.locator('#bw-run').select_option(runs['C002']['run_id'])
                expect(page.locator('#bw-report')).to_be_visible(timeout=15000)
                page.goto(h.portal_url+'/#agent2')
                frame=page.frame_locator('#agent-frame-agent2, #agent-frame')
                expect(frame.locator('#bw-company')).to_have_value('C002',timeout=30000)
                expect(frame.locator('#bw-meta')).to_contain_text(runs['C002']['bundle_id'],timeout=30000)
                page.reload()
                expect(frame.locator('#bw-company')).to_have_value('C002',timeout=30000)
                expect(frame.locator('#bw-meta')).to_contain_text(runs['C002']['bundle_id'],timeout=30000)
                checks.append(dict(id='OUTER-PORTAL-RESTORE',status='pass',observed='Actual Portal iframe and outer reload retain C002, bundle workspace and pinned run without exposing legacy P1 comparison'))
                page.goto(h.portal_url+'/agent2/data-import#company=C001')
                expect(page.locator('#company')).to_have_value('C001',timeout=20000)
                page.locator('#file').set_input_files(dict(name='native-source.json',mimeType='application/json',buffer=f.snapshots.get_snapshot(f.company_ctx['C001']['scope'],datasets['C001'],data=True)))
                page.locator('#validate').click()
                expect(page.locator('#save-panel')).to_be_visible(timeout=20000)
                page.locator('#ack').check();page.locator('#save').click()
                expect(page.locator('#analysis-panel')).to_be_visible(timeout=20000)
                saved_sid=page.locator('#snapshot-meta dd').first.inner_text()
                expect(page.locator('#analyze')).to_have_text('Tiếp tục đến vụ cần rà')
                page.locator('#analyze').click()
                expect(page.locator('#bw-snapshot')).to_have_value(saved_sid,timeout=20000)
                expect(page.locator('#bw-analyze')).to_be_enabled(timeout=20000)
                checks.append(dict(id='IMPORT-TO-BUNDLE',status='pass',observed='Real Portal upload/preview/confirm snapshot navigates to common bundle workspace with exact saved company/snapshot, without invoking legacy P1 scoring'))
                assert not errors,errors
                report=dict(status='pass',checks=checks,synthetic=True,he_execution=False,cloud_plaintext_sent=False,live_deployed=False)
            except Exception as error:
                report=dict(status='fail',checks=checks,error=str(error),browser_errors=errors);page.screenshot(path=str(output/'failure.png'),full_page=True);raise
            finally:
                (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');browser.close()
    finally:support.ShadowPlanTests.tearDownClass()
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    print(json.dumps(run(p.parse_args().output.resolve()),ensure_ascii=True,indent=2))
