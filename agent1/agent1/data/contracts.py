"""Hợp đồng dữ liệu của thế giới; lỗi được trả thành bảng, không sửa âm thầm."""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

from .. import calendar_vn as cal
from .accounting import AMOUNT_TOLERANCE, BANK_FLOW_CLASS, derive_invoice_accounting, mark_observed_outcomes
from ..synth.names import valid_mst

SCHEMAS = {
    'invoices': ('invoice_id firm_id customer_id issue_date due_date amount_gross credit_note credit_note_date '
                 'paid_date_true paid_amount cash_received_amount writeoff_date writeoff_amount remaining_amount '
                 'closure_type closed_date_true observation_end outcome_status_at_end', ['invoice_id']),
    'payments': ('payment_id invoice_id ledger_invoice_id txn_id pay_date_true ledger_post_date amount kind', ['payment_id']),
    'bank_txns': ('txn_id firm_id value_date amount direction txn_type cash_flow_class '
                  'in_balance_window balance_effect', ['txn_id']),
    'promises': ('invoice_id customer_id made_date promised_date kept', []),
    'outflows': ('firm_id date category amount known_in_advance', []),
    'firms': ('firm_id mst revenue_annual cogs_ratio buffer_days opening_daily_outflow '
              'demand_exposure supply_exposure price_exposure credit_exposure', ['firm_id']),
    'customers': ('customer_id firm_id mst industry region demand_exposure '
                  'supply_exposure price_exposure credit_exposure', ['customer_id']),
    'events': ('firm_id customer_id type date magnitude previous_signal '
               'decision_threshold previous_threshold', []),
    'macro': ('week published_date covid_source common_factor covid_stress credit_crunch', ['week']),
    'daily_cash': ('firm_id date inflow_ar inflow_other inflow_financing inflow_internal '
                   'inflow_cash_deposit inflow_other_external inflow_unclassified outflow owner_draw '
                   'balance opening_balance balance_scope', ['firm_id', 'date']),
    'inventory_weekly': ('firm_id week booked_date booked_orders opening_inventory purchase_net '
                         'fulfilled_order_cost closing_inventory target_inventory purchase_date '
                         'supplier_pay_date purchase_gross demand_orders supply_capacity '
                         'sale_price_index input_cost_index', ['firm_id', 'week']),
    'shock_truth': ('episode_id week family phase strength reference_event industries regions',
                    ['episode_id', 'week']),
}
def validate_feature_columns(columns):
    """Chỉ các đặc trưng T1 đã đăng ký mới được vào mô hình."""
    from ..models.features import validate_feature_columns as validate_allowed
    validate_allowed(columns)


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
        credit = inv['credit_note'].fillna(0)
        check('invoices.credit_note_amount', np.isfinite(credit).all() and
              (credit >= 0).all() and (credit <= inv['amount_gross'] + AMOUNT_TOLERANCE).all())
        check('invoices.credit_note_date', (credit.gt(AMOUNT_TOLERANCE) == inv['credit_note_date'].notna()).all() and
              (inv['credit_note_date'].isna() | (inv['credit_note_date'] >= inv['issue_date'])).all())
        check('invoices.writeoff_after_issue', (inv['writeoff_date'].isna() |
              (inv['writeoff_date'] >= inv['issue_date'])).all())
        observed = mark_observed_outcomes(inv, inv['observation_end'].iloc[0])
        check('invoices.observation_end_constant', inv['observation_end'].eq(inv['observation_end'].iloc[0]).all())
        check('invoices.outcome_status_at_end', inv['outcome_status_at_end'].eq(
              observed['outcome_status_at_end']).all())
        check('invoices.bad_debt_confirmed_only', inv['is_bad_debt'].eq(observed['is_bad_debt']).all())
    if ready('shock_truth'):
        truth = tables['shock_truth']
        strength = pd.to_numeric(truth['strength'], errors='coerce').to_numpy(dtype=float)
        check('shock_truth.valid_path', truth['family'].isin(['demand', 'supply', 'price', 'credit']).all() and
              truth['phase'].isin(['calm', 'rise', 'shock', 'recovery']).all() and
              np.isfinite(strength).all() and (strength >= 0).all() and
              (strength[truth['phase'].eq('calm').to_numpy()] == 0).all())
    if ready('macro'):
        macro = tables['macro']
        check('macro.published_after_week', macro['published_date'].notna().all() and
              (macro['published_date'] >= macro['week'] + pd.Timedelta(days=7)).all())
        check('macro.covid_source', macro['covid_source'].isin(['oxcgrt', 'synthetic_fallback']).all())
    for name in ('firms', 'customers'):
        if ready(name):
            exposure = tables[name][['demand_exposure', 'supply_exposure',
                                     'price_exposure', 'credit_exposure']]
            check(f'{name}.exposure', np.isfinite(exposure).all().all() and exposure.gt(0).all().all())
    for child, col, parent, pcol in [
        ('invoices', 'firm_id', 'firms', 'firm_id'), ('invoices', 'customer_id', 'customers', 'customer_id'),
        ('customers', 'firm_id', 'firms', 'firm_id'), ('payments', 'invoice_id', 'invoices', 'invoice_id'),
        ('payments', 'ledger_invoice_id', 'invoices', 'invoice_id'), ('payments', 'txn_id', 'bank_txns', 'txn_id'),
        ('promises', 'invoice_id', 'invoices', 'invoice_id'), ('promises', 'customer_id', 'customers', 'customer_id'),
        ('bank_txns', 'firm_id', 'firms', 'firm_id'), ('outflows', 'firm_id', 'firms', 'firm_id'),
        ('daily_cash', 'firm_id', 'firms', 'firm_id'),
        ('inventory_weekly', 'firm_id', 'firms', 'firm_id'),
    ]:
        if ready(child, parent):
            check(f'{child}.{col}.foreign_key', tables[child][col].isin(tables[parent][pcol]).all())
    if ready('invoices', 'customers'):
        j = tables['invoices'].merge(tables['customers'][['customer_id', 'firm_id']], on='customer_id', suffixes=('', '_customer'))
        check('invoices.customer_firm', (j['firm_id'] == j['firm_id_customer']).all())
    if ready('promises', 'invoices'):
        prom = tables['promises']
        issue = tables['invoices'].set_index('invoice_id')['issue_date']
        check('promises.after_invoice', (prom['made_date'] >= prom['invoice_id'].map(issue)).all())
        check('promises.future_commitment', (prom['promised_date'] > prom['made_date']).all())
    if ready('events'):
        decisions = tables['events'][tables['events']['type'].isin(
            ['seller_credit_hold', 'seller_credit_release'])]
        hold = decisions['type'].eq('seller_credit_hold')
        valid_scores = np.where(hold,
                                (decisions['magnitude'] < decisions['decision_threshold']) &
                                (decisions['previous_signal'] < decisions['previous_threshold']),
                                (decisions['magnitude'] > decisions['decision_threshold']) &
                                (decisions['previous_signal'] > decisions['previous_threshold']))
        check('events.credit_decision_observed_signal', valid_scores.all())
        transitions = decisions.sort_values(['customer_id', 'date']).groupby('customer_id')['type'].apply(list)
        check('events.credit_decision_transitions', all(
            all(kind == ('seller_credit_hold' if i % 2 == 0 else 'seller_credit_release')
                for i, kind in enumerate(types)) for types in transitions))
        defaults = (tables['events'][tables['events']['type'].eq('customer_default')]
                    .groupby('customer_id')['date'].min())
        default_holds = tables['events'][tables['events']['type'].eq('seller_default_hold')]
        check('events.default_hold_after_event', not len(default_holds) or
              (default_holds['date'] > default_holds['customer_id'].map(defaults)).all())
    if ready('payments', 'invoices'):
        pay = tables['payments']
        normalized_amount = pay['amount'] - pay['fx_adjustment'] if 'fx_adjustment' in pay else pay['amount']
        amt = normalized_amount.groupby(pay['invoice_id']).sum()
        if 'fx_adjustment' in pay:
            check('payments.fx_normalized_nonnegative', (normalized_amount >= 0).all())
            currencies = tables['invoices'].set_index('invoice_id')['original_currency']
            check('payments.fx_only_foreign', ((pay.fx_adjustment == 0) | pay.invoice_id.map(currencies).eq('USD')).all())
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
        writeoff = tables['invoices'].set_index('invoice_id')['writeoff_date']
        check('payments.before_writeoff', (pay['invoice_id'].map(writeoff).isna() |
              (pay['pay_date_true'] <= pay['invoice_id'].map(writeoff))).all())
        expected = derive_invoice_accounting(tables['invoices'], pay)
        inv = tables['invoices']
        for col in ('paid_amount', 'cash_received_amount', 'writeoff_amount', 'remaining_amount'):
            check(f'invoices.{col}.reconciled', np.allclose(inv[col], expected[col], atol=AMOUNT_TOLERANCE, rtol=1e-9))
        for col in ('paid_date_true', 'ledger_clear_date', 'first_payment_date', 'closed_date_true'):
            if col not in inv:
                continue
            actual_date = pd.to_datetime(inv[col])
            correct_date = pd.to_datetime(expected[col])
            check(f'invoices.{col}.reconciled', (actual_date.eq(correct_date) |
                  (actual_date.isna() & correct_date.isna())).all())
        check('invoices.closure_type.reconciled', inv['closure_type'].eq(expected['closure_type']).all())
        check('invoices.not_overclosed', (inv['amount_gross'] - inv['credit_note'] -
              expected['paid_amount'] - expected['writeoff_amount'] >= -AMOUNT_TOLERANCE).all())
    if ready('payments', 'bank_txns'):
        paid = tables['payments'].groupby('txn_id')['amount'].sum()
        bank = tables['bank_txns'].set_index('txn_id')
        fee = bank['fee_deducted'] if 'fee_deducted' in bank else 0
        check('bank_txns.amount_matches_payments', np.allclose(paid, (bank['amount'] + fee).reindex(paid.index), atol=1, rtol=1e-9))
        check('bank_txns.payment_type', bank.reindex(paid.index)['txn_type'].eq('customer_payment').all())
    if ready('bank_txns'):
        bank = tables['bank_txns']
        check('bank_txns.cash_flow_class', bank['cash_flow_class'].eq(bank['txn_type'].map(BANK_FLOW_CLASS)).all())
        check('bank_txns.incoming_only', bank['direction'].eq('in').all())
        if ready('daily_cash'):
            daily = tables['daily_cash']
            inside = bank['value_date'].between(daily['date'].min(), daily['date'].max())
            check('bank_txns.balance_window', bank['in_balance_window'].eq(inside).all())
            expected_effect = np.where(inside, bank['amount'], 0.)
            check('bank_txns.balance_effect', np.allclose(bank['balance_effect'], expected_effect,
                  atol=AMOUNT_TOLERANCE, rtol=1e-9))
    if ready('daily_cash'):
        d = tables['daily_cash'].sort_values(['firm_id', 'date'])
        net = d['inflow_ar'] + d['inflow_other'] - d['outflow'] - d['owner_draw']
        expected = net.groupby(d['firm_id']).cumsum() + d['opening_balance']
        check('daily_cash.balance', np.allclose(d['balance'], expected, atol=1, rtol=1e-9))
        check('daily_cash.finite', np.isfinite(d[['balance', 'opening_balance', 'outflow']]).all().all())
        parts = ['inflow_financing', 'inflow_internal', 'inflow_cash_deposit',
                 'inflow_other_external', 'inflow_unclassified']
        check('daily_cash.other_breakdown', np.allclose(d[parts].sum(axis=1), d['inflow_other'], atol=1, rtol=1e-9))
        check('daily_cash.balance_scope', d['balance_scope'].eq('operating_bank_account').all())
        if ready('firms'):
            f = tables['firms'].set_index('firm_id')
            opening = d['firm_id'].map(f['buffer_days'] * f['opening_daily_outflow'])
            check('daily_cash.opening_from_initial_scale', np.allclose(d['opening_balance'], opening,
                  atol=1, rtol=1e-9))
            check('firms.opening_daily_outflow', np.isfinite(f['opening_daily_outflow']).all() and
                  f['opening_daily_outflow'].gt(0).all())
    if ready('inventory_weekly', 'firms'):
        stock = tables['inventory_weekly'].sort_values(['firm_id', 'week'])
        f = tables['firms'].set_index('firm_id')
        prior = stock.groupby('firm_id')['closing_inventory'].shift()
        first = 1.5 * stock['firm_id'].map(f['revenue_annual'] * f['cogs_ratio'] / 52)
        expected_open = prior.fillna(first)
        check('inventory_weekly.opening_rollforward', np.allclose(stock['opening_inventory'], expected_open,
              atol=1, rtol=1e-9))
        base_orders = stock['booked_orders'] / stock['sale_price_index']
        cost_factor = stock['firm_id'].map(f['cogs_ratio']) * stock['input_cost_index']
        check('inventory_weekly.fulfillment', np.allclose(stock['fulfilled_order_cost'],
              base_orders * cost_factor, atol=1, rtol=1e-9))
        trailing_orders = base_orders.groupby(stock['firm_id']).transform(
            lambda values: values.ewm(alpha=.3, adjust=False).mean())
        check('inventory_weekly.target_from_past_orders', np.allclose(stock['target_inventory'],
              1.5 * trailing_orders * cost_factor, atol=1, rtol=1e-9))
        check('inventory_weekly.shock_channels',
              np.isfinite(stock[['demand_orders', 'supply_capacity', 'sale_price_index',
                                 'input_cost_index']]).all().all() and
              stock['supply_capacity'].between(0, 1).all() and
              stock['sale_price_index'].gt(0).all() and stock['input_cost_index'].gt(0).all() and
              np.allclose(stock['booked_orders'], stock['demand_orders'] * stock['supply_capacity'],
                          atol=1, rtol=1e-9))
        expected_buy = np.maximum(0., stock['fulfilled_order_cost'] + stock['target_inventory'] - stock['opening_inventory'])
        check('inventory_weekly.purchase_policy', np.allclose(stock['purchase_net'], expected_buy,
              atol=1, rtol=1e-9))
        check('inventory_weekly.closing_rollforward', np.allclose(stock['closing_inventory'],
              stock['opening_inventory'] + stock['purchase_net'] - stock['fulfilled_order_cost'],
              atol=1, rtol=1e-9))
        check('inventory_weekly.purchase_after_booking',
              (stock['purchase_date'].isna() | (stock['purchase_date'] >= stock['booked_date'])).all())
        check('inventory_weekly.nonnegative', np.isfinite(stock[['booked_orders', 'opening_inventory',
              'purchase_net', 'fulfilled_order_cost', 'closing_inventory', 'target_inventory',
              'purchase_gross']]).all().all() and (stock[['booked_orders', 'opening_inventory',
              'purchase_net', 'fulfilled_order_cost', 'closing_inventory', 'target_inventory',
              'purchase_gross']] >= -AMOUNT_TOLERANCE).all().all())
    if ready('inventory_weekly', 'outflows'):
        stock, out = tables['inventory_weekly'], tables['outflows']
        if 'supplier_due_date' in stock or 'supplier_payment_mode' in stock:
            check('inventory_weekly.supplier_terms_columns',
                  {'supplier_due_date', 'supplier_payment_mode'} <= set(stock) and
                  'firms' in tables and 'supplier_payment_mode' in tables['firms'])
            if ({'supplier_due_date', 'supplier_payment_mode'} <= set(stock) and
                    'firms' in tables and 'supplier_payment_mode' in tables['firms']):
                bought = stock['purchase_gross'].gt(AMOUNT_TOLERANCE)
                mode = stock['firm_id'].map(tables['firms'].set_index('firm_id')['supplier_payment_mode'])
                cash = bought & mode.eq('cash')
                credit = bought & mode.eq('credit')
                check('inventory_weekly.supplier_payment_mode',
                      mode.isin(['cash', 'credit']).all() and stock['supplier_payment_mode'].eq(mode).all())
                check('inventory_weekly.supplier_date_order',
                      (stock.loc[bought, 'purchase_date'] <= stock.loc[bought, 'supplier_due_date']).all() and
                      (stock.loc[bought, 'supplier_due_date'] <= stock.loc[bought, 'supplier_pay_date']).all() and
                      stock.loc[~bought, ['purchase_date', 'supplier_due_date', 'supplier_pay_date']].isna().all().all())
                check('inventory_weekly.cash_supplier_immediate',
                      stock.loc[cash, 'purchase_date'].eq(stock.loc[cash, 'supplier_due_date']).all() and
                      stock.loc[cash, 'purchase_date'].eq(stock.loc[cash, 'supplier_pay_date']).all())
                check('inventory_weekly.credit_supplier_positive_term',
                      stock.loc[credit, 'supplier_due_date'].gt(stock.loc[credit, 'purchase_date']).all())
        purchases = stock.groupby(['firm_id', 'supplier_pay_date'])['purchase_gross'].sum()
        supplier = out[out['category'].eq('supplier')].groupby(['firm_id', 'date'])['amount'].sum()
        keys = purchases.index.union(supplier.index)
        check('inventory_weekly.supplier_cash_reconciled', np.allclose(
              purchases.reindex(keys, fill_value=0), supplier.reindex(keys, fill_value=0),
              atol=1, rtol=1e-9))
    if ready('daily_cash', 'bank_txns'):
        d, bank = tables['daily_cash'], tables['bank_txns']
        keys = pd.MultiIndex.from_frame(d[['firm_id', 'date']])
        observed = bank[bank['value_date'].between(d['date'].min(), d['date'].max())]
        check('bank_txns.within_cash_window', pd.MultiIndex.from_frame(
              observed[['firm_id', 'value_date']]).isin(keys).all())
        for column, flow_class in [('inflow_ar', 'ar'), ('inflow_financing', 'financing'),
                                   ('inflow_internal', 'internal_transfer'),
                                   ('inflow_cash_deposit', 'cash_to_bank'),
                                   ('inflow_other_external', 'other_external'),
                                   ('inflow_unclassified', 'unclassified')]:
            actual = observed.loc[observed['cash_flow_class'].eq(flow_class)].groupby(
                ['firm_id', 'value_date'])['balance_effect'].sum().reindex(keys, fill_value=0.)
            check(f'daily_cash.{column}.bank_reconciled', np.allclose(d[column], actual.to_numpy(), atol=1, rtol=1e-9))
    if ready('daily_cash', 'outflows'):
        d, out = tables['daily_cash'], tables['outflows']
        keys = pd.MultiIndex.from_frame(d[['firm_id', 'date']])
        observed = out[out['date'].between(d['date'].min(), d['date'].max())]
        actual = observed.groupby(['firm_id', 'date'])['amount'].sum().reindex(keys, fill_value=0.)
        check('daily_cash.outflow.reconciled', np.allclose(d['outflow'], actual.to_numpy(), atol=1, rtol=1e-9))
    from ..models.features import FEATURES
    try:
        validate_feature_columns(FEATURES)
    except ValueError as exc:
        check('features.allowlist', False, exc)
    else:
        check('features.allowlist', True)
    result = pd.DataFrame(rows)
    if raise_on_error and not result['passed'].all():
        raise ValueError('Hợp đồng dữ liệu không đạt: ' + ', '.join(result.loc[~result['passed'], 'check']))
    return result
