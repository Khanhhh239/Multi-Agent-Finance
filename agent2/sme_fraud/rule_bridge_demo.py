"""Synthetic, disjoint history/reference/evaluation exports for bridge models.

No labels or expected findings enter either export. These are local backtest
fixtures, never a claim of sufficient training data for a real enterprise.
"""
from copy import deepcopy
from datetime import datetime, timedelta

from .generate import TZ, stamp
from .import_files import canonical, digest
from .native_rule_demo import base, finish
from .rule_snapshot import CONTRACT

VERSION = 'rule-bridge-company-demo/1.0.0'
COMPANIES = {'C001': 'isolation_forest', 'C002': 'ecod'}
PERIODS = dict(history_start='2025-06-01T00:00:00+07:00', history_end='2025-07-05T00:00:00+07:00',
               reference_start='2025-07-10T00:00:00+07:00', reference_end='2025-07-20T00:00:00+07:00',
               evaluation_start='2025-08-01T00:00:00+07:00')


def source_data(company):
    if company not in COMPANIES:
        raise ValueError('Only the explicitly simulated C001/C002 demo is supported')
    case = base()
    case.at = datetime(2025, 8, 6, 11, tzinfo=TZ)
    for name in ('employees', 'vendors', 'customers'):
        for record in case.tables[name]:
            record['recorded_at'] = record['observed_at'] = '2025-05-01T00:00:00+07:00'
    # The producer explicitly declares these synthetic identities and bank codes.
    # No missing real-world account/institution is filled by this producer.
    case.vendor['bank_account'] = 'SIM_DEMO_VENDOR_' + company
    case.vendor['bank_code'] = 'SIMBANK'
    scale = 1 if company == 'C001' else 4
    candidates = []
    dates = [(datetime(2025, 6, 1, 9, tzinfo=TZ) + timedelta(days=i, hours=i % 8), i) for i in range(32)]
    dates += [(datetime(2025, 7, 10, 9, tzinfo=TZ) + timedelta(days=i, hours=i % 8), 32 + i) for i in range(8)]
    dates += [(datetime(2025, 8, 1, 10, tzinfo=TZ) + timedelta(days=i, hours=i % 6), 40 + i) for i in range(5)]
    for at, index in dates:
        amount = (850_007 + ((index * 792_317 + 51_113) % 1_900_000)) * scale
        if index == 44:
            amount = 35_000_007 * scale
        row = case.pay(at, amount, invoice_number=f'SIM_BRIDGE_INV_{index:03}', invoice_gross_vnd=amount,
                       created_at=stamp(at - timedelta(minutes=25 + index % 15)), approved_at=stamp(at - timedelta(minutes=2)),
                       observed_at=stamp(at), recipient_account=case.vendor['bank_account'], recipient_bank_code='SIMBANK',
                       business_purpose='Thanh toan mo phong cho demo bridge')
        if index >= 40:
            candidates.append(row['transaction_id'])
    source = finish(case, company)
    source['tenant_id'] = 'demo'
    source['source_id'] = 'synthetic-rule-bridge-company-demo-v1'
    evaluation = _export(source, company, '2025-08-06T00:00:00+07:00', candidates)
    history = deepcopy(source)
    allowed = {r['transaction_id'] for r in history['tables']['transactions'][:40]}
    # Keep the exact same synthetic export facts, but physically exclude the
    # evaluation transactions and their linked records from the fit snapshot.
    for name, rows in history['tables'].items():
        history['tables'][name] = [r for r in rows if (not r.get('transaction_id') or r['transaction_id'] in allowed)
                                  and r['observed_at'] <= PERIODS['reference_end']]
    training = _export(history, company, PERIODS['reference_end'], [history['tables']['transactions'][-1]['transaction_id']])
    return training, evaluation


def _export(source, company, as_of, candidates):
    source['as_of'] = as_of
    for name, rows in source['tables'].items():
        source['coverage'][name].update(observed_at=as_of, covered_through=as_of,
                                        record_count=len(rows), records_sha256=digest(canonical(rows)))
    return dict(contract_version=CONTRACT, tenant_id='demo', company_id=company,
                source=source, candidate_transaction_ids=list(candidates))


def fit_config(snapshot_id, method):
    return dict(version='company-fit-config/1.0.0', snapshot_id=snapshot_id, method_id=method,
                missing_policy='median_flags', minimum_history=20, profile_id='synthetic-rule-bridge-demo-v1',
                evaluation_mode='backtest', **PERIODS)
