"""Recovery queue and clear explanations in Chrome; synthetic provider/plan,
real HTTP/evaluation/correction storage. Real model acceptance is separate."""
import json,socket,sys,threading,time
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];APP=ROOT/'agent3_tax_compliance'
sys.path.insert(0,str(APP));sys.path.insert(0,str(APP/'tests/explanation'));sys.path.insert(0,str(APP/'data/local_web/browser_tools'))
import uvicorn
from playwright.sync_api import sync_playwright,expect
from src.app import create_app
import test_explanation as fixtures
from natural_fixture import payload


class Provider:
    def generate(self,context,policy):return payload(context)


def main():
    case=fixtures.ExplanationIntegrationTests('test_natural_draft_is_not_promoted_to_validated_claims');case.setUp();f=case.fixture
    f.correct_direction();policy=case.policy.model_copy(update={'style':'NATURAL_DRAFT'})
    out=APP/'data/automation_v2/browser';out.mkdir(parents=True,exist_ok=True)
    class Queue:
        def inspect(self,ctx,payer,rid):
            record=case.workflow.base.record(ctx,payer,rid)
            return record,{'entries':[]},'fixture-plan',None
        def run(self,ctx,payer,rid,command):
            record=case.workflow.base.record(ctx,payer,rid);item=record.items[0]
            report=dict(run_id='fixture-run',record_id=rid,record_revision=record.revision,stale=False,errors=[],recommended=1,
                entries=[dict(field_path='items.'+item.item_id+'.description',issue_codes=['REPEATED_SUFFIX'],state='PROCESSED',
                    selection={'decision':'RECOMMENDED','selected_value':'Service month)'},
                    recovery={'original_value':item.description.value,'suggested_value':'Service month)'})])
            if getattr(self,'exhausted',False):
                report.update(attempt=2,errors=[{'code':'WORKER_TIMEOUT'}],recommended=0)
                report['entries'][0].pop('selection');report['entries'][0]['state']='ERROR'
            return report
    queue=Queue()
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(create_app(f.settings),host='127.0.0.1',port=port,log_level='error'))
    thread=threading.Thread(target=server.run,daemon=True);checks=[];errors=[];posts=[]
    try:
        with f.patches(),patch('src.recovery.api.AutomationReview',return_value=queue),patch('src.explanation_v2.service.load_config',return_value=(policy,case.corpus)),patch('src.explanation_v2.api.load_config',return_value=(policy,case.corpus)),patch('src.explanation_v2.service.provider_for',return_value=Provider()),sync_playwright() as pw:
            thread.start()
            for _ in range(100):
                if server.started:break
                time.sleep(.05)
            browser=pw.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
            page=browser.new_page(viewport={'width':1440,'height':1000});page.on('pageerror',lambda e:errors.append(str(e)))
            page.on('request',lambda r:posts.append(r.url) if r.method=='POST' else None)
            page.goto(f'http://127.0.0.1:{port}/review');page.locator('#token').fill(f.headers['Authorization'].split(' ',1)[1]);page.locator('#payer').fill(f.payer);page.get_by_role('button',name='Kết nối',exact=True).click()
            page.locator('[data-record="'+f.record_id+'"]').click();expect(page.locator('#page-image')).to_be_visible()
            expect(page.locator('#recovery-queue-status')).to_contain_text('trường cần chú ý')
            assert not any('/automation-review?' in u for u in posts);checks.append('Opening a record loads diagnostics without invoking OCR automatically')
            original=case.workflow.base.record(f.ctx,f.payer,f.record_id)
            page.locator('#auto-chain').check();expect(page.locator('#automation-status')).to_contain_text('Đã xử lý bản đã lưu',timeout=45000)
            expect(page.locator('#recovery-queue-status')).to_contain_text('1 gợi ý')
            assert case.workflow.base.record(f.ctx,f.payer,f.record_id)==original
            checks.append('Opt-in runs recovery queue before evaluation and explanation, with saved CFR unchanged')
            page.locator('#step-explanation').click();expect(page.locator('#user-guide')).to_contain_text('Đã đọc được gì?');expect(page.locator('#user-guide')).to_contain_text('Bạn cần làm gì?')
            expect(page.locator('#explanation-status')).to_contain_text('cần đối chiếu')
            checks.append('Deterministic read/missing/action guide accompanies the explicitly unapproved natural draft')
            page.locator('#step-data').click();page.locator('#apply-recovery-recommendations').click()
            assert page.evaluate('Array.from(state.edits.values()).filter(e=>e.checked.checked).some(e=>e.input.value==="Service month)")')
            assert case.workflow.base.record(f.ctx,f.payer,f.record_id)==original
            before=len(posts)
            if not page.locator('#run-region-recovery').is_visible():page.locator('#recovery-queue > summary').click()
            page.locator('#run-region-recovery').click();expect(page.locator('#status')).to_contain_text('Lưu hoặc bỏ bản nháp');assert len(posts)==before
            checks.append('Recommended proposals enter only the draft; drafts block further recovery writes')
            page.once('dialog',lambda d:d.accept());page.locator('[data-record="'+f.record_id+'"]').click()
            expect(page.locator('#dirty-count')).to_have_text('Chưa có thay đổi')
            page.locator('#auto-chain').uncheck()
            held=[];pattern='**/automation-review?*'
            def route(r):
                if r.request.method=='POST':held.append(r)
                else:r.continue_()
            page.route(pattern,route)
            if not page.locator('#run-region-recovery').is_visible():page.locator('#recovery-queue > summary').click()
            page.locator('#run-region-recovery').click();expect(page.locator('#run-region-recovery')).to_be_disabled();assert held
            page.locator('[data-record="'+f.record_id+'"]').click();held[0].continue_();page.unroute(pattern)
            expect(page.locator('#apply-recovery-recommendations')).to_be_hidden()
            checks.append('Reloading a record fences a late recovery response and cannot apply old suggestions')
            queue.exhausted=True
            if not page.locator('#run-region-recovery').is_visible():page.locator('#recovery-queue > summary').click()
            page.locator('#run-region-recovery').click();expect(page.locator('#recovery-queue-status')).to_contain_text('Đã hết hai lượt',timeout=15000)
            expect(page.locator('#retry-region-recovery')).to_be_hidden();expect(page.locator('#apply-recovery-recommendations')).to_be_hidden()
            checks.append('Exhausted retry budget is explained clearly and offers neither another retry nor an apply action')
            for width in (390,1440):
                page.set_viewport_size({'width':width,'height':1000});page.screenshot(path=str(out/f'width-{width}.png'),full_page=True)
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
            checks.append('Recovery queue and guide fit mobile and desktop')
            assert not errors,errors;browser.close()
    finally:
        server.should_exit=True
        if thread.is_alive():thread.join(10)
        case.doCleanups()
    result={'result':'PASS','checks':checks,'page_errors':errors,'scope':'Synthetic queue/provider, real Chrome/HTTP/evaluation/SQLite; no OCR or legal accuracy claim'}
    (out/'result.json').write_bytes((json.dumps(result,indent=2)+'\n').encode());print(json.dumps(result,indent=2))


if __name__=='__main__':main()
