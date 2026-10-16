"""Real Chrome, synthetic invoice + actual ZEN. LLM output is a test double."""
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
import test_explanation as fixtures


def main():
    fixture=fixtures.ExplanationIntegrationTests('test_sidecar_validated_preserves_report_and_replay')
    fixture.setUp();output=APP/'data/plan12/browser';output.mkdir(parents=True,exist_ok=True)
    checks=[];errors=[]
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(create_app(fixture.fixture.settings),host='127.0.0.1',port=port,log_level='error'))
    thread=threading.Thread(target=server.run,daemon=True)
    try:
        thread.start()
        for _ in range(100):
            if server.started:break
            time.sleep(.05)
        if not server.started:raise RuntimeError('Test server did not start')
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
            page=browser.new_page(viewport={'width':1366,'height':900})
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{port}/review')
            page.locator('#token').fill(fixture.fixture.headers['Authorization'].split(' ',1)[1])
            page.locator('#payer').fill(fixture.fixture.payer)
            page.get_by_role('button',name='Kết nối',exact=True).click()
            page.locator('[data-record="'+fixture.fixture.record_id+'"]').click()
            expect(page.locator('#compliance-title')).to_have_text('Các kiểm tra trong phạm vi đã đạt',timeout=15000)
            page.locator('#explanation-detail > summary').click()
            page.locator('#generate-explanation').click()
            expect(page.locator('#explanation-status')).to_contain_text('Diễn giải bằng mẫu',timeout=15000)
            expect(page.locator('#explanation-claims > li')).not_to_have_count(0)
            checks.append('Default offline/template explanation on pinned evaluation without touching verdict')
            with patch('src.explanation_v2.service.load_config',return_value=(fixture.policy,fixture.corpus)),patch('src.explanation_v2.service.provider_for',return_value=fixture.provider()):
                page.locator('#generate-explanation').click()
                expect(page.locator('#explanation-status')).to_contain_text('đã kiểm tra từng phát biểu',timeout=15000)
                expect(page.locator('#explanation-sources')).to_contain_text(fixture.corpus.chunks[0].document_id)
            checks.append('Validated claims and locator provenance rendered; provider is synthetic, not Qwen inference')
            page.locator('#explanation-claims details').first.locator('summary').click()
            expect(page.locator('#explanation-claims details').first).to_contain_text('evaluation:')
            page.screenshot(path=str(output/'01_desktop.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1'),'Mobile overflow'
            page.screenshot(path=str(output/'02_mobile.png'),full_page=True)
            checks.append('Desktop/mobile 390px: no horizontal overflow, source references accessible')
            page.get_by_label('MST người mua',exact=True).fill('1111111111')
            page.locator('#generate-explanation').click()
            expect(page.locator('#status')).to_contain_text('Lưu hoặc bỏ bản nháp')
            checks.append('Unsaved correction cannot request explanation for a mismatched draft')
            page.locator('#reason').fill('Synthetic explanation revision test')
            page.locator('#save').click()
            expect(page.locator('#record-summary')).to_contain_text('Bản 3',timeout=15000)
            expect(page.locator('#explanation-detail')).to_be_hidden()
            expect(page.locator('#explanation-claims > li')).to_have_count(0)
            checks.append('Saving correction removes explanation of the previous revision')
            assert not errors,errors
            browser.close()
    finally:
        server.should_exit=True
        if thread.is_alive():thread.join(10)
        fixture.doCleanups()
    result=dict(result='PASS',checks=checks,page_errors=errors,
                scope='Synthetic invoice/native ZEN/real Chrome; LLM test double; no legal or model accuracy claim')
    (output/'result.json').write_bytes((json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode())
    print(json.dumps(result,ensure_ascii=True,indent=2))


if __name__=='__main__':main()
