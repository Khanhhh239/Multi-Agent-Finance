from __future__ import annotations

from dataclasses import dataclass

from agent4.engine.metrics import REGISTRY, M, MetricDef
from agent4.metric_selection.catalog import MetricCatalogAdapter

CUSTOM_IDS = frozenset(m.id for m in M if m.kind == "custom")
SYNTHETIC_CUSTOM_HANDLERS = frozenset(
    {
        "ar_aging",
        "overdue_receivables",
        "dso_actual",
        "ap_due_soon",
        "unbalanced_journals",
        "top_sales_transactions",
        "payroll_summary",
        "cit_estimate",
        "mgmt_vs_tax_gap",
        "vat_position",
    }
)
SYNTHETIC_VERIFIED_GENERIC = frozenset(
    {
        "net_revenue",
        "gross_revenue",
        "revenue_deductions",
        "cogs",
        "gross_profit",
        "gross_margin_pct",
        "operating_expenses",
        "operating_profit",
        "profit_before_tax",
        "income_tax_expense",
        "net_profit",
        "net_margin_pct",
        "cash_and_equivalents",
        "ar_balance",
        "net_cash_flow",
    }
)
SYNTHETIC_VERIFIED_GROUP_BYS = {
    "net_revenue": ("month",),
    "gross_profit": ("month",),
    "gross_margin_pct": ("month",),
    "ar_aging": ("customer",),
    "payroll_summary": ("department",),
}


@dataclass(frozen=True)
class Capability:
    metric_id: str
    source_status: str
    synthetic_status: str
    real_data_status: str
    handler: str
    reason: str | None
    verified_group_bys: tuple[str, ...]

    @property
    def executable_synthetic(self) -> bool:
        return self.synthetic_status == "SUPPORTED"


class CatalogSnapshot:
    def __init__(self) -> None:
        self.adapter = MetricCatalogAdapter()
        self.hash = self.adapter.version
        self._capabilities = {metric.id: self._capability(metric) for metric in self.adapter}
        if len(self._capabilities) != 66:
            raise ValueError("canonical catalog must contain exactly 66 metrics")

    @staticmethod
    def _capability(metric: MetricDef) -> Capability:
        if metric.kind != "custom":
            verified = metric.id in SYNTHETIC_VERIFIED_GENERIC
            return Capability(
                metric.id,
                "SOURCE_PRESENT",
                "SUPPORTED" if verified else "EXECUTABLE_UNVERIFIED",
                "BLOCKED",
                "GENERIC_COMPILER",
                (
                    "real schema/auth/domain approval unavailable"
                    if verified
                    else "generic compiler available but independent finance fixture missing"
                ),
                SYNTHETIC_VERIFIED_GROUP_BYS.get(metric.id, ()),
            )
        supported = metric.id in SYNTHETIC_CUSTOM_HANDLERS
        return Capability(
            metric.id,
            "SOURCE_PRESENT",
            "SUPPORTED" if supported else "BLOCKED",
            "BLOCKED",
            f"custom:{metric.id}",
            None if supported else "custom handler/domain fixture not approved",
            SYNTHETIC_VERIFIED_GROUP_BYS.get(metric.id, ()),
        )

    def get(self, metric_id: str) -> MetricDef:
        try:
            return REGISTRY[metric_id]
        except KeyError as exc:
            raise KeyError(f"unknown metric: {metric_id}") from exc

    def capability(self, metric_id: str) -> Capability:
        return self._capabilities[metric_id]

    def public_metrics(
        self,
        allowed: frozenset[str] | None = None,
        allowed_views: frozenset[str] | None = None,
    ) -> list[dict]:
        result = []
        for metric in self.adapter:
            if allowed is not None and metric.id not in allowed:
                continue
            if allowed_views is not None and not set(metric.views).intersection(allowed_views):
                continue
            cap = self.capability(metric.id)
            result.append(
                {
                    "id": metric.id,
                    "label": metric.label,
                    "description": metric.description,
                    "kind": metric.kind,
                    "unit": metric.unit,
                    "group_bys": list(metric.group_bys),
                    "views": list(metric.views),
                    "synthetic_status": cap.synthetic_status,
                    "real_data_status": cap.real_data_status,
                    "verified_group_bys": list(cap.verified_group_bys),
                    "reason": cap.reason,
                }
            )
        return result
