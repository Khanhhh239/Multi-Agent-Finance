import numpy as np
import pandas as pd

from agent2 import eval_v4


def test_saved_alerts_keep_test_row_order_without_pickle(monkeypatch, tmp_path):
    df = pd.DataFrame({"split": ["train", "test", "validation", "test"],
                       "company_id": ["c"] * 4, "transaction_id": ["tr", "b", "va", "a"],
                       "case_id": ["", "case_b", "", "case_a"], "is_fraud": [0, 1, 0, 1]})
    monkeypatch.setattr(eval_v4, "run_candidates", lambda *args: ({"L3": np.array([.2, .9])}, {}, {"L3": 0}))
    monkeypatch.setattr(eval_v4, "alerts_for", lambda *args: ({"L3": np.array([False, True])}, {}))
    monkeypatch.setattr(eval_v4, "summarise", lambda *args: {"L3": {"recall": .5}})
    path = tmp_path / "alerts.npz"
    assert eval_v4.p1_temporal(df, path)["L3"]["recall"] == .5
    with np.load(path, allow_pickle=False) as archive:
        assert archive["transaction_id"].tolist() == ["b", "a"]
        assert archive["case_id"].tolist() == ["case_b", "case_a"]
        assert archive["names"].tolist() == ["L3"]
        assert archive["alerts"].tolist() == [[False, True]]


def test_parallel_candidates_preserve_registered_order_and_outputs(monkeypatch):
    class Model:
        def __init__(self, value):
            self.value = value

        def fit(self, train, valid):
            return self

        def score(self, frame):
            return np.full(len(frame), self.value)

    candidates = {"a": lambda: Model(1), "b": lambda: Model(2), "c": lambda: Model(3)}
    monkeypatch.setattr(eval_v4, "CANDIDATES", candidates)
    frame = pd.DataFrame({"x": [1, 2]})
    monkeypatch.setattr(eval_v4, "WORKERS", 1)
    sequential = eval_v4.run_candidates(frame, frame, frame)
    monkeypatch.setattr(eval_v4, "WORKERS", 3)
    parallel = eval_v4.run_candidates(frame, frame, frame)
    for before, after in zip(sequential[:2], parallel[:2]):
        assert list(after) == ["a", "b", "c"]
        for name in before:
            np.testing.assert_array_equal(before[name], after[name])
