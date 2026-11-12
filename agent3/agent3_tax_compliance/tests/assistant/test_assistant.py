"""Tax-risk assistant: adaptive pack invariants, statement reading, matching, dated rules, end to end on a synthetic enterprise."""
import json
import random
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from lxml import html as lhtml

from src.assistant import impact, pipeline, report, synth
from src.assistant.evaluate import evaluate
from src.assistant.matching import match_payments
from src.assistant.models import BankTxn, InvoiceFact
from src.assistant.pack import CORE_THRESHOLDS, PackError, load_pack
from src.assistant.rules import load_ruleset, param
from src.assistant.sources import parse_amount, read_bank_statement, read_xlsx
from src.extraction.xml_invoice import words_to_int

PROJECT = Path(__file__).resolve().parents[2]
HYPOTHETICAL = PROJECT / 'configs/assistant/examples/ruleset_hypothetical_10m.json'
AS_OF = date(2026, 10, 15)


@pytest.fixture(scope='module')
def ws(tmp_path_factory):
    out = tmp_path_factory.mktemp('enterprise') / 'minhan'
    synth.generate(out, seed=7)
    return out


@pytest.fixture(scope='module')
def rep(ws):
    return pipeline.run(ws, pipeline.DEFAULT_RULESET, AS_OF)


# ------------------------------------------------------------------ amounts in words
def test_vietnamese_amount_words_round_trip():
    rng = random.Random(1)
    values = [0, 5, 10, 15, 21, 101, 105, 1005, 15000, 1000000, 1001000, 2200000, 260500000, 1234567890] + [rng.randint(1, 10**11) for _ in range(300)]
    for n in values:
        assert words_to_int(synth.int_to_words_vi(n)) == n, (n, synth.int_to_words_vi(n))


# ------------------------------------------------------------------ adaptive pack
def _pack(tmp_path, **changes):
    data = dict(pack_version=1, profile=dict(tax_code=synth.valid_tax_id('010999998'), legal_name='A', filing_period='MONTH'),
                bank_formats=[synth.BANK_A])
    data.update(changes)
    p = tmp_path / 'pack.json'
    p.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    return p


def test_pack_may_only_tighten_and_only_add_flags(tmp_path):
    assert load_pack(_pack(tmp_path, thresholds={'match_days_after_invoice': 30})).thresholds['match_days_after_invoice'] == 30
    with pytest.raises(PackError):
        load_pack(_pack(tmp_path, thresholds={'match_days_after_invoice': CORE_THRESHOLDS['match_days_after_invoice'][0] + 1}))
    with pytest.raises(PackError):
        load_pack(_pack(tmp_path, policies=[dict(id='X', flag='f', disable_rule='R01_PAYMENT_EVIDENCE')]))
    with pytest.raises(PackError):
        load_pack(_pack(tmp_path, reference_lists=[dict(name='no date', tax_ids=['0100109106'])]))
    with pytest.raises(PackError):
        load_pack(_pack(tmp_path, profile=dict(tax_code='0100109107', legal_name='A')))


# ------------------------------------------------------------------ statements
def test_amount_parsing_follows_bank_format():
    assert parse_amount('1.200.000') == Decimal(1200000)
    assert parse_amount('1,200,000.50', thousands=',', decimal='.') == Decimal('1200000.50')
    assert parse_amount('') is None


def test_csv_and_xlsx_statements_with_titles_and_footers(tmp_path):
    p = _pack(tmp_path, bank_formats=[synth.BANK_A, synth.BANK_B])
    pack = load_pack(p)
    csv_path = tmp_path / 'a.csv'
    csv_path.write_text('SAO KÊ\n\nNgày giao dịch,Nội dung,Số tiền ghi nợ,Số tiền ghi có,Số tài khoản đối ứng,Tên đơn vị đối ứng\n'
                        '05/08/2026,TT HD 123,"2.200.000",,0123-456,CONG TY A\n06/08/2026,Thu tien,,"5.000.000",999,KHACH\n,Tổng cộng,,,,\n', encoding='utf-8')
    a = read_bank_statement(csv_path, pack)
    assert [(t.booked, t.amount, t.direction, t.counterparty_account) for t in a] == [
        (date(2026, 8, 5), Decimal(2200000), 'OUT', '0123456'), (date(2026, 8, 6), Decimal(5000000), 'IN', '999')]
    x = tmp_path / 'b.xlsx'
    synth._write_xlsx(x, [['Posting Date', 'Ref', 'Remark', 'Debit', 'Credit', 'Beneficiary Account', 'Beneficiary Name'],
                          ['2026-08-07', 'R1', 'Pay', 3300000, '', '777', 'SELLER B']])
    assert read_xlsx(x.read_bytes())[1][3] == Decimal(3300000)
    b = read_bank_statement(x, pack)
    assert b[0].amount == Decimal(3300000) and b[0].direction == 'OUT' and b[0].counterparty_name == 'SELLER B'


# ------------------------------------------------------------------ matching
def _inv(key, gross, day, account='111', number='501', seller='0101', name='Cong ty Ban'):
    return InvoiceFact(key=key, file=key, role='PURCHASE', seller_tax_id=seller, seller_name=name, seller_account=account, buyer_tax_id='x',
                       buyer_name=None, buyer_address=None, template='1', symbol='K26TAA', number=number, issue_date=day, currency='VND',
                       net=None, vat=Decimal(gross) / 11, gross=Decimal(gross), payment_label='CK', descriptions=(), guard_errors=(), signed=True)


def _txn(tid, amount, day, account='111', name='', desc='TT'):
    return BankTxn(tid, day, Decimal(amount), 'OUT', account, name, desc, tid)


TH = {'match_days_before_invoice': 7, 'match_days_after_invoice': 90, 'split_payment_max_parts': 4}


def test_closest_pair_wins_when_two_invoices_share_seller_and_amount():
    invs = [_inv('a', 11000000, date(2026, 7, 28)), _inv('b', 11000000, date(2026, 9, 12), number='502')]
    txns = [_txn('t1', 11000000, date(2026, 9, 18)), _txn('t2', 11000000, date(2026, 8, 2), account='999')]
    m = {x.invoice_keys: (x.status, x.txn_ids) for x in match_payments(invs, txns, TH, {})}
    assert m[('b',)] == ('MATCHED', ('t1',))
    assert m[('a',)] == ('AMBIGUOUS', ('t2',))


def test_split_combined_number_signal_and_decision():
    invs = [_inv('split', 55000000, date(2026, 9, 5)), _inv('c1', 6480000, date(2026, 8, 22)), _inv('c2', 5400000, date(2026, 8, 24), number='777'),
            _inv('num', 9900000, date(2026, 7, 13), account=None, number='345'), _inv('dec', 11000000, date(2026, 9, 3), number='900')]
    txns = [_txn('s1', 20000000, date(2026, 9, 12)), _txn('s2', 20000000, date(2026, 9, 20)), _txn('s3', 15000000, date(2026, 10, 3)),
            _txn('cb', 11880000, date(2026, 8, 30)), _txn('n1', 9900000, date(2026, 7, 20), account=None, desc='TT HD 345 V03')]
    dec = {'dec': dict(action='PAYMENT_EVIDENCE_ATTACHED', evidence='UNC 1', by='kt')}
    m = {x.invoice_keys: x.method for x in match_payments(invs, txns, TH, dec)}
    assert m[('split',)] == 'SPLIT_PAYMENTS' and m[('num',)] == 'INVOICE_NUMBER' and m[('dec',)] == 'DECISION'
    assert m[('c1', 'c2')] == 'COMBINED_PAYMENT'


# ------------------------------------------------------------------ dated parameters
def test_threshold_is_chosen_by_issue_date():
    rs = load_ruleset(pipeline.DEFAULT_RULESET)
    assert param(rs, 'NON_CASH_THRESHOLD', date(2025, 6, 30))[0] == '20000000'
    assert param(rs, 'NON_CASH_THRESHOLD', date(2025, 7, 1))[0] == '5000000'
    assert param(rs, 'NON_CASH_THRESHOLD', None) is None


# ------------------------------------------------------------------ end to end on the synthetic enterprise
def test_end_to_end_matches_every_label_without_false_alarms(ws, rep):
    res = evaluate(rep, ws / 'labels.json')
    assert res['exact_match'] == res['invoices'], res['mismatches']
    assert all(m['fp'] == 0 and m['fn'] == 0 for m in res['per_code'].values())


def test_money_at_risk_is_the_sum_of_distinct_invoices(rep):
    per = {}
    originals = {i.key for i in rep.invoices if not i.duplicate_of}
    for it in rep.items:
        if it.status == 'AT_RISK' and it.invoice_keys[0] in originals:
            per[it.invoice_keys[0]] = max(per.get(it.invoice_keys[0], Decimal(0)), it.amount)
    assert rep.totals['at_risk_vat'] == sum(per.values()) and rep.totals['at_risk_invoices'] == len(per)
    assert rep.totals['penalty_estimate'] == (rep.totals['at_risk_vat'] * Decimal('0.20')).quantize(Decimal(1))
    assert all('DRAFT' in it.basis[-1] for it in rep.items)


def test_same_inputs_give_the_same_report(ws, rep):
    again = pipeline.run(ws, pipeline.DEFAULT_RULESET, AS_OF)
    assert report.to_json(again) == report.to_json(rep)


def test_policy_flags_never_change_rule_results(ws, rep):
    flagged = {f.invoice_keys[0] for f in rep.policy_flags}
    assert len(flagged) == 2
    assert all(it.code.startswith('R') for it in rep.items)


def test_report_files_render(ws, rep, tmp_path):
    paths = report.write(rep, tmp_path / 'out')
    doc = lhtml.fromstring(paths['html'].read_text(encoding='utf-8'))
    assert 'Dữ liệu mô phỏng' in doc.text_content() and 'DRAFT' in doc.text_content()
    assert report.money(rep.totals['at_risk_vat']) in doc.text_content()
    assert json.loads(paths['json'].read_text(encoding='utf-8'))['totals']['at_risk_vat'] == str(rep.totals['at_risk_vat'])


def test_law_change_impact_respects_effective_dates(ws, rep):
    after = pipeline.run(ws, HYPOTHETICAL, AS_OF)
    res = impact.compare(rep, after)
    removed = {c['key']: c['removed'] for c in res['changes']}
    assert sum('R02_SAME_DAY_CUMULATIVE' in v for v in removed.values()) == 3
    july_cash = [it for it in rep.items if it.code == 'R01_PAYMENT_EVIDENCE' and any(
        i.key == it.invoice_keys[0] and i.issue_date.month == 7 for i in rep.invoices)]
    assert july_cash and all(it.invoice_keys[0] not in removed for it in july_cash)
    assert res['delta'] < 0


def test_not_claimed_decision_removes_risk_but_keeps_audit_trail(ws, rep):
    dup = next(it for it in rep.items if it.code == 'R05_DUPLICATE')
    key = dup.invoice_keys[0]
    decided = pipeline.run(ws, pipeline.DEFAULT_RULESET, AS_OF, extra_decisions={
        key: dict(invoice_key=key, action='NOT_CLAIMED', evidence='Bản trùng, không đưa vào tờ khai', by='Kế toán trưởng')})
    after = [it for it in decided.items if key in it.invoice_keys and it.code == 'R05_DUPLICATE']
    assert after and all(it.status == 'INFO' and it.amount == 0 and 'Kế toán trưởng' in it.detail for it in after)
    assert decided.totals['at_risk_vat'] == rep.totals['at_risk_vat']  # duplicate copy was never counted twice


def test_calendar_has_cit_deadlines_and_moves_deadlines_off_weekends(ws, rep):
    cal = {c['period']: c for c in rep.calendar}
    vat_aug = cal['Tờ khai thuế GTGT tháng 08/2026']
    assert vat_aug['due'] == date(2026, 9, 21) and vat_aug['moved_from'] == date(2026, 9, 20)        # 20/09/2026 is a Sunday
    q3 = cal['Tạm nộp thuế TNDN quý 3/2026']
    assert q3['due'] == date(2026, 11, 2) and 'Điều 24' in q3['basis'] and '245/2026' in q3['extension']
    assert cal['Quyết toán thuế TNDN năm 2026']['due'] == date(2027, 3, 31)
