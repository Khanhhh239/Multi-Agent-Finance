"""Guided clarification and scoped, single-use continuation sessions."""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from threading import Lock
from typing import Any
from uuid import uuid4

from agent4.core.cache import LRUTTLCache
from agent4.core.catalog import MetricCatalog
from agent4.core.errors import ContractError
from agent4.metric_selection.validator import validate_metrics

from .planner import (
    _MESSAGES,
    _PERIOD_DIMENSIONS,
    ALLOWED_DIMENSIONS,
    _apply_time_grain,
    _metric_ambiguity,
    _supported_dimension,
    parse_time_slot,
    requests_comparison,
)
from .validator import PlanClarification, ValidatedPlan, _safe_text, validate_semantic_plan_draft

_METRICS = {
    "profit": {"gross_profit", "net_profit"},
    "margin": {"gross_margin", "net_profit_margin", "gross_margin_pct", "net_margin_pct"},
    "debt": {"ar_balance", "ap_balance", "loan_balance", "debt_balance"},
}
_VIEWS = {
    "mgmt": ("Quản trị", "Management"),
    "tax": ("Thuế", "Tax"),
}
_DIMENSIONS = {
    "branch_code": ("Chi nhánh", "Branch"),
    "product_line": ("Dòng sản phẩm", "Product line"),
    "department_code": ("Phòng ban", "Department"),
    "cost_category": ("Khoản mục chi phí", "Cost category"),
    "partner_code": ("Đối tác", "Partner"),
    "segment": ("Phân khúc", "Segment"),
    "month": ("Tháng", "Month"),
    "quarter": ("Quý", "Quarter"),
    "year": ("Năm", "Year"),
}
_SLOTS = ("metric_ids", "dimensions", "filters", "view", "time", "operation", "sort", "top_k")


def _invalid() -> ContractError:
    return ContractError("invalid_request", "clarification", "Invalid clarification turn.")


def build_clarification_payload(
    draft: dict, metrics: dict, catalog: MetricCatalog, auth: dict, query: dict
) -> dict:
    """Expose only validated slots and currently authorized choices."""
    decision = validate_semantic_plan_draft(draft, metrics, catalog, auth)
    if not isinstance(decision, PlanClarification):
        raise _invalid()
    locale = query["locale"]
    question = query["normalized_question"]
    language = int(locale == "en-US")
    visible = catalog.list_visible_metrics(auth)
    selected = [catalog.get_capability(mid) for mid in draft["metric_ids"]]
    view = draft["view"]
    metric_intent = _metric_ambiguity(question)
    snapshot = metric_intent == "debt" or any(cap["period_type"] == "snapshot" for cap in selected)
    prompts = []
    for slot in decision.unresolved_slots:
        kind = "as_of" if slot == "time" and snapshot else slot
        choices: list[dict[str, str]] = []
        if slot == "metric":
            group = _METRICS.get(metric_intent)
            for item in visible:
                mid = item["metric_id"]
                if (group is None or mid in group) and (
                    view is None or view in item["supported_views"]
                ):
                    label = item.get("label_en") or mid.replace("_", " ")
                    choices.append({"value": mid, "label": label if language else item["label"]})
        elif slot == "view":
            choices = [
                {"value": value, "label": names[language]}
                for value, names in _VIEWS.items()
                if value in auth["allowed_views"]
                and all(value in cap["supported_views"] for cap in selected)
            ]
        elif slot == "dimensions":
            choices = [
                {"value": value, "label": _DIMENSIONS[value][language]}
                for value in sorted(ALLOWED_DIMENSIONS)
                if all(_supported_dimension(value, cap, question) for cap in selected)
            ]
        elif slot == "time":
            choices = _date_choices(query.get("reporting_calendar", {}), locale, snapshot)
        elif slot == "sort":
            choices = [
                {"value": f"{mid} {direction}", "label": f"{mid} {label[language]}"}
                for mid in draft["metric_ids"]
                for direction, label in (
                    ("asc", ("tăng dần", "ascending")),
                    ("desc", ("giảm dần", "descending")),
                )
            ]
        elif slot == "top_k":
            choices = [{"value": str(value), "label": str(value)} for value in (5, 10, 20)]
        prompts.append({"slot": slot, "prompt": _MESSAGES[locale][kind], "choices": choices})

    return {
        "contract_version": "query.clarification.v1",
        "question_for_user": " ".join(prompt["prompt"] for prompt in prompts),
        "unresolved_slots": list(decision.unresolved_slots),
        "partial_interpretation": {
            key: deepcopy(draft[key])
            for key in _SLOTS
            if ("metric" if key == "metric_ids" else key) not in decision.unresolved_slots
            and draft[key] is not None
        },
        "slot_prompts": prompts,
    }


class ClarificationSessionStore:
    def __init__(self, *, ttl_seconds: float = 300, max_turns: int = 3) -> None:
        if type(max_turns) is not int or not 1 <= max_turns <= 3:
            raise ValueError("Clarification turns must be between 1 and 3.")
        self._max_turns = max_turns
        self._lock = Lock()
        self._sessions: LRUTTLCache[tuple[str, str, str], dict] = LRUTTLCache(
            max_entries=500,
            ttl_seconds=ttl_seconds,
            max_bytes_budget=8 * 1024 * 1024,
            max_rows_per_entry=1,
        )

    def start(
        self, draft: dict, metrics: dict, catalog: MetricCatalog, auth: dict, query: dict
    ) -> dict:
        payload = build_clarification_payload(draft, metrics, catalog, auth, query)
        session_id = uuid4().hex
        stored = self._sessions.set(
            (auth["tenant_id"], auth["user_id"], session_id),
            {
                "draft": draft,
                "metrics": {
                    key: metrics[key]
                    for key in ("status", "metric_ids", "catalog_hash", "validated_capabilities")
                },
                "query": query,
                "policy_hash": auth["policy_hash"],
                "turns": 0,
            },
        )
        if not stored:
            raise ContractError(
                "clarification_unavailable",
                "clarification",
                "Clarification session is unavailable.",
                retryable=True,
                final_status="temporarily_unavailable",
            )
        return {**payload, "session_id": session_id}


def resolve_clarification_turn(
    store: ClarificationSessionStore,
    session_id: str,
    answers: dict[str, Any] | str,
    catalog: MetricCatalog,
    auth: dict,
    *,
    row_cap: int = 1000,
) -> ValidatedPlan | dict:
    if not isinstance(session_id, str) or len(session_id) != 32:
        raise _invalid()
    key = (auth["tenant_id"], auth["user_id"], session_id)
    with store._lock:
        session = store._sessions.get(key)
        if (
            session is None
            or session["turns"] >= store._max_turns
            or session["policy_hash"] != auth["policy_hash"]
            or session["metrics"]["catalog_hash"] != catalog.get_catalog_hash()
        ):
            raise _invalid()
        draft, metrics, query = session["draft"], session["metrics"], session["query"]
        payload = build_clarification_payload(draft, metrics, catalog, auth, query)
        slots = draft["unresolved_slots"].copy()
        if isinstance(answers, str):
            answers = {slots[0]: answers}
        if not isinstance(answers, dict) or not answers or not answers.keys() <= set(slots):
            raise _invalid()

        # Count invalid attempts too. Save only validated draft changes.
        session["turns"] += 1
        store._sessions.set(key, session)
        prompts = {item["slot"]: item for item in payload["slot_prompts"]}
        for slot in ("view", "metric", "time", "dimensions", "filters", "sort", "top_k"):
            if slot not in answers:
                continue
            value = answers[slot]
            if isinstance(value, str):
                _safe_text(value)
                value = value.strip()
            if slot == "metric":
                mid = _choice(value, prompts[slot])
                metrics = validate_metrics(
                    {
                        "status": "resolved",
                        "metric_ids": [mid],
                        "clarification_question": None,
                        "unsupported_reason": None,
                    },
                    {"candidates": [{"metric_id": mid}]},
                    catalog,
                    auth,
                    {
                        "requested_view": draft["view"]
                        or next(
                            view
                            for view in auth["allowed_views"]
                            if view in catalog.get_capability(mid)["supported_views"]
                        )
                    },
                )
                draft["metric_ids"] = [mid]
            elif slot == "time" and isinstance(value, str):
                periods = [cap["period_type"] for cap in metrics["validated_capabilities"].values()]
                if prompts[slot]["choices"]:
                    value = next(
                        (
                            choice["value"]
                            for choice in prompts[slot]["choices"]
                            if value.casefold() == choice["label"].casefold()
                        ),
                        value,
                    )
                draft["time"] = parse_time_slot(
                    value,
                    locale=query["locale"],
                    period_type=next(iter(periods), None),
                )
                if draft["time"]["mode"] == "none":
                    raise _invalid()
            elif slot in ("view", "dimensions") and isinstance(value, str):
                choice = _choice(value, prompts[slot])
                draft[slot] = choice if slot == "view" else [choice]
            elif slot == "sort" and isinstance(value, str):
                mid, direction = _choice(value, prompts[slot]).split()
                draft[slot] = {"metric_id": mid, "direction": direction}
            elif (
                slot == "top_k" and isinstance(value, str) and value.isascii() and value.isdecimal()
            ):
                if len(value) > 3:
                    raise _invalid()
                draft[slot] = int(value)
            else:
                draft[slot] = value
            slots.remove(slot)

        draft.update(
            unresolved_slots=slots,
            status="needs_clarification",
            question_for_user=payload["question_for_user"],
        )
        if not slots and requests_comparison(query["normalized_question"]):
            store._sessions.discard(key)
            raise ContractError(
                "unsupported_metric",
                "clarification",
                "Comparison is outside this query contract.",
                final_status="unsupported",
            )
        # Validate value shapes before deriving dependent slots from them.
        validate_semantic_plan_draft(
            {**draft, "unresolved_slots": slots or [next(iter(answers))]},
            metrics,
            catalog,
            auth,
            row_cap=row_cap,
        )
        if "metric" in answers:
            expected_mode = (
                "as_of"
                if catalog.get_capability(draft["metric_ids"][0])["period_type"] == "snapshot"
                else "range"
            )
            if draft["time"]["mode"] != expected_mode and "time" not in slots:
                if "time" in answers:
                    raise _invalid()
                slots.append("time")
                draft["time"] = parse_time_slot("", locale=query["locale"])
        grains = [grain for grain in _PERIOD_DIMENSIONS if grain in draft["dimensions"]]
        if "dimensions" in answers and draft["operation"] != "ranking":
            draft["operation"] = (
                "timeseries" if grains else "breakdown" if draft["dimensions"] else "aggregate"
            )
        _apply_time_grain(draft["time"], draft["operation"], grains)
        if (
            draft["operation"] == "ranking"
            and not draft["sort"]
            and not {"metric", "sort"} & set(slots)
        ):
            slots.append("sort")
        draft.update(
            unresolved_slots=slots,
            status="needs_clarification" if slots else "ready",
            question_for_user=payload["question_for_user"] if slots else None,
        )
        result = validate_semantic_plan_draft(draft, metrics, catalog, auth, row_cap=row_cap)
        if isinstance(result, ValidatedPlan):
            store._sessions.discard(key)
            return result
        if session["turns"] >= store._max_turns:
            store._sessions.discard(key)
            raise _invalid()
        payload = build_clarification_payload(draft, metrics, catalog, auth, query)
        store._sessions.set(key, {**session, "draft": draft, "metrics": metrics})
        return {**payload, "session_id": session_id}


def _choice(value: Any, prompt: dict) -> str:
    if isinstance(value, str):
        matches = {
            option["value"]
            for option in prompt["choices"]
            if value.casefold() in (option["value"].casefold(), option["label"].casefold())
        }
        if len(matches) == 1:
            return matches.pop()
    raise _invalid()


def _date_choices(calendar: dict, locale: str, snapshot: bool) -> list[dict[str, str]]:
    vi = locale == "vi-VN"
    try:
        if snapshot:
            watermark = date.fromisoformat(calendar["data_watermark"]).isoformat()
            label = f"Ngày {watermark}" if vi else f"As of {watermark}"
            return [{"value": watermark, "label": label}]
        closed = date.fromisoformat(calendar["last_closed_month"] + "-01")
    except (KeyError, TypeError, ValueError):
        return []
    month = closed.isoformat()[:7]
    choices = [{"value": month, "label": f"Tháng {month}" if vi else f"Month {month}"}]
    quarter_index = closed.year * 4 + closed.month // 3 - 1
    year, quarter = divmod(quarter_index, 4)
    if year >= 1:
        value = f"Q{quarter + 1} {year:04d}"
        choices.append({"value": value, "label": f"Quý {quarter + 1}/{year}" if vi else value})
    return choices
