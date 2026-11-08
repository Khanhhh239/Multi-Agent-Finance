"""Phân tầng chỉ theo thông tin quan sát được tại cutoff."""
import numpy as np
import pandas as pd


def assign_strata(df):
    out = pd.DataFrame(index=df.index)
    out['customer_history'] = np.where(df['c_n_hist'].fillna(0) < 4, 'new', 'known')
    # Ngưỡng tiền tại chính cutoff/công ty, không lấy phân vị từ các tuần tương lai.
    threshold = df.groupby(['firm_id', 'cutoff'])['amount_gross'].transform(lambda s: s.quantile(.9))
    out['invoice_size'] = np.where(df['amount_gross'] >= threshold, 'top10', 'other90')
    out['term'] = pd.cut(df['term_days'], [-1, 0, 30, 60, np.inf], labels=['COD', '1-30', '31-60', '60+']).astype(str)
    T = pd.to_datetime(df['cutoff'])
    out['regime'] = np.select([T.between('2021-07-01', '2021-10-31'), T.between('2022-10-01', '2023-06-30'),
                               df['days_to_tet'].between(-14, 21)], ['covid', 'crunch', 'tet'], default='normal')
    for col in ('industry', 'posting_mode', 'tail'):
        if col in df:
            out[col] = df[col].astype(str)
    return out
