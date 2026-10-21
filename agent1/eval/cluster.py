"""Bootstrap theo công ty từ tổng tổn thất; giữ trọng số hàng và lấy mẫu cụm có lặp."""
import numpy as np
import pandas as pd


def ratio_ci(numerator, denominator, *, n=300, seed=7):
    """Tỷ số các tổng; mỗi phần tử đại diện trọn một công ty."""
    numerator, denominator = np.asarray(numerator, float), np.asarray(denominator, float)
    if numerator.ndim != 1 or numerator.shape != denominator.shape or not len(numerator):
        raise ValueError('Cần hai vector tổng theo công ty cùng độ dài')
    if not np.isfinite(numerator).all() or not np.isfinite(denominator).all() or (denominator < 0).any():
        raise ValueError('Tổng phải hữu hạn, mẫu số không âm')
    rng = np.random.default_rng(seed)
    ix = rng.integers(0, len(numerator), size=(n, len(numerator)))
    den = denominator[ix].sum(1)
    valid = den > 0
    ratios = numerator[ix].sum(1)[valid] / den[valid]
    return dict(ci_low=float(np.quantile(ratios, .025)) if len(ratios) else np.nan,
                ci_high=float(np.quantile(ratios, .975)) if len(ratios) else np.nan,
                bootstrap_n=n, bootstrap_valid=int(valid.sum()), n_firms=len(numerator))


def mean_ci(values, groups, *, baseline=None, n=300, seed=7):
    values, groups = np.asarray(values, float), np.asarray(groups)
    if len(values) != len(groups) or not len(values) or not np.isfinite(values).all():
        raise ValueError('Tổn thất/nhóm phải hợp lệ và không rỗng')
    df = pd.DataFrame({'group': groups, 'value': values})
    if baseline is not None:
        df['baseline'] = np.asarray(baseline, float)
    g = df.groupby('group', sort=True).agg(total=('value', 'sum'), count=('value', 'size'))
    rng = np.random.default_rng(seed)
    chunk=max(1,min(n,1000000//len(g)))
    totals,counts=g.total.to_numpy(),g['count'].to_numpy()
    base_sum=df.groupby('group',sort=True).baseline.sum().to_numpy() if baseline is not None else None
    boot_parts,pct_parts=[],[]
    for start in range(0,n,chunk):
        ix=rng.integers(0,len(g),size=(min(chunk,n-start),len(g)))
        sums=totals[ix].sum(1)
        boot_parts.append(sums/counts[ix].sum(1))
        if base_sum is not None:
            denominator=base_sum[ix].sum(1);valid=denominator>0
            pct_parts.append(100*(denominator[valid]-sums[valid])/denominator[valid])
    boot=np.concatenate(boot_parts)
    result = {'ci_low': float(np.quantile(boot, .025)), 'ci_high': float(np.quantile(boot, .975)),
              'bootstrap_n': n, 'n_firms': len(g)}
    if baseline is not None:
        pct=np.concatenate(pct_parts)
        result.update(improvement_pct=100 * (np.mean(baseline) - values.mean()) / max(np.mean(baseline), 1e-12),
                      improvement_ci_low=float(np.quantile(pct, .025)) if len(pct) else np.nan,
                      improvement_ci_high=float(np.quantile(pct, .975)) if len(pct) else np.nan)
    return result
