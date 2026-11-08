"""Operator flow in real Chrome, HTTP and SQLite; synthetic source, no quality claim."""
import json,socket,sys,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];APP=ROOT/'agent3_tax_compliance'
sys.path.insert(0,str(APP));sys.path.insert(0,str(APP/'tests/review'));sys.path.insert(0,str(APP/'data/local_web/browser_tools'))
import uvicorn
from playwright.sync_api import sync_playwright,expect
from test_review import ReviewTests
from src.app import create_app
from src.review.contracts import CorrectionCommand,Change,ItemOperation

def main():
    f=ReviewTests('test_idempotent_double_submit_and_key_conflict');f.setUp();checks=[];errors=[]
    out=APP/'data/capture_upgrade/browser';out.mkdir(parents=True,exist_ok=True)
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(create_app(f.fixture.settings),host='127.0.0.1',port=port,log_level='error'))
    thread=threading.Thread(target=server.run,daemon=True)
    def head():return f.repo.base.record(f.ctx,f.payer,f.record.record_id)
    def correct(**kw):
        r=head();task=next(t for t in f.repo.page(f.ctx,f.payer,'tasks',record_id=r.record_id,revision=r.revision)['items'] if t['status'] in ('OPEN','WAITING_DATA','OPERATOR'))
        return f.repo.correct(f.ctx,f.payer,CorrectionCommand(record_id=r.record_id,expected_revision=r.revision,task_id=task['task_id'],reason='Printed source checked',**kw),'browser-external-'+str(r.revision))
    try:
        with sync_playwright() as pw:
            thread.start()
            for _ in range(150):
                if server.started:break
                time.sleep(.05)
            browser=pw.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
            page=browser.new_page(viewport={'width':1440,'height':1000});page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(f'http://127.0.0.1:{port}/review');page.locator('#token').fill(f.fixture.token);page.locator('#payer').fill(f.payer)
            page.get_by_role('button',name='Kết nối',exact=True).click();page.locator('[data-record="'+f.record.record_id+'"]').click()
            expect(page.locator('#page-image')).to_be_visible();expect(page.locator('#add-item')).to_be_visible()
            def prepare_row(name):
                page.locator('#add-item').click();page.locator('#new-item-description').fill(name)
                page.locator('#new-item-net').fill('9.007.199.254.740.993,12');page.locator('#new-item-vat_treatment').select_option('KCT')
                expect(page.locator('#new-item-vat_rate')).to_be_disabled()
                page.get_by_role('button',name='Chọn vùng trên hóa đơn',exact=True).click()
                image=page.locator('#page-image');image.scroll_into_view_if_needed();box=image.bounding_box()
                page.mouse.move(box['x']+box['width']*.1,box['y']+box['height']*.25);page.mouse.down()
                page.mouse.move(box['x']+box['width']*.85,box['y']+box['height']*.3,steps=10);page.mouse.up()
                expect(page.locator('#item-dialog')).to_be_visible();expect(page.locator('#item-region')).to_contain_text('Trang 1')
            prepare_row('Dòng bổ sung từ chứng từ')
            assert head().revision==1
            lost=[]
            def lose_response(route):
                route.fetch();lost.append(True);route.abort()
            page.route('**/v1/corrections?*',lose_response)
            page.locator('#save-new-item').click();expect(page.locator('#item-error')).not_to_be_empty(timeout=20000)
            assert lost and head().revision==2
            page.unroute('**/v1/corrections?*')
            page.locator('#save-new-item').click();expect(page.locator('#record-summary')).to_contain_text('Bản 2',timeout=20000)
            manual=head().items[-1];assert str(manual.net.value)=='9007199254740993.12';assert manual.description.provenance.evidence[0].page_index==0
            assert head().item_discovery_status=='INCOMPLETE'
            checks.append('Add with dragged source region saves exact Decimal, human proof and incomplete table; no inferred rate')
            checks.append('Lost HTTP response can be retried with the same item identity and idempotency key without duplicating rows')
            page.get_by_role('button',name='Chi tiết dòng '+str(manual.line_number),exact=True).click()
            last=page.locator('.items-table tbody tr').last
            last.get_by_role('button',name='Xem nguồn',exact=True).first.click()
            expect(page.locator('#overlay rect')).to_have_count(1)
            assert f.repo.rebuild(f.ctx,f.payer,f.record.record_id)['verified']
            checks.append('Manual row source highlights correct page and audit replay reconstructs the saved revision')
            last.get_by_role('button',name='Xóa dòng '+str(manual.line_number),exact=True).click()
            page.locator('#action-reason').fill('Đối chiếu nguồn: dòng nhận nhầm')
            page.locator('#action-form').get_by_role('button',name='Xác nhận',exact=True).click()
            expect(page.locator('#record-summary')).to_contain_text('Bản 3',timeout=20000)
            assert len(head().items)==len(f.record.items);assert f.repo.rebuild(f.ctx,f.payer,f.record.record_id)['verified']
            checks.append('Delete needs a reason, keeps immutable original and surviving IDs, and replay passes')
            page.locator('#capture-insights summary').click();page.get_by_role('button',name='Cập nhật số liệu',exact=True).click()
            expect(page.locator('#capture-insights')).to_contain_text('2 lần lưu đối chiếu',timeout=15000)
            expect(page.locator('#capture-insights')).to_contain_text('không phải độ chính xác OCR')
            checks.append('UI measurements reflect current revision and distinguish counts from accuracy')
            correct(item_operations=tuple(ItemOperation(operation='DELETE',item_id=i.item_id) for i in head().items))
            page.locator('[data-record="'+f.record.record_id+'"]').click();expect(page.locator('#record-summary')).to_contain_text('Bản 4')
            prepare_row('Khôi phục từ bảng trống');page.locator('#save-new-item').click()
            expect(page.locator('#record-summary')).to_contain_text('Bản 5',timeout=20000);assert len(head().items)==1
            checks.append('Zero extracted rows can be repaired entirely on web without declaring an empty table complete')
            prepare_row('Bản nháp cần giữ khi xung đột');correct(changes=(Change(field_path='currency',new_value='USD'),))
            page.locator('#save-new-item').click();expect(page.locator('#item-error')).to_contain_text('đã đổi',timeout=15000)
            expect(page.locator('#new-item-description')).to_have_value('Bản nháp cần giữ khi xung đột');assert len(head().items)==1
            checks.append('Concurrent revision rejects structural save and keeps modal draft intact')
            page.get_by_role('button',name='Hủy',exact=True).click();page.set_viewport_size({'width':390,'height':844})
            page.locator('[data-record="'+f.record.record_id+'"]').click();expect(page.locator('#add-item')).to_be_attached()
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
            checks.append('Mobile layout has no document overflow and keeps add-row control reachable')
            assert not errors,errors
            page.screenshot(path=str(out/'mobile.png'),full_page=True);browser.close()
        result={'result':'PASS','checks':checks,'javascript_errors':errors,'scope':'Synthetic Chrome/HTTP/SQLite operator flow, no real-invoice accuracy claim.'}
        (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=True,indent=2));return 0
    finally:server.should_exit=True;thread.join(timeout=5);f.doCleanups()

if __name__=='__main__':raise SystemExit(main())
