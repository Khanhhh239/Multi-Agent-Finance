"""Conservative business-metadata ranking signals."""
from __future__ import annotations

from typing import Any

from ..catalog.adapter import MetricCatalogAdapter
from ..retrieval.embedding import normalize_text
from ..schemas import MetricCandidate


def _contains(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


class MetadataRanker:
    def __init__(self, catalog: MetricCatalogAdapter) -> None:
        self.catalog = catalog

    def components(
        self,
        question: str,
        candidate: MetricCandidate,
        context: dict[str, Any] | None = None,
    ) -> dict[str, float]:
        query = normalize_text(question)
        metric = self.catalog.get(candidate.metric_id)
        scores: dict[str, float] = {}

        ratio_signal = _contains(query, ("phần trăm", "%", "tỷ suất", "biên ", "hệ số"))
        if ratio_signal:
            scores["unit_ratio"] = 0.30 if metric.unit in {"%", "ratio"} else -0.08

        days_signal = _contains(query, ("bao nhiêu ngày", "số ngày", "bao lâu", "runway"))
        if days_signal:
            scores["unit_days"] = 0.28 if metric.unit == "days" else -0.04

        snapshot_signal = _contains(
            query,
            ("hiện tại", "còn bao nhiêu", "số dư", "cuối kỳ", "trong tài khoản", "đang nợ"),
        )
        explicit_flow = _contains(query, ("dòng tiền", "biến động tiền", "thu chi trong", "trong kỳ"))
        if snapshot_signal:
            scores["period_snapshot"] = 0.25 if metric.period_type == "snapshot" else -0.08
        elif explicit_flow:
            scores["period_flow"] = 0.12 if metric.period_type == "flow" else -0.04

        group_signals = {
            "customer": ("khách hàng nào", "theo khách hàng", "khách nợ lớn", "top khách"),
            "salesperson": ("theo nhân viên", "nhân viên phụ trách", "theo sales"),
            "vendor": ("nhà cung cấp nào", "theo nhà cung cấp", "top nhà cung cấp"),
            "cost_category": ("khoản mục", "cơ cấu chi phí", "chi phí gồm"),
        }
        for group_by, phrases in group_signals.items():
            if _contains(query, phrases):
                scores[f"group_by_{group_by}"] = 0.28 if group_by in metric.group_bys else -0.04

        tax_signal = _contains(query, ("thuế", "chịu thuế", "tính thuế", "được trừ"))
        if tax_signal:
            scores["tax_view"] = 0.18 if "tax" in metric.views and metric.default_view == "tax" else 0.0

        requested_view = (context or {}).get("view")
        if requested_view in {"mgmt", "tax"}:
            scores["explicit_view"] = 0.20 if requested_view in metric.views else -0.20

        return scores

    def score(
        self,
        question: str,
        candidate: MetricCandidate,
        context: dict[str, Any] | None = None,
    ) -> float:
        return sum(self.components(question, candidate, context).values())
