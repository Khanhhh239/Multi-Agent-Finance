from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QueryOptions(StrictModel):
    include_table: bool
    explain_metrics: bool


class QueryRequest(StrictModel):
    api_version: Literal["v1"]
    question: str = Field(min_length=1, max_length=4000)
    locale: Literal["vi-VN", "en-US"]
    session_id: str | None
    options: QueryOptions


def make_query_request(question: str) -> QueryRequest:
    return QueryRequest(
        api_version="v1",
        question=question,
        locale="vi-VN",
        session_id=None,
        options=QueryOptions(include_table=True, explain_metrics=True),
    )


class TimeDraft(StrictModel):
    mode: Literal["range", "as_of", "none"]
    start: date | None
    end: date | None
    as_of: date | None
    grain: Literal["day", "week", "month", "quarter", "year"] | None

    @classmethod
    def range(cls, start: date, end: date, grain: str | None = None) -> TimeDraft:
        return cls(mode="range", start=start, end=end, as_of=None, grain=grain)

    @classmethod
    def as_of_date(cls, value: date, grain: str | None = None) -> TimeDraft:
        return cls(mode="as_of", start=None, end=None, as_of=value, grain=grain)

    @classmethod
    def none(cls) -> TimeDraft:
        return cls(mode="none", start=None, end=None, as_of=None, grain=None)

    @model_validator(mode="after")
    def consistent(self) -> TimeDraft:
        if self.mode == "range":
            if not self.start or not self.end or self.as_of is not None:
                raise ValueError("range requires start/end and forbids as_of")
            if self.end < self.start:
                raise ValueError("time end precedes start")
        elif self.mode == "as_of":
            if not self.as_of or self.start is not None or self.end is not None:
                raise ValueError("as_of requires as_of and forbids range dates")
        elif any((self.start, self.end, self.as_of, self.grain)):
            raise ValueError("none time cannot contain dates or grain")
        return self


class FilterDraft(StrictModel):
    field: str
    operator: Literal["eq", "neq", "in", "gte", "lte", "between"]
    values: list[str] = Field(min_length=1, max_length=100)


class SortDraft(StrictModel):
    metric_id: str
    direction: Literal["asc", "desc"]


class ComparisonDraft(StrictModel):
    mode: Literal["previous_period", "year_over_year", "custom"]
    start: date | None = None
    end: date | None = None


class SemanticPlanDraft(StrictModel):
    plan_version: Literal["1.0"]
    status: Literal["ready", "needs_clarification", "unsupported"]
    metric_ids: list[str]
    time: TimeDraft
    dimensions: list[str]
    filters: list[FilterDraft] = Field(max_length=20)
    view: Literal["mgmt", "tax"] | None
    operation: Literal["aggregate", "timeseries", "breakdown", "rank", "compare"] | None
    sort: SortDraft | None
    top_k: int | None = Field(ge=1, le=100)
    comparison: ComparisonDraft | None
    question_for_user: str | None
    unresolved_slots: list[str]
    reason_code: str | None

    @model_validator(mode="after")
    def status_contract(self) -> SemanticPlanDraft:
        if len(self.metric_ids) != len(set(self.metric_ids)):
            raise ValueError("duplicate metric_ids")
        if len(self.dimensions) != len(set(self.dimensions)):
            raise ValueError("duplicate dimensions")
        if self.status == "ready":
            if not self.metric_ids:
                raise ValueError("ready plan requires metric_ids")
            if self.question_for_user or self.unresolved_slots or self.reason_code:
                raise ValueError("ready plan contains unresolved fields")
        elif self.status == "needs_clarification":
            if not self.question_for_user or not self.unresolved_slots:
                raise ValueError("clarification requires a question and unresolved slots")
        elif not self.reason_code:
            raise ValueError("unsupported requires reason_code")
        return self


class AuthContext(StrictModel):
    user_id: str
    tenant_id: str
    roles: frozenset[str]
    allowed_views: frozenset[Literal["mgmt", "tax"]]
    allowed_metrics: frozenset[str] | None = None


class ValidatedPlan(StrictModel):
    metric_ids: tuple[str, ...]
    time: TimeDraft
    dimensions: tuple[str, ...]
    filters: tuple[FilterDraft, ...]
    view: Literal["mgmt", "tax"]
    operation: Literal["aggregate", "timeseries", "breakdown", "rank", "compare"]
    sort: SortDraft | None
    top_k: int | None
    comparison: ComparisonDraft | None
    tenant_id: str
    catalog_hash: str
    policy_hash: str
    applied_defaults: tuple[str, ...] = ()

    model_config = ConfigDict(extra="forbid", frozen=True)


class BoundQuery(StrictModel):
    sql: str
    params: tuple[Any, ...]
    metric_ids: tuple[str, ...]
    dimensions: tuple[str, ...]
    units: dict[str, str]
    row_cap: int
    fingerprint: str
    source: str
    catalog_hash: str

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)


class ResultColumn(StrictModel):
    key: str
    type: Literal["date", "string", "decimal", "integer", "boolean"]
    unit: str | None = None


class ResultData(StrictModel):
    columns: list[ResultColumn]
    rows: list[dict[str, str | int | bool | None]]
    row_count: int
    truncated: bool


class ErrorData(StrictModel):
    code: str
    message: str
    retryable: bool = False


class Provenance(StrictModel):
    catalog_hash: str
    data_watermark: str | None
    source: str
    query_fingerprint: str | None


class Interpretation(StrictModel):
    metric_ids: list[str]
    dimensions: list[str]
    view: str | None
    time: TimeDraft


class QueryResponse(StrictModel):
    api_version: Literal["v1"]
    request_id: str
    status: Literal[
        "ready",
        "needs_clarification",
        "unsupported",
        "forbidden",
        "no_data",
        "temporarily_unavailable",
        "error",
    ]
    error: ErrorData | None
    answer: str
    data: ResultData | None
    interpretation: Interpretation | None
    provenance: Provenance | None
    warnings: list[str]


def decimal_string(value: Any) -> str | int | bool | None:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("non-finite Decimal result")
        return format(value, "f")
    if isinstance(value, float):
        value = Decimal(str(value))
        if not value.is_finite():
            raise ValueError("non-finite numeric result")
        return format(value, "f")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)
