import pandas as pd

from agent2.input_values import integer_token, timestamp
from agent2.inference_v4 import snapshot_input


def test_timezones_and_integral_tokens_are_canonical_without_rounding():
    assert timestamp('2025-09-28T20:00:00Z') == '2025-09-29T03:00:00+07:00'
    assert timestamp('2025-09-29T02:30:00') == '2025-09-29T02:30:00+07:00'
    assert timestamp('2025-09-29T02:30:00', 'UTC') == '2025-09-29T09:30:00+07:00'
    assert integer_token('1000.0') == '1000'
    assert integer_token('1000.1') == '1000.1'
    assert integer_token('99999999999999999999') == '99999999999999999999'
    assert integer_token(pd.NA) == timestamp(pd.NaT) == ''


def test_mixed_offsets_do_not_invert_chronology_or_week_filter(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    pd.DataFrame([{'company_id': 'a', 'transaction_id': 'x', 'txn_type': 'cash_expense', 'amount_vnd': '1000.0',
                   'created_at': '2025-09-28T19:00:00Z', 'approved_at': '2025-09-29T02:30:00',
                   'posted_at': '2025-09-28T20:00:00Z'}]).to_csv(source / 'transactions.csv', index=False)
    frames, report, _ = snapshot_input(source, tmp_path / 'snapshot', 'a', '2025-W40', require_full=False)
    assert report['errors'] == []
    assert frames['transactions'].amount_vnd.tolist() == ['1000']
    assert frames['transactions'].posted_at.iloc[0] == '2025-09-29T03:00:00+07:00'
