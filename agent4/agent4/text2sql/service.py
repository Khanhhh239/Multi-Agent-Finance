from __future__ import annotations

import os
import time
import uuid
from datetime import date
from pathlib import Path

from .catalog import CatalogSnapshot
from .compiler import SQLCompiler
from .errors import DataUnavailable, Forbidden, PlanRejected, Text2SQLError
from .execution import DuckDBReadOnlyExecutor
from .models import (
    AuthContext,
    ErrorData,
    Interpretation,
    Provenance,
    QueryRequest,
    QueryResponse,
    ResultData,
    SemanticPlanDraft,
)
from .selector import OfflineSemanticSelector
from .validation import SemanticValidator

DEMO_WARNING = "DEMO DATA — NOT REAL FINANCIAL RESULTS"


class QueryService:
    def __init__(
        self,
        catalog: CatalogSnapshot,
        selector: OfflineSemanticSelector,
        validator: SemanticValidator,
        compiler: SQLCompiler,
        executor: DuckDBReadOnlyExecutor,
    ) -> None:
        self.catalog = catalog
        self.selector = selector
        self.validator = validator
        self.compiler = compiler
        self.executor = executor

    def query(self, request: QueryRequest, auth: AuthContext) -> QueryResponse:
        request_id = f"req-{uuid.uuid4().hex[:20]}"
        started = time.perf_counter()
        try:
            draft = self.selector.select(request.question)
            if draft.status == "needs_clarification":
                return self._decision(request_id, draft, "needs_clarification")
            if draft.status == "unsupported":
                return self._decision(request_id, draft, "unsupported")
            plan = self.validator.validate(draft, auth)
            bound = self.compiler.compile(plan)
            data, watermark = self.executor.execute(bound)
            status = "ready"
            warnings = [DEMO_WARNING]
            partial = self._is_partial(plan.time, watermark)
            if partial:
                warnings.append(f"Dữ liệu mới cập nhật đến {watermark}; kỳ yêu cầu chưa đầy đủ.")
            if self._is_no_data(data, bound.metric_ids, bound.units):
                status = "no_data"
                answer = "Không có dữ liệu đủ điều kiện trong phạm vi đã chọn."
                data = None
            else:
                if self._has_null_ratio(data, bound.units):
                    warnings.append("Không tính được tỷ lệ do mẫu số bằng 0 hoặc thiếu dữ liệu.")
                answer = self._render(plan.metric_ids, data, plan.time, plan.view)
                if partial:
                    answer += f" Dữ liệu cập nhật đến {watermark}."
            return QueryResponse(
                api_version="v1", request_id=request_id, status=status,
                error=None, answer=answer, data=data,
                interpretation=Interpretation(
                    metric_ids=list(plan.metric_ids), dimensions=list(plan.dimensions),
                    view=plan.view, time=plan.time,
                ),
                provenance=Provenance(
                    catalog_hash=plan.catalog_hash, data_watermark=watermark,
                    source=bound.source, query_fingerprint=bound.fingerprint,
                ), warnings=warnings,
            )
        except (Forbidden, PlanRejected) as exc:
            return QueryResponse(
                api_version="v1", request_id=request_id, status=exc.status, error=ErrorData(
                    code=exc.code, message=str(exc), retryable=False,
                ), answer=str(exc), data=None, interpretation=None, provenance=None,
                warnings=[DEMO_WARNING],
            )
        except DataUnavailable as exc:
            return QueryResponse(
                api_version="v1", request_id=request_id, status="temporarily_unavailable",
                error=ErrorData(code=exc.code, message="Nguồn dữ liệu tạm thời không khả dụng.", retryable=True),
                answer="Không thể truy vấn dữ liệu lúc này; vui lòng thử lại.", data=None,
                interpretation=None, provenance=None, warnings=[DEMO_WARNING],
            )
        except Text2SQLError as exc:
            return QueryResponse(
                api_version="v1", request_id=request_id, status="error",
                error=ErrorData(code=exc.code, message="Truy vấn bị chặn bởi lớp an toàn.", retryable=False),
                answer="Không thể xử lý truy vấn an toàn.", data=None,
                interpretation=None, provenance=None, warnings=[DEMO_WARNING],
            )
        finally:
            _ = round((time.perf_counter() - started) * 1000, 3)

    def _decision(self, request_id: str, draft: SemanticPlanDraft, status: str) -> QueryResponse:
        answer = draft.question_for_user or "Yêu cầu này chưa được hỗ trợ bởi danh mục hiện tại."
        error = None if status == "needs_clarification" else ErrorData(
            code=draft.reason_code or "unsupported_metric", message=answer, retryable=False,
        )
        return QueryResponse(
            api_version="v1", request_id=request_id, status=status,
            error=error, answer=answer, data=None,
            interpretation=None,
            provenance=Provenance(
                catalog_hash=self.catalog.hash, data_watermark=None,
                source="synthetic_duckdb", query_fingerprint=None,
            ), warnings=[DEMO_WARNING],
        )

    @staticmethod
    def _is_no_data(
        data: ResultData, metric_ids: tuple[str, ...], units: dict[str, str]
    ) -> bool:
        if data.row_count == 0:
            return True
        if any(units.get(metric_id) in {"%", "ratio", "days"} for metric_id in metric_ids):
            return False
        return all(all(row.get(metric) is None for metric in metric_ids) for row in data.rows)

    @staticmethod
    def _has_null_ratio(data: ResultData, units: dict[str, str]) -> bool:
        ratio_ids = [key for key, unit in units.items() if unit in {"%", "ratio", "days"}]
        return any(row.get(key) is None for row in data.rows for key in ratio_ids)

    @staticmethod
    def _is_partial(scope, watermark: str | None) -> bool:
        if not watermark:
            return False
        available = date.fromisoformat(watermark)
        requested_end = scope.end if scope.mode == "range" else scope.as_of
        return bool(requested_end and requested_end > available)

    def _render(self, metric_ids: tuple[str, ...], data: ResultData, time_scope, view: str) -> str:
        labels = [self.catalog.get(metric_id).label for metric_id in metric_ids]
        if data.row_count == 1 and not any(key in data.rows[0] for key in ("month", "branch", "customer")):
            facts = []
            for metric_id, label in zip(metric_ids, labels, strict=True):
                value = data.rows[0].get(metric_id)
                unit = self.catalog.get(metric_id).unit
                facts.append(f"{label}: {value if value is not None else 'không tính được'} {unit}")
            return f"{'; '.join(facts)} (khung {view}, {self._time_label(time_scope)})."
        return f"Kết quả {', '.join(labels)} gồm {data.row_count} dòng ({self._time_label(time_scope)}, khung {view})."

    @staticmethod
    def _time_label(scope) -> str:
        if scope.mode == "range":
            return f"{scope.start.isoformat()}–{scope.end.isoformat()}"
        return f"tại {scope.as_of.isoformat()}"


def build_default_service(database_path: str | Path | None = None) -> QueryService:
    if database_path is None:
        database_path = os.getenv("AGENT4_DB", "data/cfo_warehouse.duckdb")
    catalog = CatalogSnapshot()
    return QueryService(
        catalog=catalog,
        selector=OfflineSemanticSelector(catalog),
        validator=SemanticValidator(catalog),
        compiler=SQLCompiler(catalog),
        executor=DuckDBReadOnlyExecutor(database_path),
    )
