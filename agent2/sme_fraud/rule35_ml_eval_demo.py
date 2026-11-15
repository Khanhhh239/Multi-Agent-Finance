"""Deterministic >5-candidate synthetic evaluation generator for 35-rule vs 35-rule + ML trials.

No ground-truth or split labels are embedded into snapshot payloads. History/reference
records end strictly before evaluation_start, while evaluation snapshots share the
prior timeline as read-only history_only context (excluded from candidate_transaction_ids).
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
import random

from .accounting import enrich_accounting
from .generate import TZ, stamp
from .import_files import canonical, digest
from .native_rule_demo import approved, authorities, base, evidence
from .native_rule_node import TABLES, VERSION as NATIVE_VERSION
from .rule_snapshot import CONTRACT

FIT_END = '2026-09-21T00:00:00+07:00'
EVAL_AS_OF = '2026-10-20T00:00:00+07:00'
COMPANY_METHODS = {'C001': 'isolation_forest', 'C002': 'ecod'}
PERIODS = dict(
    history_start='2026-07-01T00:00:00+07:00',
    history_end='2026-08-31T23:59:59+07:00',
    reference_start='2026-09-01T00:00:00+07:00',
    reference_end='2026-09-21T00:00:00+07:00',
    evaluation_start='2026-10-01T00:00:00+07:00',
)


def fit_config(snapshot_id, method_id):
    return dict(
        version='company-fit-config/1.0.0',
        snapshot_id=snapshot_id,
        method_id=method_id,
        missing_policy='median_flags',
        minimum_history=15,
        profile_id='rule35-ml-eval-v1',
        evaluation_mode='backtest',
        **PERIODS,
    )


def _finalize(c, *, tenant_id, company_id, as_of, candidate_ids, source_id):
    c.tables['transactions'] = c.rows
    for rows in c.tables.values():
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict) and 'company_id' in row:
                    row['company_id'] = company_id
    enrich_accounting(c.tables, 20261115)
    tables = {name: deepcopy(c.tables.get(name, [])) for name in TABLES}
    for name, rows in tables.items():
        for row in rows:
            row['company_id'] = company_id
            if name == 'companies':
                row.setdefault('recorded_at', '2023-01-01T00:00:00+07:00')
            if 'observed_at' not in row:
                row['observed_at'] = row.get('recorded_at') or row.get('posted_at') or '2023-01-01T00:00:00+07:00'
    # Align calendar/company history cutoff to evaluation/fit as_of.
    coverage = {
        name: dict(
            status='complete',
            observed_at=as_of,
            covered_from='2023-01-01T00:00:00+07:00',
            covered_through=as_of,
            history_basis='since_inception',
            record_count=len(rows),
            records_sha256=digest(canonical(rows)),
        )
        for name, rows in tables.items()
    }
    source = dict(
        version=NATIVE_VERSION,
        tenant_id=tenant_id,
        company_id=company_id,
        as_of=as_of,
        source_id=source_id,
        is_simulated=True,
        tables=tables,
        coverage=coverage,
    )
    return dict(
        contract_version=CONTRACT,
        tenant_id=tenant_id,
        company_id=company_id,
        source=source,
        candidate_transaction_ids=list(candidate_ids),
    )


def _seed_baseline_tables(c, company_id, scale, at_ref):
    c.at = at_ref
    c.director.update(
        employee_id=f'{company_id}_EMP_DIR',
        full_name=f'{company_id} Director',
        bank_account=f'{company_id}_STAFF_DIR_BANK',
        bank_code='SIMBANK',
        phone='0901000010',
        address=f'{company_id} Staff Addr 10',
        approval_limit_vnd=500_000_000 * scale,
        self_approval_limit_vnd=5_000_000 * scale,
    )
    c.maker.update(
        employee_id=f'{company_id}_EMP_MAKER',
        full_name=f'{company_id} Maker',
        bank_account=f'{company_id}_STAFF_MAKER_BANK',
        bank_code='SIMBANK',
        phone='0901000011',
        address=f'{company_id} Staff Addr 11',
        approval_limit_vnd=200_000_000 * scale,
        self_approval_limit_vnd=2_000_000 * scale,
    )
    c.worker.update(
        employee_id=f'{company_id}_EMP_WORKER',
        full_name=f'{company_id} Worker',
        bank_account=f'{company_id}_STAFF_WORKER_BANK',
        bank_code='SIMBANK',
        phone='0901000012',
        address=f'{company_id} Staff Addr 12',
        approval_limit_vnd=5_000_000 * scale,
        self_approval_limit_vnd=1_000_000 * scale,
    )
    for emp in (c.director, c.maker, c.worker):
        c.g.employees[emp['employee_id']] = emp
    c.vendor.update(
        vendor_id=f'{company_id}_V_PRIMARY',
        name=f'{company_id} Mekong Precision Trading Co',
        representative_id=f'{company_id}_REP_MAIN',
        bank_account=f'{company_id}_VEND_MAIN_BANK',
        bank_code='SIMBANK',
        phone='0908111001',
        address=f'10 Nguyen Hue, {company_id}',
        national_id=f'{company_id}_NAT_MAIN',
        tax_code=f'{company_id}_TAX_MAIN',
        registered_at='2022-01-10T00:00:00+07:00',
        onboarded_at='2022-02-01T00:00:00+07:00',
        recorded_at='2023-01-01T00:00:00+07:00',
        observed_at='2023-01-01T00:00:00+07:00',
    )
    authorities(c)
    # Replace self-approve authority with maker's scaled self limit.
    c.tables['approval_authorities'][0]['max_amount_vnd'] = 2_000_000 * scale
    c.tables['companies'][0]['company_id'] = company_id
    c.tables['companies'][0]['saturday_operations'] = 0

    c.tables['vendor_status_history'] = [
        dict(
            vendor_id=c.vendor['vendor_id'],
            company_id=company_id,
            status='active',
            effective_at='2023-01-01T00:00:00+07:00',
            observed_at='2023-01-01T00:00:00+07:00',
        )
    ]

    # Seed supporting evidence/master tables using exact exception_validation PROFILES schemas.
    evidence(c, 'operating_schedules', schedule_id=f'{company_id}_SCHED_STD',
             action='all', weekdays='0,1,2,3,4', start_time='08:00', end_time='18:00',
             holiday_work_allowed=0,
             effective_from='2023-01-01T00:00:00+07:00', effective_to='2027-12-31T23:59:59+07:00')
    evidence(c, 'workflow_policies', workflow_policy_id=f'{company_id}_WF_BASE',
             control_id=f'{company_id}_CTRL_STD', txn_type='vendor_payment', required=1,
             allow_override=0, authorized_override_roles='', override_max_vnd=0,
             effective_from='2023-01-01T00:00:00+07:00', effective_to='2027-12-31T23:59:59+07:00')
    evidence(c, 'closing_periods', closing_id=f'{company_id}_CLOSE_09',
             period_start='2026-09-01', period_end='2026-09-30', closing_at='2026-09-30T23:59:59+07:00')
    evidence(c, 'materiality_policies', policy_id=f'{company_id}_MAT_STD',
             effective_from='2023-01-01', effective_to='2027-12-31', materiality_vnd=50_000_000 * scale)
    evidence(c, 'document_series', series_id=f'{company_id}_SER_INV', fiscal_year=2026,
             document_type='invoice', start_number=1, closed_through_number=100,
             closed_at='2026-10-19T23:59:59+07:00', cancellation_log_complete=1)

    c.tables['advances'] = [dict(
        advance_id=f'{company_id}_ADV_01',
        company_id=company_id,
        employee_id=c.worker['employee_id'],
        issued_at='2026-07-01T09:00:00+07:00',
        original_amount_vnd=5_000_000 * scale,
        original_due_at='2026-12-31T17:00:00+07:00',
        recorded_at='2026-07-01T09:00:00+07:00',
        observed_at='2026-07-01T09:00:00+07:00',
    )]


def _add_clean_payment(c, tx_id, at, amount, *, vendor=None, scale=1, company_id='C001',
                       hour_override=None, doc=True, invoice_gross_vnd=None, invoice_number=None,
                       approver_id=None, bank_code='SIMBANK', bank_account=None, imbalance=0):
    v = vendor or c.vendor
    ts_at = at if hour_override is None else at.replace(hour=hour_override)
    inv_no = invoice_number or f'INV_{tx_id}'
    inv_gross = int(invoice_gross_vnd if invoice_gross_vnd is not None else amount)
    tx = c.pay(
        ts_at,
        int(amount),
        vendor=v,
        approver_id=approver_id or c.director['employee_id'],
        created_at=stamp(ts_at - timedelta(minutes=20)),
        approved_at=stamp(ts_at - timedelta(minutes=2)),
        invoice_number=inv_no,
        invoice_gross_vnd=inv_gross,
        recipient_account=bank_account if bank_account is not None else v['bank_account'],
        recipient_bank_code=bank_code,
        support_doc_count=1 if doc else 0,
        goods_receipt_verified=1 if doc else 0,
        approval_limit_vnd=500_000_000 * scale,
    )
    tx['transaction_id'] = tx_id
    tx['company_id'] = company_id
    if imbalance:
        c.tables.setdefault('journal_lines', []).append(dict(
            line_id=f'JL_IMB_{tx_id}',
            document_id=f'JD_IMB_{tx_id}',
            transaction_id=tx_id,
            company_id=company_id,
            posted_at=tx['posted_at'],
            observed_at=tx['posted_at'],
            account_code='112',
            debit_vnd=0,
            credit_vnd=int(imbalance),
            vendor_id=v['vendor_id'],
            employee_id='',
            customer_id='',
        ))
    if doc:
        c.tables['transaction_documents'].append(dict(
            record_id=f'DOC_{tx_id}',
            company_id=company_id,
            transaction_id=tx_id,
            vendor_id=v['vendor_id'],
            document_type='invoice',
            invoice_number=inv_no,
            invoice_gross_vnd=inv_gross,
            status='verified',
            evidence_id=f'EV_{tx_id}',
            verifier_id=c.director['employee_id'],
            verified_at=stamp(ts_at - timedelta(minutes=10)),
            observed_at=stamp(ts_at),
        ))
    return tx


def _add_history_and_reference(c, company_id, scale, prefix):
    rng = random.Random(20261115 + (1 if company_id == 'C001' else 2))
    history_ids = []
    # 30 history payments in July-August 2026, strictly Monday-Friday daytime.
    day = datetime(2026, 7, 1, 10, 15, tzinfo=TZ)
    idx = 0
    while idx < 30:
        if day.weekday() < 5:
            idx += 1
            amt = (1_050_000 + rng.randint(0, 45) * 13_700) * scale
            tid = f'{prefix}_HIST_{idx:02d}'
            _add_clean_payment(c, tid, day, amt, scale=scale, company_id=company_id, doc=True)
            history_ids.append(tid)
        day += timedelta(days=1)

    # 10 reference payments in Sep 1..18, 2026.
    ref_day = datetime(2026, 9, 1, 10, 30, tzinfo=TZ)
    r_idx = 0
    while r_idx < 10:
        if ref_day.weekday() < 5:
            r_idx += 1
            amt = (1_120_000 + rng.randint(0, 35) * 11_300) * scale
            tid = f'{prefix}_REF_{r_idx:02d}'
            _add_clean_payment(c, tid, ref_day, amt, scale=scale, company_id=company_id, doc=True)
            history_ids.append(tid)
        ref_day += timedelta(days=1)
    # Include baseline clean payroll entries in fit/reference windows so normal payroll is modeled.
    for m_idx, p_day in enumerate((datetime(2026, 8, 25, 10, 0, tzinfo=TZ), datetime(2026, 9, 18, 10, 0, tzinfo=TZ)), start=1):
        p_id = f'{prefix}_PAY_{m_idx:02d}'
        _add_payroll_tx(c, p_id, p_day, 14_200_000 * scale, company_id=company_id, scale=scale, terminated=False)
        history_ids.append(p_id)
    return history_ids


def build_fit_source(company_id='C001', tenant_id='demo'):
    """Build strictly pre-evaluation fit + reference bundle (40 history/ref transactions)."""
    scale = 1 if company_id == 'C001' else 3
    c = base()
    _seed_baseline_tables(c, company_id, scale, datetime(2026, 7, 1, 10, 0, tzinfo=TZ))
    hist_ids = _add_history_and_reference(c, company_id, scale, f'{company_id}_PRE')
    return _finalize(
        c,
        tenant_id=tenant_id,
        company_id=company_id,
        as_of=FIT_END,
        candidate_ids=hist_ids[-10:],
        source_id=f'synthetic-{company_id.lower()}-fit-baseline-v1',
    )


def _add_payroll_tx(c, tx_id, at, amount, *, company_id, scale, terminated=False):
    tx = c.pay(at, int(amount), kind='payroll', employee_id=c.worker['employee_id'],
               created_at=stamp(at - timedelta(minutes=20)),
               approved_at=stamp(at - timedelta(minutes=2)),
               support_doc_count=1)
    tx['transaction_id'] = tx_id
    tx['company_id'] = company_id
    period = '2026-10'
    tx['payroll_period'] = period
    c.tables['attendance'].append(dict(
        company_id=company_id,
        employee_id=c.worker['employee_id'],
        payroll_period=period,
        observed_at=stamp(at - timedelta(hours=2)),
        days_worked_observed=22,
        approved_leave_days=0,
        alternative_work_evidence=0,
    ))
    evidence(
        c, 'payroll_entitlements',
        entitlement_id=f'ENT_{tx_id}',
        company_id=company_id,
        employee_id=c.worker['employee_id'],
        payroll_period=period,
        leave_type='regular_payroll',
        required_work_days=22,
        approved_paid_leave_days=0,
        entitled_amount_vnd=int(amount),
        observed_at=stamp(at - timedelta(hours=2)),
    )
    if terminated:
        evidence(
            c, 'employment_events',
            employment_event_id=f'{company_id}_TERM_01',
            company_id=company_id,
            employee_id=c.worker['employee_id'],
            event_type='termination',
            effective_date='2026-09-25',
            observed_at='2026-09-25T17:00:00+07:00',
        )
        evidence(
            c, 'payroll_settlements',
            settlement_id=f'{company_id}_SETTLE_01',
            company_id=company_id,
            employee_id=c.worker['employee_id'],
            transaction_id=tx_id,
            payroll_period=period,
            payment_kind='regular_salary',
            service_period_start='2026-10-01',
            service_period_end='2026-10-10',
            authorized_amount_vnd=int(amount),
            observed_at=stamp(at),
        )
    return tx


def build_eval_source(company_id='C001', tenant_id='demo'):
    """Build 40-history + 25-candidate evaluation bundle tailored cleanly per company."""
    scale = 1 if company_id == 'C001' else 3
    c = base()
    _seed_baseline_tables(c, company_id, scale, datetime(2026, 7, 1, 10, 0, tzinfo=TZ))
    _add_history_and_reference(c, company_id, scale, f'{company_id}_PRE')

    cands = []
    if company_id == 'C001':
        # 1-2: Simultaneous P1 invoice overrun (2 atomic slots).
        t_p1 = datetime(2026, 10, 2, 10, 0, tzinfo=TZ)
        for suffix, amt in (('01_P1A', 15_000_000), ('02_P1B', 14_000_000)):
            tid = f'C1_EV_{suffix}'
            cands.append(tid)
            _add_clean_payment(c, tid, t_p1, amt, scale=scale, company_id=company_id,
                               invoice_number='INV_C1_P1_OVER', invoice_gross_vnd=18_000_000)

        # 3: C2 self-approval exceeding maker self_approval_limit_vnd (1 slot -> total 3/5 rule hits).
        cands.append('C1_EV_03_C2')
        _add_clean_payment(c, 'C1_EV_03_C2', datetime(2026, 10, 5, 10, 0, tzinfo=TZ), 16_000_000,
                           scale=scale, company_id=company_id, approver_id=c.maker['employee_id'])

        # 4: Master-quality overlap control (B5/E4 shared vendor bank & phone, 0 rule alert).
        v_dup = deepcopy(c.vendor)
        v_dup.update(
            vendor_id='C001_V_DUP_BANK',
            name='Red River Components JSC',
            representative_id='C001_REP_DUP',
            national_id='C001_NAT_UNIQ',
            tax_code='C001_TAX_UNIQ',
            address='99 Tran Hung Dao, Hanoi',
        )
        c.tables['vendors'].append(v_dup)
        cands.append('C1_EV_04_B5E4')
        _add_clean_payment(c, 'C1_EV_04_B5E4', datetime(2026, 10, 6, 10, 0, tzinfo=TZ), 1_240_000,
                           vendor=v_dup, scale=scale, company_id=company_id)

        # 5: Context-only C1 (after hours, clean valid small payment, 0 alert).
        cands.append('C1_EV_05_C1CTX')
        _add_clean_payment(c, 'C1_EV_05_C1CTX', datetime(2026, 10, 7, 21, 30, tzinfo=TZ), 1_190_000,
                           scale=scale, company_id=company_id)

        # 6: Payroll non-applicable vendor-rule check.
        cands.append('C1_EV_06_PAYROLL')
        _add_payroll_tx(c, 'C1_EV_06_PAYROLL', datetime(2026, 10, 8, 10, 0, tzinfo=TZ), 14_500_000,
                        company_id=company_id, scale=scale, terminated=False)

        # 7-8: Two high-magnitude multi-feature anomalies WITHOUT rule hits -> ML ranks #1 & #2 cleanly.
        v_clean_alt = deepcopy(c.vendor)
        v_clean_alt.update(
            vendor_id='C001_V_CLEAN_ALT',
            name='Dong Nai Automation Systems Ltd',
            representative_id='C001_REP_CLEAN_ALT',
            bank_account='C001_VEND_ALT_BANK',
            phone='0908999111',
            address='45 Vo Van Tan, HCMC',
            national_id='C001_NAT_ALT',
            tax_code='C001_TAX_ALT',
        )
        c.tables['vendors'].append(v_clean_alt)
        cands.append('C1_EV_07_ML_CLEAN')
        _add_clean_payment(c, 'C1_EV_07_ML_CLEAN', datetime(2026, 10, 9, 14, 0, tzinfo=TZ), 84_317_250,
                           vendor=v_clean_alt, scale=scale, company_id=company_id, doc=False, imbalance=12_000_000)

        cands.append('C1_EV_08_ML_SECOND')
        _add_clean_payment(c, 'C1_EV_08_ML_SECOND', datetime(2026, 10, 12, 15, 0, tzinfo=TZ), 68_421_900,
                           vendor=v_clean_alt, scale=scale, company_id=company_id, doc=False, imbalance=8_500_000)

        # 9-25 (17 rows including shared cross-company ID SHARED_AUDIT_00): clean normal controls.
        day = datetime(2026, 10, 13, 10, 0, tzinfo=TZ)
        for i in range(16):
            while day.weekday() >= 5:
                day += timedelta(days=1)
            tid = f'C1_EV_{9 + i:02d}_NORM'
            cands.append(tid)
            _add_clean_payment(c, tid, day + timedelta(minutes=i * 15), 1_080_000 + i * 19_500,
                               scale=scale, company_id=company_id)
            if i % 4 == 3:
                day += timedelta(days=1)
        cands.append('SHARED_AUDIT_00')
        _add_clean_payment(c, 'SHARED_AUDIT_00', datetime(2026, 10, 16, 11, 0, tzinfo=TZ), 1_210_000,
                           scale=scale, company_id=company_id)

    elif company_id == 'C002':
        # 1: A6 rounded overrun over invoice gross (1 slot).
        cands.append('C2_EV_01_A6')
        _add_clean_payment(c, 'C2_EV_01_A6', datetime(2026, 10, 2, 10, 0, tzinfo=TZ), 7_500_000,
                           scale=scale, company_id=company_id, invoice_gross_vnd=7_489_123)

        # 2: B1 vendor bank matches worker bank (1 slot).
        v_b1 = deepcopy(c.vendor)
        v_b1.update(vendor_id='C002_V_B1', name='Saigon Harbor Logistics', representative_id='C002_REP_B1',
                    bank_account=c.worker['bank_account'], phone='0908222111', address='25 Bach Dang, HCMC',
                    national_id='C002_NAT_B1', tax_code='C002_TAX_B1')
        c.tables['vendors'].append(v_b1)
        cands.append('C2_EV_02_B1')
        _add_clean_payment(c, 'C2_EV_02_B1', datetime(2026, 10, 5, 10, 0, tzinfo=TZ), 4_200_000,
                           vendor=v_b1, scale=scale, company_id=company_id)

        # 3: B2 vendor shares phone & address with worker (1 slot).
        v_b2 = deepcopy(c.vendor)
        v_b2.update(vendor_id='C002_V_B2', name='Ben Thanh Freight Ltd', representative_id='C002_REP_B2',
                    bank_account='C002_VEND_B2_BANK', phone=c.worker['phone'], address=c.worker['address'],
                    national_id='C002_NAT_B2', tax_code='C002_TAX_B2')
        c.tables['vendors'].append(v_b2)
        cands.append('C2_EV_03_B2')
        _add_clean_payment(c, 'C2_EV_03_B2', datetime(2026, 10, 6, 10, 0, tzinfo=TZ), 4_500_000,
                           vendor=v_b2, scale=scale, company_id=company_id)

        # 4: E2 payroll regular salary after termination effective_date (1 slot -> total 4/5 rule hits!).
        cands.append('C2_EV_04_E2')
        _add_payroll_tx(c, 'C2_EV_04_E2', datetime(2026, 10, 7, 10, 0, tzinfo=TZ), 18_000_000,
                        company_id=company_id, scale=scale, terminated=True)

        # 5: B5/E4 master-quality shared vendor overlap (0 alert).
        v_dup = deepcopy(c.vendor)
        v_dup.update(vendor_id='C002_V_DUP', name='Delta Spare Parts Co', representative_id='C002_REP_DUP',
                     national_id='C002_NAT_DUP', tax_code='C002_TAX_DUP', address='88 Dong Khoi, HCMC')
        c.tables['vendors'].append(v_dup)
        cands.append('C2_EV_05_B5E4')
        _add_clean_payment(c, 'C2_EV_05_B5E4', datetime(2026, 10, 8, 10, 0, tzinfo=TZ), 3_480_000,
                           vendor=v_dup, scale=scale, company_id=company_id)

        # 6: F4 scope-level receivable diagnostic seeded separately + clean payment row.
        evidence(c, 'receivable_invoices', invoice_id='C002_REC_OLD', customer_id=c.tables['customers'][0]['customer_id'],
                 gross_vnd=25_000_000, issued_at='2026-06-01T10:00:00+07:00', due_at='2026-07-01T10:00:00+07:00',
                 status='issued', observed_at='2026-06-01T10:00:00+07:00', evidence_id='C002_EV_REC')
        evidence(c, 'receipt_coverage', coverage_id='C002_REC_COV', covered_from='2026-06-01T00:00:00+07:00',
                 covered_through=EVAL_AS_OF, observed_at=EVAL_AS_OF)
        cands.append('C2_EV_06_CTRL')
        _add_clean_payment(c, 'C2_EV_06_CTRL', datetime(2026, 10, 9, 10, 0, tzinfo=TZ), 3_520_000,
                           scale=scale, company_id=company_id)

        # 7: Clean high-magnitude outlier without any rule hit -> ECOD fills the 5th slot!
        cands.append('C2_EV_07_ML_CLEAN')
        _add_clean_payment(c, 'C2_EV_07_ML_CLEAN', datetime(2026, 10, 12, 16, 0, tzinfo=TZ), 175_642_300,
                           scale=scale, company_id=company_id, doc=False, imbalance=20_000_000)

        # 8-25 (17 clean normal payments + SHARED_AUDIT_00 isolated to C002).
        day = datetime(2026, 10, 13, 10, 0, tzinfo=TZ)
        for i in range(17):
            while day.weekday() >= 5:
                day += timedelta(days=1)
            tid = f'C2_EV_{8 + i:02d}_NORM'
            cands.append(tid)
            _add_clean_payment(c, tid, day + timedelta(minutes=i * 15), 3_300_000 + i * 31_700,
                               scale=scale, company_id=company_id)
            if i % 4 == 3:
                day += timedelta(days=1)
        cands.append('SHARED_AUDIT_00')
        _add_clean_payment(c, 'SHARED_AUDIT_00', datetime(2026, 10, 16, 11, 0, tzinfo=TZ), 3_690_000,
                           scale=scale, company_id=company_id)
    else:
        raise ValueError(f'Unsupported company {company_id}')

    assert len(cands) == 25, f'{company_id} expected 25 candidates, got {len(cands)}'
    return _finalize(
        c,
        tenant_id=tenant_id,
        company_id=company_id,
        as_of=EVAL_AS_OF,
        candidate_ids=cands,
        source_id=f'synthetic-{company_id.lower()}-eval-25cand-v1',
    )
