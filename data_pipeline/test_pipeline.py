"""Automated smoke generation, cross-agent export, v2 staging, and reconciliation tests.

Runs strictly inside a temporary directory (`tmp_path` / `TemporaryDirectory`) so git working
tree directories are never polluted.
"""
from __future__ import annotations

import csv
import json
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import duckdb
import pytest

REPO = Path(__file__).resolve().parents[1]
for rel in ('', 'agent1', 'agent2', 'agent3/agent3_tax_compliance', 'agent4', 'shared/finance_input/src'):
    p = str((REPO / rel).resolve())
    if p not in sys.path:
        sys.path.insert(0, p)

from data_pipeline import demo_inputs, enterprise, export, stage, validate


@pytest.fixture(scope='module')
def smoke_dataset(tmp_path_factory) -> dict:
    base = tmp_path_factory.mktemp('mpx10_smoke_e2e')
    ds_dir = base / 'dataset'
    demo_dir = base / 'demo_bundle'

    profile = json.loads((REPO / 'data_pipeline/profiles/enterprise_x10.json').read_text(encoding='utf-8'))
    profile['annual_invoice_counts'] = {k: max(360, int(v) // 1000) for k, v in profile['annual_invoice_counts'].items()}
    profile['annual_gross_revenue_vnd'] = {k: int(v) // 1000 for k, v in profile['annual_gross_revenue_vnd'].items()}
    profile.update(customers=180, vendors=120, employees=50, items=40, assets=10, contracts=20)

    t0 = time.perf_counter()
    model = enterprise.Enterprise(profile, ds_dir)
    try:
        model.run()
    finally:
        model.db.close()
    gen_sec = time.perf_counter() - t0

    t1 = time.perf_counter()
    export.export_agent1(ds_dir)
    a1_sec = time.perf_counter() - t1

    t2 = time.perf_counter()
    export.export_agent2(ds_dir)
    a2_sec = time.perf_counter() - t2

    t3 = time.perf_counter()
    export.export_agent3(ds_dir)
    a3_sec = time.perf_counter() - t3

    t4 = time.perf_counter()
    val_summary = validate.validate(ds_dir)
    val_sec = time.perf_counter() - t4

    demo_inputs.build(ds_dir, demo_dir)

    return {
        'dataset': ds_dir,
        'demo': demo_dir,
        'validation': val_summary,
        'timings': {
            'generate_sec': round(gen_sec, 3),
            'export_a1_sec': round(a1_sec, 3),
            'export_a2_sec': round(a2_sec, 3),
            'export_a3_sec': round(a3_sec, 3),
            'validate_sec': round(val_sec, 3),
        },
    }


def test_vnd_to_words_roundtrip():
    assert export.vnd_to_words(11_000_000) == 'Mười một triệu đồng chẵn'
    assert export.vnd_to_words(0) == 'Không đồng chẵn'
    samples = [
        0, 1, 5, 10, 11, 15, 20, 21, 25, 100, 101, 105, 115, 121, 125,
        1_000, 1_005, 1_015, 10_500, 500_000, 2_200_000, 3_300_000, 4_900_000,
        6_600_000, 11_000_000, 19_800_000, 19_900_000, 38_500_000, 250_000_000,
        999_999_999_999,
    ]
    for idx in range(1, 200):
        samples.append((idx * 17_389_421) % 900_000_000_000)
    for n in samples:
        words = export.vnd_to_words(n)
        parsed = validate._words_to_int(words)
        assert parsed == n, f'Mismatch for {n}: {words!r} -> {parsed}'


def test_enterprise_personas_and_ap_spread(smoke_dataset):
    con = duckdb.connect(str(smoke_dataset['dataset'] / 'warehouse.duckdb'), read_only=True)
    try:
        # 1. Verify distinct realized delay medians across PROMPT, STANDARD_CORP, CHRONIC_LATE
        delays = dict(
            con.execute("""
                WITH inv_settled AS (
                    SELECT i.invoice_id, cp.persona, date_diff('day', i.due_date, max(r.receipt_date)) delay_d
                    FROM ar_invoice i
                    JOIN customer_persona cp USING(customer_code)
                    JOIN ar_receipt r USING(invoice_id)
                    GROUP BY i.invoice_id, cp.persona, i.due_date, i.total_amount
                    HAVING sum(r.amount) = i.total_amount
                )
                SELECT persona, median(delay_d) FROM inv_settled GROUP BY persona
            """).fetchall()
        )
        assert delays['PROMPT'] <= -3, f'Expected PROMPT early settlement <= -3d, got {delays}'
        assert 0 <= delays['STANDARD_CORP'] <= 10, f'Expected STANDARD_CORP 0..10d, got {delays}'
        assert 18 <= delays['CHRONIC_LATE'] <= 55, f'Expected CHRONIC_LATE 18..55d, got {delays}'

        # 2. Verify CHRONIC_LATE split installments & DISPUTE_PRONE partial/withheld open balances
        multi_part_chronic = con.execute("""
            SELECT count(*) FROM (
                SELECT i.invoice_id
                FROM ar_invoice i
                JOIN customer_persona cp USING(customer_code)
                JOIN ar_receipt r USING(invoice_id)
                WHERE cp.persona = 'CHRONIC_LATE'
                GROUP BY i.invoice_id
                HAVING count(*) >= 2
            )
        """).fetchone()[0]
        partial_dispute = con.execute("""
            SELECT count(*) FROM (
                SELECT i.invoice_id, sum(r.amount) paid, i.total_amount tot
                FROM ar_invoice i
                JOIN customer_persona cp USING(customer_code)
                JOIN ar_receipt r USING(invoice_id)
                LEFT JOIN ar_adjustment a USING(invoice_id)
                WHERE cp.persona = 'DISPUTE_PRONE' AND a.invoice_id IS NULL
                GROUP BY i.invoice_id, i.total_amount
                HAVING sum(r.amount) > 0 AND sum(r.amount) < i.total_amount
            )
        """).fetchone()[0]
        assert multi_part_chronic > 10, 'Expected split installments for CHRONIC_LATE customers'
        assert partial_dispute > 0, 'Expected partial/withheld open invoices for DISPUTE_PRONE customers'

        # 3. Verify ap_bill.bill_date spreads across days of the month (not 100% on day 1)
        distinct_dom = con.execute('SELECT count(DISTINCT day(bill_date)) FROM ap_bill').fetchone()[0]
        assert distinct_dom >= 15, f'Expected ap_bill spread across >= 15 days of month, got {distinct_dom}'
    finally:
        con.close()


def test_export_and_stage_agent1(smoke_dataset):
    ds_dir = smoke_dataset['dataset']
    a1_res = stage.a1(ds_dir)
    assert a1_res['passed'] is True
    assert a1_res['longitudinal_months'] >= 45
    assert a1_res['reconciled_weeks'] >= 190
    assert a1_res['cash_sale_vnd'] > 0
    assert a1_res['variable_cost_vnd'] > 0
    assert a1_res['overdue_outflows'] > 0
    assert a1_res['upcoming_outflows'] > 0

    # Verify Agent 1 compact T1 Ledger & feature builder extracts differentiated customer_delay_180d across personas
    import pandas as pd
    from agent1.adaptive.compact_t1 import FEATURES, Ledger, prepare_features
    from agent1.adaptive.data import SCHEMAS, parse_rows, suggested_mapping

    data = {kind: [] for kind in SCHEMAS}
    for kind in SCHEMAS:
        for path in sorted((ds_dir / 'inputs/a1').rglob('*_' + kind + '.csv')):
            raw = pd.read_csv(path, dtype=str, keep_default_na=False)
            rows, errs, _ = parse_rows(raw, kind, suggested_mapping(raw.columns, kind), '%Y-%m-%d', 'plain')
            assert not errs
            data[kind].extend(rows)

    inv_df = pd.DataFrame(data['invoices'])
    pay_df = pd.DataFrame(data['payments']).rename(columns={'payment_date': 'date'})
    history = Ledger(inv_df, pay_df).snapshot('2026-10-14')
    opened = history[(history.remaining_amount > 0.01) & history.written_off_at.isna()].copy()
    assert len(opened) > 0
    X = prepare_features(opened, history, '2026-10-14')
    delay_col = X[:, FEATURES.index('customer_delay_180d')]
    assert float(delay_col.max() - delay_col.min()) > 15.0, 'Customer delay feature should differentiate personas!'


def test_export_and_stage_agent2_v2(smoke_dataset):
    ds_dir = smoke_dataset['dataset']
    # Verify tabular CSV preserves ground-truth anomalies & canonical fields
    tx_rows = list(demo_inputs.csv_rows(ds_dir / 'inputs/a2/transactions_full.csv'))
    by_id = {r['transaction_id']: r for r in tx_rows}
    for must_have in ('DUP-PAY', 'TEST-UNBALANCED', 'SPLIT-1', 'CSPLIT-1', 'WKND-SELF-1', 'SPIKE-ROUND-1', 'COLLUSION-PAY-1'):
        assert must_have in by_id, f'Missing seeded anomaly {must_have} in Agent 2 slice!'
    assert any(r['payment_channel'] == 'cash' for r in tx_rows)
    assert any(r['creator_id'] == r['approver_id'] for r in tx_rows)
    assert any(r['tax_deductible'] == '0' for r in tx_rows)
    assert any(r['vendor_id'] and r['counterparty_tax_code'] == '' for r in tx_rows)

    # Verify end-to-end Agent 2 v2 /api/v1/companies/MPX10/imports/{upload,preview,commit} staging
    a2_res = stage.a2(ds_dir)
    assert a2_res['passed'] is True
    assert 'DUP-PAY' in a2_res['canonical_rule_hits'].get('P1', [])
    assert len(a2_res['canonical_rule_hits'].get('E3', [])) > 0
    assert a2_res['feature_signal_counts']['self_approval_rows'] >= 2
    assert a2_res['feature_signal_counts']['employee_bank_overlap_rows'] >= 1
    assert a2_res['feature_signal_counts']['imbalanced_journal_rows'] >= 1


def test_export_and_stage_agent3_xml_and_ap_mix(smoke_dataset):
    ds_dir = smoke_dataset['dataset']
    a3_res = stage.a3(ds_dir)
    assert a3_res['passed'] is True
    assert a3_res['words_errors'] == 0
    assert a3_res['arith_errors'] == 0
    assert a3_res['matched_payments'] > 50
    assert a3_res['risk_by_code'].get('R02_SAME_DAY_CUMULATIVE', 0) >= 2
    assert a3_res['policy_flags'] >= 2

    # Spot-check an XML file directly for realistic <THHDVu>, integer <DGia>, and <TgTTTBChu>
    sample_zip = sorted((ds_dir / 'inputs/a3').rglob('purchase_*.zip'))[-1]
    with zipfile.ZipFile(sample_zip) as zf:
        sample_xml = ET.fromstring(zf.read(zf.namelist()[0]))
    desc = sample_xml.findtext('DLHDon/NDHDon/DSHHDVu/HHDVu/THHDVu') or ''
    dgia = sample_xml.findtext('DLHDon/NDHDon/DSHHDVu/HHDVu/DGia') or ''
    words = sample_xml.findtext('DLHDon/NDHDon/TToan/TgTTTBChu') or ''
    assert not desc.startswith('I00'), f'Expected realistic Vietnamese item name, got {desc}'
    assert '.' not in dgia and dgia.isdigit()
    assert words.endswith('đồng chẵn')


def test_validate_and_portal_demo_bundle(smoke_dataset):
    val = smoke_dataset['validation']
    failed = {k: v for k, v in val['checks'].items() if not v['pass']}
    assert val['all_pass'] is True, f'Validation checks failed: {failed}'
    assert all(g['passed'] for g in val['ground_truth'])

    demo_dir = smoke_dataset['demo']
    for fname in ('01_invoices.csv', '02_sao_ke_chung.csv', '03_transactions.csv', '03_agent2_bundle.json', '04_hoa_don.zip'):
        assert (demo_dir / fname).is_file(), f'Missing {fname} in demo bundle'

    # Verify portal/bank_intake.py and portal/agent2_intake.py parse the demo bundle cleanly
    from portal import agent2_intake, bank_intake

    norm_fn = lambda s: str(s).lower().replace('_', ' ').strip()  # noqa: E731
    bank_raw = (demo_dir / '02_sao_ke_chung.csv').read_bytes()
    header = next(bank_intake.csv_rows(bank_raw))
    assert bank_intake.columns(header, norm_fn) is not None

    csv_body, csv_sum = agent2_intake.build_contract(
        (demo_dir / '03_transactions.csv').read_bytes(), 'demo', 'MPX10', 'Minh Phát', name='03_transactions.csv'
    )
    assert len(csv_body) > 0 and csv_sum['rows'] > 0

    json_body, json_sum = agent2_intake.build_contract(
        (demo_dir / '03_agent2_bundle.json').read_bytes(), 'demo', 'MPX10', 'Minh Phát', name='03_agent2_bundle.json'
    )
    assert len(json_body) > 0 and json_sum['native_json'] is True and json_sum['rows'] > 100


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='mpx10_verify_') as tmp:
        class _Factory:
            def mktemp(self, name: str) -> Path:
                p = Path(tmp) / name
                p.mkdir(parents=True, exist_ok=True)
                return p

        bundle = smoke_dataset.__wrapped__(_Factory()) if hasattr(smoke_dataset, '__wrapped__') else None
        if bundle is None:
            raise SystemExit(pytest.main([__file__, '-v', '-s']))
        test_vnd_to_words_roundtrip()
        test_enterprise_personas_and_ap_spread(bundle)
        test_export_and_stage_agent1(bundle)
        test_export_and_stage_agent2_v2(bundle)
        test_export_and_stage_agent3_xml_and_ap_mix(bundle)
        test_validate_and_portal_demo_bundle(bundle)
        print('ALL PIPELINE TESTS PASSED:', json.dumps(bundle['timings'], indent=2))
