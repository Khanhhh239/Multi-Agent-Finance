"""Repeated T5 imports must preserve payable installments and bank links."""

from copy import deepcopy
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from agent1.adaptive.data import as_of, merge_import, parse_rows, suggested_mapping, validate_dataset
from agent1.adaptive.obligation_imports import plan_obligation_import
from agent1.adaptive.obligations import cash_schedule
from agent1_service.api import create_app


def expense(identifier='RENT-11', **changes):
    return dict(dict(expense_id=identifier, obligation_ref='LEASE-A', payment_period='2026-11',
                     installment_no='1', date='2026-11-20', amount=100, category='rent',
                     known_at='2026-11-01'), **changes)


def book():
    return dict(invoices=[dict(invoice_id='I', customer_id='C', amount=10, issue_date='2026-10-01',
                              due_date='2026-10-10', known_at='2026-10-01')],
                payments=[dict(payment_id='P', invoice_id='I', amount=10,
                               payment_date='2026-10-10', known_at='2026-10-10')], outflows=[])


def legacy(**changes):
    return {key: value for key, value in expense(**changes).items()
            if key not in ('obligation_ref', 'payment_period', 'installment_no')}


def test_overlap_addition_and_new_period_preserve_the_unpaid_previous_period():
    data = merge_import(book(), 'outflows', [expense()])
    december = expense('RENT-12', payment_period='2026-12', date='2026-12-20')
    for rows in ([december], [expense(), december]):
        updated = merge_import(data, 'outflows', rows)
        assert {row['expense_id'] for row in updated['outflows']} == {'RENT-11', 'RENT-12'}
        assert sum(row['amount'] for row in cash_schedule(updated, '2026-12-01')['outflows']) == 200
        assert next(row for row in cash_schedule(updated, '2026-12-01')['obligations']
                    if row['expense_id'] == 'RENT-11')['status'] == 'overdue'
    with pytest.raises(ValueError, match='kỳ hoặc đợt khác'):
        merge_import(data, 'outflows', [dict(december, expense_id='RENT-11', known_at='2026-11-10')])
    assert len(data['outflows']) == 1 and data['outflows'][0]['date'] == '2026-11-20'


def test_alternate_id_and_later_upload_clock_do_not_duplicate_or_rewrite_history():
    data = merge_import(book(), 'outflows', [expense()])
    incoming = expense('ERP-OTHER', obligation_ref='lease-a', known_at='2026-11-11')
    plan = plan_obligation_import(data, [incoming])
    assert plan['counts'] == dict(new=0, changed=0, unchanged=1, review=0)
    assert plan['rows'][0]['input_expense_id'] == 'ERP-OTHER'
    assert plan['rows'][0]['expense_id'] == 'RENT-11'
    assert 'nạp thanh toán' in plan['rows'][0]['message']
    assert merge_import(data, 'outflows', [incoming]) == data
    assert cash_schedule(data, '2026-11-12')['outflows'][0]['amount'] == 100


def test_duplicate_business_item_inside_one_file_is_kept_once_but_conflicting_versions_are_blocked():
    plan = plan_obligation_import(book(), [expense(), expense('OTHER')])
    assert plan['counts'] == dict(new=1, changed=0, unchanged=1, review=0)
    assert len(merge_import(book(), 'outflows', [expense(), expense('OTHER')])['outflows']) == 1
    with pytest.raises(ValueError, match='nhiều nội dung'):
        merge_import(book(), 'outflows', [expense(), expense('OTHER', amount=200, known_at='2026-11-11')])


def test_revision_matches_business_identity_keeps_bank_links_and_historical_remainder():
    data = merge_import(book(), 'outflows', [expense()])
    data['bank'] = [dict(bank_id='B', account='A', date='2026-11-10', direction='out', amount=40,
                         known_at='2026-11-10')]
    data['expense_payments'] = [dict(settlement_id='S', expense_id='RENT-11', bank_id='B', amount=40,
                                     payment_date='2026-11-10', known_at='2026-11-10')]
    updated = merge_import(data, 'outflows', [expense('OTHER', amount=120, date='2026-12-05', known_at='2026-11-11')])
    assert updated['outflows'][0]['expense_id'] == 'RENT-11'
    assert updated['outflows'][0]['payment_period'] == '2026-11'
    assert updated['expense_payments'] == data['expense_payments']
    assert cash_schedule(updated, '2026-11-10')['outflows'][0]['amount'] == 60
    assert cash_schedule(updated, '2026-11-12')['outflows'][0]['amount'] == 80
    assert as_of(updated, '2026-11-10')['outflows'][0]['date'] == '2026-11-20'


def test_component_and_installment_are_distinct_even_with_equal_dates_and_amounts():
    rows = [expense('PRINCIPAL', category='loan_principal', source='Loan A', verified=True),
            expense('INTEREST', category='loan_interest', source='Loan A', verified=True),
            expense('SECOND', category='loan_principal', installment_no='2', source='Loan A', verified=True)]
    data = merge_import(book(), 'outflows', rows)
    assert len(data['outflows']) == 3
    assert sum(row['amount'] for row in cash_schedule(data, '2026-11-12')['outflows']) == 300


def test_legacy_rows_remain_usable_can_be_identified_and_cannot_lose_their_identity():
    data = merge_import(book(), 'outflows', [legacy()])
    assert cash_schedule(data, '2026-11-12')['obligations'][0]['identity_status'] == 'missing'
    assert plan_obligation_import(data, [legacy()])['warnings']
    assert plan_obligation_import(data, [expense('NEW', obligation_ref='LEASE-B')])['warnings']
    upgraded = merge_import(data, 'outflows', [expense(known_at='2026-11-10')])
    assert cash_schedule(upgraded, '2026-11-09')['obligations'][0]['identity_status'] == 'missing'
    assert cash_schedule(upgraded, '2026-11-12')['obligations'][0]['identity_status'] == 'identified'
    assert merge_import(upgraded, 'outflows', [legacy(known_at='2026-11-11')]) == upgraded
    corrected = deepcopy(upgraded)
    corrected['outflows'] = [{k: v for k, v in upgraded['outflows'][0].items() if k != 'payment_period'}]
    with pytest.raises(ValueError, match='Cần đủ'):
        validate_dataset(corrected)
    corrected = dict(deepcopy(upgraded), outflows=[legacy(known_at='2026-11-11')])
    with pytest.raises(ValueError, match='Không được bỏ định danh'):
        validate_dataset(corrected)


@pytest.mark.parametrize('change', [dict(payment_period='2026-13'), dict(payment_period='2026-Q0'),
    dict(payment_period='November'), dict(installment_no='0'), dict(installment_no='1.5'),
    dict(obligation_ref='')])
def test_invalid_or_partial_business_identity_blocks_import(change):
    with pytest.raises(ValueError):
        merge_import(book(), 'outflows', [expense(**change)])


@pytest.mark.parametrize('period', ['2026-11', '2026-Q4', '2026'])
def test_identity_csv_aliases_and_excel_numeric_installment(period):
    frame = pd.DataFrame([dict(legacy(), contract_id='LEASE-A', payment_period=period, installment_no=1.0)])
    rows, errors, _ = parse_rows(frame, 'outflows', suggested_mapping(frame.columns, 'outflows'), '%Y-%m-%d', 'plain')
    assert not errors
    assert rows[0]['obligation_ref'] == 'LEASE-A' and rows[0]['installment_no'] == '1'
    assert merge_import(book(), 'outflows', rows)['outflows'][0]['payment_period'] == period


def test_dataset_validation_and_corrections_cannot_bypass_business_identity():
    data = merge_import(book(), 'outflows', [expense()])
    duplicated = deepcopy(data)
    duplicated['outflows'].append(expense('OTHER'))
    with pytest.raises(ValueError, match='Trùng hợp đồng'):
        validate_dataset(duplicated)
    changed = deepcopy(data)
    changed['outflows'] = [dict(data['outflows'][0], payment_period='2026-12')]
    with pytest.raises(ValueError, match='đã dùng'):
        validate_dataset(changed)


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(state_dir=tmp_path/'data', key_dir=tmp_path/'keys', token='test-t5-import', firm_id='SME')) as client:
        client.headers['Authorization'] = 'Bearer test-t5-import'
        yield client


def preview(client, rows, kind='outflows'):
    response = client.post('/v1/imports/preview',
        files={'file': ('t5.csv', pd.DataFrame(rows).to_csv(index=False).encode('utf-8-sig'), 'text/csv')},
        data=dict(kind=kind, date_format='%Y-%m-%d', number_format='plain'))
    assert response.status_code == 200, response.text
    return response.json()


def save(client, rows, kind='outflows'):
    planned = preview(client, rows, kind)
    assert planned['can_commit'], planned
    response = client.post('/v1/imports/' + planned['id'] + '/commit')
    assert response.status_code == 200, response.text
    return planned, response.json()


def test_preview_counts_full_rows_commit_replay_forecast_and_export_agree(client):
    for kind, rows in book().items():
        if rows:
            save(client, rows, kind)
    salary = expense('SALARY', obligation_ref='PAYROLL', category='salary', amount=200)
    save(client, [expense(), salary])
    rows = [expense('ERP-OTHER', known_at='2026-11-11'), dict(salary, amount=250, known_at='2026-11-11'),
            expense('RENT-12', payment_period='2026-12', date='2026-12-20')]
    planned, saved = save(client, rows)
    assert planned['counts'] == dict(new=1, changed=1, unchanged=1, review=0)
    assert [r['classification'] for r in planned['row_results']] == ['unchanged', 'changed', 'new']
    assert planned['row_results'][1]['before']['amount'] == 200
    assert planned['row_results'][1]['after']['amount'] == 250
    assert (saved['new'], saved['changed'], saved['unchanged']) == (1, 1, 1)
    replayed = client.post('/v1/imports/' + planned['id'] + '/commit').json()
    assert replayed['version'] == saved['version'] and replayed['replayed']
    repeated, _ = save(client, rows)
    assert repeated['counts'] == dict(new=0, changed=0, unchanged=3, review=0)
    records = client.get('/v1/records', params={'kind':'outflows'}).json()['rows']
    assert len(records) == 3 and all(row['identity_status'] == 'identified' for row in records)
    response = client.post('/v1/predict', json=dict(cutoff='2026-11-12', opening_balance=1000,
                                                 payments_complete=True, horizon_weeks=13))
    assert response.status_code == 200, response.text
    plan = response.json()
    assert sum(row['cash_out'] for row in plan['weeks']) == 450
    assert plan['weeks'][-1]['balance'] == 550
    export = client.get('/v1/forecasts/' + plan['id'] + '/xlsx')
    sheet = load_workbook(BytesIO(export.content))['Nghĩa vụ T5']
    headers = [cell.value for cell in sheet[1]]
    assert all(field in headers for field in ['Hợp đồng/khoản cố định', 'Kỳ thanh toán', 'Đợt đến hạn'])
    template = pd.read_csv(BytesIO(client.get('/v1/templates/outflows').content), dtype=str)
    assert template.loc[0, 'payment_period'] == '2026-11' and template.loc[0, 'installment_no'] == '1'


def test_error_blocks_whole_batch_and_stale_preview_cannot_overwrite_new_data(client):
    save(client, [expense()])
    before = client.get('/v1/workspace').json()['counts']
    invalid = preview(client, [expense('RENT-12', payment_period='2026-12'),
                               expense(payment_period='2027-01', known_at='2026-11-11')])
    assert not invalid['can_commit'] and invalid['counts']['review'] == 1
    assert client.post('/v1/imports/' + invalid['id'] + '/commit').status_code == 422
    assert client.get('/v1/workspace').json()['counts'] == before
    pending = preview(client, [expense('RENT-12', payment_period='2026-12')])
    save(client, [expense('OTHER-CONTRACT', obligation_ref='LEASE-B')])
    assert client.post('/v1/imports/' + pending['id'] + '/commit').status_code == 409
    assert client.get('/v1/records', params={'kind':'outflows'}).json()['total'] == 2


def test_source_correction_preserves_identity_and_cannot_move_an_item_to_a_new_period(client):
    save(client, [expense()])
    def source_edit(values):
        version = client.app.state.store.get('SME', 'company_dataset_active')[0]['version']
        return client.post('/v1/corrections/preview', json=dict(base_hash=version,
            changes=[dict(kind='outflows', identifier='RENT-11', values=values)],
            reviewed_by='Kế toán kiểm thử', note='Đối chiếu hợp đồng'))
    assert source_edit(dict(payment_period='2026-12')).status_code == 422
    assert source_edit(dict(obligation_ref='', payment_period='', installment_no='')).status_code == 422
    response = source_edit(dict(amount=120))
    assert response.status_code == 200, response.text
    committed = client.post('/v1/corrections/' + response.json()['id'] + '/commit',
                            json=dict(idempotency_key='t5-edit'))
    assert committed.status_code == 200, committed.text
    repeated = preview(client, [expense(amount=120, known_at='2026-11-12')])
    assert repeated['can_commit'] and repeated['counts']['unchanged'] == 1


def test_browser_reviews_all_import_rows_diffs_and_blocks_wrong_period(client, browser_runtime, client_proxy):
    playwright, chrome = browser_runtime
    salary = expense('SALARY', obligation_ref='PAYROLL', category='salary', amount=200)
    save(client, [expense(), salary])
    rows = [expense('ERP-OTHER'), dict(salary, amount=250, known_at='2026-11-11')]
    rows += [expense('NEW-' + str(i), obligation_ref='<img src=x onerror=unsafe>' if i == 22 else 'LEASE-' + str(i))
             for i in range(23)]
    payload = pd.DataFrame(rows).to_csv(index=False).encode('utf-8-sig')
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=str(chrome), headless=True)
        try:
            page = browser.new_page(viewport=dict(width=1500, height=1000))
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.route('**/*', client_proxy(client))
            page.goto('http://testserver/workspace#data')
            playwright.expect(page.locator('#connection-state')).to_contain_text('Đã kết nối')
            page.locator('#table-kind').select_option('outflows')
            page.locator('#date-format').select_option('%Y-%m-%d')
            page.locator('#number-format').select_option('plain')
            page.locator('#imported-by').fill('Kiểm thử T5')
            page.locator('#import-file').set_input_files(dict(name='t5.csv', mimeType='text/csv', buffer=payload))
            page.locator('#import-form button[type=submit]').click()
            playwright.expect(page.locator('#preview-title')).to_contain_text('23 thêm mới · 1 sửa · 1 trùng giữ nguyên')
            panel = page.locator('#import-plan')
            playwright.expect(panel.locator('tbody tr')).to_have_count(22)  # 20 items plus before/after
            page.get_by_label('Lọc kết quả nạp T5').select_option('changed')
            panel.locator('details summary').click()
            playwright.expect(panel.locator('details')).to_contain_text('200')
            playwright.expect(panel.locator('details')).to_contain_text('250')
            page.get_by_label('Lọc kết quả nạp T5').select_option('new')
            panel.get_by_role('button', name='Sau →', exact=True).click()
            playwright.expect(panel.locator('tbody tr')).to_have_count(3)
            playwright.expect(panel).to_contain_text('<img src=x onerror=unsafe>')
            assert panel.locator('img').count() == 0
            output = Path(__file__).resolve().parents[2] / 'outputs/ui_checks/t5_import'
            output.mkdir(parents=True, exist_ok=True)
            for width in (1500, 390):
                page.set_viewport_size(dict(width=width, height=1000))
                page.wait_for_function('() => document.documentElement.scrollWidth <= innerWidth')
                panel.screenshot(path=str(output / f't5_import_{width}.png'))
            page.locator('#commit-import').click()
            playwright.expect(page.locator('#preview-panel')).to_be_hidden()
            assert client.get('/v1/records', params={'kind':'outflows'}).json()['total'] == 25
            bad = expense(payment_period='2026-12', known_at='2026-11-11')
            page.locator('#import-file').set_input_files(dict(name='bad.csv', mimeType='text/csv',
                buffer=pd.DataFrame([bad]).to_csv(index=False).encode('utf-8-sig')))
            page.locator('#import-form button[type=submit]').click()
            playwright.expect(page.locator('#commit-import')).to_be_disabled()
            playwright.expect(panel).to_contain_text('Cần kiểm tra')
            assert not errors, errors
        finally:
            browser.close()
