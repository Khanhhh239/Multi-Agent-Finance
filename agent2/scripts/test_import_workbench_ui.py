"""Explicit Playwright acceptance against real HTTP/store, synthetic data only.

Run: .venv/Scripts/python.exe scripts/test_import_workbench_ui.py --output-dir PATH
Requires the optional playwright package and an installed Chrome (not runtime deps).
"""
import argparse
from contextlib import closing
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
import sys
import tempfile
import threading

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sme_fraud.auth import FileAuthorizer
from sme_fraud.review_server import make_server
from sme_fraud.snapshots import SnapshotStore


def run(output):
    from playwright.sync_api import sync_playwright, expect
    output.mkdir(parents=True,exist_ok=True)
    checks=[]
    def passed(name):checks.append(dict(check=name,passed=True))
    source=json.loads((Path(__file__).resolve().parents[1]/'sme_fraud/web/import-demo.json').read_text('utf-8'))
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder);token=secrets.token_urlsafe(32);path=root/'policy.json'
        policy=dict(policy_version='1.0.0',principals=[dict(actor_id='ui-test-reviewer',tenant_id='demo',token_sha256=hashlib.sha256(token.encode()).hexdigest(),status='active',expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),memberships=[dict(company_id=cid,role='accountant',status='active',permissions=['data.import']) for cid in ('C001','C002')])])
        def policy_write():path.write_text(json.dumps(policy),encoding='utf-8')
        policy_write();store=SnapshotStore(root/'snapshot.sqlite3');server=make_server(0,FileAuthorizer(path),store)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def count():
            with closing(sqlite3.connect(store.path)) as conn:return conn.execute('SELECT count(*) FROM snapshots').fetchone()[0]
        def upload(page,data,name='demo.json'):
            page.locator('#file').set_input_files(dict(name=name,mimeType='application/json',buffer=json.dumps(data,ensure_ascii=False).encode('utf-8')))
        errors=[]
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(channel='chrome',headless=True)
                context=browser.new_context(viewport=dict(width=1280,height=900));page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(f'http://127.0.0.1:{server.server_port}/')
                expect(page.locator('#validate')).to_be_disabled();page.locator('#credential').fill('wrong'*8);page.locator('#connect').click();expect(page.locator('#notice')).to_contain_text('xác thực');passed('no default bypass; invalid credential rejected')
                page.locator('#credential').fill(token);page.locator('#connect').click();expect(page.locator('#identity')).to_be_visible();expect(page.locator('#credential')).to_have_value('');expect(page.locator('#company option')).to_have_count(2);passed('authorized company selection; password cleared')
                bad=copy.deepcopy(source);bad['transactions'][1].pop('record_id');upload(page,bad);page.locator('#validate').click();expect(page.locator('#errors')).to_contain_text('Dòng 2');expect(page.locator('#save-panel')).to_be_hidden();assert count()==0;passed('row-specific invalid input cannot save')
                page.locator('#file').set_input_files(dict(name='broken.json',mimeType='application/json',buffer=b'{\n "oops": '));page.locator('#validate').click();expect(page.locator('#notice')).to_contain_text('JSON');expect(page.locator('#save-panel')).to_be_hidden();passed('malformed JSON explained')
                upload(page,source);page.locator('#validate').click();expect(page.locator('#save-panel')).to_be_visible();expect(page.locator('#limits')).to_contain_text('chưa đủ');expect(page.locator('#save')).to_be_disabled();expect(page.locator('#preview-summary')).to_contain_text('5 bản ghi');page.screenshot(path=str(output/'01-preview.png'),full_page=True);passed('source limits visible before explicit acknowledgment')
                # Simulate response loss AFTER server committed; retry must reuse the same key.
                keys=[]
                def lose_response(route):
                    keys.append(route.request.headers.get('idempotency-key'));response=route.fetch();assert response.status==200;route.abort('failed')
                page.route('**/imports/*/commit',lose_response,times=1);page.locator('#ack').check();page.locator('#save').click();expect(page.locator('#notice')).to_contain_text('Mất kết nối');assert count()==1
                def capture(route):keys.append(route.request.headers.get('idempotency-key'));route.continue_()
                page.route('**/imports/*/commit',capture,times=1);page.locator('#save').click();expect(page.locator('#analysis-panel')).to_be_visible();assert count()==1 and keys[0]==keys[1];passed('lost commit response retried without duplicate snapshot')
                requests=[]
                page.on('request',lambda r:requests.append(r.post_data_json) if r.url.endswith('/analyze') else None)
                page.locator('#as-of').fill('2026-10-30T09:00:00');page.locator('#analyze').click();expect(page.locator('#rows .transaction')).to_have_count(5,timeout=30000);assert requests[-1]==dict(as_of='2026-10-30T09:00:00+07:00',view='review')
                expect(page.locator('#groups .group')).to_have_count(1);expect(page.locator('#groups')).to_contain_text('2.000.000');expect(page.locator('#coverage')).to_contain_text('chưa đánh giá');page.screenshot(path=str(output/'02-results.png'),full_page=True);passed('five inputs five results; one simultaneous group; explicit Vietnam cutoff')
                page.locator('#filter').select_option('unavailable');expect(page.locator('#rows .transaction')).to_have_count(1);expect(page.locator('#rows')).to_contain_text('MISSING');expect(page.locator('#rows')).to_contain_text('Bổ sung');passed('missing sources distinct from no-signal')
                page.locator('#filter').select_option('no_signal');expect(page.locator('#rows .transaction')).to_have_count(0);passed('no-signal filter excludes rows with other warnings or missing checks')
                page.locator('#filter').select_option('all');page.locator('#as-of').fill('2026-09-01T00:00:00');expect(page.locator('#results')).to_be_hidden();page.locator('#analyze').click();expect(page.locator('#results')).to_be_visible(timeout=30000);expect(page.locator('#rows .transaction')).to_have_count(0);passed('cutoff change hides stale results; no future rows')
                page.reload();expect(page.locator('#connection')).to_be_visible();expect(page.locator('#analysis-panel')).to_be_hidden();assert token not in page.evaluate('JSON.stringify({...sessionStorage,...localStorage})')
                page.locator('#credential').fill(token);page.locator('#connect').click();expect(page.locator('#analysis-panel')).to_be_visible();expect(page.locator('#as-of')).to_have_value('2026-09-01T00:00');assert count()==1;passed('reload restores only saved context after reauthentication; no stored credential')
                # Changed source must remove acknowledgment and all earlier results.
                precise=copy.deepcopy(source);precise['transactions'][-1]['amount_vnd']=999999999999999999;precise['transactions'][-1]['description']='<img src=x onerror="window.agent2xss=1">'
                upload(page,precise);expect(page.locator('#save-panel')).to_be_hidden();expect(page.locator('#analysis-panel')).to_be_hidden();page.locator('#validate').click();expect(page.locator('#save-panel')).to_be_visible();page.locator('#ack').check();page.locator('#save').click();expect(page.locator('#analysis-panel')).to_be_visible();page.locator('#as-of').fill('2026-10-30T09:00:00');page.locator('#analyze').click();expect(page.locator('#rows .transaction')).to_have_count(5,timeout=30000);expect(page.locator('#rows')).to_contain_text('999.999.999.999.999.999 đ');assert page.locator('#rows img').count()==0 and page.evaluate('window.agent2xss') is None;passed('18-digit money exact; untrusted text never HTML')
                upload(page,source);page.locator('#validate').click();expect(page.locator('#save-panel')).to_be_visible();page.locator('#edit-source').click();page.locator('#company').select_option('C002');expect(page.locator('#save-panel')).to_be_hidden();expect(page.locator('#validate')).to_be_disabled();passed('company change invalidates file and previous preview')
                # Wrong-scope data cannot be saved, even if submitted from an authorized company.
                upload(page,source);page.locator('#validate').click();expect(page.locator('#notice')).to_contain_text('quyền');expect(page.locator('#save-panel')).to_be_hidden();passed('cross-company source rejected by backend')
                page.locator('#company').select_option('C001');upload(page,source);page.locator('#validate').click();expect(page.locator('#save-panel')).to_be_visible();page.locator('#ack').check()
                before=count();policy['principals'][0]['memberships'][0]['status']='revoked';policy_write();page.locator('#save').click();expect(page.locator('#notice')).to_contain_text('quyền');assert count()==before;passed('permission revoked between preview and commit denied')
                policy['principals'][0]['memberships'][0]['status']='active';policy_write()
                # Changing a file on disk without choosing it again cannot use an old preview.
                disk_file=root/'changed.json';disk_file.write_text(json.dumps(source),encoding='utf-8');page.locator('#file').set_input_files(str(disk_file));page.locator('#validate').click();expect(page.locator('#save-panel')).to_be_visible();page.locator('#ack').check()
                changed=copy.deepcopy(source);changed['transactions'][0]['description']='Changed on disk after preview';disk_file.write_text(json.dumps(changed),encoding='utf-8');before=count();page.locator('#save').click();expect(page.locator('#notice')).to_contain_text('tệp');assert count()==before;passed('edited disk file cannot commit using old preview')
                upload(page,source);page.locator('#validate').click();expect(page.locator('#save-panel')).to_be_visible();page.locator('#ack').check()
                page.evaluate('window.realNow=Date.now; Date.now=()=>window.realNow()+86400000');page.locator('#save').click();expect(page.locator('#notice')).to_contain_text('hết hạn');expect(page.locator('#validate')).to_be_visible();expect(page.locator('#save-panel')).to_be_hidden();assert count()==before;page.evaluate('Date.now=window.realNow');passed('expired preview requires accessible revalidation action')
                # Responsive layout: no clipped primary controls or horizontal page overflow.
                page.set_viewport_size(dict(width=390,height=844));page.screenshot(path=str(output/'03-mobile.png'),full_page=True);assert page.evaluate('document.documentElement.scrollWidth <= innerWidth');passed('mobile width 390 without horizontal overflow')
                assert not errors,errors;passed('no browser JavaScript errors')
                context.close();browser.close()
        finally:server.shutdown();server.server_close();thread.join(5)
    report=dict(status='passed',checks=checks,count=len(checks),browser='installed Chrome via Playwright; isolated context',data='synthetic_only',snapshot_database='temporary_isolated',browser_errors=errors)
    (output/'browser_tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(dict(status='passed',checks=len(checks)),ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',type=Path,required=True);args=parser.parse_args();run(args.output_dir.resolve())
