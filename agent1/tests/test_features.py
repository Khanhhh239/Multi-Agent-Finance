"""Ca đối nghịch cho đặc trưng as-of và nhãn kiểm duyệt."""
import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
from agent1.models.features import (SnapshotBuilder, FEATURES, add_labels,
                                    MODEL_VISIBLE_COLUMNS, model_snapshot_view,
                                    published_macro_as_of)
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


def test_short_final_installment_remains_open_with_correct_balance():
    inv = invoices()
    pay = pd.DataFrame({'invoice_id': ['o2'], 'pay_date_true': pd.to_datetime(['2023-03-15']),
                        'amount': [160.], 'kind': ['final']})
    row = SnapshotBuilder(inv, pay).snapshot('2023-03-20').set_index('invoice_id').loc['o2']
    assert row.paid_frac_so_far == pytest.approx(160 / 180)
    assert row.amount_open == pytest.approx(20.)


def test_credit_note_closure_is_not_a_cash_payment_event():
    inv = invoices()
    inv['credit_note'] = 0.
    inv['credit_note_date'] = pd.NaT
    inv.loc[inv.invoice_id == 'o2', 'credit_note'] = 180.
    inv.loc[inv.invoice_id == 'o2', 'credit_note_date'] = pd.Timestamp('2023-04-01')
    before = SnapshotBuilder(inv).snapshot('2023-03-20')
    after = SnapshotBuilder(inv).snapshot('2023-04-02')
    assert 'o2' in before.invoice_id.values
    assert 'o2' not in after.invoice_id.values


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
    with pytest.raises(ValueError, match='chưa được duyệt'):
        validate_feature_columns(FEATURES + ['new_future_answer_2030'])
    from agent1.models.t1 import HazardGBM
    with pytest.raises(ValueError, match='chưa được duyệt'):
        HazardGBM(feats=[*FEATURES, 'new_future_answer_2030'])


def test_forecast_view_keeps_only_registered_as_of_columns():
    inv = invoices()
    inv['unknown_future_answer'] = [1, 2, 3, 4, 5]
    inv['credit_exposure'] = 2.
    cutoff = pd.Timestamp('2023-03-20')
    builder = SnapshotBuilder(inv)
    raw = builder.snapshot(cutoff)
    visible = builder.model_snapshot(cutoff)
    assert list(visible.columns) == [name for name in MODEL_VISIBLE_COLUMNS if name in raw]
    assert not {'label_date', 'paid_date_true', 'writeoff_date', 'unknown_future_answer',
                'credit_exposure'} & set(visible)
    changed = inv.copy()
    changed.loc[changed.invoice_id == 'o1', 'paid_date_true'] = pd.Timestamp('2030-01-01')
    pd.testing.assert_frame_equal(visible, SnapshotBuilder(changed).model_snapshot(cutoff))
    with pytest.raises(ValueError, match='khác cutoff'):
        model_snapshot_view(raw, '2023-03-19')
    with pytest.raises(ValueError, match='chưa phát hành'):
        model_snapshot_view(raw.assign(issue_date=pd.Timestamp('2024-01-01')), cutoff)


def test_macro_publication_gate_hides_current_and_latent_values():
    macro = pd.DataFrame({'week': pd.to_datetime(['2024-01-01', '2024-01-08']),
                          'published_date': pd.to_datetime(['2024-01-15', '2024-01-22']),
                          'covid_source': ['oxcgrt', 'oxcgrt'],
                          'covid_stress': [.2, .9], 'credit_crunch': [.8, .7],
                          'common_factor': [5., 9.], 'unknown_future_macro': [1, 2]})
    assert published_macro_as_of(macro, '2024-01-14').empty
    first = published_macro_as_of(macro, '2024-01-21')
    assert first.iloc[0]['week'] == pd.Timestamp('2024-01-01')
    assert list(first.columns) == ['week', 'published_date', 'covid_stress']
    assert published_macro_as_of(macro, '2024-01-22').iloc[0]['covid_stress'] == .9
    fallback = macro.assign(covid_source='synthetic_fallback')
    assert published_macro_as_of(fallback, '2024-01-22').empty
    with pytest.raises(ValueError, match='công bố'):
        published_macro_as_of(macro.drop(columns='published_date'), '2024-01-22')


def test_compact_snapshot_cache_preserves_features_and_invalidates_source_changes(tmp_path,monkeypatch):
    from scripts import run_t1 as runner
    root=tmp_path/'worlds';world=root/'small';world.mkdir(parents=True)
    cache=tmp_path/'cache';cache.mkdir()
    inv=invoices();inv.to_parquet(world/'invoices.parquet',index=False)
    pd.DataFrame().to_parquet(world/'payments.parquet',index=False)
    monkeypatch.setattr(runner,'SYNTH',root);monkeypatch.setattr(runner,'PROCESSED',cache)
    cutoffs=pd.to_datetime(['2023-03-20','2023-04-01'])
    expected=SnapshotBuilder(inv).build(cutoffs)
    actual=runner.snapshots('small',cutoffs)
    assert_frame_equal(actual[FEATURES],expected[FEATURES],check_dtype=False,rtol=1e-6)
    assert_frame_equal(actual,runner.snapshots('small',cutoffs))
    inv.loc[inv.invoice_id=='future','amount_gross']=2e12
    inv.to_parquet(world/'invoices.parquet',index=False)
    after=runner.snapshots('small',cutoffs)
    assert_frame_equal(actual,after)
    assert len(list(cache.glob('*.parquet')))==2
