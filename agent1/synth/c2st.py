"""C2ST theo công ty giữ lại; dùng cùng các đặc trưng quan sát được ở hai nguồn."""
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.metrics import roc_auc_score
from ..threads import NT
from ..eval.metrics import bootstrap_ci


def structure_features(inv):
    amount = inv.amount_gross / inv.groupby('firm_id').amount_gross.transform('median')
    return pd.DataFrame({'log_amount_rel': np.log(amount.clip(lower=1e-9)),
        'term_days': (inv.due_date - inv.issue_date).dt.days,
        'issue_dow': inv.issue_date.dt.dayofweek, 'due_dow': inv.due_date.dt.dayofweek,
        'issue_dom': inv.issue_date.dt.day, 'due_dom': inv.due_date.dt.day,
        'late_days': (inv.paid_date_true - inv.due_date).dt.days.clip(-60, 365)})


def structure_features_v2(inv):
    """Đặc trưng mở rộng để TÁCH khác biệt chủ đích khỏi khác biệt hành vi (Sprint 4).
    late_rank = hạng phân vị của trễ trong công ty (thang-không-đơn-vị: bỏ chênh lệch mức trễ do VN khác Mỹ, giữ HÌNH DẠNG);
    cust_late_loo = trung bình late_rank của khách trên các HĐ KHÁC (độ bền hành vi khách)."""
    f = structure_features(inv)
    paid = inv.paid_date_true
    f['paid_dow'] = paid.dt.dayofweek
    f['paid_dom'] = paid.dt.day
    f['issue_weekend'] = (inv.issue_date.dt.dayofweek >= 5).astype(int)
    f['late_rank'] = f.groupby(inv.firm_id.to_numpy())['late_days'].rank(pct=True)
    g = f.groupby(inv.customer_id.to_numpy())['late_rank']
    n = g.transform('count'); s = g.transform('sum')
    f['cust_late_loo'] = ((s - f['late_rank']) / (n - 1)).where(n >= 6)
    f['cust_n'] = np.log1p(n)
    return f


def match_window(inv, months, seed=7):
    """Cắt mỗi công ty về một cửa sổ phát hành liên tục dài `months` tháng (vị trí ngẫu nhiên, cố định theo seed).
    Bộ thật tham chiếu chỉ dài ~14 tháng; đặc trưng cấp khách (số HĐ/khách, tỷ lệ khách 1 HĐ) phụ thuộc độ dài cửa sổ,
    nên so trên cửa sổ khác nhau sẽ đo nhầm độ dài quan sát thành 'hành vi'."""
    rng = np.random.default_rng(seed)
    span = pd.Timedelta(days=int(round(months * 30.4)))
    keep = []
    for _, g in inv.groupby('firm_id', sort=True):
        lo, hi = g.issue_date.min(), g.issue_date.max() - span
        start = lo if hi <= lo else lo + (hi - lo) * float(rng.random())
        keep.append(g[(g.issue_date >= start) & (g.issue_date < start + span)])
    return pd.concat(keep).reset_index(drop=True)


FEATURE_SETS = {
    'legacy_full': ['log_amount_rel', 'term_days', 'issue_dow', 'due_dow', 'issue_dom', 'due_dom', 'late_days'],
    'designed': ['term_days'],      # kỳ hạn: khác biệt có chủ đích (VN theo Atradius vs hệ SAP Mỹ) — KHÔNG phải mục tiêu <0,75
    'behavioral': ['log_amount_rel', 'issue_dow', 'due_dow', 'paid_dow', 'issue_dom', 'due_dom', 'paid_dom',
                   'issue_weekend', 'late_rank', 'cust_late_loo', 'cust_n'],
}


def classifier_two_sample(real, synthetic, seed=7, max_rows=100000, feature_set='legacy_full'):
    Xs, ys, split, groups = [], [], [], []
    rng = np.random.default_rng(seed)
    for label, df in enumerate([real, synthetic]):
        # Đặc trưng cấp khách tính trên TOÀN BỘ miền rồi mới lấy mẫu (không làm lệch số HĐ/khách giữa hai miền).
        F = (structure_features(df) if feature_set == 'legacy_full' else structure_features_v2(df))[FEATURE_SETS[feature_set]]
        pick = df.sample(min(len(df), max_rows), random_state=seed).index
        d = df.loc[pick].copy(); F = F.loc[pick]
        firms = d.firm_id.unique(); rng.shuffle(firms)
        if len(firms) < 2:
            raise ValueError('Mỗi miền cần ít nhất hai công ty để tách theo cụm')
        train_firms = set(firms[:max(1, int(.7 * len(firms)))])
        Xs.append(F); ys.append(np.full(len(d), label))
        split.append(d.firm_id.isin(train_firms).to_numpy())
        groups.extend([f'{label}:{fid}' for fid in d.firm_id])
    X = pd.concat(Xs, ignore_index=True); y = np.concatenate(ys); train = np.concatenate(split)
    model = lgb.train(dict(objective='binary', num_leaves=15, min_data_in_leaf=100, num_threads=NT,
        verbosity=-1, seed=seed), lgb.Dataset(X[train], y[train]), 200)
    p = model.predict(X[~train]); truth = y[~train]
    # Bootstrap có thể rút chỉ một miền nếu ít cụm; bỏ mẫu không xác định AUC.
    def auc(a, b):
        return roc_auc_score(a, b) if len(np.unique(a)) == 2 else np.nan
    low, high = bootstrap_ci(auc, truth, p, groups=np.array(groups)[~train], n=300, seed=seed)
    return dict(AUC=roc_auc_score(truth, p), ci_low=low, ci_high=high, seed=seed,
                n_train=int(train.sum()), n_test=int((~train).sum()), bootstrap_n=300), \
        pd.DataFrame({'feature': X.columns, 'gain': model.feature_importance('gain')}).sort_values('gain', ascending=False)
