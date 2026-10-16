import datetime as dt

import numpy as np
import pandas as pd
import pytest

from agent2.feedback_v4 import apply, learn
from agent2.review_store_v4 import ReviewStore


def test_learning_is_company_scoped_and_excludes_unknown_suspected_and_worth(tmp_path):
    store = ReviewStore(tmp_path / 'db.sqlite')
    for company in ('a', 'b'):
        ingest = store.add_ingest(company, tmp_path, {})
        cases = [{'company_id': company, 'case_id': str(i), 'feedback_vector': {'rule:C3': i % 2}} for i in range(8)]
        store.add_score(company, ingest, '2025-W40', cases, {'model_version': 'v1'})
        for i, case in enumerate(store.list_cases(company)[:7]):
            conclusion = ['confirmed', 'legitimate', 'suspected', 'worth_review'][i % 4]
            store.decide(company, case['case_id'], 'QA', conclusion, 'synthetic test', worth_review=True)
    cutoff = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=1)
    learned = learn(store, 'a', cutoff, minimum=4)
    assert learned['company_id'] == 'a'
    assert learned['labelled_cases'] == 4
    assert learned['positive_cases'] == 2
    assert learned['status'] == 'trained'
    assert len(learned['decision_ids']) == 4
    earlier = learn(store, 'a', '2000-01-01T00:00:00+00:00', minimum=4)
    assert earlier['status'] == 'insufficient_labels'
    assert earlier['labelled_cases'] == 0


def test_correction_cannot_demote_hard_triggers_or_cross_scope_or_leak_future():
    frame = pd.DataFrame({'company_id': ['a'] * 4, 'week': ['2025-W40'] * 4})
    matrix = pd.DataFrame({'rule:C3': [1, 0, 0, 0]})
    artifact = {'schema_version': 1, 'company_id': 'a', 'status': 'trained',
                'cutoff': '2025-01-01T00:00:00+07:00', 'created_at': '2025-01-02T00:00:00+07:00',
                'features': ['rule:C3'], 'weights': [-1000], 'intercept': 0}
    start = pd.Timestamp('2025-09-29T00:00:00+07:00')
    flags, score = apply(frame, np.array([.01, .9, .8, .7]), [1, 0, 0, 0], matrix, artifact, 'a', start)
    assert flags[0]
    assert score[0] > max(score[1:])
    assert flags.sum() == 3
    with pytest.raises(ValueError, match='another company'):
        apply(frame, np.ones(4), np.zeros(4), matrix, artifact, 'b', start)
    artifact['created_at'] = '2026-01-01T00:00:00+07:00'
    with pytest.raises(ValueError, match='retrospective'):
        apply(frame, np.ones(4), np.zeros(4), matrix, artifact, 'a', start)
