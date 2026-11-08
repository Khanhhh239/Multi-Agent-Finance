#!/usr/bin/env python3
"""G13 bước 2–3 — chọn chính sách cảnh báo trên nguồn, đóng băng, áp một lần lên dự báo E2E của tgt.

  python scripts/sprint5/g13_policy.py

Đầu vào:  outputs/g13/src_backtest/t6_shortfall_predictions.csv  (nguồn, nhãn thật src)
          outputs/e2e/protocol/t6_shortfall_predictions.csv      (tgt, E2E nhãn T9 ước lượng, -fullweek)
Đầu ra:   outputs/g13/policy_grid_src.csv, policy_choice.json, alert_policy_v2.csv
Đăng ký trước: docs/03_Evaluation/G13_ALERT_POLICY.md (không đổi sau khi xem tgt).
"""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent1.paths import OUT, SYNTH  # noqa: E402
from agent1.eval.alert_policy import (fit_isotonic, oof_calibrate, select_policy, policy_metrics,  # noqa: E402
                                      firm_bootstrap, FA_BUDGET)

VERSION = 'g13-isotonic-confirm-v1'
HORIZON = 13


def load(path):
    d = pd.read_csv(path, parse_dates=['cutoff'])
    return d


def main():
    res = OUT / 'g13'; res.mkdir(exist_ok=True)
    src = load(res / 'src_backtest' / 't6_shortfall_predictions.csv')
    tgt = load(OUT / 'e2e' / 'protocol' / 't6_shortfall_predictions.csv')
    cash_src = pd.read_parquet(SYNTH / 'src' / 'daily_cash.parquet', columns=['firm_id', 'date', 'balance'])
    cash_tgt = pd.read_parquet(SYNTH / 'tgt' / 'daily_cash.parquet', columns=['firm_id', 'date', 'balance'])
    p, y = f'p{HORIZON}', f'y{HORIZON}'
    grids, rows, choices = [], [], {}
    for model, s in src.groupby('model'):
        s = s.reset_index(drop=True)
        for calib in ('raw', 'isotonic'):
            s_use = s.assign(q=s[p] if calib == 'raw' else oof_calibrate(s, p, y))
            choice, grid = select_policy(s_use, cash_src, 'q', horizon_days=7 * HORIZON)
            grids.append(grid.assign(model=model, calibration=calib))
            # đóng băng: hiệu chỉnh cuối học trên TOÀN BỘ src, ngưỡng/k từ lưới src
            t = tgt[tgt.model == model].reset_index(drop=True)
            if t.empty:
                continue
            q_t = t[p] if calib == 'raw' else fit_isotonic(s[y], s[p]).predict(t[p])
            t_use = t.assign(q=q_t)
            m_src = policy_metrics(s_use, cash_src, 'q', choice['tau'], choice['k'], 7 * HORIZON)
            m_tgt = policy_metrics(t_use, cash_tgt, 'q', choice['tau'], choice['k'], 7 * HORIZON)
            ci = firm_bootstrap(t_use, cash_tgt, 'q', choice['tau'], choice['k'], 7 * HORIZON)
            rows.append(dict(model=model, calibration=calib, horizon=HORIZON, **choice, fa_budget=FA_BUDGET,
                             src_detected=m_src['detected_at_least_4w'], src_fa=m_src['false_alarms_per_firm_year'],
                             src_events=m_src['n_events'], **m_tgt, **ci,
                             threshold_selected_on='source_only', target_used_for_selection=False,
                             measurement_version=VERSION))
            choices[f'{model}|{calib}'] = choice
            print(model, calib, choice, {k: round(v, 3) for k, v in m_tgt.items()}, flush=True)
    pd.concat(grids).to_csv(res / 'policy_grid_src.csv', index=False)
    out = pd.DataFrame(rows)
    out.to_csv(OUT / 'e2e' / 'protocol' / 'alert_policy_v2.csv', index=False)
    (res / 'policy_choice.json').write_text(json.dumps(choices, indent=2, ensure_ascii=False), encoding='utf-8')
    print(out[['model', 'calibration', 'tau', 'k', 'src_detected', 'src_fa', 'n_events', 'detected_at_least_4w',
               'median_lead_weeks', 'false_alarms_per_firm_year']].round(3).to_string(index=False))


if __name__ == '__main__':
    main()
