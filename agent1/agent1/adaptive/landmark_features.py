"""The user's eighteen observed T1 features in six business SHAP groups."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .compact_ensemble import (
    CompactEnsemble,
    CompactHazard,
    CompactRule,
    load_compact_model,
)
from .compact_t1 import feature_context

SCHEMA = "t1-landmark-18-v2"
FEATURES = (
    "relative_amount",
    "term_days",
    "age_days",
    "received_fraction",
    "receipt_recency_days",
    "receipt_count",
    "received_fraction_28d",
    "customer_settlements_180d",
    "customer_delay_180d",
    "customer_delay_std_180d",
    "customer_delay_trend_180d",
    "company_delay_180d",
    "company_delay_trend_180d",
    "customer_overdue_share",
    "customer_overdue90_share",
    "company_overdue_share",
    "company_overdue90_share",
    "customer_outstanding_share",
)
GROUPS = (
    ("invoice_terms", "Giá trị và điều khoản", (0, 1)),
    ("invoice_age", "Tuổi hóa đơn", (2,)),
    ("receipt_state", "Trạng thái thu tiền", (3, 4, 5, 6)),
    ("customer_history", "Lịch sử khách", (7, 8, 9, 10)),
    ("company_history", "Lịch sử doanh nghiệp", (11, 12)),
    ("overdue_context", "Công nợ hiện tại", (13, 14, 15, 16, 17)),
)


def delay_statistics(paid, cutoff):
    """Delay dispersion and OLS trend in delay-days per 30 calendar days."""
    events = paid.copy()
    events["delay"] = (
        (events.settled - events.due_date).dt.days.clip(-60, 180).astype(float)
    )
    events["time"] = (events.settled - pd.Timestamp(cutoff)).dt.total_seconds() / (
        86400 * 30
    )
    events["time2"] = events.time**2
    events["time_delay"] = events.time * events.delay
    stats = events.groupby("customer_id").agg(
        count=("delay", "size"),
        median=("delay", "median"),
        std=("delay", "std"),
        time=("time", "mean"),
        time2=("time2", "mean"),
        delay=("delay", "mean"),
        time_delay=("time_delay", "mean"),
    )
    variance = stats.time2 - stats.time**2
    stats["trend"] = np.divide(
        stats.time_delay - stats.time * stats.delay,
        variance,
        out=np.zeros(len(stats)),
        where=variance.to_numpy() > 1e-10,
    )
    company_delay = float(events.delay.median()) if len(events) else 0.0
    company_std = float(events.delay.std(ddof=0)) if len(events) else 0.0
    company_trend = (
        float(
            np.mean(
                (events.time - events.time.mean())
                * (events.delay - events.delay.mean())
            )
            / events.time.var(ddof=0)
        )
        if len(events) > 1 and events.time.var(ddof=0) > 1e-10
        else 0.0
    )
    return stats, company_delay, company_std, company_trend


def prepare_features(opened, history, cutoff):
    cutoff = pd.Timestamp(cutoff)
    if not {"receipt_count", "received_28d"}.issubset(opened.columns):
        raise ValueError(
            "The eighteen-feature schema requires observed receipt counts and 28-day cash"
        )
    paid, open_book, scale = feature_context(history, cutoff)
    stats, company_delay, company_std, company_trend = delay_statistics(paid, cutoff)
    counts = opened.customer_id.map(stats["count"]).fillna(0).to_numpy(float)
    medians = (
        opened.customer_id.map(stats["median"]).fillna(company_delay).to_numpy(float)
    )
    dispersion = (
        opened.customer_id.map(stats["std"]).fillna(company_std).to_numpy(float)
    )
    trends = (
        opened.customer_id.map(stats["trend"]).fillna(company_trend).to_numpy(float)
    )
    past_due = (cutoff - open_book.due_date).dt.days
    open_book["overdue30"] = open_book.remaining_amount.where(past_due > 30, 0.0)
    open_book["overdue90"] = open_book.remaining_amount.where(past_due > 90, 0.0)
    totals = open_book.groupby("customer_id")[
        ["remaining_amount", "overdue30", "overdue90"]
    ].sum()
    firm_total = float(open_book.remaining_amount.sum())
    firm30 = float(open_book.overdue30.sum() / firm_total) if firm_total else 0.0
    firm90 = float(open_book.overdue90.sum() / firm_total) if firm_total else 0.0
    shares30 = totals.overdue30 / totals.remaining_amount.clip(lower=1.0)
    shares90 = totals.overdue90 / totals.remaining_amount.clip(lower=1.0)
    concentration = totals.remaining_amount / max(firm_total, 1.0)
    values = np.column_stack(
        (
            np.log1p(np.clip(opened.amount.to_numpy(float) / scale, 0, 100)),
            (opened.due_date - opened.issue_date).dt.days.clip(0, 365).to_numpy(float),
            (cutoff - opened.issue_date).dt.days.clip(0, 730).to_numpy(float),
            (opened.received / opened.amount).clip(0, 1).to_numpy(float),
            (cutoff - opened.last_receipt)
            .dt.days.fillna(180)
            .clip(0, 180)
            .to_numpy(float),
            np.log1p(opened.receipt_count.to_numpy(float)),
            (opened.received_28d / opened.amount).clip(0, 1).to_numpy(float),
            np.log1p(counts),
            (counts * medians + 5 * company_delay) / (counts + 5),
            np.sqrt((counts * dispersion**2 + 5 * company_std**2) / (counts + 5)),
            (counts * trends + 5 * company_trend) / (counts + 5),
            np.full(len(opened), company_delay),
            np.full(len(opened), company_trend),
            opened.customer_id.map(shares30).fillna(firm30).to_numpy(float),
            opened.customer_id.map(shares90).fillna(firm90).to_numpy(float),
            np.full(len(opened), firm30),
            np.full(len(opened), firm90),
            opened.customer_id.map(concentration).fillna(0.0).to_numpy(float),
        )
    )
    if values.shape != (len(opened), len(FEATURES)) or not np.isfinite(values).all():
        raise ValueError("Invalid eighteen-feature landmark state")
    return values


class LandmarkHazard(CompactHazard):
    feature_schema = SCHEMA
    feature_names = FEATURES
    shap_groups = GROUPS
    prepare_state = staticmethod(prepare_features)


class LandmarkRule(CompactRule):
    feature_schema = SCHEMA
    feature_names = FEATURES
    shap_groups = GROUPS
    prepare_state = staticmethod(prepare_features)

    def __init__(self, name, hazard, metadata=None):
        super().__init__(name, hazard, metadata)
        self.active = {"due": (1, 2), "customer": (1, 2, 8), "survival": (2,)}[name]


class LandmarkEnsemble(CompactEnsemble):
    feature_schema = SCHEMA
    feature_names = FEATURES
    shap_groups = GROUPS
    prepare_state = staticmethod(prepare_features)


def load_landmark(directory, metadata):
    return load_compact_model(
        directory,
        metadata,
        {
            "classifier": LandmarkHazard,
            "rule": LandmarkRule,
            "ensemble": LandmarkEnsemble,
        },
    )
