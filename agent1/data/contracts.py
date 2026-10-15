"""Hợp đồng dữ liệu của thế giới; lỗi được trả thành bảng, không sửa âm thầm."""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

from .. import calendar_vn as cal
from ..synth.names import valid_mst

SCHEMAS = {
    'invoices': ('invoice_id firm_id customer_id issue_date due_date amount_gross paid_date_true writeoff_date', ['invoice_id']),
    'payments': ('payment_id invoice_id ledger_invoice_id txn_id pay_date_true ledger_post_date amount kind', ['payment_id']),
    'bank_txns': ('txn_id firm_id value_date amount direction', ['txn_id']),
    'promises': ('invoice_id customer_id made_date promised_date kept', []),
    'outflows': ('firm_id date category amount known_in_advance', []),
    'firms': ('firm_id mst', ['firm_id']),
    'customers': ('customer_id firm_id mst', ['customer_id']),
    'events': ('firm_id customer_id type date magnitude', []),
    'macro': ('week common_factor covid_stress credit_crunch', ['week']),
    'daily_cash': ('firm_id date inflow_ar inflow_other outflow owner_draw balance opening_balance', ['firm_id', 'date']),
}
FORBIDDEN_FEATURES = frozenset({
    'paid_date_true', 'ledger_clear_date', 'label_date', 'remaining', 'event', 'time_obs', 'bad_known',
    'is_bad_debt', 'writeoff_date', 'paid_amount', 'days_late_true', 'dispute', 'partial',
    'liquidity_at_due', 'stress_at_due', 'ontime_logit', 'late_med', 'late_sig', 'reliability',
    'default_week', 'default_date', 'break_day', 'break_shift', 'pd_frailty', 'kept',
})


def validate_feature_columns(columns):
    """Chặn nhãn/biến tiềm ẩn lọt vào danh sách đặc trưng."""
    bad = FORBIDDEN_FEATURES.intersection(columns)
    if bad:
        raise ValueError(f'Đặc trưng cấm: {sorted(bad)}')


def validate_world(directory, *, raise_on_error=True):
    """Kiểm lược đồ, khoá, tham chiếu, tiền và số dư; trả bảng từng bất biến."""
    directory = Path(directory)
    tables, rows = {}, []

    def check(name, passed, detail=''):
        rows.append(dict(check=name, passed=bool(passed), detail=str(detail)))

    for name, (cols, key) in SCHEMAS.items():
        path = directory / f'{name}.parquet'
        check(f'{name}.exists', path.exists())
        if not path.exists():
            continue
        df = pd.read_parquet(path)
        tables[name] = df
        missing = set(cols.split()) - set(df.columns)
        check(f'{name}.columns', not missing, sorted(missing))
        if missing:
            continue
        if key:
            check(f'{name}.key', not df.duplicated(key).any() and not df[key].isna().any().any())
        for col in cols.split():
            if 'date' in col or col == 'week':
                check(f'{name}.{col}.dtype', pd.api.types.is_datetime64_any_dtype(df[col]))
        if 'amount' in df:
            check(f'{name}.amount', pd.api.types.is_numeric_dtype(df['amount']) and
                  np.isfinite(df['amount']).all() and (df['amount'] >= 0).all())
        if 'mst' in df:
            check(f'{name}.mst', df['mst'].map(lambda v: valid_mst(str(v))).all())

    def ready(*names):
        return all(n in tables and set(SCHEMAS[n][0].split()) <= set(tables[n]) for n in names)

    if ready('invoices'):
        inv = tables['invoices']
        check('invoices.amount_gross', np.isfinite(inv['amount_gross']).all() and (inv['amount_gross'] > 0).all())
        check('invoices.paid_after_issue', (inv['paid_date_true'].isna() | (inv['paid_date_true'] >= inv['issue_date'])).all())
        check('invoices.due_after_issue', (inv['due_date'] >= inv['issue_date']).all())
    for child, col, parent, pcol in [
        ('invoices', 'firm_id', 'firms', 'firm_id'), ('invoices', 'customer_id', 'customers', 'customer_id'),
        ('customers', 'firm_id', 'firms', 'firm_id'), ('payments', 'invoice_id', 'invoices', 'invoice_id'),
        ('payments', 'ledger_invoice_id', 'invoices', 'invoice_id'), ('payments', 'txn_id', 'bank_txns', 'txn_id'),
        ('promises', 'invoice_id', 'invoices', 'invoice_id'), ('promises', 'customer_id', 'customers', 'customer_id'),
        ('bank_txns', 'firm_id', 'firms', 'firm_id'), ('outflows', 'firm_id', 'firms', 'firm_id'),
        ('daily_cash', 'firm_id', 'firms', 'firm_id'),
    ]:
        if ready(child, parent):
            check(f'{child}.{col}.foreign_key', tables[child][col].isin(tables[parent][pcol]).all())
    if ready('invoices', 'customers'):
        j = tables['invoices'].merge(tables['customers'][['customer_id', 'firm_id']], on='customer_id', suffixes=('', '_customer'))
        check('invoices.customer_firm', (j['firm_id'] == j['firm_id_customer']).all())
    if ready('payments', 'invoices'):
        pay = tables['payments']
        amt = pay.groupby('invoice_id')['amount'].sum()
        gross = tables['invoices'].set_index('invoice_id')['amount_gross'].reindex(amt.index)
        check('payments.not_overpaid', (amt <= gross + 1.0).all())
        issue = tables['invoices'].set_index('invoice_id')['issue_date']
        check('payments.after_issue', (pay['pay_date_true'] >= pay['invoice_id'].map(issue)).all())
        dates = pay['pay_date_true'].dropna()
        calendar = {d: cal.is_business_day(d) for d in dates.unique()}
        bd = dates.map(calendar).mean() if len(dates) else 1.0
        check('payments.business_day_share', bd >= .985, f'{bd:.6f}')
        # FIFO cố ý gán nhầm ngày sổ giữa các HĐ; ngày sổ có thể trước ngày NH
        # của HĐ được gán. Đây là nhiễu nhãn cần đo, không phải bất biến nhân quả.
        check('payments.ledger_dates_present', pay['ledger_post_date'].notna().all(),
              f"fifo_precedes_true_share={(pay['ledger_post_date'] < pay['pay_date_true']).mean():.6f}")
    if ready('payments', 'bank_txns'):
        paid = tables['payments'].groupby('txn_id')['amount'].sum()
        bank = tables['bank_txns'].set_index('txn_id')
        fee = bank['fee_deducted'] if 'fee_deducted' in bank else 0
        check('bank_txns.amount_matches_payments', np.allclose(paid, (bank['amount'] + fee).reindex(paid.index), atol=1, rtol=1e-9))
    if ready('daily_cash'):
        d = tables['daily_cash'].sort_values(['firm_id', 'date'])
        net = d['inflow_ar'] + d['inflow_other'] - d['outflow'] - d['owner_draw']
        expected = net.groupby(d['firm_id']).cumsum() + d['opening_balance']
        check('daily_cash.balance', np.allclose(d['balance'], expected, atol=1, rtol=1e-9))
        check('daily_cash.finite', np.isfinite(d[['balance', 'opening_balance', 'outflow']]).all().all())
    from ..models.features import FEATURES
    validate_feature_columns(FEATURES)
    check('features.no_latent_columns', True)
    result = pd.DataFrame(rows)
    if raise_on_error and not result['passed'].all():
        raise ValueError('Hợp đồng dữ liệu không đạt: ' + ', '.join(result.loc[~result['passed'], 'check']))
    return result
