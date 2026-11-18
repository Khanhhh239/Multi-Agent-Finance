"""Isolated real-browser acceptance; no live Portal account or business state."""
import argparse
import base64
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import secrets
import sys
import tempfile
import threading

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(ROOT.parent)]
from sme_fraud.auth import FileAuthorizer
from sme_fraud.import_files import canonical,digest
from sme_fraud.native_rule_demo import scenario
from sme_fraud.review_server import make_server
from sme_fraud.snapshots import SnapshotStore
from test_rule_source_intake import package


def run(output,workbook):
    from playwright.sync_api import sync_playwright,expect
    output.mkdir(parents=True,exist_ok=False);checks=[];errors=[]
    with tempfile.TemporaryDirectory(prefix='agent2-multi-source-ui-') as temp:
        root=Path(temp);token=secrets.token_urlsafe(32);policy=root/'access.json'
        policy.write_bytes(canonical(dict(policy_version='1.0.0',principals=[dict(actor_id='source-ui-reviewer',tenant_id='native-demo',token_sha256=digest(token.encode()),status='active',expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),memberships=[dict(company_id=c,role='accountant',status='active',permissions=['data.import']) for c in ('C001','C002')])])) )
        store=SnapshotStore(root/'snapshots.db');server=make_server(0,FileAuthorizer(policy),store)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(channel='chrome',headless=True);page=browser.new_page(viewport=dict(width=1440,height=1000))
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{server.server_port}/data-import');page.locator('#credential').fill(token);page.locator('#connect').click();expect(page.locator('#identity')).to_be_visible()
                page.locator('#source-mode').select_option('rules')
                with page.expect_download() as download:page.get_by_role('link',name='Mẫu Excel 35 luật',exact=True).click()
                assert download.value.suggested_filename.endswith('.xlsx');checks.append('download_blank_multi_sheet_template')
                page.locator('#file').set_input_files(workbook)
                expect(page.locator('#validate')).to_be_disabled();page.locator('#inspect-source').click();expect(page.locator('#native-mapping')).to_be_visible(timeout=30000)
                expect(page.locator('#native-as-of')).not_to_have_value('');checks.append('inspect_excel_metadata_tables_and_headers')
                page.locator('#native-attest').check();page.locator('#validate').click()
                expect(page.locator('#save-panel')).to_be_visible(timeout=30000);expect(page.locator('#rule-readiness .readiness-check')).to_have_count(35)
                expect(page.locator('#rule-readiness')).to_contain_text('không phải kết luận');expect(page.locator('#save')).to_be_disabled()
                checks.append('preview_35_readiness_without_claiming_violation_or_full_coverage')
                page.screenshot(path=str(output/'readiness.png'),full_page=True)
                page.locator('#edit-source').click();vendor=page.locator('.source-card[data-source-key="vendors"]')
                vendor.locator('summary').first.click()
                vendor.get_by_text('Phạm vi lịch sử của bảng này',exact=True).click();vendor.locator('[data-coverage="status"]').select_option('partial')
                expect(page.locator('#save-panel')).to_be_hidden();page.locator('#native-attest').check();page.locator('#validate').click()
                expect(page.locator('#save-panel')).to_be_visible(timeout=30000)
                expect(page.locator('[data-check-id="check_7"]')).to_have_class('readiness-check needs_data')
                checks.append('coverage_edit_requires_recheck_and_changes_affected_readiness')
                page.locator('#edit-source').click()
                vendor.locator('[data-coverage="status"]').select_option('unknown')
                for field in ('covered_from','observed_at'):vendor.locator('[data-coverage="'+field+'"]').fill('')
                page.locator('#native-attest').check();page.locator('#validate').click()
                expect(page.locator('#save-panel')).to_be_visible(timeout=30000)
                b1=page.locator('[data-check-id="check_7"]');b1.locator('summary').click();expect(b1).to_contain_text('Chưa khai báo phạm vi nguồn')
                checks.append('withdrawing_file_coverage_replaces_old_complete_claim')
                page.set_viewport_size(dict(width=390,height=844))
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                page.screenshot(path=str(output/'readiness-mobile.png'),full_page=True)
                page.set_viewport_size(dict(width=1440,height=1000));checks.append('readiness_mobile_has_no_horizontal_overflow')
                page.locator('#ack').check();page.locator('#save').click();expect(page.locator('#analysis-panel')).to_be_visible(timeout=30000)
                page.locator('#analyze').click();expect(page.locator('#results')).to_be_visible(timeout=30000);checks.append('excel_commit_and_analyze_same_immutable_snapshot')
                page.locator('#new-import').click()
                source,_=scenario('B1',True);parts=json.loads(package(source,rename=True))['files']
                page.locator('#file').set_input_files([dict(name=f['name'],mimeType='text/csv',buffer=base64.b64decode(f['content_b64'])) for f in parts])
                page.locator('#inspect-source').click();expect(page.locator('#native-mapping')).to_be_visible(timeout=30000)
                card=page.locator('.source-card[data-source-key="so-chi.csv"]');card.locator('[data-table]').select_option('transactions');card.get_by_text('Ánh xạ',exact=False).first.click()
                card.locator('[data-source-column="MaGD"]').fill('transaction_id')
                page.locator('#native-as-of').fill(source['as_of'][:19]);page.locator('#native-source-id').fill('SIM-C001-multi-CSV');page.locator('#native-simulated').select_option('true')
                page.locator('#native-ids').fill(source['tables']['transactions'][-1]['transaction_id'])
                page.screenshot(path=str(output/'csv-mapping.png'),full_page=True)
                page.locator('#validate').click();expect(page.locator('#save-panel')).to_be_visible(timeout=30000)
                expect(page.locator('#rule-readiness .ready')).to_have_count(0);checks.append('multi_csv_file_and_column_mapping_with_unknown_coverage_not_ready')
                page.locator('#ack').check();page.locator('#save').click();expect(page.locator('#analysis-panel')).to_be_visible(timeout=30000)
                checks.append('multi_csv_commit_preserves_mapped_source')
                page.locator('#new-import').click();page.locator('#company').select_option('C002');expect(page.locator('#native-mapping')).to_be_hidden();expect(page.locator('#file')).to_have_value('')
                page.locator('#file').set_input_files(workbook);page.locator('#inspect-source').click();expect(page.locator('#native-mapping')).to_be_visible(timeout=30000)
                page.locator('#native-attest').check();page.locator('#validate').click();expect(page.locator('#errors')).to_contain_text('doanh nghiệp');expect(page.locator('#save-panel')).to_be_hidden()
                checks.append('company_switch_resets_source_and_rejects_foreign_company_workbook')
                if errors:raise AssertionError(errors)
                browser.close()
        finally:server.shutdown();server.server_close();thread.join(5)
    report=dict(status='passed',checks=checks,count=len(checks),page_errors=errors,synthetic_only=True,live_services_changed=False)
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(report))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--workbook',type=Path,required=True);a=parser.parse_args();run(a.output.resolve(),a.workbook.resolve())
