"""Week-by-week simulation of the accountant feedback loop.

Compares, on the same deployment year (validation + test periods), what happens to the alert queue when the
user's one-click verdicts are used in different ways:

  static          no learning (baseline)
  relax           the draft design: a signal that is judged false-positive gets its threshold relaxed
                  (its weight multiplied down), a confirmed one gets it raised
  reweight        AAD-style: online logistic correction on top of the base score, trained from verdicts
  reweight+audit  same, plus a few randomly chosen *non-alerted* rows per company-week sent for review
                  (cures the selective-label bias: only alerted rows ever get a label)

Reviewer = oracle that can be wrong with probability `noise`. Hard-trigger rules cannot be silenced:
the correction is clipped so a row with a hard trigger never drops out of the top of the queue.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .methods import EntityDeviation, empirical_rank
from .metrics import entity_key, tie_break

GAMMA = 10.0


def build_matrix(df, rules_ref, entity: EntityDeviation):
    rule_rank = empirical_rank(rules_ref, df["rule_graph"].to_numpy(dtype=float))
    parts = entity.parts(df)
    ent_raw = np.vstack(list(parts.values())).T
    ent_rank = empirical_rank(entity.ref_score, ent_raw.max(axis=1))
    hits = (df[[c for c in df.columns if c.startswith("hit_")]].to_numpy(dtype=float) > 0).astype(float)
    x = np.hstack([rule_rank[:, None], ent_rank[:, None], hits, np.clip(ent_raw, 0, 10) / 10.0])
    base = np.maximum(rule_rank, ent_rank)
    # signal of origin for the 'relax' policy: 0 = rules, 1 = entity
    origin = (ent_rank > rule_rank).astype(int)
    return x, base, origin


def simulate(df: pd.DataFrame, x: np.ndarray, base: np.ndarray, origin: np.ndarray, mode: str, budget=3,
             audit=2, noise=0.0, seed=0, lr=.3, l2=.002, pos_weight=3.0, soft=0.0):
    rng = np.random.default_rng(seed)
    y = df["is_fraud"].to_numpy()
    weeks = df["week"].to_numpy()
    company = df["company_id"].to_numpy()
    ekey = entity_key(df).to_numpy()
    jitter = tie_break(len(df), seed)
    hard = df["rule_hard"].to_numpy(dtype=float) > 0 if "rule_hard" in df else np.zeros(len(df), bool)
    w = np.zeros(x.shape[1])
    source_weight = np.ones(2)
    cum, tp_rows, cases_found, alerts_total, case_tp, case_n = [], 0, set(), 0, 0, 0
    case_ids = df["case_id"].to_numpy()
    for wk in np.unique(weeks):
        idx = np.where(weeks == wk)[0]
        if mode == "relax":
            score = np.maximum(base[idx] * np.where(origin[idx] == 0, source_weight[0], source_weight[1]), 0)
        elif mode.startswith("reweight"):
            score = GAMMA * base[idx] + x[idx] @ w
            score = np.where(hard[idx], np.maximum(score, GAMMA * base[idx]), score)   # hard triggers cannot be pushed down
        else:
            score = base[idx]
        score = score + jitter[idx]
        pick = []
        for c in np.unique(company[idx]):
            loc = idx[company[idx] == c]
            s = score[company[idx] == c]
            order = np.argsort(-s)[:budget]
            pick.extend(loc[order].tolist())
        pick = np.array(pick, dtype=int)
        alerts_total += len(pick)
        tp_rows += int(y[pick].sum())
        for i in pick:
            if y[i]:
                cases_found.add(case_ids[i])
        # reviewer verdicts at entity-case level
        verdict = {}
        for i in pick:
            verdict.setdefault((company[i], ekey[i]), []).append(i)
        labelled, labels = [], []
        for members in verdict.values():
            truth = int(any(y[m] for m in members))
            seen = truth if rng.random() >= noise else 1 - truth
            case_n += 1
            case_tp += truth
            for m in members:
                labelled.append(m)
                labels.append(seen)
                if mode == "relax":
                    k = origin[m]
                    source_weight[k] = float(np.clip(source_weight[k] * (1.04 if seen else .94), .3, 1.5))
        if mode == "reweight+audit":
            chosen = set(pick.tolist())
            for c in np.unique(company[idx]):
                pool = [i for i in idx[company[idx] == c] if i not in chosen]
                if pool:
                    for i in rng.choice(pool, min(audit, len(pool)), replace=False):
                        labelled.append(i)
                        labels.append(int(y[i]) if rng.random() >= noise else 1 - int(y[i]))
        if mode.startswith("reweight") and labelled:
            xi = x[np.array(labelled)]
            yi = np.array(labels, dtype=float)
            yi = soft + (1 - 2 * soft) * yi          # label smoothing = assumed reviewer error rate
            z = GAMMA * base[np.array(labelled)] + xi @ w
            p = 1 / (1 + np.exp(-(z - GAMMA * .98)))
            sw = np.where(yi > .5, pos_weight, 1.0)
            grad = ((p - yi) * sw)[:, None] * xi
            w -= lr * (grad.mean(axis=0) + l2 * w)
        cum.append(tp_rows)
    positives_cases = len({c for c, f in zip(case_ids, y) if f})
    return dict(mode=mode, alerts=alerts_total, tp_rows=tp_rows, row_precision=tp_rows / max(1, alerts_total),
                cases_found=len(cases_found), cases_total=positives_cases, case_recall=len(cases_found) / max(1, positives_cases),
                entity_cases=case_n, entity_case_precision=case_tp / max(1, case_n), weekly_cum_tp=cum)
