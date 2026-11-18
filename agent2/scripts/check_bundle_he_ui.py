"""Portal HE-mode/continuation UI with deterministic test transport (not native FHE proof)."""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(ROOT/'tests_he'),str(ROOT.parent)]
from test_bundle_he import Fixture
import test_release_shadow_plan as support
from test_portal_auth import PortalHarness,portal
from sme_fraud.review_server import make_server


def run(output):
    from playwright.sync_api import sync_playwright,expect
    output.mkdir(parents=True,exist_ok=False);owner=unittest.TestCase();report={};errors=[];checks=[]
    support.ShadowPlanTests.setUpClass()
    try:
        f=Fixture(owner);f.activate()
        up,down,post=f.he._mock_worker_handlers()
        with ExitStack() as stack,PortalHarness() as h,sync_playwright() as p:
            for name,fn in [('upload',up),('download',down),('post',post)]:stack.enter_context(patch('experiments.he4.coordinator.'+name,side_effect=fn))
            f.node.auth=h.authorizer
            h.agent.shutdown();h.agent.server_close()
            h.agent=make_server(0,h.authorizer,f.svc.snapshots,f.svc.resources,he_backend=f.backend,
                                case_queue_store=f.svc.case_queue,release_service=f.svc)
            portal.CFG['agents']['agent2']['port']=h.agent.server_port
            thread=threading.Thread(target=h.agent.serve_forever,daemon=True);thread.start();h.threads.append(thread)
            browser=p.chromium.launch(channel='chrome',headless=True);page=browser.new_page(viewport=dict(width=1440,height=1000),locale='vi-VN')
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.add_init_script('sessionStorage.setItem("kt-session",'+json.dumps(h.token)+');')
            try:
                page.goto(h.portal_url+'/agent2/#company=C001')
                page.locator('#bw-snapshot').select_option(f.sid)
                page.locator('#bw-execution-mode').select_option('cloud_ciphertext_only')
                page.locator('#bw-analyze').click()
                expect(page.locator('#bw-resume')).to_be_visible(timeout=30000)
                run_id=page.locator('#bw-run').input_value();assert run_id and len(f.jobs())==1
                checks.append('Operator starts pinned HE mode and receives durable pending run')
                page.reload();expect(page.locator('#bw-run')).to_have_value(run_id,timeout=30000)
                expect(page.locator('#bw-resume')).to_be_visible(timeout=15000)
                expect(page.locator('#bw-execution-mode')).to_have_value('cloud_ciphertext_only')
                scope=h.authorizer.authorize('Bearer '+h.token,'C001');f.node.jobs._process(scope,f.jobs()[0])
                page.locator('#bw-resume').click();expect(page.locator('#bw-report')).to_be_visible(timeout=30000)
                expect(page.locator('#bw-mode')).to_contain_text('HE trên cloud')
                expect(page.locator('#bw-execution-mode')).to_have_value('cloud_ciphertext_only')
                expect(page.locator('#bw-limits')).to_contain_text('Chưa khả dụng')
                assert len(f.jobs())==1
                checks.append('Reload/resume retains HE mode/job and enters common queue/report')
                expect(page.locator('#bw-cases button')).not_to_have_count(0)
                page.locator('#bw-cases button').first.click()
                expect(page.locator('#bw-task-create')).to_be_enabled(timeout=15000)
                with page.expect_download() as dl:page.locator('#bw-json').click()
                dl.value.save_as(str(output/'he-business-report.json'))
                saved=json.loads((output/'he-business-report.json').read_bytes())
                assert saved['he_execution'] and saved['run_id']==run_id
                checks.append('HE result opens same case evidence/review/task workspace and exports pinned report')
                page.screenshot(path=str(output/'desktop.png'),full_page=True)
                page.set_viewport_size(dict(width=390,height=844))
                assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+2')
                page.screenshot(path=str(output/'mobile.png'),full_page=True)
                checks.append('Mobile layout does not overflow')
                page.goto(h.portal_url+'/agent2/#company=C002')
                expect(page.locator('#bw-company')).to_have_value('C002',timeout=15000)
                expect(page.locator('#bw-cases button')).to_have_count(0)
                expect(page.locator('#bw-execution-mode option[value=cloud_ciphertext_only]')).to_have_count(0)
                checks.append('C002 cannot see C001 HE run or select an unpinned HE bundle')
                assert not errors,errors
                report=dict(status='pass',checks=checks,synthetic_transport=True,actual_fhe=False,live_deployed=False)
            except Exception as error:
                report=dict(status='fail',checks=checks,error=str(error),browser_errors=errors)
                page.screenshot(path=str(output/'failure.png'),full_page=True);raise
            finally:
                (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');browser.close()
    finally:owner.doCleanups();support.ShadowPlanTests.tearDownClass()
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    print(json.dumps(run(p.parse_args().output.resolve()),ensure_ascii=True,indent=2))
