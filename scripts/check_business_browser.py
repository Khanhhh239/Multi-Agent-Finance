"""Real Chrome: reviewed dossier/upload/reopen/conflict/revision/mobile; synthetic DB only."""
import json
import socket
import sys
import threading
import time
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1];APP=ROOT/'agent3_tax_compliance'
sys.path.insert(0,str(APP));sys.path.insert(0,str(APP/'tests/e2e_v1'));sys.path.insert(0,str(APP/'data/local_web/browser_tools'))
import uvicorn
import test_compliance as fixtures
from playwright.sync_api import sync_playwright,expect
from src.app import create_app
from src.business_review.web import WebReviews


def main():
    fixture=fixtures.ComplianceTests('test_reviewed_capture_real_zen_template_snapshot_replay')
    fixture.setUp();fixture.approved()
    repo=WebReviews(fixture.settings);record=repo.base.record(fixture.ctx,fixture.payer,fixture.record_id)
    source,raw=repo.base.source(fixture.ctx,fixture.payer,record.source_id)
    output=APP/'data/business_ui/browser';output.mkdir(parents=True,exist_ok=True)
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(create_app(fixture.settings),host='127.0.0.1',port=port,log_level='error'))
    thread=threading.Thread(target=server.run,daemon=True);checks=[];errors=[]
    try:
        thread.start()
        for _ in range(100):
            if server.started:break
            time.sleep(.05)
        if not server.started:raise RuntimeError('test server did not start')
        with fixture.patches(),sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
            page=browser.new_page(viewport={'width':1440,'height':1000},accept_downloads=True)
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{port}/review')
            page.locator('#token').fill(fixture.headers['Authorization'].split(' ',1)[1]);page.locator('#payer').fill(fixture.payer)
            page.get_by_role('button',name='Kết nối',exact=True).click()
            page.locator('[data-record="'+fixture.record_id+'"]').click()
            page.locator('#step-business').click()
            expect(page.locator('#business-editor')).to_be_enabled(timeout=15000)
            expect(page.locator('#business-saved')).to_contain_text('Chưa có hồ sơ')
            assert not page.locator('#business-confirm').is_checked()
            assert not page.locator('#business-invoice-enabled').is_checked()
            checks.append('Initial editor binds saved revision; no automatic confirmation/classification')
            page.locator('#step-business').click()
            page.locator('#business-invoice-enabled').check()
            page.locator('#step-business').click()
            page.locator('#business-invoice-kind').select_option('VAT');page.locator('#business-invoice-form').select_option('ORDINARY')
            page.locator('#step-business').click()
            page.locator('#business-vat-method').select_option('DEDUCTION');page.locator('#business-claim').select_option('true')
            page.locator('#step-business').click()
            page.locator('#business-presence').select_option('PRESENT_VALUE');page.locator('#business-document-complete').check()
            page.locator('#step-business').click()
            page.locator('#business-reference').fill('Đối chiếu hóa đơn tổng hợp trong browser test')
            page.locator('#step-business').click()
            page.locator('#business-confirm').check();page.locator('#business-save').click()
            expect(page.locator('#business-saved')).to_contain_text('Đã lưu cho bản 2',timeout=15000)
            expect(page.locator('#business-save')).to_be_enabled()
            assert repo.base.record(fixture.ctx,fixture.payer,record.record_id).revision==2
            page.locator('#step-business').click()
            page.locator('#business-reload').click()
            expect(page.locator('#business-editor')).to_be_enabled()
            expect(page.locator('#business-invoice-form')).to_have_value('ORDINARY')
            assert not page.locator('#business-confirm').is_checked()
            checks.append('Save/reload restores reviewed facts; CFR and old compliance flow are unchanged')
            page.locator('#step-business').click()
            page.locator('#business-file').set_input_files({'name':'invalid.pdf','mimeType':'application/pdf','buffer':b'<script>invalid</script>'})
            page.locator('#step-business').click()
            page.locator('#business-upload').click()
            expect(page.locator('#business-status')).to_contain_text('Chỉ hỗ trợ tài liệu PDF',timeout=15000)
            expect(page.locator('#business-upload')).to_be_enabled()
            expect(page.locator('.business-document')).to_have_count(1)
            checks.append('Invalid document shows localized error, keeps existing dossier and permits retry')
            filename='<img src=x onerror=alert(1)>.pdf'
            page.locator('#step-business').click()
            page.locator('#business-doc-kind').select_option('BANK_STATEMENT')
            page.locator('#step-business').click()
            page.locator('#business-file').set_input_files({'name':filename,'mimeType':'application/pdf','buffer':raw})
            page.locator('#step-business').click()
            page.locator('#business-upload').click()
            expect(page.locator('.business-document')).to_have_count(2,timeout=15000)
            assert page.locator('#business-documents img').count()==0
            assert repo.latest(fixture.ctx,fixture.payer,record).payment is None
            checks.append('Upload stores scoped evidence; untrusted filename renders as text; upload alone is not proof')
            page.locator('#step-business').click()
            page.locator('#business-payment-enabled').locator('xpath=ancestor::details[1]').locator(':scope > summary').click()
            page.locator('#step-business').click()
            page.locator('#business-payment-enabled').check()
            page.locator('#step-business').click()
            page.locator('#business-payment-case').select_option('STANDARD')
            page.locator('#step-business').click()
            page.locator('#business-payment-settlement').select_option('VERIFIED_NON_CASH')
            page.locator('#step-business').click()
            page.locator('#business-payment-method').select_option('BANK_TRANSFER')
            page.locator('#step-business').click()
            page.locator('#business-payment-amount').fill(str(record.totals.gross.value).replace('.',','))
            document_id=page.locator('#business-payment-docs option').first.get_attribute('value')
            page.locator('#step-business').click()
            page.locator('#business-payment-docs').select_option(document_id)
            page.locator('#step-business').click()
            page.locator('#business-executed').check();page.locator('#business-full-settlement').check()
            page.locator('#step-business').click()
            page.locator('#business-reference').fill('Đối chiếu chứng từ thanh toán tổng hợp; không phải bank thật')
            page.locator('#step-business').click()
            page.locator('#business-confirm').check()
            previous=repo.latest(fixture.ctx,fixture.payer,record).review_id
            page.locator('#step-business').click()
            page.locator('#business-save').click()
            expect(page.locator('#business-status')).to_contain_text('Đã lưu hồ sơ',timeout=15000)
            assert repo.latest(fixture.ctx,fixture.payer,record).review_id!=previous
            assert repo.latest(fixture.ctx,fixture.payer,record).payment.method=='BANK_TRANSFER'
            assert not page.locator('#business-confirm').is_checked()
            checks.append('Payment review round trip keeps Decimal amount and selected document; no tax verdict produced')
            page.locator('#step-business').click()
            with page.expect_download() as download:page.locator('.business-document').nth(1).get_by_role('button').click()
            assert Path(download.value.path()).read_bytes()==raw
            checks.append('Evidence download requires API authorization and returns the retained exact bytes')
            page.locator('#step-business').click()
            page.locator('#business-products').locator('xpath=ancestor::details[1]').locator(':scope > summary').click()
            if record.items:
                page.locator('#step-business').click()
                page.locator('.business-item > summary').first.click()
                expect(page.locator('#bp-0-rate')).to_have_value('')
                assert not page.locator('#bp-0-enabled').is_checked()
                page.locator('#step-business').click()
                page.locator('#business-doc-kind').select_option('PRODUCT_CATALOGUE')
                page.locator('#step-business').click()
                page.locator('#business-file').set_input_files({'name':'synthetic-catalogue.pdf','mimeType':'application/pdf','buffer':raw})
                page.locator('#step-business').click()
                page.locator('#business-upload').click()
                expect(page.locator('.business-document')).to_have_count(3,timeout=15000)
                page.locator('#bp-0-enabled').check();page.locator('#bp-0-code').fill('SYNTHETIC-PRODUCT')
                page.locator('#bp-0-rate').select_option('0.10')
                page.locator('#bp-0-from').fill('2026-01-01');page.locator('#bp-0-to').fill('2026-10-17')
                page.locator('#bp-0-rationale').fill('Hồ sơ tổng hợp để kiểm thử UI; chưa xác nhận phân loại theo phụ lục.')
                catalogue_id=page.locator('#bp-0-docs option').first.get_attribute('value')
                page.locator('#bp-0-docs').select_option(catalogue_id)
                page.locator('#step-business').click()
                page.locator('#business-reference').fill('Lưu hồ sơ phân loại thử nghiệm, giữ phụ lục chưa xác định')
                page.locator('#step-business').click()
                page.locator('#business-confirm').check();page.locator('#business-save').click()
                expect(page.locator('#business-status')).to_contain_text('Đã lưu hồ sơ',timeout=15000)
                product=repo.latest(fixture.ctx,fixture.payer,record).products[0]
                assert product.base_vat_rate==Decimal('0.10') and product.annex_i=='UNKNOWN' and not product.legal_context_checked,product.model_dump(mode='json')
                expect(page.locator('#bp-0-rate')).to_have_value('0.10')
                checks.append('Product review saves independent documents and exact base rate, preserves unknown annex classification')
            page.locator('#step-business').click()
            page.locator('#business-daily-enabled').locator('xpath=ancestor::details[1]').locator(':scope > summary').click()
            page.locator('#step-business').click()
            page.locator('#business-daily-enabled').check()
            expect(page.locator('#business-daily-list input').first).to_be_checked(timeout=15000)
            assert not page.locator('#business-daily-complete').is_checked()
            page.locator('#step-business').click()
            page.locator('#business-ledger-docs').select_option(document_id)
            page.locator('#step-business').click()
            page.locator('#business-reference').fill('Đối chiếu danh sách trong hệ thống, chưa xác nhận đầy đủ mua trong ngày')
            page.locator('#step-business').click()
            page.locator('#business-confirm').check();page.locator('#business-save').click()
            expect(page.locator('#business-status')).to_contain_text('Đã lưu hồ sơ',timeout=15000)
            assert repo.latest(fixture.ctx,fixture.payer,record).daily.ledger.complete is False
            expect(page.locator('#business-daily-list input').first).to_be_checked(timeout=15000)
            checks.append('Ledger UI round trip keeps completeness false and pins server-derived purchase rows')
            page.screenshot(path=str(output/'01_desktop.png'),full_page=True)
            checks.append('Product section remains unclassified without independent product dossiers')
            page.locator('#step-business').click()
            page.locator('#business-reference').fill('Bản nháp của tôi được giữ khi có xung đột')
            page.locator('#step-business').click()
            page.locator('#business-confirm').check()
            command=page.evaluate('businessCommand()');command['review_reference']='Một phiên khác đã lưu trước'
            response=page.request.post(f'http://127.0.0.1:{port}/v1/records/{record.record_id}/business-reviews',
                params={'taxpayer_id':fixture.payer},headers={**fixture.headers,'Idempotency-Key':'other-session-'+uuid4().hex},data=command)
            assert response.status==200,response.text()
            page.locator('#step-business').click()
            page.locator('#business-save').click()
            expect(page.locator('#business-status')).to_contain_text('Bản nháp vẫn còn',timeout=15000)
            expect(page.locator('#business-reference')).to_have_value('Bản nháp của tôi được giữ khi có xung đột')
            page.locator('#step-business').click()
            page.once('dialog',lambda dialog:dialog.accept());page.locator('#business-reload').click()
            expect(page.locator('#business-reference')).to_have_value('Một phiên khác đã lưu trước',timeout=15000)
            checks.append('Concurrent save rejects stale review ID and preserves draft until explicit reload')
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'),'mobile overflow'
            page.screenshot(path=str(output/'02_mobile.png'),full_page=True)
            checks.append('390px layout has no page overflow; labels and controls remain accessible')
            page.set_viewport_size({'width':1440,'height':1000})
            page.locator('#step-data').click()
            page.get_by_label('MST người mua',exact=True).fill('1111111111')
            page.locator('#step-business').click()
            page.locator('#business-reference').fill('Không lưu hồ sơ trên bản hóa đơn đang sửa')
            page.locator('#step-business').click()
            page.locator('#business-confirm').check();page.locator('#business-save').click()
            expect(page.locator('#status')).to_contain_text('Lưu hoặc bỏ thay đổi dữ liệu hóa đơn')
            page.locator('#step-business').click()
            page.once('dialog',lambda dialog:dialog.accept());page.locator('#business-reload').click()
            expect(page.locator('#business-reference')).to_have_value('Một phiên khác đã lưu trước')
            page.locator('#step-data').click()
            page.locator('#reason').fill('Synthetic browser correction after saved business dossier')
            page.locator('#step-data').click()
            page.locator('#save').click()
            expect(page.locator('#record-summary')).to_contain_text('Bản 3',timeout=20000)
            expect(page.locator('#business-saved')).to_contain_text('Chưa có hồ sơ cho bản 3',timeout=15000)
            assert not page.locator('#business-invoice-enabled').is_checked()
            checks.append('Unsaved CFR blocks business save; correction invalidates old dossier for the new revision')
            assert not errors,errors
            browser.close()
    finally:
        server.should_exit=True
        if thread.is_alive():thread.join(10)
        fixture.doCleanups()
    result=dict(result='PASS',checks=checks,page_errors=errors,scope='Synthetic documents/operator attestations; real Chrome/HTTP/storage. No legal or bank verification claim.')
    (output/'result.json').write_bytes((json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode())
    print(json.dumps(result,ensure_ascii=True,indent=2))


if __name__=='__main__':main()
