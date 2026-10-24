"""v6 secondary score: bundle integrity and the guarantee that it never changes the alerts (synthetic test doubles)."""
import json

import lightgbm as lgb
import numpy as np
import pandas as pd
import pytest

from agent2.pipeline_v4 import run
from agent2.v6_model import V6Scorer, make_bundle, save_bundle
from tests_agent2.test_pipeline_v4 import config, world  # noqa: F401  (fixture)

COLUMNS = ["log_amount", "receipt_days_late"]


def tiny_bundle(path):
    rng = np.random.default_rng(0)
    x = rng.normal(size=(300, 2)).astype(np.float32)
    y = (x[:, 0] > .5).astype(int)
    boosters = [lgb.train({"objective": "binary", "verbosity": -1, "num_leaves": 4, "seed": s}, lgb.Dataset(x, label=y), 10) for s in range(2)]
    return save_bundle(make_bundle(boosters, COLUMNS, {"candidate": "test"}), path)


def test_bundle_round_trip_checksum_and_missing_columns(tmp_path):
    digest = tiny_bundle(tmp_path / "m.joblib")
    scorer = V6Scorer.load(tmp_path / "m.joblib", digest)
    frame = pd.DataFrame({"log_amount": [0., 1., 2.], "receipt_days_late": [0., 0., 3.]})
    scores = scorer.score(frame)
    assert scores.shape == (3,) and ((0 <= scores) & (scores <= 1)).all() and scores[2] > scores[0]
    with pytest.raises(ValueError, match="checksum"):
        V6Scorer.load(tmp_path / "m.joblib", "0" * 64)
    with pytest.raises(ValueError, match="lacks 1 model columns"):
        scorer.score(frame[["log_amount"]])
    assert list(V6Scorer.percentile(np.array([.1, .9, .5]))) == [0., 1., .5]


def test_secondary_score_never_changes_the_alerts(world, tmp_path):  # noqa: F811
    digest = tiny_bundle(tmp_path / "m.joblib")
    plain, _ = run(world, tmp_path / "plain", config(), "2025-W40", "C001")
    cfg = {**config(), "v6_model_path": str(tmp_path / "m.joblib"), "v6_model_sha256": digest}
    used, _ = run(world, tmp_path / "used", cfg, "2025-W40", "C001")
    bad, _ = run(world, tmp_path / "bad", {**cfg, "v6_model_sha256": "0" * 64}, "2025-W40", "C001")
    assert plain["v6_secondary_score"] == "not_configured"
    assert used["v6_secondary_score"] == "used_as_secondary_score" and used["v6_model_sha256"] == digest
    assert bad["v6_secondary_score"].startswith("skipped")
    base = pd.read_csv(tmp_path / "plain" / "alerts.csv", keep_default_na=False)
    with_v6 = pd.read_csv(tmp_path / "used" / "alerts.csv", keep_default_na=False)
    assert list(with_v6.transaction_id) == list(base.transaction_id) and "v6_score" in with_v6 and "v6_score" not in base
    assert with_v6.v6_percentile.between(0, 1).all()
    skipped = pd.read_csv(tmp_path / "bad" / "alerts.csv", keep_default_na=False)
    assert list(skipped.transaction_id) == list(base.transaction_id) and "v6_score" not in skipped
    assert json.loads((tmp_path / "used" / "report.json").read_text(encoding="utf-8"))["priority_score_is_fraud_probability"] is False
