"""Build a semantic draft using business vocabulary and validated metric capabilities."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from agent4.core.errors import ContractError

from ._time import parse_time_slot

__all__ = ["build_semantic_plan_draft", "parse_time_slot"]

_STAGE = "query_planning"
_DIMENSIONS = {
    "month": r"tháng|months?",
    "quarter": r"quý|quarters?",
    "year": r"năm|years?",
    "branch_code": r"chi nhánh|branch(?:es)?|branch_code",
    "product_line": r"dòng sản phẩm|nhóm sản phẩm|product lines?|product_line",
    "department_code": r"phòng ban|phòng|departments?|department_code",
    "cost_category": r"khoản mục chi phí|khoản mục|cost categor(?:y|ies)|cost_category",
    "partner_code": r"mã đối tác|đối tác|khách hàng|nhà cung cấp|partners?|customers?|vendors?|suppliers?|partner_code",
    "segment": r"phân khúc(?: khách hàng)?|segments?",
}
_PERIOD_DIMENSIONS = ("month", "quarter", "year")
_DIMENSION_NAMES = "(?:" + "|".join(f"(?:{names})" for names in _DIMENSIONS.values()) + ")"
_DIMENSION_TOKEN = re.compile(
    r"\b(?:" + "|".join(f"(?P<{field}>{names})" for field, names in _DIMENSIONS.items()) + r")\b"
)
_FILTERS = {
    "branch_code": {
        "HN": r"hà nội|ha noi",
        "HCM": r"(?:tp\.? )?hồ chí minh|ho chi minh(?: city)?|sài gòn",
        "DN": r"đà nẵng|da nang",
    },
    "product_line": {
        "IT": "thiết bị cntt",
        "OFF": "thiết bị văn phòng",
        "CON": "vật tư tiêu hao",
        "SVC": "dịch vụ kỹ thuật",
    },
    "department_code": {
        "BGD": "ban giám đốc",
        "KD": "kinh doanh|sales",
        "MKT": "marketing",
        "KT": "kỹ thuật|technical services",
        "KHO": "kho vận|logistics",
        "TCKT": "tài chính(?: -)? kế toán|finance and accounting",
        "HCNS": "hành chính(?: -)? nhân sự|human resources",
    },
    "cost_category": {
        "LUONG": "lương|salaries",
        "BAOHIEM": "bảo hiểm|insurance",
        "THUONG": "thưởng|bonuses",
        "THUE_MB": "thuê mặt bằng|rent",
        "DIEN_NUOC": "(?:tiền )?điện(?:,| và)? nước|utilities",
        "VIENTHONG": "viễn thông|telecom",
        "MARKETING": "quảng cáo|marketing",
        "VANCHUYEN": "vận chuyển|shipping",
        "CONGTAC": "công tác phí|business travel",
        "TIEPKHACH": "tiếp khách",
        "KHAUHAO": "khấu hao|depreciation",
        "PHANMEM": "phần mềm|software",
        "VPP": "văn phòng phẩm|office supplies",
        "BAOHIEM_TS": "bảo hiểm tài sản|property insurance",
        "PHI_NH": "phí ngân hàng|bank fees",
        "DUPHONG": "dự phòng nợ khó đòi",
        "VATTU_DV": "vật tư phục vụ dịch vụ",
        "THUE_PHI": "thuế, phí, lệ phí",
        "KHAC": "chi phí khác",
    },
    "segment": {
        "GOV": "cơ quan nhà nước|government",
        "SME": "doanh nghiệp vừa và nhỏ",
        "DLR": "đại lý bán lại|resellers",
        "RET": "khách lẻ|retail",
        "ENT": "doanh nghiệp lớn|enterprise",
    },
}
ALLOWED_DIMENSIONS = frozenset(_DIMENSIONS)
ALLOWED_FILTER_VALUES = {field: frozenset(values) for field, values in _FILTERS.items()}
PARTNER_CODE_PATTERN = (
    r"(?:KH[0-9]{4,7}|KHLE-(?:HN|HCM|DN)|NCC-[A-Z0-9]{2,12}(?:-[A-Z0-9]{2,12}){0,3})"
)
_SQL = re.compile(
    r"\b(?:select\b[^?]*\bfrom|select\s+\*|(?:drop|create|alter|truncate)\s+table|"
    r"insert\s+into|delete\s+from|update\s+\w+\s+set|or\s+1\s*=\s*1|"
    r"read_(?:csv(?:_auto)?|parquet)|gl_wide|gl_entry|gl_journal|ar_invoice(?:_line)?|"
    r"ar_receipt|ar_adjustment|ap_bill|ap_payment|duckdb_tables|v_(?:gl|mgmt|tax)|"
    r"dim_(?:account|branch|department|employee|partner|item|product_line|cost_category|period)|"
    r"period_close|inventory_txn|fixed_asset|loan_schedule|service_contract|company_info|"
    r"(?:table|bảng) (?:budget|loan|payroll)|(?:budget|loan|payroll) table)\b|--|/\*",
    re.IGNORECASE,
)
_RESERVED_IDS = {
    "select",
    "from",
    "drop",
    "insert",
    "delete",
    "update",
    "budget",
    "loan",
    "payroll",
}
_GROUP = r"(?:theo(?: từng)?|từng|by|per|each)"
_EXPLICIT_GROUP = r"(?:group(?:ed)? by|breakdown by|phân tích theo|phân bổ theo|chia theo)"
_RANK = r"\b(?:top|bottom|xếp hạng|rank(?:ing)?|cao nhất|thấp nhất|highest|lowest|best|worst)\b"
_LIMIT = r"\b(?:top|bottom)\s*([+-]?\d{1,3})(?!\w|[.,]\d)"
_SORT = r"\b(?:sắp xếp|sort(?:ed)?|order(?:ed)?|tăng dần|giảm dần|ascending|descending)\b"
_ASC = r"\b(?:bottom|thấp nhất|nhỏ nhất|tăng dần|lowest|worst|ascending|asc)\b"
_DESC = r"\b(?:cao nhất|lớn nhất|giảm dần|highest|best|descending|desc)\b"
_VIEWS = {
    "mgmt": r"quản trị|management (?:view|books|reporting)|mgmt",
    "tax": r"góc nhìn thuế|sổ thuế|báo cáo thuế|theo thuế|tax (?:view|books|reporting)|(?:under|in|for|view) tax",
}
_MESSAGES = {
    "vi-VN": {
        "profit": "Bạn muốn xem lợi nhuận gộp hay lợi nhuận ròng?",
        "margin": "Bạn muốn xem biên lợi nhuận gộp hay biên lợi nhuận ròng?",
        "debt": "Bạn muốn xem công nợ phải thu hay công nợ phải trả?",
        "metric": "Bạn muốn xem chỉ tiêu tài chính nào?",
        "time": "Bạn muốn xem trong kỳ nào?",
        "as_of": "Bạn muốn chốt số dư vào ngày nào?",
        "view": "Bạn muốn xem theo góc nhìn quản trị hay thuế?",
        "dimensions": "Bạn muốn phân tích theo chiều nghiệp vụ nào?",
        "filters": "Bạn muốn lọc theo giá trị nghiệp vụ nào?",
        "sort": "Bạn muốn sắp xếp theo chỉ tiêu nào và theo thứ tự nào?",
        "top_k": "Bạn muốn lấy bao nhiêu kết quả, từ 1 đến 100?",
    },
    "en-US": {
        "profit": "Would you like gross profit or net profit?",
        "margin": "Would you like gross margin or net profit margin?",
        "debt": "Would you like accounts receivable or accounts payable?",
        "metric": "Which financial metric would you like to see?",
        "time": "Which time period would you like to see?",
        "as_of": "What as-of date should I use for the balance?",
        "view": "Would you like the management view or the tax view?",
        "dimensions": "Which business dimension should I group by?",
        "filters": "Which business values should I filter on?",
        "sort": "Which metric and direction should I sort by?",
        "top_k": "How many results would you like, from 1 to 100?",
    },
}


def _has(pattern: str, text: str) -> bool:
    return bool(re.search(rf"\b(?:{pattern})\b", text))


def _metric_ambiguity(question: str) -> str:
    if _has(r"công nợ|outstanding balances?", question) and not _has(
        r"phải thu|phải trả|khách hàng|nhà cung cấp|receivable|payable", question
    ):
        return "debt"
    if not _has(r"gộp|ròng|sau thuế|trước thuế|gross|net|operating|before tax|after tax", question):
        if _has(r"(?:biên|tỷ suất) lợi nhuận|profit margin", question):
            return "margin"
        if _has(r"lợi nhuận|profit", question):
            return "profit"
    return "metric"


def _filters(question: str, original: str) -> tuple[list[dict], bool]:
    filters = []
    unresolved = False
    for field, vocabulary in _FILTERS.items():
        marker = _DIMENSIONS[field]
        terms = "|".join(
            f"(?P<{code}>{code.lower()}|{alias})"
            for code, alias in sorted(vocabulary.items(), key=lambda pair: -len(pair[1]))
        )
        value_pattern = rf"(?:{terms})(?![\w-])"
        values = []
        # Codes need an explicit field or an uppercase spelling.
        for marker_match in re.finditer(rf"\b(?:{marker})(?:\s*[:=]|\s)\s*", question):
            rest = question[marker_match.end() :]
            while value_match := re.match(value_pattern, rest):
                values.append(value_match.lastgroup)
                separator = re.match(r"\s*,\s*|\s+(?:và|hoặc|and|or)\s+", rest[value_match.end() :])
                if separator is None:
                    break
                rest = rest[value_match.end() + separator.end() :]
        for code, alias in vocabulary.items():
            if (code != "IT" and re.search(rf"(?<![\w-]){code}(?![\w-])", original)) or (
                field == "branch_code" and _has(alias, question)
            ):
                values.append(code)
        values = list(dict.fromkeys(values))
        if (
            re.search(rf"\b(?:for|at|of|của|tại|ở)\s+(?:the\s+)?(?:{marker})\s+[\w-]+", question)
            and not values
        ):
            unresolved = True
        if values:
            filters.append(_filter(field, values))

    partners = list(
        dict.fromkeys(re.findall(rf"(?<![\w-]){PARTNER_CODE_PATTERN}(?![\w-])", question.upper()))
    )
    if partners:
        filters.append(_filter("partner_code", partners))
    return filters, unresolved


def _filter(field: str, values: list[str]) -> dict[str, Any]:
    return {
        "field": field,
        "op": "=" if len(values) == 1 else "IN",
        "value": values[0] if len(values) == 1 else values,
    }


def _dimensions(question: str, ranking: bool) -> list[str]:
    marker = rf"{_GROUP}|(?:top|bottom)\s+\d+" if ranking else _GROUP
    dimensions = []
    for match in re.finditer(
        rf"\b(?:{marker}) ({_DIMENSION_NAMES}\b"
        rf"(?:(?:,\s*|\s+(?:và|and)\s+){_DIMENSION_NAMES}\b)*)",
        question,
    ):
        dimensions.extend(token.lastgroup for token in _DIMENSION_TOKEN.finditer(match[1]))
    for grain in _PERIOD_DIMENSIONS:
        if _has(f"{grain}ly", question):
            dimensions.append(grain)
    return list(dict.fromkeys(dimensions))


def _unresolved_grouping(question: str, sort_requested: bool) -> bool:
    view_cues = r"góc nhìn|sổ (?:thuế|quản trị)|thuế|quản trị|management|tax"
    for match in re.finditer(rf"\b(?:{_EXPLICIT_GROUP}|theo(?: từng)?|by|per) ", question):
        target = question[match.end() :]
        if re.match(rf"(?:{_DIMENSION_NAMES}|{view_cues})\b", target):
            continue
        if sort_requested and match[0].strip() in {"by", "theo"}:
            continue
        if match[0] == "by " and re.match(r"\d", target):
            continue
        return True
    return False


def _supported_dimension(field: str, capability: dict[str, Any], question: str) -> bool:
    aliases = {"branch_code": ("branch",), "department_code": ("department",)}
    if field == "partner_code":
        if _has(r"nhà cung cấp|vendors?|suppliers?|ncc-[\w-]+", question):
            aliases[field] = ("vendor",)
        elif _has(r"khách hàng|customers?|kh\d+|khle-\w+", question):
            aliases[field] = ("customer",)
    return bool({field, *aliases.get(field, ())}.intersection(capability["supported_dimensions"]))


def _metric_input(metrics: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    if not isinstance(metrics, dict):
        raise ContractError("invalid_request", _STAGE, "Invalid validated metric set.")
    ids = metrics.get("metric_ids")
    capabilities = metrics.get("validated_capabilities")
    status = metrics.get("status")
    if (
        not isinstance(ids, list)
        or not isinstance(capabilities, dict)
        or any(
            not isinstance(item, str)
            or not re.fullmatch(r"[a-z][a-z0-9_]*", item)
            or item in _RESERVED_IDS
            or _SQL.search(item)
            for item in ids
        )
        or len(ids) != len(set(ids))
        or set(ids) != set(capabilities)
        or not ((status == "validated" and ids) or (status == "needs_clarification" and not ids))
    ):
        raise ContractError("invalid_request", _STAGE, "Invalid validated metric set.")

    caps = [capabilities[item] for item in ids]
    for cap in caps:
        if (
            not isinstance(cap, dict)
            or cap.get("period_type") not in ("flow", "snapshot")
            or any(
                not isinstance(cap.get(key), (list, tuple))
                or any(not isinstance(value, str) for value in cap[key])
                for key in ("supported_views", "supported_dimensions", "supported_operations")
            )
        ):
            raise ContractError("invalid_request", _STAGE, "Invalid metric capabilities.")
    return ids.copy(), caps


def build_semantic_plan_draft(
    normalized_query: dict[str, Any],
    validated_metrics: dict[str, Any],
    query_context: dict[str, Any],
) -> dict[str, Any]:
    """Extract slots. Drafts still require the downstream validation gate."""
    original = unicodedata.normalize("NFKC", normalized_query["question"])
    question = " ".join(original.casefold().split())
    locale = normalized_query["locale"]
    if _SQL.search(question):
        raise ContractError("invalid_request", _STAGE, "Prohibited query content.")
    ids, capabilities = _metric_input(validated_metrics)
    periods = {cap["period_type"] for cap in capabilities}
    if len(periods) > 1:
        raise ContractError("incompatible_metrics", _STAGE, "Incompatible metric periods.")
    period_type = next(iter(periods), None)
    time = parse_time_slot(question, locale=locale, period_type=period_type)
    metric_intent = _metric_ambiguity(question)
    views = {view for view, pattern in _VIEWS.items() if _has(pattern, question)}
    requested_view = query_context.get("requested_view")
    if requested_view is not None and requested_view not in ("mgmt", "tax"):
        raise ContractError("invalid_request", _STAGE, "Invalid requested business view.")
    if requested_view:
        views.add(requested_view)
    view = next(iter(views), "mgmt") if len(views) < 2 else None

    ranking = _has(_RANK, question)
    dimensions = _dimensions(question, ranking)
    filters, unknown_filter = _filters(question, original)
    limits = {int(limit) for limit in re.findall(_LIMIT, question)}
    top_k = next(iter(limits)) if len(limits) == 1 else None
    sort_requested = ranking or _has(_SORT, question)
    asc, desc = _has(_ASC, question), _has(_DESC, question)
    sort = None
    if sort_requested and len(ids) == 1 and asc != desc:
        sort = {"metric_id": ids[0], "direction": "asc" if asc else "desc"}
    elif ranking and len(ids) == 1 and top_k is not None and not (asc or desc):
        sort = {"metric_id": ids[0], "direction": "desc"}

    operation = "aggregate"
    if ranking or top_k is not None:
        operation = "ranking"
    elif any(grain in dimensions for grain in _PERIOD_DIMENSIONS):
        operation = "timeseries"
    elif dimensions:
        operation = "breakdown"

    unresolved = {}
    if not ids or metric_intent != "metric":
        unresolved["metric"] = metric_intent
    if time["mode"] == "none":
        unresolved["time"] = (
            "as_of" if period_type == "snapshot" or metric_intent == "debt" else "time"
        )
    if view is None:
        unresolved["view"] = "view"
    grains = [grain for grain in _PERIOD_DIMENSIONS if grain in dimensions]
    if (
        (operation == "ranking" and not dimensions)
        or len(grains) > 1
        or _unresolved_grouping(question, sort_requested)
    ):
        unresolved["dimensions"] = "dimensions"
    elif grains and time["mode"] == "range":
        time["grain"] = grains[0]
    negated_filter = filters and _has(
        r"except|exclude|excluding|without|không (?:bao gồm|gồm|tính)|ngoại trừ|trừ|not in",
        question,
    )
    disjunctive_filters = len(filters) > 1 and _has(r"or|hoặc|hay", question)
    if unknown_filter or negated_filter or disjunctive_filters:
        unresolved["filters"] = "filters"
    if sort_requested and sort is None and "metric" not in unresolved:
        unresolved["sort"] = "sort"
    if (top_k is not None and not 1 <= top_k <= 100) or (
        ranking and _has("top|bottom", question) and top_k is None
    ):
        unresolved["top_k"] = "top_k"
        top_k = None

    reason = None
    if not unresolved:
        if _has(r"so sánh|versus|vs|compared (?:to|with)|year.over.year", question):
            reason = "unsupported_comparison"
        elif any(
            view not in cap["supported_views"]
            or not {operation, "rank" if operation == "ranking" else operation}.intersection(
                cap["supported_operations"]
            )
            or any(
                not _supported_dimension(field, cap, question)
                for field in [*dimensions, *(flt["field"] for flt in filters)]
            )
            for cap in capabilities
        ):
            reason = "incompatible_plan"

    metric_unresolved = "metric" in unresolved
    if metric_unresolved and "time" in unresolved and operation == "aggregate":
        operation = None
    return {
        "plan_version": "1.0",
        "status": "needs_clarification" if unresolved else "unsupported" if reason else "ready",
        "metric_ids": [] if metric_unresolved else ids,
        "time": time,
        "dimensions": dimensions,
        "filters": filters,
        "view": view,
        "operation": operation,
        "sort": None if metric_unresolved else sort,
        "top_k": top_k,
        "comparison": None,
        "question_for_user": " ".join(_MESSAGES[locale][key] for key in unresolved.values())
        or None,
        "unresolved_slots": list(unresolved),
        "reason_code": reason,
    }
