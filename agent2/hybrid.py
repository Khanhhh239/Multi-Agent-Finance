"""Hybrid detectors studied on world v4 (method study, stage 2).

Three generic ideas, none tied to a particular scheme (no new red-flag feature or detector was added here):

1. Family-balanced training (`LGBM(balance="family")`): every fraud family in the training labels carries the same total
   weight, so a few high-volume schemes do not decide the trees. Motivation: rare and unseen schemes.
2. Feature-level fusion, "L4": LightGBM on L3 inputs plus the label-free detector outputs (each EntityDeviation tail,
   the entity maximum, autoencoder error rank, Isolation Forest rank). The detectors are fitted on the firm's own
   training period without labels; the trees learn when each one is trustworthy. Related: stacking (Wolpert 1992),
   "JET results as features" (Gronewald et al.), semi-supervised use of unsupervised scores (ADBench, XGBOD by Zhao and
   Hryniewicki 2018).
3. Collective evidence (`Collective`): fraud is a case that repeats (ACFE 2024 median duration 8-24 months). Stage 1
   scores every row; stage 2 adds, for each row, what the past 90 days of the same creator / approver / vendor / employee /
   customer looked like (max rank, number of rows in the top 1 and 5 percent, row count) and re-scores. Stage-1 scores
   on the training period are cross-fitted in time blocks so stage 2 never learns from in-sample scores. Causal: only
   earlier rows are used. Related: collective classification (Sen et al. 2008), relational features in GADBench.

Plus the alert policy: `slots_alerts` = exploit/explore split of each company-week budget (see alerting.select_mixed).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import methods as M
from .data import engineered_columns, friend_columns, rule_columns

KEYS = ("creator_id", "approver_id", "vendor_id", "employee_id", "customer_id")
U_RANK = ("u_entity_r", "u_ae_r", "u_if_r")


# ---------------------------------------------------------------------------------------------- label-free detector outputs
def attach_unsupervised(df: pd.DataFrame, cache: Path | None = None, seed=0) -> pd.DataFrame:
    """Fit EntityDeviation, autoencoder and Isolation Forest on the training period (no labels); attach their outputs.

    Ranks are relative to the firm's own training-period distribution, so the columns transfer between firms."""
    cache = Path(cache) if cache else None
    if cache and cache.exists():
        u = pd.read_pickle(cache)
    else:
        tr, va = df[df.split == "train"], df[df.split == "validation"]
        ent = M.EntityDeviation().fit(tr, va)
        cols = {f"u_ent_{k}": np.clip(v, 0, 12) for k, v in ent.parts(df).items()}
        e_all = ent.score(df)
        ae = M.Autoencoder(name="ae", seed=seed).fit(tr)
        a_all = ae.score(df)
        iso = M.IForest(name="if", seed=seed).fit(tr)
        i_all = iso.score(df)
        trm = (df.split == "train").to_numpy()
        cols.update(u_entity=e_all, u_entity_r=M.empirical_rank(e_all[trm], e_all), u_ae_r=M.empirical_rank(a_all[trm], a_all),
                    u_if_r=M.empirical_rank(i_all[trm], i_all))
        u = pd.DataFrame(cols)
        u.insert(0, "transaction_id", df["transaction_id"].values)
        if cache:
            u.to_pickle(cache)
    return df.merge(u, on="transaction_id", how="left", validate="one_to_one")


def u_columns(df):
    return [c for c in df.columns if c.startswith("u_ent_")] + list(U_RANK)


FEATURE_SETS = {
    "L3": lambda d: friend_columns(d) + engineered_columns(d) + rule_columns(d),
    "L4": lambda d: friend_columns(d) + engineered_columns(d) + rule_columns(d) + u_columns(d),
}


# ---------------------------------------------------------------------------------------------- supervised learner
def family_weights(train: pd.DataFrame) -> np.ndarray:
    """Legitimate rows weight 1; each fraud family gets an equal share of the original positive mass."""
    y = train["is_fraud"].to_numpy()
    w = np.ones(len(train))
    fam = train["fraud_type"].to_numpy()
    pos = y == 1
    if pos.sum() == 0:
        return w
    names, counts = np.unique(fam[pos], return_counts=True)
    share = pos.sum() / len(names)
    for n, c in zip(names, counts):
        w[pos & (fam == n)] = share / c
    return w


class LGBM(M.Base):
    """LightGBM as in methods.Supervised, plus optional family-balanced sample weights."""
    regime = "S"

    def __init__(self, cols_fn, name, balance=None, seed=0, grid=((7, .05), (15, .05))):
        self.cols_fn, self.name, self.balance, self.seed, self.grid = cols_fn, name, balance, seed, grid

    def __getstate__(self):
        state = self.__dict__.copy()
        state["cols_fn"] = None
        return state

    def fit(self, train, valid=None):
        import lightgbm as lgb
        from sklearn.metrics import average_precision_score
        self.cols = self.cols_fn(train)
        x, y = train[self.cols].to_numpy(dtype=np.float32), train["is_fraud"].to_numpy()
        sw = family_weights(train) if self.balance == "family" else None
        pos_weight = max(1.0, (len(y) - y.sum()) / max(1, y.sum())) ** .5
        best = (-1.0, None)
        for leaves, lr in self.grid:
            m = lgb.LGBMClassifier(n_estimators=600, learning_rate=lr, num_leaves=leaves, min_child_samples=10, subsample=.8,
                                   subsample_freq=1, colsample_bytree=.6, reg_lambda=2.0, scale_pos_weight=pos_weight,
                                   random_state=self.seed, verbose=-1, n_jobs=4)
            if valid is not None and valid["is_fraud"].sum() > 0:
                xv = valid[self.cols].to_numpy(dtype=np.float32)
                m.fit(x, y, sample_weight=sw, eval_set=[(xv, valid["is_fraud"].to_numpy())], eval_metric="average_precision",
                      callbacks=[lgb.early_stopping(60, verbose=False)])
                ap = average_precision_score(valid["is_fraud"], m.predict_proba(xv)[:, 1])
            else:
                m.set_params(n_estimators=200)
                m.fit(x, y, sample_weight=sw)
                ap = 0.0
            if ap > best[0]:
                best = (ap, m)
        self.model = best[1]
        return self

    def score(self, df):
        return self.model.predict_proba(df[self.cols].to_numpy(dtype=np.float32))[:, 1]


# ---------------------------------------------------------------------------------------------- collective evidence
def memory_features(frame: pd.DataFrame, window="90D") -> pd.DataFrame:
    """For each row: statistics of the same entity's *earlier* rows (same company) within `window`.

    `frame` needs company_id, t, r (stage-1 rank in [0, 1]) and the KEYS columns that exist."""
    frame = frame.sort_values("t", kind="stable")
    out = pd.DataFrame(index=frame.index)
    for k in KEYS:
        if k not in frame.columns:
            continue
        ok = frame[k].astype(str) != ""
        sub = frame.loc[ok, ["company_id", "t", "r", k]].copy()
        sub["g"] = sub["company_id"] + ":" + sub[k].astype(str)
        sub["hi"] = (sub["r"] >= .99).astype(float)
        sub["mid"] = (sub["r"] >= .95).astype(float)
        sub["one"] = 1.0
        # sorted by group then time, so the rolling result (group order of appearance, rows in order) aligns by position
        sub = sub.sort_values(["g", "t"], kind="stable")
        roll = sub.groupby("g", sort=False).rolling(window, on="t", closed="left")
        mx = pd.Series(roll["r"].max().to_numpy(), index=sub.index)
        sm = roll[["hi", "mid", "one"]].sum()
        out[f"m_{k}_max"] = mx.reindex(frame.index).fillna(0.0)
        for c in ("hi", "mid", "one"):
            out[f"m_{k}_{c}"] = pd.Series(sm[c].to_numpy(), index=sub.index).reindex(frame.index).fillna(0.0)
    out["m_any_max"] = out[[c for c in out.columns if c.endswith("_max")]].max(axis=1)
    out["m_any_hi"] = out[[c for c in out.columns if c.endswith("_hi")]].max(axis=1)
    return out.reindex(frame.index)


class Collective(M.Base):
    regime = "S"

    def __init__(self, base_factory, name, folds=4, seed=0):
        self.base_factory, self.name, self.folds, self.seed = base_factory, name, folds, seed

    def _frame(self, df, r):
        cols = ["transaction_id", "company_id", "t"] + [k for k in KEYS if k in df.columns]
        return df[cols].assign(r=r)

    def _stage2_x(self, df, mem):
        types = [c for c in df.columns if c.startswith("type_")]
        x = pd.concat([df[["transaction_id"]].reset_index(drop=True), df[types].reset_index(drop=True)], axis=1)
        x = x.merge(mem, on="transaction_id", how="left")
        return x.drop(columns="transaction_id")

    def _memory_for(self, df, r, history):
        cur = self._frame(df, r)
        if history is not None and len(history):
            hist = history[(history.t < cur.t.min()) & ~history.transaction_id.isin(cur.transaction_id)]
            both = pd.concat([hist, cur], ignore_index=True)
        else:
            both = cur.reset_index(drop=True)
        mem = memory_features(both)
        mem.insert(0, "transaction_id", both["transaction_id"].values)
        mem.insert(1, "r", both["r"].values)
        return mem[mem.transaction_id.isin(cur.transaction_id)]

    def fit(self, train, valid=None):
        import lightgbm as lgb
        train = train.sort_values("t", kind="stable")
        block = pd.qcut(train["t"].rank(method="first"), self.folds, labels=False).to_numpy()
        oof = np.zeros(len(train))
        for k in range(self.folds):
            m = self.base_factory().fit(train[block != k], valid)
            oof[block == k] = m.score(train[block == k])
        self.base = self.base_factory().fit(train, valid)
        self.ref = np.sort(oof)
        r_tr = M.empirical_rank(self.ref, oof)
        hist_tr = self._frame(train, r_tr)
        mem_tr = self._memory_for(train, r_tr, None)
        x_tr = self._stage2_x(train, mem_tr)
        self.history = hist_tr
        eval_set = None
        if valid is not None and valid["is_fraud"].sum() > 0:
            r_va = M.empirical_rank(self.ref, self.base.score(valid))
            mem_va = self._memory_for(valid, r_va, hist_tr)
            eval_set = [(self._stage2_x(valid, mem_va).to_numpy(dtype=np.float32), valid["is_fraud"].to_numpy())]
            self.history = pd.concat([hist_tr, self._frame(valid, r_va)], ignore_index=True)
        self.x_cols = list(x_tr.columns)
        y = train["is_fraud"].to_numpy()
        pos_weight = max(1.0, (len(y) - y.sum()) / max(1, y.sum())) ** .5
        self.model = lgb.LGBMClassifier(n_estimators=400 if eval_set else 150, learning_rate=.05, num_leaves=7, min_child_samples=20,
                                        subsample=.8, subsample_freq=1, colsample_bytree=.8, reg_lambda=2.0, scale_pos_weight=pos_weight,
                                        random_state=self.seed, verbose=-1, n_jobs=4)
        kw = dict(eval_set=eval_set, eval_metric="average_precision", callbacks=[lgb.early_stopping(60, verbose=False)]) if eval_set else {}
        self.model.fit(x_tr.to_numpy(dtype=np.float32), y, **kw)
        return self

    def set_history(self, frames: list[pd.DataFrame]):
        """Deployment on another firm: its earlier periods, scored by stage 1 (no labels needed)."""
        parts = [self._frame(f, M.empirical_rank(self.ref, self.base.score(f))) for f in frames]
        self.history = pd.concat(parts, ignore_index=True)
        return self

    def score(self, df):
        r = M.empirical_rank(self.ref, self.base.score(df))
        mem = self._memory_for(df, r, self.history)
        x = self._stage2_x(df, mem)[self.x_cols]
        return self.model.predict_proba(x.to_numpy(dtype=np.float32))[:, 1]


# ---------------------------------------------------------------------------------------------- label-free novelty channel
class Novelty(M.Base):
    """max of validation-period ranks of the rule score and label-free detector outputs (cold start, no labels)."""
    regime = "H"

    def __init__(self, cols=("rule_graph", "u_entity"), name="Novelty max(Rules,Entity)"):
        self.cols, self.name = cols, name

    def fit(self, train, valid=None):
        ref = valid if valid is not None else train
        self.ref = {c: np.sort(ref[c].to_numpy(dtype=float)) for c in self.cols}
        return self

    def score(self, df):
        ranks = [M.empirical_rank(self.ref[c], df[c].to_numpy(dtype=float)) for c in self.cols]
        return np.max(ranks, axis=0) + 1e-3 * np.mean(ranks, axis=0)
