import numpy as np
import pandas as pd
import pytest

from agent2.deployment_v4 import PreparedV4Detector, policy_components


def bundle():
    return {"schema_version": 2, "models": {},
            "frozen": {"chosen": "Rules+Graph (friend)", "cold_start": "Rules+Graph (friend)"}}


def frame(company="c"):
    return pd.DataFrame({"company_id": [company] * 8, "week": [1] * 8, "rule_graph": np.arange(8.)})


def test_policy_resolution_keeps_the_registered_slots_components():
    assert policy_components("L3 2+1 Nmax(R,E)") == ["L3", "Novelty max(R,E)"]
    with pytest.raises(ValueError, match="unknown"):
        policy_components("invented")


def test_scoring_needs_no_target_labels_and_keeps_budget_and_company_scope():
    d = frame()
    det = PreparedV4Detector(bundle()).fit(d.iloc[:2], d.iloc[2:4])
    flags, score, _ = det.alerts(d)
    assert flags.sum() == 3
    assert np.isfinite(score).all()
    with pytest.raises(ValueError, match="company"):
        det.score(frame("other"))
    with pytest.raises(ValueError, match="budget"):
        det.alerts(d, 2)


def test_serving_history_rejects_multiple_companies_and_missing_periods():
    with pytest.raises(ValueError, match="one company"):
        PreparedV4Detector(bundle()).fit(frame("a"), frame("b"))
    with pytest.raises(ValueError, match="non-empty"):
        PreparedV4Detector(bundle()).fit(frame().iloc[:0], frame())
