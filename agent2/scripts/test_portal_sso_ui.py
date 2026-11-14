"""Browser acceptance: login once in Portal, use the real Agent2 bridge and store."""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(ROOT.parent)]
from test_portal_auth import PortalHarness
from portal import server as portal


def run(output):
    from playwright.sync_api import sync_playwright, expect
    output.mkdir(parents=True,exist_ok=True);checks=[];errors=[]
    def passed(name):checks.append(dict(check=name,passed=True))
    with PortalHarness() as h, ExitStack() as stack:
        profile=dict(portal.COMPANY_FIELDS,code='C001',legal_name='Doanh nghiệp mô phỏng C001')
        portal.write_json(portal.COMPANY_FILE,profile)
        def agent_state(aid):
            return dict(id=aid,number=int(aid[-1]),name=portal.AGENTS[aid]['name'],summary='Nguồn mô phỏng kiểm thử',state='running' if aid=='agent2' else 'stopped',owned=False,port=h.agent.server_port if aid=='agent2' else 1,url='/agent2/' if aid=='agent2' else '/',root='isolated-test',log='/api/agents/'+aid+'/log',exit_code=None)
        stack.enter_context(patch.object(portal,'agent_state',side_effect=agent_state))
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True);context=browser.new_context(viewport=dict(width=1440,height=1000));page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
            client_auth=[]
            page.on('request',lambda r:client_auth.append(r.headers.get('authorization')) if '/agent2/api/' in r.url else None)
            page.goto(h.portal_url+'/#agent2');frame=page.frame_locator('#agent-frame')
            expect(frame.locator('#portal-access')).to_be_visible(timeout=15000);expect(frame.locator('#connection')).to_be_hidden();expect(frame.locator('#validate')).to_be_disabled();passed('locked Portal shows login guidance, never a local token form')
            frame.locator('#portal-login').click();expect(page.locator('#gate')).to_be_visible();page.locator('#gate-password').fill('Synthetic-Demo-2026!');page.locator('#gate-confirm-field input').fill('Synthetic-Demo-2026!');page.locator('#gate-submit').click();expect(page.locator('#intake')).to_be_visible(timeout=15000);passed('first Portal password setup creates existing shared session')
            page.evaluate('location.hash="agent2"');expect(frame.locator('#identity')).to_be_visible();expect(frame.locator('#connection')).to_be_hidden();expect(frame.locator('#company option')).to_have_count(2);passed('single login automatically opens authorized company selector in iframe')
            frame.locator('#file').set_input_files(dict(name='demo.json',mimeType='application/json',buffer=json.dumps(h.data).encode()));frame.locator('#validate').click();expect(frame.locator('#save-panel')).to_be_visible();frame.locator('#ack').check();frame.locator('#save').click();expect(frame.locator('#analysis-panel')).to_be_visible();frame.locator('#as-of').fill('2026-10-30T09:00:00');frame.locator('#analyze').click();expect(frame.locator('#rows .transaction')).to_have_count(5,timeout=30000);expect(frame.locator('#groups .group')).to_have_count(1);assert h.count()==1;page.screenshot(path=str(output/'01-portal-workbench.png'),full_page=True);passed('Portal session completes upload preview commit analysis: 5 rows, one group')
            page.reload();frame=page.frame_locator('#agent-frame');expect(frame.locator('#analysis-panel')).to_be_visible(timeout=15000);expect(frame.locator('#connection')).to_be_hidden();passed('reload restores snapshot context without typing credentials')
            with page.expect_popup() as new_page:page.locator('#agent-newtab').click()
            tab=new_page.value;tab.on('pageerror',lambda e:errors.append(str(e)));expect(tab.locator('#identity')).to_be_visible(timeout=15000);assert '/agent2/' in tab.url and not any(s in tab.url for s in ('session=','token=','ticket='));assert tab.evaluate('window.opener === null');expect(tab.locator('#connection')).to_be_hidden();passed('separate tab shares existing Portal login with no credential URL and no opener')
            status=tab.evaluate('async()=>{const r=await fetch("/agent2/api/v1/companies/OTHER/imports/validate",{method:"POST",headers:{"Content-Type":"application/json","X-Platform":"1","X-Session":sessionStorage.getItem("kt-session")},body:"{}"});return r.status;}');assert status==403;passed('browser cannot select an ungranted company by crafting API requests')
            frame.locator('#disconnect').click();expect(page.locator('#intake')).to_be_visible();assert page.url.endswith('#data');passed('return-to-Portal button navigates the parent workspace')
            page.locator('#lock-now').click();expect(page.locator('#gate')).to_be_visible()
            # Old tab still has a copied session token; the backend must reject it immediately.
            status=tab.evaluate('async()=>{const r=await fetch("/agent2/api/v1/ui/context",{headers:{"X-Platform":"1","X-Session":sessionStorage.getItem("kt-session")}});return r.status;}');assert status==401
            tab.locator('#analyze').click();expect(tab.locator('#portal-access')).to_be_visible();expect(tab.locator('#results')).to_be_hidden();expect(tab.locator('#connection')).to_be_hidden();passed('locking Portal immediately revokes old-tab API and clears private results on action')
            page.locator('#gate-password').fill('wrong-password');page.locator('#gate-submit').click();expect(page.locator('#gate-error')).to_contain_text('không đúng');passed('invalid Portal password does not unlock Agent2')
            page.locator('#gate-password').fill('Synthetic-Demo-2026!');page.locator('#gate-submit').click();expect(page.locator('#intake')).to_be_visible();page.evaluate('location.hash="agent2"');frame=page.frame_locator('#agent-frame');expect(frame.locator('#identity')).to_be_visible();passed('fresh Portal login reconnects Agent2 automatically')
            # Policy changes must update the selector and drop old snapshot/file context.
            h.policy['memberships'][0]['status']='revoked';h.write_policy();expect(frame.locator('#company')).to_have_value('C002',timeout=20000);expect(frame.locator('#company option')).to_have_count(1);expect(frame.locator('#analysis-panel')).to_be_hidden();expect(frame.locator('#file')).to_have_value('');passed('membership revocation refreshes selector and drops prior snapshot/file context')
            # Revoke current session while the UI is idle, then reload: no local fallback.
            current=page.evaluate('sessionStorage.getItem("kt-session")');portal.SESSIONS[current]=time.time()-1;page.reload();frame=page.frame_locator('#agent-frame');expect(frame.locator('#portal-access')).to_be_visible(timeout=15000);expect(frame.locator('#connection')).to_be_hidden();passed('expired Portal session cannot fall back to a local credential')
            with patch.object(h.authorizer,'mode','local'):
                page.reload();frame=page.frame_locator('#agent-frame');expect(frame.locator('#portal-message')).to_contain_text('chưa chạy ở chế độ Portal',timeout=15000);expect(frame.locator('#connection')).to_be_hidden();passed('misconfigured backend never shows the local credential form inside Portal')
            assert not any(client_auth),client_auth;passed('browser sends Portal session headers, never backend Bearer or bridge secret')
            assert not errors,errors;passed('no browser JavaScript errors')
            context.close();browser.close()
    result=dict(status='passed',checks=checks,count=len(checks),browser='Chrome via Playwright',data='synthetic_only',servers='isolated temporary Portal and Agent2',browser_errors=errors)
    (output/'portal_browser_tests.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(dict(status='passed',checks=len(checks))))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',type=Path,required=True);args=parser.parse_args();run(args.output_dir.resolve())
