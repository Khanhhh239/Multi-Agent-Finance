"""Offline review/export/score in real Chrome, synthetic PDF and no OCR inference."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]; APP = ROOT / 'agent3_tax_compliance'
sys.path.insert(0, str(APP)); sys.path.insert(0, str(APP / 'tests/quality'))
sys.path.insert(0, str(APP / 'data/local_web/browser_tools'))
from playwright.sync_api import sync_playwright, expect
import invoice_test as runner
from test_ocr_runner import NativeClient


def main():
    output = APP / 'data/invoice_test_browser'; output.mkdir(exist_ok=True)
    checks = []; errors = []
    with tempfile.TemporaryDirectory(dir=APP / 'data') as directory:
        work = Path(directory); prepared = work / 'prepared'; runs = work / 'runs'
        source = APP / 'tests/fixtures/ocr/functional_set_v1/syn-00-pdf_text.pdf'
        with patch.object(runner, 'WORK', work), patch.object(runner, 'PREPARED', prepared), patch.object(runner.ocr_quality, 'OUTPUT', runs):
            runner.prepare(source, prepared, '1', number_locale='VI')
            with patch('src.adapters.ocr.worker_client.WorkerClient', NativeClient):
                code = runner.run(SimpleNamespace(pages='1', run_id='offline_fixture', config=None, dedicated_machine=False))
            assert code == 0
            manifest_before = (runs / 'offline_fixture/manifest.json').read_bytes()
            with sync_playwright() as pw:
                browser = pw.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe', headless=True)
                context = browser.new_context(accept_downloads=True, viewport={'width': 1440, 'height': 1000})
                page = context.new_page(); page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto((work / 'results/offline_fixture/review.html').as_uri())
                expect(page.locator('#status')).to_contain_text('Chưa có nhãn')
                assert page.locator('.source img').evaluate_all('(images)=>images.every(i=>i.complete && i.naturalWidth>0)')
                checks.append('Offline report opens with readable source images and does not claim accuracy before labels')
                number = page.locator('tr').filter(has=page.get_by_role('cell', name='Số hóa đơn', exact=True))
                number.get_by_role('button', name='Giá trị này đúng', exact=True).click()
                expect(number.locator('input[type=text]')).to_have_value('DEMO/000')
                seller = page.locator('tr').filter(has=page.get_by_role('cell', name='Tên người bán', exact=True))
                seller.locator('input[type=text]').fill('DELIBERATELY WRONG SYNTHETIC LABEL')
                with page.expect_download() as downloaded:
                    page.locator('#export').click()
                labels_path = work / 'labels.json'; downloaded.value.save_as(labels_path)
                labels = runner.read(labels_path)['cases']['invoice-p001']['labels']
                assert set(labels['fields']) == {'invoice.number', 'parties.seller.name'}
                assert labels['review_status'] == 'DRAFT' and not labels['complete']
                checks.append('Export contains only explicitly reviewed cells, with draft provenance and exact string values')
                runner.score(SimpleNamespace(run_id='offline_fixture', labels=labels_path))
                scored = runner.read(next((work / 'results/offline_fixture').glob('score_*.json')))
                assert sum(c['score']['labeled'] for c in scored['cases']) == 2
                assert sum(c['score']['correct'] for c in scored['cases']) == 1
                assert len(scored['priority_errors']) == 1
                assert (runs / 'offline_fixture/manifest.json').read_bytes() == manifest_before
                checks.append('Scoring detects a deliberate wrong label without changing frozen inputs or capture data')
                runner.review('offline_fixture')
                page.reload()
                expect(page.locator('tr.CORRECT')).to_have_count(1)
                expect(page.locator('tr.WRONG_PRESENT')).to_have_count(1)
                checks.append('Reopening a scored report preserves manual labels and colors correct and wrong-present cells')
                number = page.locator('tr[data-field="invoice.number"]')
                number.get_by_label('Đã đối chiếu', exact=True).uncheck()
                expect(page.locator('#save-state')).to_contain_text('đã lưu')
                page.reload()
                number = page.locator('tr[data-field="invoice.number"]')
                expect(number.get_by_label('Đã đối chiếu', exact=True)).not_to_be_checked()
                expect(number.locator('input[type=text]')).to_have_value('DEMO/000')
                checks.append('Autosave preserves unchecked review state and draft text without re-confirming scored labels')
                wrong = runner.read(labels_path); wrong['cases']['invoice-p001']['sha256'] = '0' * 64
                runner.write(work / 'wrong_hash.json', wrong)
                try: runner.score(SimpleNamespace(run_id='offline_fixture', labels=work / 'wrong_hash.json'))
                except ValueError: pass
                else: raise AssertionError('Mismatched source hash was accepted')
                checks.append('Labels cannot be applied to a different source hash')
                imported = runner.read(labels_path)
                del imported['cases']['invoice-p001']['labels']['fields']['parties.seller.name']
                page.locator('#import-file').set_input_files({'name': 'import.json', 'mimeType': 'application/json',
                                                            'buffer': json.dumps(imported).encode()})
                expect(page.locator('#message')).to_contain_text('Đã nhập nhãn')
                expect(page.locator('tr[data-field="parties.seller.name"]').get_by_label('Đã đối chiếu', exact=True)).not_to_be_checked()
                expect(page.locator('tr[data-field="invoice.number"]').get_by_label('Đã đối chiếu', exact=True)).to_be_checked()
                checks.append('Import replaces reviewed cells for supplied cases without retaining labels omitted from the file')
                for width in (1440, 390):
                    page.set_viewport_size({'width': width, 'height': 1000})
                    page.screenshot(path=str(output / f'review-{width}.png'), full_page=True)
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
                checks.append('Desktop and mobile review have no horizontal page overflow')
                assert not errors, errors
                browser.close()
    result = {'result': 'PASS', 'checks': checks, 'page_errors': errors,
              'scope': 'Real Chrome, synthetic native PDF and inventory double. No real OCR accuracy claim.'}
    runner.write(output / 'result.json', result)
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0


if __name__ == '__main__': raise SystemExit(main())
