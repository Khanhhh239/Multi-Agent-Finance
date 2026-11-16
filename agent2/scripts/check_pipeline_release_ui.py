"""Isolated real Portal/browser release acceptance. No live credentials or HE claim."""
import argparse
import json
from pathlib import Path
import sys
import threading
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(ROOT/'tests_he'),str(ROOT.parent)]
from test_portal_auth import PortalHarness,portal
from training_snapshot_support import native,scope,commit
from sme_fraud.pipeline_release import ReleaseService
from sme_fraud.pipeline_release_store import ReleaseStore
from sme_fraud.review_server import make_server


def run(output):
    from playwright.sync_api import sync_playwright,expect
    output.mkdir(parents=True,exist_ok=False);checks=[];errors=[];report={}
    with PortalHarness() as h,sync_playwright() as p:
        for m in h.policy['memberships']:m['role']='director'
        h.write_policy();h.agent.shutdown();h.agent.server_close()
        svc=ReleaseService(ReleaseStore(h.root/'releases.db',b'u'*32),h.store,h.resources)
        ids={}
        for company in ('C001','C002'):ids[company]=commit(h.store,native(company),scope(company),'ui-'+company)
        h.agent=make_server(0,h.authorizer,h.store,h.resources,release_service=svc)
        portal.CFG['agents']['agent2']['port']=h.agent.server_port
        t=threading.Thread(target=h.agent.serve_forever,daemon=True);t.start();h.threads.append(t)
        browser=p.chromium.launch(channel='chrome',headless=True)
        page=browser.new_page(viewport=dict(width=1440,height=1050),locale='vi-VN')
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.add_init_script('sessionStorage.setItem("kt-session",'+json.dumps(h.token)+');')
        def state(company):
            status,v=h.request(h.url('pipeline-releases',company));assert status==200,v;return v
        def ready():
            expect(page.locator('#work')).to_be_visible(timeout=20000)
            expect(page.locator('#refresh')).to_be_enabled(timeout=20000)
        def prepare(name):
            page.locator('#name').fill(name);page.locator('#prepare').click();ready()
            return page.locator('#bundle').input_value()
        def qualify_approve():
            page.locator('#qualify').click();expect(page.locator('#approve')).to_be_enabled(timeout=20000)
            page.locator('#reason').fill('Synthetic browser staging approval');page.locator('#approve').click()
            expect(page.locator('#activate')).to_be_enabled(timeout=20000)
        try:
            page.goto(h.portal_url+'/agent2/pipeline-releases#company=C001');ready()
            expect(page.locator('#snapshot')).to_have_value(ids['C001'])
            first=prepare('Browser candidate A');qualify_approve()
            page.locator('#activate').click();expect(page.locator('#pointer')).to_contain_text('revision 1',timeout=20000)
            page.locator('#run').click();expect(page.locator('#result')).to_contain_text('4 giao',timeout=20000);ready()
            checks.append(dict(id='UI-01',status='pass',observed='C001 prepare, real gate smoke, approve, CAS activate, actual 4-row staging result'))
            page.reload();ready();expect(page.locator('#company')).to_have_value('C001')
            page.get_by_role('button',name='Xem kết quả đã lưu').click();expect(page.locator('#result')).to_contain_text(first,timeout=10000)
            checks.append(dict(id='UI-02',status='pass',observed='Reload restores saved result; no new run or active-pointer change'))
            # A durable pin simulates enterprise loss after capture, before compute.
            own=h.authorizer.authorize('Bearer '+h.token,'C001')
            svc.store.pin(own,'browser-interrupted-run','staging',dict(snapshot_id=ids['C001'],as_of=native()['source']['as_of']))
            second=prepare('Browser candidate B');qualify_approve()
            page.locator('#activate').click();expect(page.locator('#pointer')).to_contain_text('revision 2',timeout=20000);ready()
            page.get_by_role('button',name='Tiếp tục đúng lượt').click();expect(page.locator('#result')).to_contain_text(first,timeout=20000);ready()
            assert state('C001')['pointers']['staging']['bundle_id']==second
            checks.append(dict(id='UI-03',status='pass',observed='Resume persisted old request after switching active bundle: result still first bundle'))
            page.locator('#bundle').select_option(first);page.locator('#diff').click();expect(page.locator('#diff-result')).not_to_have_text('',timeout=10000);ready()
            expect(page.locator('#rollback')).to_be_enabled();page.locator('#rollback').click()
            expect(page.locator('#pointer')).to_contain_text('revision 3',timeout=20000);ready()
            c1=state('C001');assert c1['pointers']['staging']['bundle_id']==first and len(c1['runs'])==2
            checks.append(dict(id='UI-04',status='pass',observed='Rollback to exact previously approved bundle; old observations remain; revision increases'))
            page.locator('#lane').select_option('production');expect(page.locator('#activate')).to_be_disabled();expect(page.locator('#approve')).to_be_disabled()
            page.locator('#qualify').click();ready();expect(page.locator('#gates')).to_contain_text('BLOCKED')
            assert c1['pointers']['production']['revision']==0
            checks.append(dict(id='UI-05',status='pass',observed='Production gate visible blocked, controls disabled and pointer absent'))
            page.locator('#lane').select_option('staging');page.locator('#company').select_option('C002');ready()
            expect(page.locator('#snapshot')).to_have_value(ids['C002']);assert page.locator('#bundle option').count()==0
            c2bundle=prepare('Browser C002 release');qualify_approve()
            page.locator('#activate').click();expect(page.locator('#pointer')).to_contain_text('revision 1',timeout=20000);ready()
            page.locator('#run').click();expect(page.locator('#result')).to_contain_text(c2bundle,timeout=20000);ready()
            page.reload();ready();expect(page.locator('#company')).to_have_value('C002')
            c2=state('C002');assert len(c2['runs'])==1 and len(state('C001')['runs'])==2
            checks.append(dict(id='UI-06',status='pass',observed='C002 full real engine workflow; reload keeps C002; snapshots/bundles/results isolated'))
            page.screenshot(path=str(output/'desktop.png'),full_page=True)
            page.set_viewport_size(dict(width=390,height=844));page.screenshot(path=str(output/'mobile.png'),full_page=True)
            overflow=page.evaluate('document.documentElement.scrollWidth > innerWidth+2')
            assert not overflow,'Mobile layout overflows viewport'
            checks.append(dict(id='UI-07',status='pass',observed='Desktop/mobile render and no viewport overflow'))
            for m in h.policy['memberships']:
                if m['company_id']=='C002':m['role']='accountant'
            h.write_policy();page.reload();expect(page.locator('#notice')).to_be_visible(timeout=10000);expect(page.locator('#work')).to_be_hidden()
            checks.append(dict(id='UI-08',status='pass',observed='Director permission revoked server-side: manager DTO denied, work screen hidden'))
            assert not errors,errors
            report=dict(version='pipeline-release-ui-acceptance/1.0.0',created_at=datetime.now(timezone.utc).isoformat(),
                        status='pass',checks=checks,browser_errors=errors,synthetic=True,cloud_he_executed=False,live_deployed=False,
                        companies={c:dict(bundle_count=len(s['bundles']),run_count=len(s['runs']),staging_revision=s['pointers']['staging']['revision']) for c,s in [('C001',c1),('C002',c2)]})
        except Exception as error:
            page.screenshot(path=str(output/'failure.png'),full_page=True)
            report=dict(status='fail',checks=checks,error=str(error),browser_errors=errors)
            raise
        finally:
            (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');browser.close()
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    print(json.dumps(run(parser.parse_args().output.resolve()),ensure_ascii=True,indent=2))
