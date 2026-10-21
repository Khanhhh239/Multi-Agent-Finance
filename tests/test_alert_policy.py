"""G13: xác nhận k tuần, chọn chính sách trên dữ liệu đồ chơi (không dùng tgt)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent1.eval.alert_policy import confirmed_alarm, oof_calibrate, policy_metrics, select_policy  # noqa: E402


def _toy():
    cut = pd.date_range('2024-07-01', periods=30, freq='7D')
    days = pd.date_range('2024-06-01', '2025-06-30', freq='D')
    pred, cash = [], []
    for f in range(4):
        bal = np.ones(len(days))
        p = np.full(len(cut), 0.1)
        if f < 2:   # sự kiện ở tuần 20; tín hiệu tăng dần từ tuần 12
            ev = cut[20]
            bal[(days >= ev) & (days < ev + pd.Timedelta(days=5))] = -1
            p[12:21] = 0.8
        p[5] = 0.9   # một tuần nhiễu đơn lẻ ở mọi công ty
        pred.append(pd.DataFrame(dict(firm_id=f'F{f}', cutoff=cut, p13=p, y13=0.0)))
        cash.append(pd.DataFrame(dict(firm_id=f'F{f}', date=days, balance=bal)))
    return pd.concat(pred, ignore_index=True), pd.concat(cash, ignore_index=True)


def test_confirmation_requires_consecutive_weeks():
    pred, _ = _toy()
    a1 = confirmed_alarm(pred, 'p13', 0.5, 1)
    a2 = confirmed_alarm(pred, 'p13', 0.5, 2)
    assert a1.sum() > a2.sum()
    f2 = pred.firm_id == 'F2'           # chỉ có một tuần nhiễu đơn lẻ
    assert a1[f2].sum() == 1 and a2[f2].sum() == 0


def test_confirmation_removes_single_week_false_alarm():
    pred, cash = _toy()
    m1 = policy_metrics(pred, cash, 'p13', 0.5, 1)
    m2 = policy_metrics(pred, cash, 'p13', 0.5, 2)
    assert m2['false_alarms_per_firm_year'] < m1['false_alarms_per_firm_year']
    assert m2['detected_at_least_4w'] == 1.0 and m2['n_events'] == 2


def test_select_policy_prefers_confirmed():
    pred, cash = _toy()
    choice, grid = select_policy(pred, cash, 'p13', fa_budget=0.5)
    assert choice['feasible_on_source'] and choice['k'] >= 2
    assert len(grid) > 10


def test_oof_calibration_bounded():
    pred, _ = _toy()
    pred = pred.assign(y13=(pred.p13 > 0.5).astype(float))
    c = oof_calibrate(pred, 'p13', 'y13', n_folds=2)
    assert np.all((c >= 0) & (c <= 1))
