"""Offline company fit, then browser-only inference through the real Portal.

Uses synthetic fixtures and temporary databases. Never fits in HTTP scoring.
"""
import argparse
from contextlib import closing,ExitStack
import copy
import json
from pathlib import Path
import sqlite3
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(ROOT.parent)]
from portal import server as portal
from test_portal_auth import PortalHarness
from test_four_branch_analysis import query_source
from demo_method_scores import canonical_source
from sme_fraud.import_files import canonical
from sme_fraud.method_jobs import run_fit_job
from sme_fraud.method_store import MethodStore
from sme_fraud.ml_estimators import CompanyEstimator
from sme_fraud.unsupervised_statistics import RobustZ
from sme_fraud.analysis_resources import VERSION as BINDING_VERSION
from test_snapshots import commit_fields


def run(output):
    from playwright.sync_api import sync_playwright,expect
    if output.exists() and any(output.iterdir()):raise ValueError('Choose a new empty output directory')
    output.mkdir(parents=True,exist_ok=True);checks=[];fit_receipts=[];results={};browser_errors=[]
    def record(name):checks.append(dict(check=name,passed=True))
    with PortalHarness() as h,ExitStack() as stack:
        models=MethodStore(h.root/'models.sqlite3');bindings=dict(version=BINDING_VERSION,bindings=[])
        # Explicit worker preparation, before starting any browser or inference spies.
        for member in h.policy['memberships']:member['permissions'].append('model.fit')
        h.write_policy()
        for company,method in (('C001','isolation_forest'),('C002','ecod')):
            source=canonical_source()
            for table,rows in source.items():
                if isinstance(rows,list):
                    for row in rows:
                        row['company_id']=company
                        if table=='companies':row['record_id']=company;row['source']['record_id']=company
            scope=h.authorizer.authorize('Bearer '+h.token,company)
            recheck=lambda:h.authorizer.authorize('Bearer '+h.token,company)
            draft=h.store.upload(scope,canonical(source),'training.json',company+'-history',recheck);report=h.store.preview(scope,draft['import_id'],1,recheck);receipt=h.store.commit(scope,draft['import_id'],commit_fields(report),company+'-history-save',recheck)
            config=dict(version='company-fit-config/1.0.0',snapshot_id=receipt['snapshot']['snapshot_id'],method_id=method,missing_policy='strict',minimum_history=5,profile_id='four-branch-synthetic-not-production',evaluation_mode='backtest',history_start='2026-09-02T00:00:00+07:00',history_end='2026-09-12T00:00:00+07:00',reference_start='2026-09-15T00:00:00+07:00',reference_end='2026-09-20T00:00:00+07:00',evaluation_start='2026-10-01T09:00:00+07:00',selected_columns=['log_abs_amount','amount_negative'])
            fitted={}
            for chosen in ('robust_z',method):
                config['method_id']=chosen
                fit=run_fit_job(h.store,models,h.authorizer,'Bearer '+h.token,company,config,company+'-fit-'+chosen)
                assert fit['job']['status']=='succeeded',fit;fitted[chosen]=fit['job']['artifact_id'];fit_receipts.append(fit)
            bindings['bindings'].append(dict(tenant_id='demo',company_id=company,statistics_artifact_id=fitted['robust_z'],ml_artifacts={method:fitted[method]}))
        for member in h.policy['memberships']:member['permissions']=['data.import']
        h.write_policy();record('separate offline fit prepared company-specific statistics/ML before browser requests')
        bind_path=h.root/'bindings.json';bind_path.write_bytes(canonical(bindings));h.resources.model_db=h.root/'models.sqlite3';h.resources.bindings_file=bind_path
        def states(aid):return dict(id=aid,number=int(aid[-1]),name=portal.AGENTS[aid]['name'],summary='Mô phỏng bốn nhánh',state='running' if aid=='agent2' else 'stopped',owned=False,port=h.agent.server_port if aid=='agent2' else 1,url='/agent2/' if aid=='agent2' else '/',root='isolated-four-branch-demo',log='/api/agents/'+aid+'/log',exit_code=None)
        stack.enter_context(patch.object(portal,'agent_state',side_effect=states));portal.write_json(portal.COMPANY_FILE,dict(portal.COMPANY_FIELDS,code='C001',legal_name='Doanh nghiệp mô phỏng'))
        with closing(sqlite3.connect(h.root/'models.sqlite3')) as conn:before='\n'.join(conn.iterdump())
        for target in ((CompanyEstimator,'fit'),(RobustZ,'fit'),(MethodStore,'begin_fit'),(MethodStore,'publish')):stack.enter_context(patch.object(*target,side_effect=AssertionError('Inference must not fit/write')))
        stack.enter_context(patch('sme_fraud.method_jobs.run_fit_job',side_effect=AssertionError('No fit job in HTTP')))
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True);context=browser.new_context(viewport=dict(width=1360,height=1000));page=context.new_page();page.on('pageerror',lambda e:browser_errors.append(str(e)))
            page.goto(h.portal_url+'/#data');page.locator('#gate-password').fill('Synthetic-Four-Branch-Only!');page.locator('#gate-confirm-field input').fill('Synthetic-Four-Branch-Only!');page.locator('#gate-submit').click();expect(page.locator('#intake')).to_be_visible();page.goto(h.portal_url+'/agent2/');expect(page.locator('#identity')).to_be_visible();expect(page.locator('#connection')).to_be_hidden();record('Portal login reused for analysis; no model.fit permission on browser principal')
            def analyze(key):
                page.locator('#as-of').fill('2026-10-06T09:00:00')
                with page.expect_response(lambda r:r.url.endswith('/analyze')) as response:page.locator('#analyze').click()
                assert response.value.status==200
                result=response.value.json();(output/(key+'.json')).write_bytes(canonical(result));expect(page.locator('#rows .transaction')).to_have_count(5,timeout=20000);return result
            for company in ('C001','C002'):
                if company=='C002':page.locator('#new-import').click()
                page.locator('#company').select_option(company);data=query_source(company);(output/(company+'-source.json')).write_bytes(canonical(data))
                page.locator('#file').set_input_files(dict(name=company+'.json',mimeType='application/json',buffer=canonical(data)));page.locator('#validate').click();expect(page.locator('#save-panel')).to_be_visible();page.locator('#ack').check();page.locator('#save').click();expect(page.locator('#analysis-panel')).to_be_visible()
                result=analyze(company+'-review');results[company]=result;assert result['summary']['transactions_to_review']==0
                assert all(all(c['status']=='no_signal' for c in row['checks'].values()) for row in result['rows'])
                assert all(row['branches']['ml']['available'] and row['branches']['statistics']['available'] for row in result['rows']);record(company+': all 5 law no-hit rows still receive statistics and company ML')
                expect(page.locator('#branch-summary .metric')).to_have_count(4);expect(page.locator('#results-source-limits')).to_contain_text('Chứng từ gốc');expect(page.locator('#rows .analysis-branch')).to_have_count(20);record(company+': four branch summaries, 20 row branch panels, source limitations persist')
                first=page.locator('#rows .transaction').first
                for branch in ('statistics','ml','graph'):first.locator('[data-branch="'+branch+'"] > summary').click()
                expect(first.locator('[data-branch="ml"] .relative-position')).to_be_visible();expect(first.locator('.graph-canvas')).to_have_count(1);first.locator('.graph-canvas g').first.click();expect(first.locator('.graph-figure .hint')).to_contain_text('Tài khoản ngân hàng');record(company+': relative rank, retrospective label and interactive source graph render')
                for name in ('Isolation Forest','ECOD','robust_z','raw_score','feature_contract_fingerprint'):assert name not in page.locator('#results').inner_text()
                first.screenshot(path=str(output/(company+'-four-branches.png')))
            # Missing or incompatible pins must not trigger training or drop data.
            bindings['bindings'][1]['ml_artifacts']={};bind_path.write_bytes(canonical(bindings));missing=analyze('C002-missing-model');assert all(r['branches']['ml']['status']=='unavailable' for r in missing['rows']);record('missing company model yields unavailable, still five rows, no fallback or refit')
            bindings['bindings'][1]['ml_artifacts']={'ecod':bindings['bindings'][1]['statistics_artifact_id']};bind_path.write_bytes(canonical(bindings));incompatible=analyze('C002-incompatible-model');assert all(r['branches']['ml']['status']=='unavailable' for r in incompatible['rows']);page.locator('#rows .transaction').first.locator('[data-branch="ml"] > summary').click();expect(page.locator('#rows').first).to_contain_text('không tương thích');record('incompatible fitted version is explained instead of being scored or retrained')
            page.reload();expect(page.locator('#analysis-panel')).to_be_visible();again=analyze('C002-reload');assert again['analysis_id']==incompatible['analysis_id'];record('reload reuses snapshot, pinned context and deterministic analysis ID')
            page.set_viewport_size(dict(width=390,height=844));assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');page.screenshot(path=str(output/'mobile.png'),full_page=True);record('mobile layout has no horizontal overflow')
            assert not browser_errors,browser_errors;record('no browser JavaScript errors; no algorithm/configuration in business text')
            context.close();browser.close()
        with closing(sqlite3.connect(h.root/'models.sqlite3')) as conn:assert before=='\n'.join(conn.iterdump())
        record('model database unchanged by every browser analysis request')
        assert len({fit['job']['artifact_id'] for fit in fit_receipts})==4
        (output/'offline_fit_receipts.json').write_bytes(canonical(dict(data_kind='synthetic_only',receipts=fit_receipts)))
        (output/'bindings_used.json').write_bytes(canonical(dict(version=BINDING_VERSION,bindings=[dict(tenant_id='demo',company_id=c,statistics_artifact_id=fit_receipts[0 if c=='C001' else 2]['job']['artifact_id'],ml_artifacts={m:fit_receipts[1 if c=='C001' else 3]['job']['artifact_id']}) for c,m in [('C001','isolation_forest'),('C002','ecod')]])))
    report=dict(status='passed',checks=checks,count=len(checks),browser='Chrome via Playwright',data='synthetic_only',offline_fits=4,fit_calls_during_inference=0,model_writes_during_inference=0,active_model_changed=False,queue_written=False,accuracy_claimed=False,browser_errors=browser_errors)
    (output/'summary.json').write_bytes(canonical(report));print(json.dumps(dict(status='passed',checks=len(checks),offline_fits=4,inference_fits=0)))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',type=Path,required=True);args=parser.parse_args();run(args.output_dir.resolve())
