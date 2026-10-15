"""T8: Beta–Binomial phân tầng từ lời hứa đã đến thời điểm xác minh."""
from __future__ import annotations
import numpy as np
import pandas as pd


class PromiseReliability:
    def __init__(self, strength=6., half_life=90.):
        self.strength, self.half_life = strength, half_life

    def fit(self, promises, T):
        T = pd.Timestamp(T)
        p = promises[(promises.made_date <= T) & (promises.promised_date + pd.Timedelta(days=3) <= T)].copy()
        if 'resolved_date' in p:
            p = p[p.resolved_date.notna() & (p.resolved_date <= T)]
        p = p[p.kept.notna()]
        if 'firm_id' not in p:
            p['firm_id'] = '__all__'
        p['age'] = (T - p.promised_date).dt.days
        p['weight'] = .5 ** (p.age / self.half_life)
        p['success'] = p.kept.astype(float) * p.weight
        prior = p.groupby('firm_id').kept.agg(['sum', 'count'])
        prior['prior'] = (prior['sum'] + 4) / (prior['count'] + 6)
        self.priors = prior['prior'].to_dict()
        rows = []
        for cid, g in p.groupby('customer_id'):
            rate = self.priors.get(g.firm_id.iloc[0], 4 / 6)
            w, s = g.weight.sum(), g.success.sum()
            rel = (s + self.strength * rate) / (w + self.strength)
            # Độ trễ thực chỉ từ các bản ghi đã xác minh, nếu có.
            delay = (g.actual_paid_date - g.promised_date).dt.days if 'actual_paid_date' in g else pd.Series(dtype=float)
            sensitivity = np.nan
            if 'amount' in g and g.amount.nunique() >= 3:
                sensitivity = g.amount.rank().corr(g.kept.astype(float), method='spearman')
            rows.append(dict(customer_id=cid, reliability=rel, delay=float(delay.mean()) if len(delay) else np.nan,
                             amount_sensitivity=sensitivity, recency_days=float(g.age.min()),
                             volatility=float(g.kept.astype(float).std()) if len(g) > 1 else np.nan,
                             n_resolved=len(g)))
        self.stats = pd.DataFrame(rows).set_index('customer_id') if rows else pd.DataFrame()
        self.asof = T
        return self

    def predict(self, customers):
        out = customers[['customer_id']].copy()
        prior = customers.firm_id.map(self.priors).fillna(4 / 6) if 'firm_id' in customers else pd.Series(4 / 6, index=customers.index)
        if len(self.stats):
            out = out.join(self.stats, on='customer_id')
            out['reliability'] = out.reliability.fillna(pd.Series(prior.to_numpy(), index=out.index))
        else:
            out['reliability'] = prior.to_numpy()
        return out
