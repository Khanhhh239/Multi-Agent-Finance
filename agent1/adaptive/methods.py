"""Executable method bag. No synthetic loader, no company IDs as memorization features."""

import hashlib
import time
import os
from importlib.metadata import version
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.preprocessing import SplineTransformer
from sklearn.compose import ColumnTransformer
from sklearn.neural_network import MLPClassifier
from threadpoolctl import threadpool_limits
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import (
    RandomForestClassifier,
    ExtraTreesClassifier,
    HistGradientBoostingClassifier,
)
from .data import observed, fingerprint
from .cash_history import partial_distribution

CATALOG = [
    ("due", "rule", "Ngày đến hạn", "Không cần học; điều khoản hóa đơn"),
    (
        "customer",
        "hybrid",
        "Lịch sử khách hàng",
        "Trung vị trễ khách, co về doanh nghiệp",
    ),
    (
        "survival",
        "statistical",
        "Sống sót thực nghiệm",
        "Ước lượng hazard, giữ hóa đơn chưa trả ở risk set",
    ),
    ("logistic", "supervised", "Logistic hazard", "Chuẩn hoá + regularization"),
    ("forest", "supervised", "Random forest hazard", "Bagging cây quyết định"),
    ("extra", "supervised", "Extra trees hazard", "Randomized tree ensemble"),
    ("hist", "supervised", "Histogram boosting hazard", "Boosting phi tuyến"),
    ("lightgbm", "supervised", "LightGBM hazard", "Leaf-wise gradient boosting"),
    ("xgboost", "supervised", "XGBoost hazard", "Regularized gradient boosting"),
    (
        "blend",
        "ensemble",
        "Ensemble có neo",
        "Trộn mô hình học với mốc; trọng số chọn trên validation",
    ),
]
CATALOG.extend(
    [
        ("logistic_regularized", "supervised", "Logistic regularized", "C=0.1"),
        ("forest_shallow", "supervised", "Random forest shallow", "Depth=5"),
        (
            "hist_regularized",
            "supervised",
            "Histogram regularized",
            "Regularization=10",
        ),
        ("neural_wide", "deep", "Neural wide", "MLP 64–32, validation riêng"),
        ("neural_deep", "deep", "Neural deep", "MLP 64–32–16, regularization mạnh"),
    ]
)
WEEKS = 52
CATALOG.extend(
    [
        (
            "spline",
            "statistical",
            "Hazard spline",
            "Đường cong tuổi nợ với lịch sử khách co về DN",
        ),
        (
            "neural",
            "deep",
            "Neural logistic hazard",
            "MLP hai tầng, likelihood tuần quan sát đủ",
        ),
    ]
)


def features(frame, history):
    import heapq

    def add(heaps, value):
        left, right = heaps
        heapq.heappush(left, -value)
        heapq.heappush(right, -heapq.heappop(left))
        if len(right) > len(left):
            heapq.heappush(left, -heapq.heappop(right))

    def median(heaps):
        left, right = heaps
        if not left:
            return 0.0
        return (-left[0] + right[0]) / 2 if len(left) == len(right) else -left[0]

    settled = history.dropna(subset=["settled", "settled_known_at"]).copy()
    settled["available"] = pd.concat(
        [
            settled.known_at,
            settled.settled_known_at + pd.Timedelta(days=1),
            settled.settled + pd.Timedelta(days=1),
        ],
        axis=1,
    ).max(axis=1)
    events = list(settled.sort_values("available").itertuples())
    cursor = 0
    firm = ([], [])
    customers = {}
    result = np.zeros((len(frame), 5))
    invoices = list(frame.itertuples())
    for position in np.argsort(frame.issue_date.to_numpy(), kind="stable"):
        r = invoices[position]
        while cursor < len(events) and events[cursor].available <= r.issue_date:
            e = events[cursor]
            delay = min(180, max(-60, (e.settled - e.due_date).days))
            add(firm, delay)
            add(customers.setdefault(e.customer_id, ([], [])), delay)
            cursor += 1
        group = customers.get(r.customer_id, ([], []))
        n = len(group[0]) + len(group[1])
        centre = median(firm)
        result[position] = [
            np.log1p(r.amount),
            (r.due_date - r.issue_date).days,
            (n * median(group) + 5 * centre) / (n + 5),
            centre,
            np.log1p(n),
        ]
    return result


def design(x, k):
    k = np.asarray(k)
    return np.column_stack([x, k, x[:, 1] - 7 * k])


class DistributionEnsemble:
    """Convex probability pooling; members selected exclusively on validation."""

    def __init__(self, members):
        self.members = members

    def distribution(self, frame, ages=None, horizon=13):
        return np.mean(
            [m.distribution(frame, ages, horizon) for m in self.members], axis=0
        )


class Method:
    def __init__(self, name, seed=7):
        self.variant = name
        self.name = {
            "logistic_regularized": "logistic",
            "forest_shallow": "forest",
            "hist_regularized": "hist",
        }.get(name, name)
        self.seed = seed

    def fit(self, frame, clock):
        self.history = frame.copy()
        learned = self.name not in ("due", "customer", "survival")
        self.x = features(frame, frame) if learned else None
        duration = (frame.settled - frame.issue_date).dt.days.to_numpy(float)
        available = (pd.Timestamp(clock) - frame.issue_date).dt.days.to_numpy()
        if "written_off_at" in frame:
            stop = (frame.written_off_at - frame.issue_date).dt.days.to_numpy(float)
            available = np.minimum(available, np.where(np.isfinite(stop), stop, np.inf))
        masks = []
        risk = []
        events = []
        for k in range(1, WEEKS + 1):
            m = (available >= 7 * k) & (np.isnan(duration) | (duration > 7 * (k - 1)))
            if k == 1:
                m = (available >= 7) & (np.isnan(duration) | (duration >= 0))
            event = (duration <= 7 * k) & (
                (duration > 7 * (k - 1)) | ((k == 1) & (duration == 0))
            )
            risk.append(int(m.sum()))
            events.append(int(event[m].sum()))
            if learned:
                masks.append((np.flatnonzero(m), event[m]))
        self.hazard = (np.asarray(events) + 0.5) / (np.asarray(risk) + 5)
        if not learned:
            return self
        total = sum(risk)
        if total == 0:
            raise ValueError("Không có tuần quan sát đủ")
        sample = np.sort(
            np.random.default_rng(7).choice(total, min(total, 100000), replace=False)
        )
        x = np.empty((len(sample), 7))
        y = np.empty(len(sample), int)
        offset = 0
        for k, (indices, labels) in enumerate(masks, 1):
            lo, hi = np.searchsorted(sample, [offset, offset + len(indices)])
            local = sample[lo:hi] - offset
            x[lo:hi] = design(self.x[indices[local]], np.full(hi - lo, k))
            y[lo:hi] = labels[local]
            offset += len(indices)
        if len(np.unique(y)) < 2:
            raise ValueError("Chưa đủ cả hai lớp để học")
        if self.name == "spline":
            transform = ColumnTransformer(
                [("week", SplineTransformer(n_knots=4, degree=2), [5])],
                remainder="passthrough",
            )
            self.estimator = make_pipeline(
                transform, StandardScaler(), LogisticRegression(max_iter=300)
            )
        elif self.name.startswith("neural"):
            self.estimator = make_pipeline(
                StandardScaler(),
                MLPClassifier(
                    hidden_layer_sizes={
                        "neural": (32, 16),
                        "neural_wide": (64, 32),
                        "neural_deep": (64, 32, 16),
                    }[self.name],
                    alpha=0.1 if self.name == "neural_deep" else 0.01,
                    batch_size=int(os.environ.get("AGENT1_NEURAL_BATCH_SIZE", "128")),
                    max_iter=int(os.environ.get("AGENT1_NEURAL_MAX_ITER", "100")),
                    random_state=self.seed,
                ),
            )
        elif self.name == "logistic":
            self.estimator = make_pipeline(
                StandardScaler(),
                LogisticRegression(
                    C=0.1 if self.variant == "logistic_regularized" else 1, max_iter=300
                ),
            )
        elif self.name == "forest":
            self.estimator = RandomForestClassifier(
                n_estimators=100,
                max_depth=5 if self.variant == "forest_shallow" else 10,
                min_samples_leaf=15,
                n_jobs=2,
                random_state=7,
            )
        elif self.name == "extra":
            self.estimator = ExtraTreesClassifier(
                n_estimators=100,
                max_depth=12,
                min_samples_leaf=12,
                n_jobs=2,
                random_state=7,
            )
        elif self.name == "hist":
            self.estimator = HistGradientBoostingClassifier(
                l2_regularization=10 if self.variant == "hist_regularized" else 5,
                max_iter=100,
                max_leaf_nodes=15,
                random_state=7,
            )
        elif self.name == "lightgbm":
            from lightgbm import LGBMClassifier

            self.estimator = LGBMClassifier(
                n_estimators=100,
                num_leaves=15,
                min_child_samples=30,
                verbosity=-1,
                n_jobs=2,
                random_state=7,
            )
        elif self.name == "xgboost":
            from xgboost import XGBClassifier

            self.estimator = XGBClassifier(
                n_estimators=100,
                max_depth=3,
                learning_rate=0.05,
                n_jobs=2,
                random_state=7,
            )
        else:
            raise ValueError("Unknown method")
        # Small neural minibatches suffer from nested BLAS thread overhead.
        # Limit BLAS only; tree/OpenMP budgets remain managed by the worker.
        with threadpool_limits(limits=1, user_api="blas"):
            self.estimator.fit(x, y)
        return self

    def distribution(self, frame, ages=None, horizon=13):
        x = features(frame, self.history)
        ages = (
            np.zeros(len(frame), int)
            if ages is None
            else np.maximum(np.asarray(ages, int), 0)
        )
        if self.name in ["due", "customer"]:
            days = x[:, 1] + (x[:, 2] if self.name == "customer" else 0)
            week = np.clip(np.ceil((days - ages) / 7).astype(int), 1, horizon + 1)
            p = np.zeros((len(frame), horizon + 1))
            p[np.arange(len(frame)), week - 1] = 1
            overdue = (ages > x[:, 1]) & (days <= ages)
            if overdue.any():
                # Only observed events support inflows after the contractual date.
                p[overdue] = 0
                survival = np.ones(int(overdue.sum()))
                duration = np.sort(
                    (self.history.settled - self.history.issue_date)
                    .dt.days.dropna()
                    .to_numpy()
                )
                for offset in range(horizon):
                    start = ages[overdue] + 7 * offset
                    k = np.minimum(start // 7, WEEKS - 1)
                    observed_event = (
                        np.searchsorted(duration, start + 7, side="right")
                        - np.searchsorted(duration, start, side="right")
                    ) > 0
                    h = np.where(observed_event, self.hazard[k], 0)
                    p[overdue, offset] = survival * h
                    survival *= 1 - h
                p[overdue, -1] = survival
            return p
        survival = np.ones(len(frame))
        parts = []
        for offset in range(1, horizon + 1):
            k = np.minimum(np.floor(ages / 7).astype(int) + offset, WEEKS)
            h = (
                self.hazard[k - 1]
                if self.name == "survival"
                else self.estimator.predict_proba(design(x, k))[:, 1]
            )
            h = np.clip(h, 0.0001, 0.9999)
            parts.append(survival * h)
            survival *= 1 - h
        return np.column_stack([*parts, survival])


def score(p, frame):
    days = (frame.settled - frame.issue_date).dt.days.fillna(10000).to_numpy()
    truth = days <= 28
    prob = p[:, :4].sum(1)
    # Invoice cohorts mature at 28 days, including rows still unpaid; no paid-only evaluation.
    return float(np.mean((prob - truth) ** 2))


def audit_metrics(candidate, base, frame):
    """Paired customer-cluster bootstrap; intervals concern this audit cohort only."""
    truth = (
        (frame.settled - frame.issue_date).dt.days.fillna(10000).to_numpy() <= 28
    ).astype(float)
    prob = candidate[:, :4].sum(1)
    reference = base[:, :4].sum(1)
    losses = (prob - truth) ** 2
    baseline = (reference - truth) ** 2
    groups = frame.customer_id.to_numpy()
    unique = np.unique(groups)
    rng = np.random.default_rng(7)
    sums = np.array([(baseline - losses)[groups == g].sum() for g in unique])
    counts = np.array([(groups == g).sum() for g in unique])
    samples = rng.integers(0, len(unique), size=(1000, len(unique)))
    improvement = sums[samples].sum(1) / counts[samples].sum(1)
    lo, hi = np.quantile(improvement, [0.025, 0.975])
    clipped = np.clip(prob, 1e-7, 1 - 1e-7)
    return dict(
        n=len(frame),
        customer_clusters=len(unique),
        candidate_brier4=float(losses.mean()),
        baseline_brier4=float(baseline.mean()),
        brier_improvement=float((baseline - losses).mean()),
        improvement_ci_low=float(lo),
        improvement_ci_high=float(hi),
        ci_reliable=len(unique) >= 10,
        amount_weighted_brier4=float(np.average(losses, weights=frame.amount)),
        log_loss4=float(
            -(truth * np.log(clipped) + (1 - truth) * np.log1p(-clipped)).mean()
        ),
        observed_paid_rate4=float(truth.mean()),
        predicted_paid_rate4=float(prob.mean()),
    )


def train(data, asof, progress=lambda x: None, names=None):
    asof = pd.Timestamp(asof)
    cut = asof - pd.Timedelta(days=112)
    cal_end = asof - pd.Timedelta(days=56)
    train_frame = observed(data, cut)
    train_frame = train_frame[train_frame.known_at <= train_frame.issue_date]
    cal_history = observed(data, cal_end)
    cal = cal_history[
        (cal_history.issue_date > cut)
        & (cal_history.issue_date <= asof - pd.Timedelta(days=84))
        & (cal_history.known_at <= cal_history.issue_date)
    ]
    audit_history = observed(data, asof)
    audit = audit_history[
        (audit_history.issue_date > cal_end)
        & (audit_history.issue_date <= asof - pd.Timedelta(days=28))
        & (audit_history.known_at <= audit_history.issue_date)
    ]
    if (
        len(train_frame) < 60
        or len(cal) < 20
        or len(audit) < 20
        or train_frame.settled.notna().sum() < 20
    ):
        raise ValueError(
            "Chưa đủ lịch sử: cần ≥60 hóa đơn trước 112 ngày, ≥20 đã trả, ≥20 hóa đơn ở mỗi cửa sổ kiểm định 28 ngày. Dùng dự báo theo điều khoản trước."
        )
    names = names or [r[0] for r in CATALOG if r[0] != "blend"]
    rows = []
    predictions = {}
    for name in names:
        progress(
            "Đang kiểm định phương án " + str(len(rows) + 1) + "/" + str(len(names))
        )
        started = time.monotonic()
        try:
            if name.startswith("neural") and (
                len(train_frame) < 1000
                or train_frame.settled.count() < 200
                or train_frame.customer_id.nunique() < 20
            ):
                raise ValueError("Cần 1.000 hóa đơn học, 200 tất toán và 20 khách")
            model = Method(name).fit(train_frame, cut)
            p = model.distribution(cal)
            predictions[name] = p
            rows.append(
                dict(
                    method=name,
                    validation_brier4=score(p, cal),
                    status="evaluated",
                    seconds=round(time.monotonic() - started, 3),
                )
            )
        except (ValueError, ImportError) as exc:
            rows.append(
                dict(method=name, status="unavailable", reason=type(exc).__name__)
            )
    # Equal pooling of the three best validation candidates is itself an audited candidate.
    ranked = sorted(predictions, key=lambda n: score(predictions[n], cal))[:3]
    if len(ranked) > 1:
        predictions["pool"] = np.mean([predictions[n] for n in ranked], axis=0)
        rows.append(
            dict(
                method="pool",
                members=ranked,
                validation_brier4=score(predictions["pool"], cal),
                status="evaluated",
            )
        )

    def fit_selected(selected, history, clock):
        if selected == "pool":
            return DistributionEnsemble([Method(n).fit(history, clock) for n in ranked])
        return Method(selected).fit(history, clock)

    anchor = predictions["customer"]
    choices = []
    for name, p in predictions.items():
        for w in [0, 0.25, 0.5, 0.75, 1.0]:
            choices.append((score(w * p + (1 - w) * anchor, cal), name, w))
    best, name, w = min(choices, key=lambda r: r[0])
    progress("Đang kiểm tra độc lập theo thời gian")
    refit = cal_history[cal_history.known_at <= cal_history.issue_date]
    a = Method("customer").fit(refit, cal_end)
    m = fit_selected(name, refit, cal_end)
    base = a.distribution(audit)
    candidate = w * m.distribution(audit) + (1 - w) * base
    base_score = score(base, audit)
    candidate_score = score(candidate, audit)
    accepted = candidate_score <= base_score
    metrics = audit_metrics(candidate, base, audit)
    metrics["accepted"] = bool(accepted)
    # Test is an acceptance gate, never a search set. Failed candidate remains in the report.
    progress("Đang học lại trên dữ liệu doanh nghiệp đã quan sát")
    final_frame = audit_history[audit_history.known_at <= audit_history.issue_date]
    final_anchor = Method("customer").fit(final_frame, asof)
    final_model = fit_selected(name, final_frame, asof) if accepted else final_anchor
    from .risk import train_risk

    progress("Đang kiểm định rủi ro xóa nợ")
    risk = train_risk(data, asof)
    from .collections import train_policy

    progress("Đang kiểm định danh sách thu hồi")
    collection = train_policy(data, asof)
    return dict(
        risk=risk,
        collection_policy=collection["policy"],
        collection_evaluation=collection,
        model=final_model,
        anchor=final_anchor,
        weight=w if accepted else 0.0,
        asof=str(asof.date()),
        dataset_hash=fingerprint(data),
        selection=rows,
        selected_method=name,
        selected_weight=w,
        audit=metrics,
        windows=dict(
            train_through=str(cut.date()),
            validation_label_through=str(cal_end.date()),
            audit_label_through=str(asof.date()),
        ),
        validation_n=len(cal),
        train_n=len(train_frame),
        algorithm_version="company-bag-v3",
        code_hash=hashlib.sha256(
            Path(__file__).read_bytes()
            + Path(__file__).with_name("data.py").read_bytes()
            + Path(__file__).with_name("operating.py").read_bytes()
            + Path(__file__).with_name("cash_history.py").read_bytes()
            + Path(__file__).with_name("new_credit.py").read_bytes()
            + Path(__file__).with_name("risk.py").read_bytes()
            + Path(__file__).with_name("collections.py").read_bytes()
        ).hexdigest(),
        dependencies={
            name: version(name)
            for name in ["numpy", "pandas", "scikit-learn", "lightgbm", "xgboost"]
        },
        limitation="Kiểm định xác suất trả trong 4 tuần; dải tiền 13 tuần là mô phỏng, chưa hiệu chỉnh bằng thực tế.",
    )


def forecast(
    data,
    cutoff,
    balance,
    bundle=None,
    delay_days=0,
    expense_multiplier=1.0,
    confirmed_weeks=(),
    cash_floor=0.0,
    shared_customer_risk=False,
    delay_customer=None,
    include_operating=False,
    horizon_weeks=13,
):
    if type(horizon_weeks) is not int or not 1 <= horizon_weeks <= 52:
        raise ValueError("Kỳ dự báo phải từ 1 đến 52 tuần.")
    horizon = horizon_weeks
    # Keep four-week collections scores and short-term receipt cohorts comparable.
    receipt_horizon = max(13, horizon)
    clock = pd.Timestamp(cutoff)
    frame = observed(data, clock)
    opened = frame[frame.remaining_amount > 0.01].copy()
    actions = sorted(
        (
            r
            for r in data.get("actions", [])
            if r["date"] <= cutoff and r["known_at"] <= cutoff
        ),
        key=lambda r: (r["date"], r["known_at"], r["event_id"]),
    )
    lost = {r["invoice_id"] for r in actions if r["kind"] == "write_off"}
    opened = opened[~opened.invoice_id.isin(lost)]
    if delay_days and delay_customer and delay_customer not in set(opened.customer_id):
        raise ValueError("Khách đã chọn không có hóa đơn đang mở tại ngày dự báo.")
    disputes = {}
    promises = {}
    deferred = {}
    resolved_promises = []
    ledger = frame.set_index("invoice_id")
    for event in actions:
        iid = event["invoice_id"]
        if event["kind"] in ("resolved", "dispute"):
            disputes[iid] = event["kind"] == "dispute"
        if event["kind"] in ("skip", "contact"):
            deferred[iid] = (clock - pd.Timestamp(event["date"])).days < 7
        if event["kind"] == "promise":
            promises[iid] = event["promise_date"]
            deadline = pd.Timestamp(event["promise_date"]) + pd.Timedelta(days=3)
            if deadline <= clock and iid in ledger.index:
                inv = ledger.loc[iid]
                if pd.isna(inv.settled) or inv.settled >= pd.Timestamp(event["date"]):
                    resolved_promises.append(
                        dict(
                            customer_id=inv.customer_id,
                            made_date=pd.Timestamp(event["date"]),
                            promised_date=pd.Timestamp(event["promise_date"]),
                            kept=bool(inv.settled <= deadline),
                        )
                    )
    reliability = {}
    if resolved_promises:
        from agent1.models.t8_promise import PromiseReliability

        reliability = (
            PromiseReliability()
            .fit(pd.DataFrame(resolved_promises), clock)
            .stats.reliability.to_dict()
        )
    # Descriptive drift signal; thresholds do not change the active model.
    paid = frame.dropna(subset=["settled"]).copy()
    recent = paid[paid.settled > clock - pd.Timedelta(days=28)]
    prior = paid[
        paid.settled.between(
            clock - pd.Timedelta(days=112), clock - pd.Timedelta(days=28)
        )
    ]
    shift_days = None
    if min(len(recent), len(prior)) >= 20:
        shift_days = float(
            (recent.settled - recent.due_date).dt.days.median()
            - (prior.settled - prior.due_date).dt.days.median()
        )
    if bundle and pd.Timestamp(bundle["asof"]) > clock:
        raise ValueError("Phiên bản học sau ngày dự báo")
    if opened.empty:
        p = np.zeros((0, receipt_horizon + 1))
    else:
        ages = (clock - opened.issue_date).dt.days.to_numpy()
        if bundle:
            options = {"horizon": receipt_horizon} if receipt_horizon != 13 else {}
            p = bundle["weight"] * bundle["model"].distribution(
                opened, ages, **options
            ) + (1 - bundle["weight"]) * bundle["anchor"].distribution(
                opened, ages, **options
            )
        else:
            p = (
                Method("customer")
                .fit(frame, clock)
                .distribution(opened, ages, horizon=receipt_horizon)
            )
    if delay_days:
        shift = int(np.ceil(delay_days / 7))
        delayed = np.zeros_like(p)
        for k in range(receipt_horizon + 1):
            delayed[:, min(receipt_horizon, k + shift)] += p[:, k]
        affected = (
            np.ones(len(opened), dtype=bool)
            if not delay_customer
            else (opened.customer_id == delay_customer).to_numpy()
        )
        p[affected] = delayed[affected]
    payment_times = p.copy()
    cash_p, partial_n = partial_distribution(data, opened, clock, p)
    if delay_days and partial_n:
        for i in np.flatnonzero(affected):
            if not np.array_equal(cash_p[i], p[i]):
                delayed = np.zeros(receipt_horizon + 1)
                buckets = np.minimum(
                    np.arange(receipt_horizon + 1) + shift, receipt_horizon
                )
                np.add.at(delayed, buckets, cash_p[i])
                cash_p[i] = delayed
    cash_p = np.column_stack((cash_p[:, :horizon], cash_p[:, horizon:].sum(1)))
    amounts = opened.remaining_amount.to_numpy()
    incoming = (cash_p[:, :horizon] * amounts[:, None]).sum(0)
    outgoing = np.zeros(horizon)
    known_variable = np.zeros(horizon)
    scheduled = np.zeros(horizon, bool)
    for r in data.get("outflows", []):
        if pd.Timestamp(r["known_at"]) > clock:
            continue
        days = (pd.Timestamp(r["date"]) - clock).days
        if 1 <= days <= 7 * horizon:
            outgoing[(days - 1) // 7] += r["amount"] * expense_multiplier
            scheduled[(days - 1) // 7] = True
            if r["category"] == "variable_cost":
                known_variable[(days - 1) // 7] += r["amount"] * expense_multiplier
    coverage = [
        "scheduled"
        if scheduled[i]
        else "confirmed_zero"
        if i + 1 in confirmed_weeks
        else "unknown"
        for i in range(horizon)
    ]
    operating = bundle.get("operating") if bundle and include_operating else None
    operating_weeks = min(horizon, 13) if operating else 0
    estimate = None
    new_credit = None
    if include_operating and not operating:
        raise ValueError(
            "Chưa có phiên bản được kiểm định trên lịch sử sao kê cho bán thu ngay và chi biến đổi."
        )
    if operating:
        from .operating import available_history, predict_candidate

        series, gap = available_history(data, cutoff, operating["accounts"])
        if len(series) < 52:
            raise ValueError("Thiếu tuần sao kê đã đối chiếu đến ngày dự báo.")
        estimate = predict_candidate(
            operating["name"], operating["model"], series, gap
        )[:operating_weeks]
        if operating.get("credit"):
            from .new_credit import build, point

            m = build(data, cutoff, operating["accounts"])
            if m is not None:
                new_credit = point(m, operating["credit"]["kind"])[:operating_weeks]
                incoming[:operating_weeks] += new_credit
        incoming[:operating_weeks] += estimate[:, 0]
        outgoing[:operating_weeks] += np.maximum(
            0, estimate[:, 1] * expense_multiplier - known_variable[:operating_weeks]
        )
    expected = balance + np.cumsum(incoming - outgoing)
    rng = np.random.default_rng(7)
    paths = np.full((400, horizon), float(balance)) - np.cumsum(outgoing)
    if operating:
        errors = operating["residuals"][:, :operating_weeks]
        draws = np.maximum(0, estimate + errors[rng.integers(0, len(errors), 400)])
        costs = known_variable[:operating_weeks]
        added = np.maximum(0, draws[:, :, 1] * expense_multiplier - costs)
        point_added = np.maximum(0, estimate[:, 1] * expense_multiplier - costs)
        operating_movements = draws[:, :, 0] - added + point_added
        if new_credit is not None:
            residuals = operating["credit"]["residuals"][:, :operating_weeks]
            operating_movements += np.maximum(
                0, new_credit + residuals[rng.integers(len(residuals), size=400)]
            )
        movement = np.zeros_like(paths)
        movement[:, :operating_weeks] = operating_movements
        paths += np.cumsum(movement, axis=1)
    # Independent payment-time draws; conservative labels make the assumption explicit.
    customer_draws = {}
    cash_events = np.zeros((400, horizon + 1))
    trajectory = np.arange(400)
    for customer, prob, amount in zip(opened.customer_id, cash_p, amounts):
        if shared_customer_risk:
            if customer not in customer_draws:
                customer_draws[customer] = rng.random(400)
            week = np.searchsorted(
                np.cumsum(prob / prob.sum()), customer_draws[customer]
            )
        else:
            week = rng.choice(horizon + 1, size=400, p=prob / prob.sum())
        cash_events[trajectory, np.minimum(week, horizon)] += amount
    paths += np.cumsum(cash_events[:, :horizon], axis=1)
    low, high = np.quantile(paths, [0.1, 0.9], axis=0)
    from .risk import predict_risk

    risk_values = predict_risk(bundle.get("risk") if bundle else None, opened)
    triage_p = (
        Method("customer")
        .fit(frame, clock)
        .distribution(opened, (clock - opened.issue_date).dt.days.to_numpy())[:, :4]
        .sum(1)
        if len(opened)
        else np.array([])
    )
    priorities = [
        dict(
            invoice_id=str(r.invoice_id),
            customer_id=str(r.customer_id),
            outstanding=float(r.remaining_amount),
            write_off_probability_365d_at_issue=risk_values[i],
            amount_at_risk_4w=float(r.remaining_amount * (1 - triage_p[i])),
            overdue_days=max(0, (clock - r.due_date).days),
            due_date=str(r.due_date.date()),
            disputed=disputes.get(r.invoice_id, False),
            promised_date=promises.get(r.invoice_id),
            promise_reliability=reliability.get(r.customer_id),
            reason=(
                "Chờ giải quyết tranh chấp"
                if disputes.get(r.invoice_id)
                else "Kiểm tra lời hứa đã đến hạn"
                if promises.get(r.invoice_id, "9999") <= cutoff
                else "Ưu tiên theo giá trị công nợ và kiểm định lịch sử"
            ),
            payment_probability_4w=float(payment_times[i, :4].sum()),
            triage_probability_4w=float(triage_p[i]),
        )
        for i, r in enumerate(opened.itertuples())
        if not deferred.get(r.invoice_id)
    ]
    policy = bundle.get("collection_policy", "amount") if bundle else "amount"

    def priority_value(r):
        return (
            r["amount_at_risk_4w"]
            if policy == "amount_at_risk"
            else 1 - r["triage_probability_4w"]
            if policy == "risk"
            else r["outstanding"]
        )

    priorities = sorted(priorities, key=lambda r: -priority_value(r))[:30]
    return dict(
        cutoff=str(clock.date()),
        horizon_weeks=horizon,
        operating_weeks=operating_weeks,
        mode="company_trained" if bundle else "history_baseline",
        open_invoices=len(opened),
        partial_cash_supported=partial_n,
        written_off_count=len(lost),
        payment_delay_shift_days=shift_days,
        operating_included=estimate is not None,
        new_credit_included=new_credit is not None,
        outstanding=float(amounts.sum()),
        minimum_balance=float(expected.min()),
        opening_balance=float(balance),
        cash_floor=float(cash_floor),
        unknown_outflow_weeks=[i + 1 for i, v in enumerate(coverage) if v == "unknown"],
        timing_dependence="shared_customer_stress"
        if shared_customer_risk
        else "independent",
        weeks=[
            dict(
                week=i + 1,
                date=str((clock + pd.Timedelta(days=7 * (i + 1))).date()),
                cash_in=float(incoming[i]),
                new_credit_in=float(new_credit[i])
                if new_credit is not None and i < operating_weeks
                else 0.0,
                cash_out=float(outgoing[i]),
                balance=float(expected[i]),
                low=float(low[i]),
                high=float(high[i]),
                outflow_status=coverage[i],
                below_floor_probability=float((paths[:, i] < cash_floor).mean()),
            )
            for i in range(horizon)
        ],
        collections=priorities,
        alerts=[
            dict(
                week=i + 1,
                message="Có nguy cơ xuống dưới mức tiền tối thiểu. Kiểm tra thu, chi và phạm vi lịch.",
            )
            for i in range(horizon)
            if expected[i] < cash_floor or (paths[:, i] < cash_floor).mean() >= 0.25
        ],
        assumptions=[
            f"Ước lượng hoạt động áp dụng cho {operating_weeks} tuần đầu; các tuần sau chỉ tính công nợ và lịch chi đã biết."
            if operating_weeks and horizon > operating_weeks
            else "Có ước lượng bán thu ngay và chi biến đổi từ sao kê."
            if operating
            else "Chỉ gồm công nợ đang mở và lịch chi đã khai báo; chưa gồm doanh số mới.",
            "Đã gồm ước lượng thu hóa đơn bán chịu phát hành trong kỳ dự báo."
            if new_credit is not None
            else "Chưa gồm thu từ hóa đơn bán chịu chưa phát hành.",
            f"{partial_n} hóa đơn có phân bổ theo lịch trả từng phần quan sát được. Các khoản khác dự báo phần còn lại lúc tất toán.",
            (
                "Kịch bản căng thẳng: hóa đơn cùng khách chịu chung một cú sốc."
                if shared_customer_risk
                else "Mô phỏng thời điểm trả độc lập."
            )
            + " Xác suất và dải tiền chưa hiệu chỉnh.",
            "Danh sách thu hồi xếp theo phương án đã kiểm định hoặc theo dư nợ khi dùng mốc.",
        ],
        pilot_ready=False,
    )
