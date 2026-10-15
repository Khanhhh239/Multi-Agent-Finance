import numpy as np
import pandas as pd
from agent1.models.t8_promise import PromiseReliability
from agent1.models.t7_portfolio import RegimeController, consensus_alarms


def test_promises_only_resolved_by_cutoff_affect_reliability():
    p = pd.DataFrame({'customer_id': ['c', 'c'], 'firm_id': ['f', 'f'], 'kept': [True, False],
                      'made_date': pd.to_datetime(['2024-01-01', '2024-02-01']),
                      'promised_date': pd.to_datetime(['2024-01-05', '2024-02-05'])})
    query = pd.DataFrame({'customer_id': ['c', 'new'], 'firm_id': ['f', 'unknown']})
    full = PromiseReliability().fit(p, '2024-01-15').predict(query)
    short = PromiseReliability().fit(p.iloc[:1], '2024-01-15').predict(query)
    pd.testing.assert_frame_equal(full, short)
    assert full.reliability.between(0, 1).all()


def test_consensus_prefix_invariance():
    dates = pd.date_range('2023-01-01', periods=100, freq='7D')
    z = np.r_[np.zeros(20), np.full(80, 3.)]
    full = consensus_alarms(dates, z)
    prefix = consensus_alarms(dates[:50], z[:50])
    assert full[full <= dates[49]].equals(prefix)


def test_regime_changes_parameters_and_recovers_after_quiet_period():
    c = RegimeController()
    assert c.update('2024-01-01')['state'] == 'normal'
    result = c.update('2024-01-08', portfolio_alarm=True)
    assert result['state'] == 'crisis' and result['aci_gamma'] == .03
    assert c.update('2024-06-01')['state'] == 'normal'
