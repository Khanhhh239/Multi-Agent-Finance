from __future__ import annotations

import hashlib
import json

from .catalog import CatalogSnapshot
from .errors import Forbidden, PlanRejected
from .models import AuthContext, SemanticPlanDraft, ValidatedPlan

PHYSICAL_DIMENSIONS = frozenset(
    {
        "month",
        "quarter",
        "year",
        "branch",
        "product_line",
        "customer",
        "vendor",
        "item",
        "cost_category",
        "department",
        "account",
    }
)
FILTER_FIELDS = frozenset(
    {
        "branch",
        "product_line",
        "customer",
        "vendor",
        "item",
        "cost_category",
        "department",
        "account",
    }
)
METRIC_REQUIRED_ROLES = {"payroll_summary": frozenset({"payroll_viewer"})}


def metric_allowed(metric_id: str, auth: AuthContext) -> bool:
    if auth.allowed_metrics is not None and metric_id not in auth.allowed_metrics:
        return False
    required = METRIC_REQUIRED_ROLES.get(metric_id)
    return required is None or bool(required.intersection(auth.roles))


class SemanticValidator:
    def __init__(self, catalog: CatalogSnapshot, *, max_days: int = 3660) -> None:
        self.catalog = catalog
        self.max_days = max_days

    def validate(self, draft: SemanticPlanDraft, auth: AuthContext) -> ValidatedPlan:
        if draft.status != "ready":
            raise PlanRejected(
                draft.reason_code or draft.status,
                draft.question_for_user or "Yêu cầu chưa thể thực thi.",
                status=draft.status,
            )
        metrics = []
        capabilities = []
        for metric_id in draft.metric_ids:
            try:
                metric = self.catalog.get(metric_id)
            except KeyError as exc:
                raise PlanRejected("unsupported_metric", "Chỉ số chưa được hỗ trợ.") from exc
            if not metric_allowed(metric_id, auth):
                raise Forbidden()
            capability = self.catalog.capability(metric_id)
            metrics.append(metric)
            capabilities.append(capability)

        requested_view = draft.view
        defaults: list[str] = []
        if requested_view is None:
            candidates = {m.default_view for m in metrics}
            if len(candidates) != 1:
                raise PlanRejected(
                    "ambiguous_view",
                    "Vui lòng chọn khung quản trị hoặc thuế.",
                    status="needs_clarification",
                )
            requested_view = candidates.pop()
            defaults.append(f"view={requested_view}")
        if requested_view not in auth.allowed_views:
            raise Forbidden()
        if any(requested_view not in m.views for m in metrics):
            raise PlanRejected("unsupported_view", "Khung dữ liệu không hợp lệ cho chỉ số đã chọn.")

        dimensions = tuple(draft.dimensions)
        for dimension in dimensions:
            if dimension not in PHYSICAL_DIMENSIONS:
                raise PlanRejected(
                    "unsupported_grouping", "Chiều phân tích chưa có ánh xạ dữ liệu."
                )
            if any(dimension not in m.group_bys for m in metrics):
                raise PlanRejected(
                    "unsupported_grouping",
                    f"Không thể phân tích các chỉ số đã chọn theo {dimension}.",
                )
            if any(dimension not in capability.verified_group_bys for capability in capabilities):
                raise PlanRejected(
                    "unsupported_grouping",
                    f"Chiều {dimension} chưa có fixture đối soát cho mọi chỉ số đã chọn.",
                )
        for metric, capability in zip(metrics, capabilities, strict=True):
            if not capability.executable_synthetic:
                raise PlanRejected(
                    "unsupported_data_source",
                    f"Chỉ số {metric.label} chưa có fixture tài chính đã kiểm chứng.",
                )
        for item in draft.filters:
            if item.field not in FILTER_FIELDS:
                raise PlanRejected("unsupported_filter", "Bộ lọc chưa được hỗ trợ.")
            if item.operator == "between" and len(item.values) != 2:
                raise PlanRejected("invalid_filter", "Bộ lọc between cần đúng hai giá trị.")
            if item.operator not in {"eq", "neq", "in"}:
                raise PlanRejected("unsupported_filter", "Toán tử bộ lọc chưa được hỗ trợ.")

        periods = {m.period_type for m in metrics}
        if len(periods) != 1:
            raise PlanRejected(
                "incompatible_metrics", "Không thể trộn chỉ số kỳ và số dư trong một truy vấn."
            )
        period_type = periods.pop()
        if period_type == "snapshot" and draft.time.mode != "as_of":
            raise PlanRejected("unsupported_time", "Chỉ số số dư cần ngày chốt as-of.")
        if period_type == "flow" and draft.time.mode != "range":
            raise PlanRejected("unsupported_time", "Chỉ số dòng kỳ cần ngày bắt đầu và kết thúc.")
        if draft.time.mode == "range":
            assert draft.time.start and draft.time.end
            if (draft.time.end - draft.time.start).days > self.max_days:
                raise PlanRejected(
                    "date_range_too_large", "Khoảng thời gian vượt giới hạn an toàn."
                )
        if "month" in dimensions and period_type == "snapshot":
            raise PlanRejected(
                "unsupported_grouping",
                "Chuỗi số dư cuối tháng chưa được bật cho adapter này.",
            )
        if draft.operation == "rank":
            if not draft.sort or draft.sort.metric_id not in draft.metric_ids:
                raise PlanRejected("invalid_sort", "Chỉ số sắp xếp phải nằm trong truy vấn.")
            if not draft.top_k:
                raise PlanRejected("invalid_top_k", "Truy vấn xếp hạng cần top_k.")

        operation = draft.operation or ("timeseries" if dimensions else "aggregate")
        defaults.append(f"operation={operation}") if draft.operation is None else None
        policy_payload = {
            "tenant": auth.tenant_id,
            "roles": sorted(auth.roles),
            "views": sorted(auth.allowed_views),
        }
        policy_hash = hashlib.sha256(
            json.dumps(policy_payload, sort_keys=True).encode()
        ).hexdigest()[:16]
        return ValidatedPlan(
            metric_ids=tuple(draft.metric_ids),
            time=draft.time,
            dimensions=dimensions,
            filters=tuple(draft.filters),
            view=requested_view,
            operation=operation,
            sort=draft.sort,
            top_k=draft.top_k,
            comparison=draft.comparison,
            tenant_id=auth.tenant_id,
            catalog_hash=self.catalog.hash,
            policy_hash=policy_hash,
            applied_defaults=tuple(defaults),
        )
