"""Real Chrome acceptance on temporary synthetic capture DB; never uses demo DB."""
import sys,json,threading,time,socket
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
APP=ROOT/'agent3_tax_compliance'
sys.path.insert(0,str(APP));sys.path.insert(0,str(APP/'tests/e2e_v1'))
sys.path.insert(0,str(APP/'data/local_web/browser_tools'))
from playwright.sync_api import sync_playwright,expect
import uvicorn
import test_compliance as fixtures
from src.app import create_app


def main():
    fixture=fixtures.ComplianceTests('test_reviewed_capture_real_zen_template_snapshot_replay')
    fixture.setUp();fixture.approved()
    output=APP/'data/plan09/browser';output.mkdir(parents=True,exist_ok=True)
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(create_app(fixture.settings),host='127.0.0.1',port=port,log_level='error'))
    thread=threading.Thread(target=server.run,daemon=True)
    errors=[];checks=[]
    try:
        with fixture.patches():
            thread.start()
            for _ in range(100):
                if server.started:break
                time.sleep(.05)
            if not server.started:raise RuntimeError('Browser acceptance server did not start')
            with sync_playwright() as pw:
                browser=pw.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
                page=browser.new_page(viewport={'width':1366,'height':900},accept_downloads=True)
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{port}/review')
                page.locator('#token').fill(fixture.headers['Authorization'].split(' ',1)[1]);page.locator('#payer').fill(fixture.payer)
                page.get_by_role('button',name='Kết nối',exact=True).click()
                page.locator('[data-record="'+fixture.record_id+'"]').click()
                expect(page.locator('#workspace')).to_be_visible()
                page.locator('#step-tax').click()
                page.locator('#evaluate-record').click()
                expect(page.locator('#compliance-title')).to_have_text('Các kiểm tra trong phạm vi đã đạt',timeout=30000)
                expect(page.locator('#compliance-scope')).to_contain_text('bản dữ liệu 2')
                checks.append('Synthetic reviewed capture executes native ZEN via evaluation API and renders scoped result')
                page.locator('#step-tax').click()
                page.locator('#compliance-summary details').first.locator(':scope > summary').click()
                expect(page.locator('.compliance-rule')).to_have_count(1)
                page.get_by_role('button',name='Xem nguồn: MST người bán',exact=True).click()
                expect(page.locator('#source-field')).to_contain_text('MST người bán')
                checks.append('Rule source navigates to existing source viewer; citations remain links')
                page.locator('#step-tax').click()
                with page.expect_download() as download:page.locator('#export-evaluation').click()
                data=json.loads(Path(download.value.path()).read_text(encoding='utf-8'))
                assert data['report']['record_revision']==2 and data['report']['aggregate']['verdict']=='PASS'
                checks.append('Compliance export contains matching immutable revision and result')
                page.screenshot(path=str(output/'01_desktop.png'),full_page=True)
                page.locator('#step-data').click()
                page.get_by_label('MST người mua',exact=True).fill('1111111111')
                page.locator('#step-tax').click()
                page.locator('#evaluate-record').click()
                expect(page.locator('#status')).to_contain_text('Lưu hoặc bỏ bản nháp')
                page.locator('#step-data').click()
                page.locator('#reason').fill('Synthetic browser source comparison')
                page.locator('#step-data').click()
                page.locator('#save').click()
                expect(page.locator('#record-summary')).to_contain_text('Bản 3',timeout=15000)
                expect(page.locator('#save')).to_be_enabled(timeout=15000)
                expect(page.locator('#compliance-summary')).to_be_hidden()
                checks.append('Unsaved draft is blocked; saved correction clears old revision result')
                page.locator('#step-tax').click()
                page.locator('#evaluate-record').click()
                expect(page.locator('#compliance-scope')).to_contain_text('bản dữ liệu 3',timeout=30000)
                checks.append('Reevaluation after correction renders the new revision')
                page.locator('#step-tax').click()
                page.locator('#load-evaluation-attempts').locator('xpath=ancestor::details').locator('summary').click()
                page.locator('#step-tax').click()
                page.locator('#load-evaluation-attempts').click()
                expect(page.locator('#compliance-attempts')).to_contain_text('Lần 1')
                page.set_viewport_size({'width':390,'height':844})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'),'Mobile overflow'
                page.screenshot(path=str(output/'02_mobile.png'),full_page=True)
                checks.append('Attempt history and mobile result layout at 390px')
                assert not errors,errors
                browser.close()
    finally:
        server.should_exit=True
        if thread.is_alive():thread.join(10)
        fixture.doCleanups()
    result=dict(result='PASS',scope='Synthetic approved models; isolated temporary DB and actual local Chrome/ZEN',checks=checks,page_errors=errors)
    (output/'result.json').write_bytes((json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode())
    print(json.dumps(result,ensure_ascii=True,indent=2))


if __name__=='__main__':main()
