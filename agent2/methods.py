"""Detection methods with one interface: fit(train, valid) then score(df) -> higher = more suspicious.

Regimes (stated honestly, because an SME has no labels on day one):
  U  unsupervised: fitted on unlabelled history only (IF, ECOD, HBOS, autoencoder, entity baselines)
  R  rule library only (the friend's 31 rules, no learning)
  H  hybrid, still label-free: preset rank blend of rules and unsupervised scores
  S  supervised on pooled labelled history from other firms / synthetic (upper bound, transfer risk)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import QuantileTransformer

from .data import engineered_columns, friend_columns, rule_columns

ONE_HOT_PREFIXES = ("type_", "debit_", "credit_", "pair_")


def unsupervised_columns(df):
    """Continuous / key binary columns; drops account and type one-hots that dominate distance-free scores."""
    cols = [c for c in friend_columns(df) if not c.startswith(ONE_HOT_PREFIXES)]
    return cols + engineered_columns(df)


def empirical_rank(reference: np.ndarray, scores: np.ndarray) -> np.ndarray:
    ref = np.sort(reference)
    return (np.searchsorted(ref, scores, side="left") + np.searchsorted(ref, scores, side="right")) / (2 * len(ref))


class Base:
    name = "base"
    regime = "U"

    def fit(self, train: pd.DataFrame, valid: pd.DataFrame | None = None):
        return self

    def score(self, df: pd.DataFrame) -> np.ndarray:
        raise NotImplementedError


class RuleScore(Base):
    regime = "R"

    def __init__(self, column="rule_graph", name=None):
        self.column, self.name = column, name or f"Rules[{column}]"

    def score(self, df):
        return df[self.column].to_numpy(dtype=float)


class IForest(Base):
    def __init__(self, cols_fn=unsupervised_columns, n_estimators=300, name="IsolationForest", seed=0):
        self.cols_fn, self.n, self.name, self.seed = cols_fn, n_estimators, name, seed

    def fit(self, train, valid=None):
        self.cols = self.cols_fn(train)
        self.model = IsolationForest(n_estimators=self.n, max_samples=min(2048, len(train)), random_state=self.seed, n_jobs=-1)
        self.model.fit(train[self.cols].to_numpy(dtype=np.float32))
        return self

    def score(self, df):
        return -self.model.score_samples(df[self.cols].to_numpy(dtype=np.float32))


class ECOD(Base):
    """Empirical-CDF outlier detection (Li et al., TKDE 2023), re-implemented: parameter-free, per-feature tails.

    Score = max(sum of left-tail, sum of right-tail, skew-directed sum) of -log ECDF tail probabilities. Constant
    features are dropped. Per-feature contributions give a native explanation (see `explain`).
    """

    def __init__(self, cols_fn=unsupervised_columns, name="ECOD"):
        self.cols_fn, self.name = cols_fn, name

    def fit(self, train, valid=None):
        cols = self.cols_fn(train)
        x = train[cols].to_numpy(dtype=float)
        keep = x.std(axis=0) > 1e-9
        self.cols = [c for c, k in zip(cols, keep) if k]
        x = x[:, keep]
        self.sorted = np.sort(x, axis=0)
        mean, std = x.mean(axis=0), x.std(axis=0)
        self.skew = np.sign(((x - mean) ** 3).mean(axis=0) / std ** 3)
        return self

    def tails(self, df):
        x = df[self.cols].to_numpy(dtype=float)
        n = len(self.sorted)
        left = np.empty_like(x)
        right = np.empty_like(x)
        for j in range(x.shape[1]):
            col = self.sorted[:, j]
            left[:, j] = (np.searchsorted(col, x[:, j], side="right") + 1) / (n + 2)
            right[:, j] = (n - np.searchsorted(col, x[:, j], side="left") + 1) / (n + 2)
        return -np.log(left), -np.log(right)

    def contributions(self, df):
        left, right = self.tails(df)
        auto = np.where(self.skew < 0, left, right)
        return left, right, auto

    def score(self, df):
        left, right, auto = self.contributions(df)
        return np.maximum.reduce([left.sum(1), right.sum(1), auto.sum(1)])

    def explain(self, df, top=3):
        left, right, auto = self.contributions(df)
        contrib = np.maximum.reduce([left, right, auto])
        order = np.argsort(-contrib, axis=1)[:, :top]
        return [[(self.cols[j], float(contrib[i, j])) for j in order[i]] for i in range(len(df))]


class HBOS(Base):
    def __init__(self, cols_fn=unsupervised_columns, bins=20, name="HBOS"):
        self.cols_fn, self.bins, self.name = cols_fn, bins, name

    def fit(self, train, valid=None):
        cols = self.cols_fn(train)
        x = train[cols].to_numpy(dtype=float)
        keep = x.std(axis=0) > 1e-9
        self.cols = [c for c, k in zip(cols, keep) if k]
        self.edges, self.dens = [], []
        for j in range(len(self.cols)):
            col = x[:, np.where(keep)[0][j]]
            edges = np.unique(np.quantile(col, np.linspace(0, 1, self.bins + 1)))
            if len(edges) < 3:
                edges = np.unique(np.concatenate([edges, [col.max() + 1]]))
            counts, edges = np.histogram(col, bins=edges)
            width = np.diff(edges)
            self.edges.append(edges)
            self.dens.append(np.maximum(counts / (width * len(col)), 1e-6 / max(width.mean(), 1e-9)))
        return self

    def score(self, df):
        x = df[self.cols].to_numpy(dtype=float)
        total = np.zeros(len(df))
        for j, (edges, dens) in enumerate(zip(self.edges, self.dens)):
            idx = np.clip(np.searchsorted(edges, x[:, j], side="right") - 1, 0, len(dens) - 1)
            density = dens[idx]
            outside = (x[:, j] < edges[0]) | (x[:, j] > edges[-1])
            density = np.where(outside, dens.min() * .5, density)
            total += -np.log(np.maximum(density, 1e-12))
        return total


class Autoencoder(Base):
    """Small MLP autoencoder (sklearn) on quantile-normalised features; score = mean squared reconstruction error."""

    def __init__(self, cols_fn=unsupervised_columns, hidden=(48, 12, 48), name="Autoencoder", seed=0, max_iter=60):
        self.cols_fn, self.hidden, self.name, self.seed, self.max_iter = cols_fn, hidden, name, seed, max_iter

    def fit(self, train, valid=None):
        cols = self.cols_fn(train)
        x = train[cols].to_numpy(dtype=float)
        self.cols = [c for c, k in zip(cols, x.std(axis=0) > 1e-9) if k]
        x = train[self.cols].to_numpy(dtype=float)
        self.q = QuantileTransformer(n_quantiles=200, output_distribution="normal", subsample=200_000, random_state=self.seed)
        z = self.q.fit_transform(x)
        self.model = MLPRegressor(hidden_layer_sizes=self.hidden, activation="relu", max_iter=self.max_iter, random_state=self.seed,
                                  early_stopping=False, learning_rate_init=1e-3, batch_size=256)
        self.model.fit(z, z)
        return self

    def score(self, df):
        z = self.q.transform(df[self.cols].to_numpy(dtype=float))
        return ((self.model.predict(z) - z) ** 2).mean(axis=1)


class Supervised(Base):
    """LightGBM trained on labelled rows; n_estimators / leaves chosen by validation AP (never the test split)."""
    regime = "S"

    def __init__(self, cols_fn, name, seed=0, grid=((7, .05), (15, .05))):
        self.cols_fn, self.name, self.seed, self.grid = cols_fn, name, seed, grid

    def __getstate__(self):
        state = self.__dict__.copy()
        state["cols_fn"] = None
        return state

    def fit(self, train, valid=None):
        import lightgbm as lgb
        from sklearn.metrics import average_precision_score
        self.cols = self.cols_fn(train)
        x, y = train[self.cols].to_numpy(dtype=np.float32), train["is_fraud"].to_numpy()
        best = (-1.0, None)
        pos_weight = max(1.0, (len(y) - y.sum()) / max(1, y.sum()) ** 1.0) ** .5
        for leaves, lr in self.grid:
            m = lgb.LGBMClassifier(n_estimators=600, learning_rate=lr, num_leaves=leaves, min_child_samples=10,
                                   subsample=.8, subsample_freq=1, colsample_bytree=.6, reg_lambda=2.0,
                                   scale_pos_weight=pos_weight, random_state=self.seed, verbose=-1, n_jobs=4)
            if valid is not None and valid["is_fraud"].sum() > 0:
                m.fit(x, y, eval_set=[(valid[self.cols].to_numpy(dtype=np.float32), valid["is_fraud"].to_numpy())],
                      eval_metric="average_precision", callbacks=[lgb.early_stopping(60, verbose=False)])
                s = m.predict_proba(valid[self.cols].to_numpy(dtype=np.float32))[:, 1]
                ap = average_precision_score(valid["is_fraud"], s)
            else:
                m.set_params(n_estimators=200)
                m.fit(x, y)
                ap = 0.0
            if ap > best[0]:
                best = (ap, m)
        self.model = best[1]
        return self

    def score(self, df):
        return self.model.predict_proba(df[self.cols].to_numpy(dtype=np.float32))[:, 1]


class Blend(Base):
    """Label-free preset rank blend. References come from the fit-time (training) distribution only."""
    regime = "H"

    def __init__(self, parts, weights, name):
        self.parts, self.weights, self.name = parts, weights, name

    def fit(self, train, valid=None):
        self.ref = {}
        for p in self.parts:
            p.fit(train, valid)
            self.ref[p.name] = p.score(valid if valid is not None else train)
        return self

    def score(self, df):
        total = np.zeros(len(df))
        for p, w in zip(self.parts, self.weights):
            total += w * empirical_rank(self.ref[p.name], p.score(df))
        return total


class Gate(Base):
    """Rules decide the order; the unsupervised score only breaks ties and rescues rows no rule saw.

    score = rule_rank_band + eps * unsupervised_rank. Fixes the friend's 80/20 blend, where a weak IF score
    pushed rule hits out of the top of the queue.
    """
    regime = "H"

    def __init__(self, rule, other, eps=.5, name="Gate"):
        self.rule, self.other, self.eps, self.name = rule, other, eps, name

    def fit(self, train, valid=None):
        self.other.fit(train, valid)
        self.ref = self.other.score(valid if valid is not None else train)
        return self

    def score(self, df):
        r = self.rule.score(df)
        o = empirical_rank(self.ref, self.other.score(df))
        return r + self.eps * o


def supervised_sets():
    return {
        "friend190": lambda d: friend_columns(d),
        "eng": lambda d: unsupervised_columns(d),
        "friend190+eng": lambda d: friend_columns(d) + engineered_columns(d),
        "friend190+eng+rules": lambda d: friend_columns(d) + engineered_columns(d) + rule_columns(d),
        "rules": lambda d: rule_columns(d),
    }



class EntityDeviation(Base):
    """Label-free one-sided deviation from each entity's own history (vendor, employee, creator, approver).

    Each detector is only 'active' where the entity has enough history. Score = max over detectors of
    -log(empirical tail probability measured on the training period). This is the piece meant to notice
    schemes nobody wrote a rule for (overpricing, padded payroll, expense padding, near-duplicate payments).
    """

    SPECS = [
        ("price_logratio", lambda d: d["price_n"] >= 3),
        ("price_logz", lambda d: d["price_n"] >= 3),
        ("price_shift3", lambda d: d["price_n"] >= 6),
        ("p_logratio", lambda d: (d["p_n"] >= 2) & (d["is_bonus_season"] == 0)),
        ("p_logratio_bonus", lambda d: (d["p_n"] >= 2) & (d["is_bonus_season"] == 1)),
        ("cu_logratio", lambda d: d["cu_n"] >= 5),
        ("near_dup_other_invoice_30d", lambda d: d["v_n"] >= 1),
        ("near_dup_30d", lambda d: d["v_n"] >= 1),
        ("creator_cash_near_selflimit_30d", lambda d: d["creator_cash_30d"] >= 1),
        ("amount_selflimit_ratio", lambda d: (d["self_approved"] == 1) & (d["type_cash_expense"] == 1)),
        ("creator_unsupported_selfcash_30d", lambda d: (d["type_cash_expense"] == 1) & (d["self_approved"] == 1) & (d["support_doc_count"] <= 1)),
        ("v_days_dormant_amount", lambda d: d["v_days_since_last"] >= 180),
        # world-v4 red flags (skipped automatically when the columns are absent)
        ("receipt_payer_mismatch", lambda d: d["type_customer_receipt"] == 1),
        ("collector_late_trend_90d", lambda d: d["type_customer_receipt"] == 1),
        ("payee_not_on_master", lambda d: d["type_vendor_payment"] == 1),
        ("payroll_after_leave", lambda d: d["type_payroll"] == 1),
        ("payroll_off_calendar", lambda d: d["type_payroll"] == 1),
        ("payroll_rows_same_month", lambda d: d["type_payroll"] == 1),
        ("writeoff_recency", lambda d: d["writeoff_overdue_days"] != 0),
        ("refund_to_foreign_account", lambda d: d["refund_to_foreign_account"] >= 0),
        ("return_vs_recent_sales", lambda d: d["return_vs_recent_sales"] > 0),
        ("writeoff_vs_cogs_90d", lambda d: d["writeoff_vs_cogs_90d"] > 0),
        ("creator_writeoffs_90d", lambda d: d["writeoff_vs_cogs_90d"] > 0),
        ("customer_amount_logz", lambda d: d["type_sales_invoice"] == 1),
        ("self_approved_advance_ratio", lambda d: d["self_approved_advance_ratio"] > 0),
    ]
    ALIAS = {"p_logratio_bonus": "p_logratio", "v_days_dormant_amount": "v_logratio"}
    SOURCE = {"writeoff_recency": "writeoff_overdue_days"}

    def __init__(self, name="EntityDeviation", specs=None):
        self.name = name
        self.specs = specs or self.SPECS

    def __getstate__(self):          # lambdas are not picklable; the default spec list is restored on load
        state = self.__dict__.copy()
        state["specs"] = None
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        self.specs = [(c, a) for c, a in self.SPECS if c in self.ref]

    @staticmethod
    def value(d, col):
        if col == "writeoff_recency":
            return -d["writeoff_overdue_days"].to_numpy(dtype=float)
        return d[EntityDeviation.ALIAS.get(col, col)].to_numpy(dtype=float)

    def usable(self, d, col):
        return EntityDeviation.SOURCE.get(col, EntityDeviation.ALIAS.get(col, col)) in d.columns

    def fit(self, train, valid=None):
        self.ref = {}
        self.specs = [(c, a) for c, a in self.SPECS if self.usable(train, c)]
        for col, active in self.specs:
            mask = active(train).to_numpy()
            self.ref[col] = np.sort(self.value(train, col)[mask])
        self.ref_score = self.score(train)
        return self

    def parts(self, df):
        out = {}
        for col, active in self.specs:
            ref = self.ref[col]
            mask = active(df).to_numpy()
            x = self.value(df, col)
            if len(ref) < 20:
                out[col] = np.zeros(len(df))
                continue
            tail = (len(ref) - np.searchsorted(ref, x, side="left") + 1) / (len(ref) + 1)
            out[col] = np.where(mask, -np.log(tail), 0.0)
        return out

    def score(self, df):
        p = self.parts(df)
        return np.max(np.vstack(list(p.values())), axis=0)

    def explain(self, df, top=2):
        p = self.parts(df)
        cols = list(p)
        mat = np.vstack([p[c] for c in cols]).T
        order = np.argsort(-mat, axis=1)[:, :top]
        return [[(cols[j], float(mat[i, j])) for j in order[i] if mat[i, j] > 0] for i in range(len(df))]


class RuleLogit(Base):
    """Interpretable calibrated rule weights: L2 logistic regression on rule hits only (about 34 weights)."""
    regime = "S"

    def __init__(self, name="Rules (weights learned)", C=.3):
        self.name, self.C = name, C

    def fit(self, train, valid=None):
        from sklearn.linear_model import LogisticRegression
        self.cols = rule_columns(train)
        x = (train[self.cols].to_numpy(dtype=float) > 0).astype(float)
        self.model = LogisticRegression(C=self.C, class_weight="balanced", max_iter=2000)
        self.model.fit(x, train["is_fraud"].to_numpy())
        return self

    def score(self, df):
        x = (df[self.cols].to_numpy(dtype=float) > 0).astype(float)
        return self.model.decision_function(x)


class RankFusion(Base):
    """Label-free fusion of already-fitted parts after validation-rank normalisation (mean or max)."""
    regime = "H"

    def __init__(self, parts, mode="mean", weights=None, name="Fusion", refit_parts=True):
        self.parts, self.mode, self.name = parts, mode, name
        self.weights = weights or [1.0] * len(parts)
        self.refit = refit_parts

    def fit(self, train, valid=None):
        self.ref = []
        ref_df = valid if valid is not None else train
        for p in self.parts:
            if self.refit:
                p.fit(train, valid)
            self.ref.append(p.score(ref_df))
        return self

    def score(self, df):
        ranks = [w * empirical_rank(r, p.score(df)) for p, r, w in zip(self.parts, self.ref, self.weights)]
        if self.mode == "max":
            return np.max(np.vstack(ranks), axis=0)
        return np.sum(np.vstack(ranks), axis=0) / sum(self.weights)


def fit_prior_logistic(X, y, w0, lam):
    """Class-balanced logistic regression whose weights are pulled toward a structural prior `w0` (L2 around w0).

    Prior: every detector is monotone (a bigger deviation is never safer), so weights start positive; the data can
    move them but a detector that never fired on past positives is not driven to zero as easily as with plain L2.
    """
    from scipy.optimize import minimize
    sw = np.where(y > 0, (len(y) - y.sum()) / max(1, y.sum()), 1.0)
    sw = sw / sw.mean()

    def f(theta):
        b, w = theta[0], theta[1:]
        z = X @ w + b
        loss = np.sum(sw * (np.logaddexp(0, z) - y * z)) / len(y) + lam * np.sum((w - w0) ** 2)
        p = 1 / (1 + np.exp(-z))
        g = (X.T @ (sw * (p - y))) / len(y) + 2 * lam * (w - w0)
        return loss, np.concatenate([[np.sum(sw * (p - y)) / len(y)], g])

    return minimize(f, np.concatenate([[-3.0], w0]), jac=True, method="L-BFGS-B").x


class CalibratedStack:
    """'Calibrated evidence stack': pretrained on other (labelled) worlds, applied to a new firm.

    Inputs: learned rule weights (RuleLogit decision value, trained leave-one-world-out so the stack never sees
    in-sample rule scores) and the clipped tail scores of every EntityDeviation detector, the latter measured against
    the *new firm's own* history. 13 weights plus a bias, fully inspectable.
    """

    def __init__(self, lam=.02, prior_entity=.25, clip=12.0):
        self.lam, self.prior_entity, self.clip = lam, prior_entity, clip

    def inputs(self, df, rule_model, entity):
        parts = entity.parts(df)
        return np.hstack([rule_model.score(df)[:, None], np.vstack([np.clip(v, 0, self.clip) for v in parts.values()]).T])

    def fit_worlds(self, worlds: list[pd.DataFrame], drop_family: str | None = None):
        pool = lambda d: d[d.split.isin(["train", "validation"])].pipe(lambda x: x[x.fraud_type != drop_family] if drop_family else x)
        ents = [EntityDeviation().fit(w[w.split == "train"], w[w.split == "validation"]) for w in worlds]
        Xs, Ys = [], []
        for i, w in enumerate(worlds):
            rl = RuleLogit().fit(pd.concat([pool(o) for j, o in enumerate(worlds) if j != i], ignore_index=True))
            d = pool(w)
            Xs.append(self.inputs(d, rl, ents[i]))
            Ys.append(d["is_fraud"].to_numpy())
        X, y = np.vstack(Xs), np.concatenate(Ys)
        self.rule_model = RuleLogit().fit(pd.concat([pool(o) for o in worlds], ignore_index=True))
        w0 = np.concatenate([[1.0], np.full(X.shape[1] - 1, self.prior_entity)])
        self.theta = fit_prior_logistic(X, y, w0, self.lam)
        return self

    def score(self, df, entity):
        return self.inputs(df, self.rule_model, entity) @ self.theta[1:] + self.theta[0]

    def weights(self):
        names = ["rules_learned"] + [c for c, _ in EntityDeviation.SPECS]
        return dict(zip(names, np.round(self.theta[1:], 3))) | {"bias": round(float(self.theta[0]), 3)}
