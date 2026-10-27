"""Read-only yearly/industry audit of already generated lifecycle control worlds."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent1.data.world_manifest import verify_world_manifest
from agent1.paths import SYNTH


def weighted_quantile(values, weights, q):
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    good = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    if not good.any():
        return np.nan
    order = np.argsort(values[good])
    v, w = values[good][order], weights[good][order]
    return float(v[np.searchsorted(np.cumsum(w), q * w.sum(), side='left')])


def one_world(path: Path):
    verify_world_manifest(path, validate=True)
    inv = pd.read_parquet(path / 'invoices.parquet')
    pay = pd.read_parquet(path / 'payments.parquet')
    firms = pd.read_parquet(path / 'firms.parquet')[['firm_id', 'industry']]
    cash = pd.read_parquet(path / 'daily_cash.parquet').merge(firms, on='firm_id', validate='many_to_one')
    inv = inv.merge(firms[['firm_id', 'industry']], on='firm_id', validate='many_to_one')
    end = pd.Timestamp('2025-12-31')
    assert inv.issue_date.max() <= end and cash.date.max() <= end
    assert pay.pay_date_true.max() <= end, 'Payment beyond world end needs explicit censoring'
    rows = []
    for year in range(2019, 2026):
        cutoff = pd.Timestamp(year=year, month=12, day=31)
        issued = inv[inv.issue_date.dt.year.eq(year)]
        settled = inv[inv.term_days.gt(0) & inv.paid_date_true.dt.year.eq(year) &
                      inv.closure_type.isin(['paid', 'paid_after_credit_note'])].copy()
        settled['pay_days'] = (settled.paid_date_true - settled.issue_date).dt.days
        settled['late_days'] = (settled.paid_date_true - settled.due_date).dt.days
        live = inv[inv.issue_date.le(cutoff)].copy()
        paid = pay[pay.pay_date_true.le(cutoff)].groupby('invoice_id').amount.sum()
        note = live.credit_note.fillna(0).where(live.credit_note_date.le(cutoff), 0)
        writeoff = live.writeoff_amount.fillna(0).where(live.writeoff_date.le(cutoff), 0)
        live['open_vnd'] = (live.amount_gross - note - writeoff -
                            live.invoice_id.map(paid).fillna(0)).clip(lower=0)
        live['age_days'] = (cutoff - live.due_date).dt.days
        late = live[live.age_days.gt(0) & live.open_vnd.gt(1)]
        d = cash[cash.date.dt.year.eq(year)]
        for industry in ['ALL', *sorted(firms.industry.unique())]:
            a = issued if industry == 'ALL' else issued[issued.industry.eq(industry)]
            s = settled if industry == 'ALL' else settled[settled.industry.eq(industry)]
            l = late if industry == 'ALL' else late[late.industry.eq(industry)]
            c = d if industry == 'ALL' else d[d.industry.eq(industry)]
            ar = live if industry == 'ALL' else live[live.industry.eq(industry)]
            credit = a[a.term_days.gt(0)]
            total = a.amount_gross.sum()
            credit_v = credit.amount_gross.sum()
            overdue_v = l.open_vnd.sum()
            rows.append(dict(
                world=path.name, year=year, industry=industry,
                firms=int(c.firm_id.nunique()), invoices=int(len(a)),
                net_revenue_vnd=float(a.amount_net.sum()),
                active_customers=int(a.customer_id.nunique()),
                credit_value_share=float(credit_v / total) if total else np.nan,
                credit_count_share=float(len(credit) / len(a)) if len(a) else np.nan,
                credit_term_wmean_days=float(np.average(credit.term_days, weights=credit.amount_gross)) if credit_v else np.nan,
                settled_invoices=int(len(s)),
                pay_days_p50=float(s.pay_days.median()) if len(s) else np.nan,
                pay_days_p90=float(s.pay_days.quantile(.9)) if len(s) else np.nan,
                late_days_p50=float(s.late_days.median()) if len(s) else np.nan,
                late_days_p90=float(s.late_days.quantile(.9)) if len(s) else np.nan,
                paid_late_value_share=float(s.loc[s.late_days.gt(0), 'amount_gross'].sum() / s.amount_gross.sum()) if len(s) else np.nan,
                year_end_open_ar_vnd=float(ar.open_vnd.sum()),
                year_end_overdue_ar_vnd=float(overdue_v),
                year_end_overdue_ar_share=float(overdue_v / ar.open_vnd.sum()) if ar.open_vnd.sum() else np.nan,
                overdue_age_w_p50_days=weighted_quantile(l.age_days, l.open_vnd, .5),
                overdue_age_w_p90_days=weighted_quantile(l.age_days, l.open_vnd, .9),
                overdue_ar_1_30_share=float(l.loc[l.age_days.le(30), 'open_vnd'].sum() / overdue_v) if overdue_v else np.nan,
                overdue_ar_31_60_share=float(l.loc[l.age_days.between(31, 60), 'open_vnd'].sum() / overdue_v) if overdue_v else np.nan,
                overdue_ar_61_plus_share=float(l.loc[l.age_days.gt(60), 'open_vnd'].sum() / overdue_v) if overdue_v else np.nan,
                cash_balance_p10_vnd=float(c.balance.quantile(.1)) if len(c) else np.nan,
                cash_balance_p50_vnd=float(c.balance.quantile(.5)) if len(c) else np.nan,
                cash_balance_p90_vnd=float(c.balance.quantile(.9)) if len(c) else np.nan,
                negative_balance_firm_day_share=float(c.balance.lt(0).mean()) if len(c) else np.nan,
            ))
        if year == 2025:
            final = live.set_index('invoice_id').open_vnd
            diff = (final.reindex(inv.invoice_id).to_numpy() - inv.remaining_amount.to_numpy())
            assert np.nanmax(np.abs(diff)) <= 1.01, 'Year-end AR does not reconcile to invoice accounting'
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('outputs/data/v5_existing_world_metrics_20261026.csv'))
    args = parser.parse_args()
    names = [f'v5_lifecycle_control_{seed}' for seed in (94317, 94318, 94319)]
    rows = [row for name in names for row in one_world(SYNTH / name)]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(args.output, index=False)
    print(f'{len(rows)} rows -> {args.output}')


if __name__ == '__main__':
    main()
