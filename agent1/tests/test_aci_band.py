import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent1_service.jobs import aci_band  # noqa: E402
from agent1.models.t6_cash import K  # noqa: E402


def _weekly_loop(n_weeks, truth_sd, model_sd, seed=0):
    """Mô hình hẹp hơn thực tế (model_sd < truth_sd): ACI phải nới khoảng ra."""
    rng = np.random.default_rng(seed)
    state, cover = None, []
    start = pd.Timestamp("2025-01-06")
    for w in range(n_weeks):
        T = start + pd.Timedelta(days=7 * w)
        state, aci = aci_band.update(state, T, rng.normal(0, truth_sd))
        rows, meta = aci_band.band(state, aci, T, rng.normal(0, model_sd, (2000, K)))
        cover.append((rows[0]["P10"], rows[0]["P90"]))
    return state, meta, cover


def test_aci_widens_narrow_model_towards_80pct():
    state, meta, cover = _weekly_loop(160, truth_sd=1.0, model_sd=0.6)
    rng = np.random.default_rng(1)
    y = rng.normal(0, 1.0, 4000)
    lo, hi = np.mean([c[0] for c in cover[-20:]]), np.mean([c[1] for c in cover[-20:]])
    raw = np.mean((y >= -0.6 * 1.2816) & (y <= 0.6 * 1.2816))
    adapted = np.mean((y >= lo) & (y <= hi))
    assert raw < 0.6 and adapted > raw + 0.1
    assert meta["aci_ready"] and meta["band_method"] == "copula-t+ACI"


def test_not_ready_before_eight_weeks():
    _, meta, _ = _weekly_loop(5, 1.0, 1.0)
    assert not meta["aci_ready"] and "chưa kiểm chứng" in meta["band_note"]


def test_uses_only_past_balances():
    state, aci = aci_band.update(None, "2025-01-06", 100.0)
    rows, _ = aci_band.band(state, aci, "2025-01-06", np.zeros((10, K)))
    assert len(state["pending"]) == K
    state2, _ = aci_band.update(state, "2025-01-10", 5.0)     # chưa tới hạn tuần 1 (13/01)
    assert state2["a"] == state["a"] and len(state2["pending"]) == K


def test_state_is_json_serialisable():
    import json
    state, aci = aci_band.update(None, "2025-01-06", 1.0)
    aci_band.band(state, aci, "2025-01-06", np.zeros((5, K)))
    json.dumps(state)
