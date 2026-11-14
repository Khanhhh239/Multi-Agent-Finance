"""Business flow acceptance in an isolated Portal with real CKKS and reviews.

Import-continuation mode metadata is set to HE4 in the browser fixture; this
test does not claim native Concrete execution. Native HE4 has separate evidence.
"""
import argparse
import csv
import io
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(ROOT/'tests_he'),str(ROOT.parent)]
from web_support import WebHarness
from sme_fraud.tabular_templates import sample


def run(output):
    from playwright.sync_api import sync_playwright,expect
    output.mkdir(parents=True,exist_ok=False);checks=[];errors=[];jobs={}
    with WebHarness() as f,sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True);page=browser.new_page(viewport=dict(width=1440,height=1050),locale='vi-VN');page.on('pageerror',lambda e:errors.append(str(e)))
        def settings(route):
            response=route.fetch();value=response.json();value['analysis_mode']='four_encrypted_branches';route.fulfill(response=response,json=value)
        page.route('**/agent2/api/v1/ui/settings',settings)
        page.goto(f.h.portal_url+'/#data');page.locator('#gate-password').fill('Synthetic-Workspace-2026!');page.locator('#gate-confirm-field input').fill('Synthetic-Workspace-2026!');page.locator('#gate-submit').click();expect(page.locator('#intake')).to_be_visible(timeout=15000)
        page.goto(f.h.portal_url+'/agent2/workspace');expect(page.locator('#ws-company option')).to_have_count(2,timeout=20000);expect(page.locator('#ws-home')).to_be_visible();expect(page.locator('#manage-link')).to_be_hidden()
        checks.append('Portal login opens real company-scoped work area without local access code')
        page.screenshot(path=str(output/'01-overview.png'),full_page=True)
        for company,kind in [('C001','csv'),('C002','xlsx')]:
            page.goto(f.h.portal_url+'/agent2/workspace#company='+company);expect(page.locator('#ws-home')).to_be_visible(timeout=20000);expect(page.locator('#ws-company')).to_have_value(company)
            page.get_by_role('link',name='Nhập dữ liệu mới',exact=True).click();expect(page.locator('#company')).to_have_value(company,timeout=20000)
            scope=f.h.authorizer.authorize('Bearer '+f.h.token,company);raw=json.loads(f.h.store.get_snapshot(scope,f.pair.env['queries'][company],data=True));payload=sample(raw,kind)
            page.locator('#file').set_input_files(dict(name=company+'-demo.'+kind,mimeType='text/csv' if kind=='csv' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer=payload));page.locator('#validate').click();expect(page.locator('#save-panel')).to_be_visible(timeout=20000);expect(page.locator('#save')).to_be_disabled();page.locator('#ack').check();page.locator('#save').click();expect(page.locator('#analysis-panel')).to_be_visible(timeout=20000)
            checks.append(company+': actual '+kind+' validation, acknowledgement and immutable snapshot commit')
            page.locator('#analyze').click();expect(page.locator('#company')).to_have_value(company,timeout=30000);expect(page.locator('#run')).to_be_enabled(timeout=30000);page.locator('#run').click();expect(page.locator('#rows > article.transaction')).to_have_count(5,timeout=60000)
            jobs[company]=page.locator('#result-meta dd').last.text_content();page.get_by_role('link',name='Mở hồ sơ rà và báo cáo',exact=True).click();expect(page.locator('#ws-cases > button')).to_have_count(5,timeout=30000)
            expect(page.locator('#ws-run-meta')).to_contain_text(company);expect(page.locator('#ws-run-meta')).to_contain_text(jobs[company]);checks.append(company+': selected snapshot continues to real encrypted run and five business review cases')
            page.locator('#ws-cases > button').first.click();expect(page.locator('#ws-detail')).to_contain_text('Vì sao cần kiểm tra?');expect(page.locator('#ws-save')).to_be_disabled();page.locator('#ws-start').click();expect(page.locator('#ws-save')).to_be_enabled()
            if company=='C001':
                page.get_by_text('Tài liệu bổ sung',exact=True).click()
                page.get_by_label('Bổ sung chứng từ',exact=True).set_input_files(dict(name='chung-tu-demo.pdf',mimeType='application/pdf',buffer=b'%PDF-1.4\n% synthetic acceptance attachment\n%%EOF'))
                expect(page.get_by_role('button',name='chung-tu-demo.pdf · bổ sung, chưa xác minh',exact=True)).to_be_visible(timeout=15000)
                page.get_by_text('Chứng từ và nguồn đối chiếu',exact=True).click()
                page.get_by_label('chung-tu-demo.pdf · Đã xem tài liệu bổ sung',exact=True).check()
                with page.expect_download() as attachment_download:page.get_by_role('button',name='chung-tu-demo.pdf · bổ sung, chưa xác minh',exact=True).click()
                attachment_path=output/'attachment.pdf';attachment_download.value.save_as(attachment_path)
                if not attachment_path.read_bytes().startswith(b'%PDF-'):raise AssertionError('attachment download bytes')
                checks.append('scoped supplementary PDF upload, evidence selection and authenticated download')
            page.locator('#ws-outcome').select_option('inconclusive');page.locator('#ws-explanation').fill('Đã đối chiếu bản xuất mô phỏng, chưa có chứng từ gốc.');page.locator('#ws-action').fill('Yêu cầu kế toán bổ sung hóa đơn gốc.');page.locator('#ws-missing').fill('Hóa đơn gốc đã xác minh.');
            if company=='C001':
                attempts=[]
                def lost_reply(route):
                    attempts.append(route.request.post_data_json['request_id'])
                    if len(attempts)==1:route.fetch();route.abort('failed')
                    else:route.continue_()
                page.route('**/reviews/*/save',lost_reply)
                page.locator('#ws-save').click();expect(page.locator('#ws-save')).to_be_enabled();expect(page.locator('#ws-explanation')).to_be_disabled();page.locator('#ws-save').click();expect(page.locator('#ws-detail')).to_contain_text('Đã lưu kết quả phiên bản 1',timeout=20000)
                if len(attempts)!=2 or attempts[0]!=attempts[1]:raise AssertionError('lost-reply retry changed request id')
                page.unroute('**/reviews/*/save',lost_reply);checks.append('lost save response retries the same request and creates one feedback revision')
            else:page.locator('#ws-save').click();expect(page.locator('#ws-detail')).to_contain_text('Đã lưu kết quả phiên bản 1',timeout=20000)
            expect(page.locator('#ws-review-metrics')).to_contain_text('Đã ghi kết quả');page.locator('#ws-filter').select_option('reviewed');expect(page.locator('#ws-cases > button')).to_have_count(1);page.reload();expect(page.locator('#ws-cases > button')).to_have_count(5,timeout=20000);page.locator('#ws-cases > button').first.click();expect(page.locator('#ws-detail')).to_contain_text('Đã lưu kết quả phiên bản 1');expect(page.locator('#ws-outcome')).to_have_value('inconclusive')
            with page.expect_download() as download:page.locator('#ws-csv').click()
            path=output/(company+'-report.csv');download.value.save_as(path);rows=list(csv.reader(io.StringIO(path.read_text('utf-8-sig'))))
            if len(rows)!=6 or rows[1][0]!=company:raise AssertionError('CSV company/row count')
            checks.append(company+': server feedback, filtering, reload same run and authenticated CSV download')
            page.screenshot(path=str(output/(company+'-review.png')),full_page=True)
        if jobs['C001']==jobs['C002']:raise AssertionError('company run collision')
        page.locator('#ws-company').select_option('C001');expect(page.locator('#ws-home')).to_be_visible(timeout=20000);expect(page.locator('#ws-detail')).to_be_empty();expect(page.locator('#manage-link')).to_be_hidden();checks.append('company switch clears prior private review state and manager navigation')
        scope=f.h.authorizer.authorize('Bearer '+f.h.token,'C001');store=f.node.jobs.store
        failed=store.create(scope,'workspace-browser-failed-fixture',dict(snapshot_id=f.pair.env['queries']['C001'],as_of='2026-10-03T00:00:00+07:00',artifact_id=f.pair.env['artifacts']['C001']))
        _,failed_data=store.get(scope,failed);store.save(scope,failed,failed_data,'failed','NODE_JOB_FAILED')
        page.goto(f.h.portal_url+'/agent2/encrypted-analysis#company=C001');expect(page.locator('#previous-runs option[value="'+failed+'"]')).to_have_count(1,timeout=20000);page.get_by_text('Xem lại lần phân tích đã lưu',exact=True).click();page.locator('#previous-runs').select_option(failed)
        expect(page.locator('#new-run')).to_be_enabled(timeout=20000);page.locator('#new-run').click();expect(page.locator('#rows > article.transaction')).to_have_count(5,timeout=60000)
        replacement=page.locator('#result-meta dd').last.text_content()
        if replacement==failed or store.status(scope,failed)['phase']!='failed':raise AssertionError('terminal job was reopened')
        if store.get(scope,replacement)[1]['request']['snapshot_id']!=f.pair.env['queries']['C001']:raise AssertionError('new run changed snapshot')
        checks.append('explicit new request after seeded terminal failure retains old failed job and completes real CKKS on same snapshot')
        page.goto(f.h.portal_url+'/agent2/workspace#company=C001');expect(page.locator('#ws-home')).to_be_visible(timeout=20000)
        if errors:raise AssertionError(errors)
        page.set_viewport_size(dict(width=390,height=844));mobile_action=page.locator('#ws-runs > tr').first.get_by_role('button');mobile_action.scroll_into_view_if_needed();expect(mobile_action).to_be_in_viewport()
        bounds=mobile_action.bounding_box()
        if bounds['x']<0 or bounds['x']+bounds['width']>390:raise AssertionError('mobile action overflows horizontally')
        checks.append('mobile overview keeps run actions within screen width')
        page.screenshot(path=str(output/'mobile-overview.png'),full_page=True);browser.close()
    report=dict(status='passed',checks=checks,count=len(checks),browser_errors=errors,servers='isolated Portal and enterprise node',real_ckks=True,analysis_mode_metadata_mocked=True,native_he4_claim=False,live_services_changed=False,human_business_labels=False)
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(dict(status='passed',checks=len(checks))))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();run(args.output.resolve())
