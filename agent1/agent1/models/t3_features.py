"""Đặc trưng T3 tại ngày lập; kết quả chỉ được quan sát sau khi đóng HĐ."""
import numpy as np
import pandas as pd


FEATURES = ['c_n', 'c_disp_eb', 'c_part_eb', 'log_amt_rel', 'term_days', 'c_late_eb']


def issue_features(invoices):
    inv = invoices.copy().sort_values(['issue_date', 'invoice_id'])
    # Median đến cuối ngày lập: không phụ thuộc thứ tự các HĐ trong cùng ngày.
    median = inv.groupby('firm_id').amount_gross.expanding().median().reset_index(level=0, drop=True)
    inv['_median'] = median
    day_median = inv.groupby(['firm_id', 'issue_date'])._median.last()
    keys = pd.MultiIndex.from_frame(inv[['firm_id', 'issue_date']])
    inv['log_amt_rel'] = np.log(inv.amount_gross / day_median.reindex(keys).to_numpy())
    out = []
    for _, x in inv.groupby(['firm_id', 'customer_id']):
        x = x.reset_index(drop=True)
        closed = x.paid_date_true.fillna(x.writeoff_date).fillna(pd.Timestamp('2100-01-01')).to_numpy()
        order = np.argsort(closed)
        k = np.searchsorted(closed[order], x.issue_date.to_numpy(), side='left')
        n = k.astype(float)
        row = pd.DataFrame({'invoice_id': x.invoice_id, 'c_n': n})
        for label, column, prior, strength in [('dispute', 'c_disp_eb', .02, 20),
                                               ('partial', 'c_part_eb', .05, 20),
                                               ('late', 'c_late_eb', .4, 10)]:
            values = (x.days_late_true.fillna(60) > 0).to_numpy() if label == 'late' else x[label].to_numpy()
            cumulative = np.cumsum(values[order].astype(float))
            total = np.where(k > 0, cumulative[np.maximum(k - 1, 0)], 0)
            row[column] = (total + prior * strength) / (n + strength)
        out.append(row)
    if not out:
        return inv.reindex(columns=[*inv.columns, 'c_n', 'c_disp_eb', 'c_part_eb', 'c_late_eb']).drop(columns='_median')
    return inv.merge(pd.concat(out), on='invoice_id', validate='one_to_one').drop(columns='_median')
