"""Browser check of activated models, using an isolated snapshot DB copy.

Uses actual Portal model pins/read-only model store, no live login or changes
to Portal auth. Includes reload of an operator-created shared snapshot.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import secrets
import sqlite3
import sys
import tempfile
import threading

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT.parent)]
from sme_fraud.analysis_resources import AnalysisResources
from sme_fraud.auth import FileAuthorizer
from sme_fraud.import_files import canonical,digest
from sme_fraud.review_server import make_server
from sme_fraud.snapshots import SnapshotStore


def run(preparation,output):
    from playwright.sync_api import sync_playwright,expect
    receipt=json.loads((preparation/'prepared.json').read_bytes())
    output.mkdir(parents=True,exist_ok=False);checks=[];errors=[]
    with tempfile.TemporaryDirectory(prefix='bridge-model-ui-') as temp:
        root=Path(temp);database=root/'snapshots.sqlite3'
        src=sqlite3.connect(Path(receipt['snapshot_db']).resolve().as_uri()+'?mode=ro',uri=True);dst=sqlite3.connect(database)
        try:src.backup(dst)
        finally:src.close();dst.close()
        token=secrets.token_urlsafe(32);policy=root/'auth.json'
        policy.write_bytes(canonical(dict(policy_version='1.0.0',principals=[dict(actor_id='demo-model-ui-reader',tenant_id='demo',token_sha256=digest(token.encode()),status='active',expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),memberships=[dict(company_id=c,role='accountant',status='active',permissions=['data.import']) for c in ('C001','C002')])])) )
        resources=AnalysisResources(receipt['model_db'],receipt['bindings_file'])
        server=make_server(0,FileAuthorizer(policy),SnapshotStore(database),analysis_resources=resources)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(channel='chrome',headless=True);page=browser.new_page(viewport=dict(width=1365,height=950));page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto('http://127.0.0.1:'+str(server.server_port)+'/data-import');page.locator('#credential').fill(token);page.locator('#connect').click();expect(page.locator('#identity')).to_be_visible()
                for company in receipt['companies']:
                    if page.locator('#new-import').is_visible():page.locator('#new-import').click()
                    cid=company['company_id'];page.locator('#company').select_option(cid)
                    page.locator('#file').set_input_files(preparation/company['evaluation_file']);page.locator('#validate').click();expect(page.locator('#save-panel')).to_be_visible(timeout=30000)
                    page.locator('#ack').check();page.locator('#save').click();expect(page.locator('#analysis-panel')).to_be_visible(timeout=30000)
                    with page.expect_response(lambda r:r.url.endswith('/analyze'),timeout=60000) as response:page.locator('#analyze').click()
                    result=response.value.json();assert response.value.status==200,result
                    assert result['snapshot']['snapshot_id']==company['evaluation_snapshot_id']
                    assert result['row_count']==5 and all(r['branches']['ml']['available'] and r['branches']['statistics']['available'] for r in result['rows'])
                    expect(page.locator('#rows .transaction')).to_have_count(5)
                    assert page.locator('#rows [data-branch="ml"] .badge.available').count()==10
                    checks.append(cid+': five ML/statistical results displayed from activated model pins')
                    base='http://127.0.0.1:'+str(server.server_port)+'/api/v1/companies/'+cid+'/'
                    headers={'Authorization':'Bearer '+token}
                    metadata=page.request.get(base+'snapshots/'+company['evaluation_snapshot_id'],headers=headers).json()
                    assert page.request.get(base+'imports/'+metadata['origin_import_id']+'/report',headers=headers).status==404
                    old_analysis=result['analysis_id']
                    page.reload();page.locator('#credential').fill(token);page.locator('#connect').click();expect(page.locator('#analysis-panel')).to_be_visible(timeout=30000)
                    with page.expect_response(lambda r:r.url.endswith('/analyze'),timeout=60000) as restored:page.locator('#analyze').click()
                    again=restored.value.json();assert restored.value.status==200 and again['analysis_id']==old_analysis
                    checks.append(cid+': shared operator snapshot restored without draft permissions or refit')
                    page.locator('#rows [data-branch="ml"]').first.locator('summary').click()
                    page.evaluate("document.getElementById('credential').value=''");page.screenshot(path=str(output/(cid+'.png')),full_page=True)
                assert not errors,errors;browser.close()
        finally:server.shutdown();server.server_close();thread.join(5)
    report=dict(status='passed',checks=checks,js_errors=errors,portal_model_pins=True,snapshot_db='temporary_copy',live_login_used=False,portal_roles_changed=False,model_fit_performed=False)
    (output/'report.json').write_bytes(canonical(report));print(json.dumps(report))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--preparation',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();run(args.preparation.resolve(),args.output.resolve())
