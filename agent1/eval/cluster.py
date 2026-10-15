"""Bootstrap theo công ty từ tổng tổn thất; giữ trọng số hàng và lấy mẫu cụm có lặp."""
import numpy as np
import pandas as pd


def mean_ci(values, groups, *, baseline=None, n=300, seed=7):
    values, groups = np.asarray(values, float), np.asarray(groups)
    if len(values) != len(groups) or not len(values) or not np.isfinite(values).all():
        raise ValueError('Tổn thất/nhóm phải hợp lệ và không rỗng')
    df = pd.DataFrame({'group': groups, 'value': values})
    if baseline is not None:
        df['baseline'] = np.asarray(baseline, float)
    g = df.groupby('group', sort=True).agg(total=('value', 'sum'), count=('value', 'size'))
    rng = np.random.default_rng(seed)
    ix = rng.integers(0, len(g), size=(n, len(g)))
    boot = g.total.to_numpy()[ix].sum(1) / g['count'].to_numpy()[ix].sum(1)
    result = {'ci_low': float(np.quantile(boot, .025)), 'ci_high': float(np.quantile(boot, .975)),
              'bootstrap_n': n, 'n_firms': len(g)}
    if baseline is not None:
        base_sum = df.groupby('group', sort=True).baseline.sum().to_numpy()
        denom = base_sum[ix].sum(1)
        valid = denom > 0
        pct = 100 * (denom[valid] - g.total.to_numpy()[ix][valid].sum(1)) / denom[valid]
        result.update(improvement_pct=100 * (np.mean(baseline) - values.mean()) / max(np.mean(baseline), 1e-12),
                      improvement_ci_low=float(np.quantile(pct, .025)) if len(pct) else np.nan,
                      improvement_ci_high=float(np.quantile(pct, .975)) if len(pct) else np.nan)
    return result
