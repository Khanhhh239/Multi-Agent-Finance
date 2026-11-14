"""Live Portal P1 rerun and source reconciliation, with manual user login.

Preserves the 20-minute Portal timeout: reauthentication is requested when it
expires. Never exports passwords/tokens or posts business review feedback.
"""
import argparse
import json
from pathlib import Path
import socket
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from sme_fraud.snapshots import SnapshotStore
from sme_fraud.import_files import canonical

URL='http://127.0.0.1:8800'


def page_request(page,path,body=None):
    """Use the owned page's session; never return credentials to Python."""
    if path!='/api/state' and not path.startswith(('/agent2/api/v1/','/api/agents/agent2/')):
        raise ValueError('fixed local endpoints only')
    return page.evaluate('''async ({path,body})=>{const headers={'X-Platform':'1','X-Session':sessionStorage.getItem('kt-session')||''};if(body!==null)headers['Content-Type']='application/json';const response=await fetch(path,{method:body===null?'GET':'POST',headers,body:body===null?undefined:JSON.stringify(body),cache:'no-store'});return {status:response.status,data:await response.json()};}''',dict(path=path,body=body))


def run(output,restart):
    from playwright.sync_api import sync_playwright,expect
    output.mkdir(parents=True,exist_ok=True);errors=[];checks=[];receipts_path=output/'receipts.json'
    receipts=json.loads(receipts_path.read_bytes()) if receipts_path.exists() else {}
    manifest=json.loads((ROOT/'examples/he4_p1/demo_manifest.json').read_bytes())
    references=SnapshotStore(output/'reference.sqlite3');gate_count=0
    with sync_playwright() as p:
        # The local debug transport belongs only to this fresh test browser.
        # It allows repair without discarding the user's logged-in page.
        with socket.socket() as check:check.bind(('127.0.0.1',9223))
        browser=p.chromium.launch(channel='chrome',headless=False,args=['--remote-debugging-address=127.0.0.1','--remote-debugging-port=9223'])
        page=browser.new_page(viewport=dict(width=1365,height=950));page.on('pageerror',lambda e:errors.append(str(e)))

        def request(path,body=None):
            # All authorization stays inside the page's origin/sessionStorage.
            # Only the server response is returned, never the session token.
            return page_request(page,path,body)

        def login(company=None,job=None):
            nonlocal gate_count
            gate_count+=1;page.goto(URL+'/#data')
            print(json.dumps(dict(stage='waiting_for_user_login' if gate_count==1 else 'reauthentication_required',company=company,job_id=job,password_exported=False)),flush=True)
            previous=None
            while True:
                page.locator('#intake').wait_for(state='visible',timeout=0)
                value=request('/agent2/api/v1/ui/context')
                if value['status']==200:break
                problem=dict(stage='company_context_unavailable',status=value['status'],error=value['data'].get('error') or value['data'].get('errors'),browser_kept_open=True)
                if problem!=previous:
                    print(json.dumps(problem),flush=True);previous=problem
                page.wait_for_timeout(3000)
            print(json.dumps(dict(stage='authenticated',login_number=gate_count)),flush=True)

        def api(path,body=None,company=None,job=None):
            value=request(path,body)
            if value['status']==401:
                login(company,job)
                if job:
                    resumed=request('/agent2/api/v1/companies/'+company+'/he/jobs/'+job+'/resume',{})
                    if resumed['status']!=202:raise AssertionError('saved job reauthorization failed')
                value=request(path,body)
            if value['status'] not in (200,202):raise AssertionError(dict(path=path,status=value['status'],error=value['data'].get('error') or value['data'].get('errors')))
            return value['data']

        try:
            page.goto(URL+'/#data');login()
            while True:
                try:
                    import importlib
                    workflow=importlib.reload(importlib.import_module('scripts.p1_portal_workflow'))
                    workflow.execute(page,api,output,restart,receipts,manifest,references,checks)
                    if errors:raise AssertionError(errors)
                    report=dict(status='passed',authenticated_live_portal=True,actual_four_branch_run=True,simulated_data=True,checks=checks,login_count=gate_count,portal_timeout_unchanged=True,password_exported=False,human_business_feedback_written=False,browser_errors=errors)
                    (output/'report.json').write_bytes(canonical(report));print(json.dumps(report),flush=True)
                    break
                except Exception as error:
                    (output/'failure.json').write_bytes(canonical(dict(status='not_passed',error=str(error),completed_companies=checks,password_exported=False)))
                    print(json.dumps(dict(stage='acceptance_failed_browser_kept_open',error=str(error),password_exported=False)),flush=True)
                    while not (output/'retry.request').exists():
                        if (output/'close-browser.request').exists():raise
                        page.wait_for_timeout(1000)
                    (output/'retry.request').unlink()
                    print(json.dumps(dict(stage='retry_same_browser_and_saved_requests')),flush=True)
        finally:browser.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--restart-agent2',action='store_true');a=p.parse_args();run(a.output.resolve(),a.restart_agent2)
