"""T10: đóng góp mô hình, ưu tiên thu và kịch bản dùng cùng dòng số ngẫu nhiên."""
from __future__ import annotations
import numpy as np
import pandas as pd
from .t6_cash import simulate, K
from .t1 import expand, WEEK_FEATS
from ..text.vi_templates import FEATURE_LABELS


def explain_invoice(model, X_row):
    if len(X_row) != 1:
        raise ValueError('Chỉ giải thích một hoá đơn tại một cutoff')
    X, _, _ = expand(X_row, train=False, feats=model.feats)
    contrib = model.booster.predict(X, pred_contrib=True)[0, :-1]
    names = list(model.feats) + WEEK_FEATS
    ranked = sorted(zip(names, contrib), key=lambda item: item[1])
    chosen = [p for p in ranked if p[1] < 0][:3] + [p for p in reversed(ranked) if p[1] > 0][:3]
    return [{'feature': name, 'description': FEATURE_LABELS.get(name, name), 'contribution': float(value),
             'direction': 'tăng xác suất thu trong tuần đầu' if value > 0 else 'giảm xác suất thu trong tuần đầu'}
            for name, value in chosen]


def _risk(args):
    bal, _ = simulate(**args)
    return float((bal.min(1) < 0).mean()), bal


def rank_collections(snapshot, P, sim_args, top_n=50):
    """ΔP là tác động mô phỏng của thu đủ tuần đầu, không phải hiệu quả nhân quả."""
    snapshot = snapshot.reset_index(drop=True)
    P = np.asarray(P)
    args = dict(sim_args, open_df=snapshot, P=P)
    base, _ = _risk(args)
    priority = snapshot.amount_open.to_numpy() * (1 - P[:, :2].sum(1))
    rows = []
    for ix in np.argsort(-priority)[:top_n]:
        forced = np.full(len(snapshot), -1, int); forced[ix] = 0
        risk, _ = _risk(dict(args, force_week=forced))
        row = dict(invoice_id=snapshot.iloc[ix].invoice_id, amount_open=float(snapshot.iloc[ix].amount_open),
                   late_2w_probability=float(1 - P[ix, :2].sum()), baseline_shortfall=base,
                   scenario_shortfall=risk, delta_shortfall=base - risk,
                   evidence_type='policy_simulation_not_causal')
        if 'collection_hours' in snapshot and snapshot.iloc[ix].collection_hours > 0:
            row['delta_per_hour'] = row['delta_shortfall'] / snapshot.iloc[ix].collection_hours
        rows.append(row)
    return pd.DataFrame(rows).sort_values('delta_shortfall', ascending=False) if rows else pd.DataFrame()


def what_if(sim_args, delay_customer=None, delay_weeks=2, shift_out=None, revenue_drop=None):
    args = dict(sim_args)
    if delay_customer is not None:
        args['payment_shift'] = np.where(args['open_df']['customer_id'].eq(delay_customer), delay_weeks, 0)
    if shift_out is not None:
        # (tuần nguồn, tuần đích, số tiền), chỉ số tuần bắt đầu từ 0.
        src, dst, amount = shift_out
        if not 0 <= src < K or not 0 <= dst < K or amount < 0:
            raise ValueError('Dời chi không hợp lệ')
        out = np.asarray(args['known_out'], float).copy()
        if amount > out[src]:
            raise ValueError('Số tiền dời lớn hơn khoản chi nguồn')
        out[src] -= amount; out[dst] += amount
        args['known_out'] = out
    if revenue_drop is not None:
        if not 0 <= revenue_drop <= 1:
            raise ValueError('revenue_drop trong [0,1]')
        if args.get('rev_q') is not None:
            args['rev_q'] = np.asarray(args['rev_q']) * (1 - revenue_drop)
    risk, bal = _risk(args)
    return {'shortfall_probability': risk, 'quantiles': np.quantile(bal, [.1, .5, .9], axis=0).T}


def scenario_library(sim_args=None):
    definitions = {'all_payments_plus30d': {'delay_days': 30}, 'all_payments_plus60d': {'delay_days': 60},
                   'top_customer_default': {'default_top_customer': True}, 'revenue_minus30pct': {'revenue_drop': .3}}
    if sim_args is None:
        return definitions
    # Kịch bản tất định: ngày trả tại trung vị, doanh thu tại P50, không capex ngẫu nhiên.
    P = np.asarray(sim_args['P'])
    cdf = P.cumsum(1)
    median = np.array([np.searchsorted(row, .5) for row in cdf])
    deterministic = np.zeros_like(P)
    inside = median < K
    deterministic[np.where(inside)[0], median[inside]] = 1
    args0 = dict(sim_args, P=deterministic, n=1, rho=0., rho_customer=0., capex_rate=0., p_bad=None)
    if args0.get('rev_q') is not None:
        args0['rev_q'] = np.repeat(np.asarray(args0['rev_q'])[:, 1:2], 3, axis=1)
    rows = []
    for name, definition in definitions.items():
        args = dict(args0)
        if 'delay_days' in definition:
            args['payment_shift'] = np.full(len(P), int(np.ceil(definition['delay_days'] / 7)))
        if 'default_top_customer' in definition:
            inv = args['open_df']
            if len(inv):
                top = inv.groupby('customer_id').amount_open.sum().idxmax()
                args['force_week'] = np.where(inv.customer_id.eq(top), K, -1)
        if 'revenue_drop' in definition and args.get('rev_q') is not None:
            args['rev_q'] = args['rev_q'] * (1 - definition['revenue_drop'])
        _, bal = simulate(**args)
        hit = np.flatnonzero(bal[0] < 0)
        rows.append(dict(scenario=name, runway_weeks=int(hit[0]) if len(hit) else K,
                         censored_at_13w=not bool(len(hit)), minimum_balance=float(bal.min())))
    return pd.DataFrame(rows)
