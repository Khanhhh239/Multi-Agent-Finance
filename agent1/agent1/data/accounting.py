"""Invoice settlement truth derived from dated adjustments and bank-linked payments."""
from __future__ import annotations

import numpy as np
import pandas as pd


AMOUNT_TOLERANCE = 1.0  # VND; generated invoice and payment amounts are rounded to thousands.
BANK_FLOW_CLASS = {
    'customer_payment': 'ar',
    'interest': 'other_external',
    'refund': 'other_external',
    'unknown': 'unclassified',
    'loan_disbursement': 'financing',
    'internal': 'internal_transfer',
    'cash_deposit': 'cash_to_bank',
}


def mark_bank_balance_window(bank: pd.DataFrame, start, end) -> pd.DataFrame:
    """Map each statement entry to its signed contribution to the observed account."""
    result = bank.copy()
    result['in_balance_window'] = result['value_date'].between(start, end)
    if not result['direction'].eq('in').all():
        raise ValueError('Outgoing statement entries require an explicit signed-cash rule')
    result['balance_effect'] = np.where(result['in_balance_window'], result['amount'], 0.)
    return result


def derive_invoice_accounting(invoices: pd.DataFrame, payments: pd.DataFrame) -> pd.DataFrame:
    """Return end-of-world AR and closure labels, aligned to ``invoices``.

    ``paid_date_true`` means cash has covered the face value less a *dated*
    credit note. A credit note alone and a write-off close AR without creating
    a cash-payment label. FX adjustments change bank cash, not the face-value
    obligation. Recoveries after write-off are deliberately unsupported by
    this generator and are rejected by the world contract.
    """
    inv = invoices.set_index('invoice_id', drop=False)
    face = inv['amount_gross'].astype(float)
    credit = inv['credit_note'].fillna(0).astype(float)
    credit_date = pd.to_datetime(inv['credit_note_date'])
    writeoff_date = pd.to_datetime(inv['writeoff_date'])
    due_after_credit = face - credit

    pay = payments.copy()
    pay['_face_amount'] = pay['amount'].astype(float)
    if 'fx_adjustment' in pay:
        pay['_face_amount'] -= pay['fx_adjustment'].fillna(0).astype(float)
    pay = pay.sort_values(['invoice_id', 'pay_date_true', 'payment_id'], kind='mergesort')
    paid = pay.groupby('invoice_id')['_face_amount'].sum().reindex(inv.index, fill_value=0.)
    cash_received = pay.groupby('invoice_id')['amount'].sum().reindex(inv.index, fill_value=0.)
    count = pay.groupby('invoice_id').size().reindex(inv.index, fill_value=0).astype(int)
    first = pay.groupby('invoice_id')['pay_date_true'].min().reindex(inv.index)

    pay['_cumulative'] = pay.groupby('invoice_id')['_face_amount'].cumsum()
    target = pay['invoice_id'].map(due_after_credit)
    crossed = pay[(target > AMOUNT_TOLERANCE) &
                  (pay['_cumulative'] >= target - AMOUNT_TOLERANCE)]
    cash_cross = crossed.groupby('invoice_id')['pay_date_true'].min().reindex(inv.index)
    last_ledger = pay.groupby('invoice_id')['ledger_post_date'].max().reindex(inv.index)
    completed = pd.concat([cash_cross, credit_date], axis=1).max(axis=1)
    paid_in_full = (due_after_credit > AMOUNT_TOLERANCE) & cash_cross.notna()
    paid_in_full &= writeoff_date.isna() | (completed < writeoff_date)
    paid_date = completed.where(paid_in_full)
    ledger_date = pd.concat([last_ledger, credit_date], axis=1).max(axis=1).where(paid_in_full)

    pre_writeoff = pay[pay['pay_date_true'] <= pay['invoice_id'].map(writeoff_date)]
    paid_before_writeoff = pre_writeoff.groupby('invoice_id')['_face_amount'].sum().reindex(inv.index, fill_value=0.)
    credit_before_writeoff = credit.where(credit_date <= writeoff_date, 0.)
    writeoff_amount = (face - credit_before_writeoff - paid_before_writeoff).clip(lower=0.)
    writeoff_amount = writeoff_amount.where(writeoff_date.notna(), 0.)
    remaining = (due_after_credit - paid - writeoff_amount).clip(lower=0.)

    credit_only = (due_after_credit <= AMOUNT_TOLERANCE) & (credit > 0) & credit_date.notna()
    written_off = writeoff_amount > AMOUNT_TOLERANCE
    closure_type = pd.Series('open', index=inv.index, dtype='object')
    closure_type.loc[credit_only] = 'credit_note'
    closure_type.loc[paid_in_full] = 'paid'
    closure_type.loc[paid_in_full & (credit > 0)] = 'paid_after_credit_note'
    closure_type.loc[written_off] = 'writeoff'
    closed_date = paid_date.where(paid_in_full, credit_date.where(credit_only))
    closed_date = closed_date.where(~written_off, writeoff_date)

    result = pd.DataFrame({
        'paid_date_true': paid_date,
        'ledger_clear_date': ledger_date,
        'first_payment_date': first,
        'paid_amount': paid,
        'cash_received_amount': cash_received,
        'n_payments': count,
        'writeoff_amount': writeoff_amount,
        'remaining_amount': remaining,
        'closure_type': closure_type,
        'closed_date_true': closed_date,
    }, index=inv.index)
    result['days_late_true'] = (result['paid_date_true'] - inv['due_date']).dt.days
    return result.reset_index(drop=True).set_axis(invoices.index)


def mark_observed_outcomes(invoices: pd.DataFrame, observation_end) -> pd.DataFrame:
    """Separate confirmed closure from right censoring at the data cutoff."""
    result = invoices.copy()
    end = pd.Timestamp(observation_end)
    closed = result['closed_date_true'].notna() & (result['closed_date_true'] <= end)
    result['observation_end'] = end
    result['outcome_status_at_end'] = result['closure_type'].where(closed, 'censored')
    result['is_bad_debt'] = result['outcome_status_at_end'].eq('writeoff')
    return result
