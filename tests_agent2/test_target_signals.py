import numpy as np
import pandas as pd
import pytest

from agent2 import target_signals


class FakeSignal:
    def __init__(self, **kwargs):
        pass

    def fit(self, frame):
        assert "is_fraud" not in frame
        self.reference = frame.x.mean()
        return self

    def score(self, frame):
        return abs(frame.x.to_numpy() - self.reference)

    def parts(self, frame):
        return {"x": self.score(frame)}


def test_signals_fit_only_past_and_do_not_cross_companies(monkeypatch):
    for cls in ("EntityDeviation", "Autoencoder", "IForest"):
        monkeypatch.setattr(target_signals.M, cls, FakeSignal)
    history = pd.DataFrame({"company_id": ["c"] * 3, "x": [1., 2., 3.]})
    signal = target_signals.TargetSignals().fit(history)
    now = pd.DataFrame({"company_id": ["c"], "x": [5.]})
    before = signal.transform(now)
    future = pd.concat([now, now.assign(x=100000)], ignore_index=True)
    pd.testing.assert_frame_equal(before, signal.transform(future).iloc[:1])
    np.testing.assert_array_equal(signal.entity_reference, [1, 0, 1])
    with pytest.raises(ValueError, match="fitted company"):
        signal.transform(now.assign(company_id="other"))
    with pytest.raises(ValueError, match="one non-empty company"):
        target_signals.TargetSignals().fit(history.iloc[:0])
