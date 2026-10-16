import json

import pandas as pd

from agent2.pipeline_v4 import run
from agent2.reduced_v4 import reduced_scores


def transaction(**overrides):
    return {'company_id': 'a', 'transaction_id': 'x', 'txn_type': 'vendor_payment',
            'created_at': '2025-10-01T10:00:00+07:00', 'approved_at': '2025-10-01T10:00:30+07:00',
            'posted_at': '2025-10-01T11:00:00+07:00', 'amount_vnd': '60000000', **overrides}


def test_minimum_input_runs_only_existing_fast_approval_rule(tmp_path):
    source, output = tmp_path / 'input', tmp_path / 'output'
    source.mkdir()
    pd.DataFrame([transaction()]).to_csv(source / 'transactions.csv', index=False)
    # No model or labelled history exists. Missing evidence cannot enter L4.
    report, cases = run(source, output, {}, '2025-W40', 'a')
    assert report['profile'] == 'reduced'
    assert report['enabled_rules'] == ['C3']
    assert report['alert_rows'] == 1
    assert set(cases.company_id) == {'a'}
    assert '30.0' in cases.reason.iloc[0]
    assert json.loads((output / 'run_manifest.json').read_text())['labels_read'] is False


def test_no_zero_score_filler_alerts_and_future_master_cannot_trigger():
    frames = {'transactions': pd.DataFrame([transaction(amount_vnd='1000', creator_id='e', approver_id='e')]),
              'employees': pd.DataFrame([{'company_id': 'a', 'employee_id': 'e',
                                          'recorded_at': '2025-12-01T00:00:00+07:00', 'self_approval_limit_vnd': '0'}])}
    _, flags, _, _, _ = reduced_scores(frames, 'a', '2025-W40')
    assert not flags.any()
    frames['employees']['recorded_at'] = '2024-01-01T00:00:00+07:00'
    frame, flags, _, _, _ = reduced_scores(frames, 'a', '2025-W40')
    assert flags.tolist() == [True]
    assert frame.rule_hard.tolist() == [True]


def test_reduced_mode_keeps_budget_when_many_rules_fire():
    frame = pd.DataFrame([transaction(transaction_id=str(i)) for i in range(8)])
    _, flags, _, _, _ = reduced_scores({'transactions': frame}, 'a', '2025-W40')
    assert flags.sum() == 3


def test_no_supported_trigger_produces_empty_queue_without_filling_budget(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    pd.DataFrame([transaction(amount_vnd='1000')]).to_csv(source / 'transactions.csv', index=False)
    report, cases = run(source, tmp_path / 'out', {}, '2025-W40', 'a')
    assert report['alert_rows'] == report['cases'] == 0
    assert cases.empty
    assert (tmp_path / 'out' / 'case_queue.csv').exists()
