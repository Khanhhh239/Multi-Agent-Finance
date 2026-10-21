import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent1.eval.fallback_gate import fallback_states, gated_loss  # noqa: E402


def test_no_fallback_when_blend_is_better():
    s = fallback_states(np.full(40, 0.8), np.full(40, 1.0))
    assert not s.any()


def test_falls_back_after_regime_shift_and_limits_damage():
    rng = np.random.default_rng(0)
    base = np.full(60, 1.0)
    blend = np.where(np.arange(60) < 20, 0.8, 1.6) + rng.normal(0, .02, 60)   # sau tuần 20 BLEND tệ hơn nhiều
    s = fallback_states(blend, base)
    assert not s[:20].any() and s[40:].all()
    g, _ = gated_loss(blend, base)
    assert g[20:].mean() < blend[20:].mean()      # thoái lui giảm thiệt hại
    assert g[:20].mean() == blend[:20].mean()     # trước sốc không bị can thiệp


def test_uses_only_past_data():
    base = np.full(30, 1.0)
    blend = np.full(30, 0.8); blend[15:] = 5.0
    s = fallback_states(blend, base)
    assert not s[15]          # tuần 15 là tuần xấu đầu tiên, chưa thể biết


def test_recovers_when_blend_is_good_again():
    base = np.full(80, 1.0)
    blend = np.where((np.arange(80) >= 10) & (np.arange(80) < 30), 2.0, 0.8)
    s = fallback_states(blend, base)
    assert s[25] and not s[-1]
