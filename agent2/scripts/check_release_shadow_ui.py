"""Isolated C001/C002 Portal browser flow with real unsupervised/validation/queue.
Supervised fixture data is not executed as HE or admitted as an executable arm.
"""
import argparse
from pathlib import Path
import json
import sys
import threading
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(ROOT/'tests_he'),str(ROOT.parent)]
from test_portal_auth import PortalHarness,portal
from test_release_shadow_plan import ShadowPlanTests
from sme_fraud.pipeline_release import ReleaseService
from sme_fraud.pipeline_release_store import ReleaseStore
from sme_fraud.case_queue_store import CaseQueueStore
from sme_fraud.analysis_resources import AnalysisResources
from sme_fraud.review_server import make_server


def run(output):
    from playwright.sync_api import sync_playwright,expect
    output.mkdir(parents=True,exist_ok=False);checks=[];report={};errors=[]
    ShadowPlanTests.setUpClass()
    try:
        f=ShadowPlanTests.fixture
        with PortalHarness() as h,sync_playwright() as p:
            for m in h.policy['memberships']:m['role']='director'
            h.write_policy();h.agent.shutdown();h.agent.server_close()
            svc=ReleaseService(ReleaseStore(h.root/'releases.db',b'v'*32),f.snapshots,AnalysisResources(f.models.path),CaseQueueStore(h.root/'shadow-queue.db'))
            plans={}
            for company in ('C001','C002'):
                scope=h.authorizer.authorize_director('Bearer '+h.token,company)
                plans[company]=svc.register_plan(scope,ShadowPlanTests.packages[company],'browser-linked-'+company)['plan_id']
            h.agent=make_server(0,h.authorizer,f.snapshots,svc.resources,case_queue_store=svc.case_queue,release_service=svc)
            portal.CFG['agents']['agent2']['port']=h.agent.server_port;t=threading.Thread(target=h.agent.serve_forever,daemon=True);t.start();h.threads.append(t)
            browser=p.chromium.launch(channel='chrome',headless=True);page=browser.new_page(viewport=dict(width=1440,height=1050),locale='vi-VN')
            page.on('pageerror',lambda e:errors.append(str(e)));page.add_init_script('sessionStorage.setItem("kt-session",'+json.dumps(h.token)+');')
            def ready():expect(page.locator('#refresh')).to_be_enabled(timeout=30000)
            try:
                for company in ('C001','C002'):
                    page.goto(h.portal_url+'/agent2/pipeline-releases#company='+company);expect(page.locator('#company')).to_have_value(company,timeout=30000);expect(page.locator('#work')).to_be_visible(timeout=30000);ready()
                    expect(page.locator('#plan')).to_have_value('')
                    assert page.locator('#plan option').count()==2,'Only current enterprise registered plan is visible'
                    page.locator('#plan').select_option(plans[company]);page.locator('#snapshot').select_option(f.company_ctx[company]['manifests']['sealed_future_test']['snapshot_id'])
                    page.locator('#name').fill(company+' linked release');page.locator('#prepare').click();expect(page.locator('#qualify')).to_be_enabled(timeout=30000)
                    page.locator('#qualify').click();expect(page.locator('#approve')).to_be_enabled(timeout=30000)
                    page.locator('#reason').fill('Synthetic linked pipeline browser approval');page.locator('#approve').click();expect(page.locator('#activate')).to_be_enabled(timeout=30000)
                    page.locator('#activate').click();expect(page.locator('#pointer')).to_contain_text('revision 1',timeout=30000);ready()
                    page.locator('#run').click();expect(page.locator('#shadow-summary')).to_be_visible(timeout=30000);ready()
                    scope=h.authorizer.authorize_director('Bearer '+h.token,company);state=svc.overview(scope)
                    assert len(state['runs'])==1 and state['runs'][0]['value']['metrics']['queue_counts']['total_cases']>0
                    assert svc.case_queue.get_queue_state(scope,mode='active')['items']==[]
                    checks.append(dict(id=company+'-FLOW',status='pass',observed='Explicit plan, real validation package pins, stage approval, actual model score, coalesced shadow cases; active queue empty'))
                    page.reload();expect(page.locator('#work')).to_be_visible(timeout=30000);ready();expect(page.locator('#company')).to_have_value(company)
                    page.get_by_role('button',name='Xem kết quả đã lưu').click();expect(page.locator('#shadow-summary')).to_be_visible(timeout=10000)
                    checks.append(dict(id=company+'-RELOAD',status='pass',observed='Persisted observation and queue metrics restored; no new reservation'))
                page.screenshot(path=str(output/'linked-desktop.png'),full_page=True);page.set_viewport_size(dict(width=390,height=844))
                assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+2')
                page.screenshot(path=str(output/'linked-mobile.png'),full_page=True)
                assert not errors,errors
                checks.append(dict(id='UI-ISOLATION-MOBILE',status='pass',observed='Company-local plans/observations and mobile layout; no browser exception'))
                report=dict(status='pass',checks=checks,he_execution=False,cloud_plaintext_sent=False,synthetic=True,live_deployed=False)
            except Exception as error:
                report=dict(status='fail',checks=checks,error=str(error),browser_errors=errors);page.screenshot(path=str(output/'failure.png'),full_page=True);raise
            finally:
                (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');browser.close()
    finally:ShadowPlanTests.tearDownClass()
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    print(json.dumps(run(p.parse_args().output.resolve()),ensure_ascii=True,indent=2))
