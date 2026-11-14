"""Headless local UI acceptance for all-rule source profile. No live login."""
import argparse,json,secrets,sys,tempfile,threading
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from sme_fraud.auth import FileAuthorizer
from sme_fraud.snapshots import SnapshotStore
from sme_fraud.review_server import make_server
from sme_fraud.native_rule_demo import scenario
from sme_fraud.rule_snapshot import CONTRACT
from sme_fraud.import_files import canonical,digest


def run(output,cutoff_cases=False):
    from playwright.sync_api import sync_playwright,expect
    output.mkdir(parents=True,exist_ok=False);checks=[];errors=[]
    with tempfile.TemporaryDirectory(prefix='agent2-full-rules-ui-') as temp:
        root=Path(temp);token=secrets.token_urlsafe(32);policy=root/'auth.json'
        policy.write_bytes(canonical(dict(policy_version='1.0.0',principals=[dict(actor_id='rules-ui-check',tenant_id='native-demo',token_sha256=digest(token.encode()),status='active',expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),memberships=[dict(company_id='C001',role='accountant',status='active',permissions=['data.import'])])])) )
        store=SnapshotStore(root/'snapshots.sqlite3');server=make_server(0,FileAuthorizer(policy),store);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        source,_=scenario('B1',True);sample=root/'full-rules.json';sample.write_bytes(canonical(dict(contract_version=CONTRACT,tenant_id='native-demo',company_id='C001',source=source,candidate_transaction_ids=[source['tables']['transactions'][-1]['transaction_id']])))
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(channel='chrome',headless=True);page=browser.new_page(viewport=dict(width=1365,height=950));page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto('http://127.0.0.1:'+str(server.server_port)+'/data-import');page.locator('#credential').fill(token);page.locator('#connect').click();expect(page.locator('#identity')).to_be_visible()
                page.locator('#company').select_option('C001');page.locator('#file').set_input_files(sample);page.locator('#validate').click();expect(page.locator('#preview-panel')).to_be_visible(timeout=30000);expect(page.locator('#errors')).to_have_text('');checks.append('profile_preview_accepted')
                page.locator('#ack').check();page.locator('#save').click();expect(page.locator('#analysis-panel')).to_be_visible(timeout=30000)
                assert datetime.fromisoformat(page.locator('#as-of').input_value())==datetime.fromisoformat(source['as_of'][:19]);checks.append('snapshot_saved_cutoff_set_from_source')
                with page.expect_response(lambda r:r.url.endswith('/analyze'),timeout=60000) as response:page.locator('#analyze').click()
                assert response.value.status==200;data=response.value.json();assert data['version']=='snapshot-rule-analysis/1.0.0';assert data['row_count']==1;expect(page.locator('#results')).to_be_visible();checks.append('all_rule_profile_analyzed_in_ui')
                assert '35' in page.locator('#coverage').inner_text();assert any(c['needs_review'] for c in data['rows'][0]['checks'].values());checks.append('confirmed_signal_and_catalogue_scope_visible')
                assert page.locator('#groups details').count()>=1;checks.append('scope_diagnostics_separate')
                assert page.locator('#rows details').count()>=1;checks.append('remaining_checks_collapsed')
                saved_id=data['snapshot']['snapshot_id']
                # Old clients may already have persisted a wrong cutoff. Restore
                # from the committed preview, not a mutable browser clock/value.
                page.evaluate("const s=JSON.parse(sessionStorage.getItem('agent2.workbench'));s.asOf='2026-11-14T12:00';sessionStorage.setItem('agent2.workbench',JSON.stringify(s))")
                for attempt in range(2):
                    page.reload();page.locator('#credential').fill(token);page.locator('#connect').click();expect(page.locator('#analysis-panel')).to_be_visible(timeout=30000)
                    assert datetime.fromisoformat(page.locator('#as-of').input_value())==datetime.fromisoformat(source['as_of'][:19])
                    remembered=page.evaluate("JSON.parse(sessionStorage.getItem('agent2.workbench'))")
                    assert remembered['snapshot']==saved_id
                    assert datetime.fromisoformat(remembered['asOf'])==datetime.fromisoformat(source['as_of'][:19])
                    with page.expect_response(lambda r:r.url.endswith('/analyze'),timeout=60000) as again:page.locator('#analyze').click()
                    assert again.value.status==200
                    assert again.value.json()['analysis_id']==data['analysis_id']
                    checks.append('reload_'+str(attempt+1)+'_preserves_snapshot_cutoff_and_analysis')
                if cutoff_cases:
                    for include_known in (True,False):
                        source_case=deepcopy(source);future=source_case['tables']['transactions'][-1]
                        known=deepcopy(future);known['transaction_id']='KNOWN_UI'
                        for field in ('posted_at','observed_at','created_at','approved_at'):future[field]='2025-08-13T11:00:00+07:00'
                        if include_known:source_case['tables']['transactions'].insert(0,known)
                        for table,records in source_case['tables'].items():source_case['coverage'][table].update(record_count=len(records),records_sha256=digest(canonical(records)))
                        candidates=[future['transaction_id']]+([known['transaction_id']] if include_known else [])
                        sample.write_bytes(canonical(dict(contract_version=CONTRACT,tenant_id='native-demo',company_id='C001',source=source_case,candidate_transaction_ids=candidates)))
                        page.locator('#new-import').click();page.locator('#file').set_input_files(sample);page.locator('#validate').click();expect(page.locator('#save-panel')).to_be_visible(timeout=30000)
                        page.locator('#ack').check();page.locator('#save').click();expect(page.locator('#analysis-panel')).to_be_visible(timeout=30000)
                        with page.expect_response(lambda r:r.url.endswith('/analyze'),timeout=60000) as response:page.locator('#analyze').click()
                        assert response.value.status==200;result=response.value.json();assert result['row_count']==len(candidates)
                        assert all(c['status']=='unavailable' for c in result['rows'][0]['checks'].values())
                        expect(page.locator('#rows .transaction')).to_have_count(len(candidates))
                        assert 'mốc phân tích' in page.locator('#rows .transaction').first.inner_text()
                        checks.append('mixed_cutoff_keeps_rows_in_ui' if include_known else 'all_future_cutoff_renders_unavailable_in_ui')
                page.evaluate("document.getElementById('credential').value=''");page.screenshot(path=str(output/'result.png'),full_page=True)
                assert not errors,errors;browser.close()
        finally:server.shutdown();server.server_close();thread.join(5)
    report=dict(status='passed',checks=checks,page_errors=errors,source_profile=CONTRACT,live_services_changed=False,portal_login_used=False)
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(report))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--cutoff-cases',action='store_true');a=p.parse_args();run(a.output.resolve(),a.cutoff_cases)
