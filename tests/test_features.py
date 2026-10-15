"""Ca đối nghịch cho đặc trưng as-of và nhãn kiểm duyệt."""
import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
from agent1.models.features import SnapshotBuilder, FEATURES, add_labels
from agent1.data.contracts import validate_feature_columns


def invoices():
    df = pd.DataFrame({
        'invoice_id': ['h1', 'h2', 'o1', 'o2', 'future'], 'firm_id': ['f'] * 5, 'customer_id': ['c'] * 5,
        'issue_date': pd.to_datetime(['2023-01-01', '2023-02-01', '2023-03-01', '2023-03-10', '2024-01-01']),
        'due_date': pd.to_datetime(['2023-01-15', '2023-02-15', '2023-04-01', '2023-04-10', '2024-02-01']),
        'paid_date_true': pd.to_datetime(['2023-01-20', '2023-02-20', '2023-05-01', None, None]),
        'amount_gross': [100., 200., 120., 180., 1e12], 'term_days': [14, 14, 31, 31, 31],
        'writeoff_date': pd.to_datetime([None] * 5),
    })
    return df


def test_future_rows_and_future_outcomes_do_not_change_features():
    inv = invoices()
    T = pd.Timestamp('2023-03-20')
    pay = pd.DataFrame({'invoice_id': ['o1', 'o1'], 'pay_date_true': pd.to_datetime(['2023-03-15', '2023-04-01']),
                        'amount': [10., 90.], 'kind': ['partial', 'partial']})
    prom = pd.DataFrame({'invoice_id': ['o1', 'o1'], 'customer_id': ['c', 'c'],
                         'made_date': pd.to_datetime(['2023-03-10', '2023-04-01']),
                         'promised_date': pd.to_datetime(['2023-03-15', '2023-04-10']), 'kept': [False, True]})
    full = SnapshotBuilder(inv, pay, prom).snapshot(T)
    short = inv[inv.issue_date <= T].copy()
    short.loc[short.paid_date_true > T, 'paid_date_true'] = pd.NaT
    trunc = SnapshotBuilder(short, pay[pay.pay_date_true <= T], prom[prom.made_date <= T]).snapshot(T)
    cols = FEATURES + ['invoice_id', 'top1', 'top2']
    assert_frame_equal(full[cols].reset_index(drop=True), trunc[cols].reset_index(drop=True))


def test_onboarding_does_not_use_invoices_before_visible_from():
    inv = invoices()
    T = pd.Timestamp('2023-03-20')
    full = SnapshotBuilder(inv).snapshot(T, visible_from='2023-03-01')
    short = SnapshotBuilder(inv[inv.issue_date >= '2023-03-01']).snapshot(T)
    assert_frame_equal(full[FEATURES].reset_index(drop=True), short[FEATURES].reset_index(drop=True))


def test_censor_labels_hand_cases():
    df = pd.DataFrame({'cutoff': pd.to_datetime(['2023-01-01'] * 4),
                       'label_date': pd.to_datetime(['2023-01-10', '2023-03-01', None, None]),
                       'writeoff_date': pd.to_datetime([None, None, '2023-01-20', '2023-04-01'])})
    result = add_labels(df, '2023-02-01')
    assert result.event.tolist() == [1, 0, 0, 0]
    assert result.time_obs.tolist() == [9, 31, 31, 31]
    assert result.bad_known.tolist() == [0, 0, 1, 0]
    assert np.isinf(result.remaining.iloc[2])
    with pytest.raises(ValueError, match='label_end'):
        add_labels(df, '2022-12-31')


def test_latent_columns_are_rejected():
    validate_feature_columns(FEATURES)
    with pytest.raises(ValueError, match='Đặc trưng cấm'):
        validate_feature_columns(FEATURES + ['liquidity_at_due'])
