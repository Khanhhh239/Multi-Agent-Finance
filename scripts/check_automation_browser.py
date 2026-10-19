"""Chrome acceptance: opt-in orchestration, natural draft, cache and recovery guards."""
import json
import socket
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];APP=ROOT/'agent3_tax_compliance'
sys.path.insert(0,str(APP));sys.path.insert(0,str(APP/'tests/explanation'))
sys.path.insert(0,str(APP/'data/local_web/browser_tools'))
import uvicorn
from playwright.sync_api import sync_playwright,expect
from src.app import create_app
from src.review.repository import ReviewRepository
import test_explanation as fixtures


class NaturalProvider:
    def generate(self,context,policy):
        from natural_fixture import payload
        return payload(context)


def main():
    f=fixtures.ExplanationIntegrationTests('test_natural_draft_is_not_promoted_to_validated_claims');f.setUp()
    f.fixture.correct_direction() # New revision has no evaluation/explanation yet.
    policy=f.policy.model_copy(update={'style':'NATURAL_DRAFT'})
    output=APP/'data/automation_v1/browser';output.mkdir(parents=True,exist_ok=True)
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(create_app(f.fixture.settings),host='127.0.0.1',port=port,log_level='error'))
    thread=threading.Thread(target=server.run,daemon=True);checks=[];errors=[];posts=[]
    try:
        with f.fixture.patches(),patch('src.explanation_v2.service.load_config',return_value=(policy,f.corpus)),patch('src.explanation_v2.api.load_config',return_value=(policy,f.corpus)),patch('src.explanation_v2.service.provider_for',return_value=NaturalProvider()),sync_playwright() as pw:
            thread.start()
            for _ in range(100):
                if server.started:break
                time.sleep(.05)
            browser=pw.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
            page=browser.new_page(viewport={'width':1440,'height':1000})
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.on('request',lambda r:posts.append(r.url) if r.method=='POST' else None)
            page.goto(f'http://127.0.0.1:{port}/review')
            page.locator('#token').fill(f.fixture.headers['Authorization'].split(' ',1)[1]);page.locator('#payer').fill(f.fixture.payer)
            page.get_by_role('button',name='Kết nối',exact=True).click()
            page.locator('[data-record="'+f.fixture.record_id+'"]').click()
            expect(page.locator('#record-summary')).to_contain_text('Bản 3')
            expect(page.locator('#page-image')).to_be_visible()
            assert not page.locator('#auto-chain').is_checked()
            assert not any('/evaluations?' in url for url in posts)
            checks.append('Opt-in chain does not automatically write on opening a record')
            page.locator('#auto-chain').check()
            expect(page.locator('#automation-status')).to_contain_text('Đã xử lý bản đã lưu',timeout=30000)
            expect(page.locator('#compliance-scope')).to_contain_text('bản dữ liệu 3')
            page.locator('#step-explanation').click()
            expect(page.locator('#explanation-status')).to_contain_text('cần đối chiếu')
            expect(page.locator('#explanation-claims')).to_contain_text('Tình trạng hiện tại')
            expect(page.locator('#explanation-claims')).to_contain_text('Thông tin gốc và bằng chứng')
            assert not f.service.latest(f.fixture.ctx,f.fixture.payer,f.state.evaluation_id) # Older evaluation unchanged.
            checks.append('One opt-in action runs new revision evaluation and natural draft; draft is explicitly unapproved')
            count=sum('/explanations?' in url for url in posts)
            page.locator('#run-automation').click()
            expect(page.locator('#run-automation')).to_be_enabled(timeout=15000)
            assert sum('/explanations?' in url for url in posts)==count
            checks.append('Repeated run reuses explanation when config/corpus/implementation match')
            page.locator('#auto-chain').uncheck()
            page.locator('#step-data').click();page.get_by_label('MST người mua',exact=True).fill('1111111111')
            before=len(posts)
            page.locator('#recover-extraction').click()
            expect(page.locator('#status')).to_contain_text('Lưu hoặc bỏ bản nháp')
            page.locator('#run-automation').click()
            expect(page.locator('#automation-status')).to_contain_text('Đang có bản nháp')
            assert len(posts)==before
            expect(page.get_by_label('MST người mua',exact=True)).to_have_value('1111111111')
            checks.append('Unsaved fields block both recovery and chain, with draft preserved and no POST')
            page.locator('#auto-chain').check()
            page.locator('#reason').fill('Automatic chain after confirmed correction')
            page.locator('#save').click()
            expect(page.locator('#record-summary')).to_contain_text('Bản 4',timeout=15000)
            expect(page.locator('#automation-status')).to_contain_text('Đã xử lý bản đã lưu',timeout=30000)
            expect(page.locator('#compliance-scope')).to_contain_text('bản dữ liệu 4')
            page.locator('#auto-chain').uncheck()
            checks.append('Saving correction automatically evaluates the new revision after the save guard is released')
            page.set_viewport_size({'width':390,'height':844})
            for step in ('data','business','tax','explanation'):
                page.locator('#step-'+step).click()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
            page.screenshot(path=str(output/'01_mobile.png'),full_page=True)
            page.set_viewport_size({'width':1440,'height':1000})
            page.screenshot(path=str(output/'02_desktop.png'),full_page=True)
            checks.append('Natural explanation and automation controls fit mobile and desktop')
            held=[]
            pattern='**/v1/records/'+f.fixture.record_id+'?*'
            page.route(pattern,lambda route:held.append(route))
            page.locator('[data-record="'+f.fixture.record_id+'"]').click()
            expect(page.locator('#recover-extraction')).to_be_disabled()
            assert page.locator('.data-pane').evaluate('(e)=>e.inert')
            page.wait_for_function('state.loadingRecord===true')
            assert held
            held[0].continue_();page.unroute(pattern)
            expect(page.locator('#recover-extraction')).to_be_enabled(timeout=15000)
            assert not page.locator('.data-pane').evaluate('(e)=>e.inert')
            checks.append('Loading record fences recovery and old editors until the new snapshot is ready')
            page.once('dialog',lambda d:d.accept())
            page.locator('[data-record="'+f.fixture.record_id+'"]').click()
            expect(page.locator('#page-image')).to_be_visible()
            expect(page.locator('#dirty-count')).to_have_text('Chưa có thay đổi',timeout=15000)
            with page.expect_response(lambda r:'/reextract?' in r.url,timeout=45000) as recovered:
                page.locator('#recover-extraction').click()
            assert recovered.value.status==200,recovered.value.text()
            expect(page.locator('#automation-status')).to_contain_text('Bộ trích xuất hiện tại',timeout=15000)
            checks.append('Unchanged extraction returns bounded NO_CHANGE and leaves the current record intact')
            with patch('src.extraction.repository.implementation_sha',return_value='f'*64):
                page.locator('#recover-extraction').click()
                expect(page.locator('#automation-status')).to_contain_text('Hồ sơ cũ vẫn giữ nguyên',timeout=20000)
            expect(page.locator('#record-summary')).to_contain_text('Bản 1')
            assert page.locator('[data-record="'+f.fixture.record_id+'"]').count()==1
            checks.append('New extraction opens a separate record and preserves the original reviewed record in the list')
            repo=ReviewRepository(f.fixture.settings)
            _,base,_=repo.head_context(f.fixture.ctx,f.fixture.payer,f.fixture.record_id)
            with repo.ingestion.db() as db:
                key=db.execute('SELECT ocr_config_key FROM cfr_extractions WHERE artifact_id=?',(base.artifact_id,)).fetchone()[0]
            profile=base.profile.model_copy(update={'version':'zero-row-old-extractor-test'})
            with patch('src.extraction.repository.implementation_sha',return_value='d'*64),patch('src.extraction.service.discover_rows',return_value=[]):
                empty=repo.extraction.work(f.fixture.ctx,f.fixture.payer,base.ingestion_id,key,profile)
            repo.quality.work(f.fixture.ctx,f.fixture.payer,empty.artifact_id)
            repo.ensure_tasks(f.fixture.ctx,f.fixture.payer,empty.record.record_id)
            page.locator('#refresh-records').click()
            page.locator('[data-record="'+empty.record.record_id+'"]').click()
            expect(page.locator('#record-summary')).to_contain_text('0 dòng hàng')
            before=sum('/reextract?' in url for url in posts)
            page.locator('#auto-chain').check()
            expect(page.locator('#record-summary')).to_contain_text('1 dòng hàng',timeout=20000)
            expect(page.locator('#automation-status')).to_contain_text('Đã xử lý bản đã lưu',timeout=30000)
            assert sum('/reextract?' in url for url in posts)==before+1
            assert not page.locator('#items-complete').is_checked()
            assert not repo.base.record(f.fixture.ctx,f.fixture.payer,empty.record.record_id).items
            checks.append('Zero-row old extraction recovers once, continues automatically, preserves old record and does not confirm completeness')
            assert not errors,errors
            browser.close()
    finally:
        server.should_exit=True
        if thread.is_alive():thread.join(10)
        f.doCleanups()
    result={'result':'PASS','checks':checks,'page_errors':errors,'scope':'Real Chrome/HTTP/ZEN; synthetic data and natural provider test double. No legal or semantic acceptance.'}
    (output/'result.json').write_bytes((json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode())
    print(json.dumps(result,ensure_ascii=True,indent=2))


if __name__=='__main__':main()
