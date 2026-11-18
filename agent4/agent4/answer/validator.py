"""Check drafts against verified SQL result cells for numeric, sign, and citation grounding."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from agent4.core.catalog import MetricCatalog
from agent4.core.errors import ContractError, enforce_exact_keys
from agent4.planning.validator import ValidatedPlan

from .generator import generate_grounded_answer
from .result_validator import safe_display_text

_STAGE = "answer_validation"
_DRAFT_KEYS = {"summary", "claims", "warnings", "table_caption"}
_CLAIM_KEYS = {"text", "source_columns", "source_rows"}
_SPECULATION_RE = re.compile(
    r"\b(?:because of|due to|caused by|tăng đột biến do|giảm đột biến do|"
    r"nguyên nhân do|sự kiện ra mắt)\b",
    re.IGNORECASE,
)
_DATE_SPAN_RE = re.compile(
    r"\b(?:"
    r"(?:19|20)\d{2}[-/](?:0?[1-9]|1[0-2])(?:[-/](?:0?[1-9]|[12]\d|3[01]))?"
    r"|(?:0?[1-9]|[12]\d|3[01])[/-](?:0?[1-9]|1[0-2])[/-](?:19|20)\d{2}"
    r"|(?:quý|q)\s*[1-4]\s*[/-]?\s*(?:19|20)\d{2}"
    r"|(?:tháng|t)\s*(?:0?[1-9]|1[0-2])\s*[/-]?\s*(?:19|20)\d{2}"
    r"|(?:0?[1-9]|1[0-2])[/-](?:19|20)\d{2}"
    r"|(?:năm|fy)\s+(?:19|20)\d{2}"
    r")\b",
    re.IGNORECASE,
)
_VI_SCALES = {
    "tỉ": Decimal(10**9),
    "tỷ": Decimal(10**9),
    "triệu": Decimal(10**6),
    "nghìn": Decimal(10**3),
    "ngàn": Decimal(10**3),
}
_VI_COMPOUND_MONEY_RE = re.compile(
    r"(?P<approx1>\b(?:khoảng|xấp\s+xỉ|ước(?:\s+tính)?)\s+|~\s*)?"
    r"(?P<neg1>(?:\b(?:âm|lỗ)\s+|[-−]\s*))"
    r"?(?P<approx2>\b(?:khoảng|xấp\s+xỉ|ước(?:\s+tính)?)\s+|~\s*)?"
    r"(?P<neg2>(?:\b(?:âm|lỗ)\s+|[-−]\s*))?"
    r"(?P<body>"
    r"(?:\d{1,3}(?:\.\d{3})*|\d+)(?:,\d+)?\s*(?:tỉ|tỷ|triệu|nghìn|ngàn)"
    r"(?:\s+(?:\d{1,3}(?:\.\d{3})*|\d+)(?:,\d+)?\s*(?:tỉ|tỷ|triệu|nghìn|ngàn))*"
    r"(?:\s+(?:lẻ\s+)?\d+(?:,\d+)?)?"
    r"(?:\s*(?:đồng|vnd)\b)?"
    r")",
    re.IGNORECASE,
)
_VI_PLAIN_DONG_RE = re.compile(
    r"(?P<approx>\b(?:khoảng|xấp\s+xỉ|ước(?:\s+tính)?)\s+|~\s*)?"
    r"(?P<neg>(?:\b(?:âm|lỗ)\s+|[-−]\s*))?"
    r"(?P<num>\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:[.,]\d+)?)\s*(?:đồng|vnd)\b",
    re.IGNORECASE,
)
_RAW_NUMBER_RE = re.compile(
    r"(?P<approx>\b(?:approximately|approx\.?|around|about|khoảng|xấp\s+xỉ)\s+|~\s*)?"
    r"(?P<neg>(?:\b(?:âm|lỗ|minus|negative)\s+|(?<![A-Za-z0-9])[-−]\s*))?"
    r"(?P<num>\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:[.,]\d+)?)"
    r"(?!\w)",
    re.IGNORECASE,
)
_VI_PART_RE = re.compile(
    r"(?P<num>(?:\d{1,3}(?:\.\d{3})*|\d+)(?:,\d+)?)\s*(?P<unit>tỉ|tỷ|triệu|nghìn|ngàn)",
    re.IGNORECASE,
)
_VI_REM_RE = re.compile(r"(?:lẻ\s+)?(?P<rem>\d+(?:,\d+)?)\s*(?:(?:đồng|vnd)\b)?$", re.IGNORECASE)


def _parse_vi_decimal(raw: str) -> tuple[Decimal, int]:
    """Parse a Vietnamese number token ('1.234,56' or '666,4') -> (Decimal, frac_digits)."""
    if "," in raw:
        whole, frac = raw.split(",", 1)
        whole = whole.replace(".", "")
        return Decimal(f"{whole}.{frac}"), len(frac)
    return Decimal(raw.replace(".", "")), 0


def _parse_any_decimal(raw: str) -> tuple[Decimal, int]:
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?", raw):
        return _parse_vi_decimal(raw)
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", raw):
        cleaned = raw.replace(",", "")
        frac = len(cleaned.split(".", 1)[1]) if "." in cleaned else 0
        return Decimal(cleaned), frac
    if "," in raw and "." not in raw:
        whole, frac = raw.split(",", 1)
        return Decimal(f"{whole}.{frac}"), len(frac)
    frac = len(raw.split(".", 1)[1]) if "." in raw else 0
    return Decimal(raw), frac


def _extract_mentions(
    text: str, ignore_literals: set[str]
) -> list[tuple[Decimal, int, bool, Decimal]]:
    """Extract (signed_value, sign, is_approx, tolerance) from natural-language text.

    sign is -1 if explicitly marked negative ('-', 'âm', 'lỗ'), +1 if positive, 0 if zero.
    """
    working = text
    for literal in sorted(ignore_literals, key=len, reverse=True):
        if literal:
            working = working.replace(literal, " ")
    working = _DATE_SPAN_RE.sub(" ", working)

    mentions: list[tuple[Decimal, int, bool, Decimal]] = []

    def _consume_compound(match: re.Match[str]) -> str:
        is_approx = bool(match.group("approx1") or match.group("approx2"))
        is_neg = bool(match.group("neg1") or match.group("neg2"))
        body = match.group("body")
        total = Decimal(0)
        smallest_ulp = Decimal(1)
        last_end = 0
        for part in _VI_PART_RE.finditer(body):
            val, frac_digits = _parse_vi_decimal(part.group("num"))
            scale = _VI_SCALES[part.group("unit").casefold()]
            total += val * scale
            smallest_ulp = scale * (Decimal(10) ** (-frac_digits))
            last_end = part.end()
        tail = body[last_end:].strip()
        if tail and not re.fullmatch(r"(?:đồng|vnd)", tail, re.IGNORECASE):
            rem_match = _VI_REM_RE.search(tail)
            if rem_match:
                rem_val, rem_frac = _parse_vi_decimal(rem_match.group("rem"))
                total += rem_val
                smallest_ulp = Decimal(10) ** (-rem_frac)
        sign = 0 if total == 0 else (-1 if is_neg else 1)
        signed = -total if is_neg and total != 0 else total
        tol = smallest_ulp * Decimal("0.55") if is_approx else Decimal(0)
        mentions.append((signed, sign, is_approx, tol))
        return " " * (match.end() - match.start())

    working = _VI_COMPOUND_MONEY_RE.sub(_consume_compound, working)

    def _consume_plain_dong(match: re.Match[str]) -> str:
        is_approx = bool(match.group("approx"))
        is_neg = bool(match.group("neg"))
        val, frac_digits = _parse_any_decimal(match.group("num"))
        sign = 0 if val == 0 else (-1 if is_neg else 1)
        signed = -val if is_neg and val != 0 else val
        ulp = Decimal(10) ** (-frac_digits)
        tol = ulp * Decimal("0.55") if is_approx else Decimal(0)
        mentions.append((signed, sign, is_approx, tol))
        return " " * (match.end() - match.start())

    working = _VI_PLAIN_DONG_RE.sub(_consume_plain_dong, working)

    for match in _RAW_NUMBER_RE.finditer(working):
        is_approx = bool(match.group("approx"))
        is_neg = bool(match.group("neg"))
        try:
            val, frac_digits = _parse_any_decimal(match.group("num"))
        except InvalidOperation:
            continue
        sign = 0 if val == 0 else (-1 if is_neg else 1)
        signed = -val if is_neg and val != 0 else val
        ulp = Decimal(10) ** (-frac_digits)
        tol = ulp * Decimal("0.55") if is_approx else Decimal(0)
        mentions.append((signed, sign, is_approx, tol))

    return mentions


def _matches_ground_truth(mention: tuple[Decimal, int, bool, Decimal], gt: Decimal) -> bool:
    signed_val, sign, is_approx, tol = mention
    if gt == 0:
        return signed_val == 0
    # Strict sign consistency: a negative SQL figure (< 0) can NEVER be cited as positive!
    expected_sign = -1 if gt < 0 else 1
    if sign != expected_sign:
        return False
    if signed_val == gt:
        return True
    return bool(is_approx and abs(signed_val - gt) <= tol)


def _verify_draft(
    draft: Any,
    validated_result: dict[str, Any],
    plan: ValidatedPlan,
) -> bool:
    if not isinstance(draft, dict):
        return False
    try:
        enforce_exact_keys(draft, _DRAFT_KEYS, stage=_STAGE)
    except ContractError:
        return False

    summary = draft.get("summary")
    claims = draft.get("claims")
    warnings = draft.get("warnings")
    caption = draft.get("table_caption")
    if (
        not isinstance(summary, str)
        or not summary.strip()
        or not isinstance(claims, list)
        or not isinstance(warnings, list)
        or any(not isinstance(w, str) for w in warnings)
        or (caption is not None and not isinstance(caption, str))
    ):
        return False

    required_warnings = set(validated_result.get("warnings") or ())
    if not required_warnings.issubset(set(warnings)):
        return False

    if safe_display_text(summary) == "[REDACTED]":
        return False
    if caption is not None and safe_display_text(caption) == "[REDACTED]":
        return False
    if _SPECULATION_RE.search(summary):
        return False

    result = validated_result["result"]
    rows = result["rows"]
    watermark = result.get("data_watermark") or ""
    if "partial_data_watermark" in required_warnings and watermark and watermark not in summary:
        return False

    string_cols = [col["key"] for col in result["columns"] if col["type"] == "string"]
    allowed_metrics = set(plan.metric_ids)

    if not rows:
        if claims:
            return False
        return not _extract_mentions(summary, {watermark})

    if not claims:
        return False

    all_cited_gts: list[Decimal] = []
    global_ignores: set[str] = {watermark}
    for row in rows[:5]:
        for scol in string_cols:
            if isinstance(row.get(scol), str):
                global_ignores.add(row[scol])
                global_ignores.add(safe_display_text(row[scol]))

    for claim in claims:
        if not isinstance(claim, dict):
            return False
        try:
            enforce_exact_keys(claim, _CLAIM_KEYS, stage=_STAGE)
        except ContractError:
            return False
        text = claim.get("text")
        src_cols = claim.get("source_columns")
        src_rows = claim.get("source_rows")
        if (
            not isinstance(text, str)
            or not text.strip()
            or safe_display_text(text) == "[REDACTED]"
            or _SPECULATION_RE.search(text)
            or not isinstance(src_cols, list)
            or not src_cols
            or any(not isinstance(c, str) or c not in allowed_metrics for c in src_cols)
            or not isinstance(src_rows, list)
            or not src_rows
            or any(type(r) is not int or not 0 <= r < len(rows) for r in src_rows)
        ):
            return False

        claim_ignores = set(global_ignores)
        claim_gts: list[Decimal] = []
        has_null = False
        for r_idx in src_rows:
            row = rows[r_idx]
            for scol in string_cols:
                if isinstance(row.get(scol), str):
                    claim_ignores.add(row[scol])
                    claim_ignores.add(safe_display_text(row[scol]))
            for col in src_cols:
                raw_cell = row.get(col)
                if raw_cell is None:
                    has_null = True
                else:
                    try:
                        gt_dec = Decimal(str(raw_cell))
                    except InvalidOperation:
                        return False
                    claim_gts.append(gt_dec)
                    all_cited_gts.append(gt_dec)

        mentions = _extract_mentions(text, claim_ignores)
        if not claim_gts:
            if mentions:
                return False
            if has_null and not re.search(
                r"không xác định|undefined|n/a|null", text, re.IGNORECASE
            ):
                return False
            continue

        if not mentions:
            return False
        # Every numeric mention in the claim must match a cited SQL cell (value AND sign!)
        if any(not any(_matches_ground_truth(m, gt) for gt in claim_gts) for m in mentions):
            return False
        # Every cited non-null SQL cell must be represented in the claim
        if any(not any(_matches_ground_truth(m, gt) for m in mentions) for gt in claim_gts):
            return False

    # Also verify EVERY numeric mention across the full summary (prevents smuggling an ungrounded
    # number or flipping the sign in parenthetical prose outside/around claim text!)
    for row in rows:
        for col in plan.metric_ids:
            if row.get(col) is not None:
                try:
                    gt_dec = Decimal(str(row[col]))
                    if gt_dec not in all_cited_gts:
                        all_cited_gts.append(gt_dec)
                except InvalidOperation:
                    return False

    summary_mentions = _extract_mentions(summary, global_ignores)
    if not all_cited_gts:
        if summary_mentions:
            return False
    else:
        if not summary_mentions:
            return False
        if any(
            not any(_matches_ground_truth(m, gt) for gt in all_cited_gts) for m in summary_mentions
        ):
            return False

    return True


def validate_answer(
    draft: dict,
    validated_result: dict,
    plan: ValidatedPlan,
    catalog: MetricCatalog,
    *,
    locale: str = "vi-VN",
    fallback_on_failure: bool = True,
) -> dict:
    is_valid = _verify_draft(draft, validated_result, plan)
    if not is_valid:
        if not fallback_on_failure:
            raise ContractError("ungrounded_answer", _STAGE, "Answer failed grounding.")
        expected = generate_grounded_answer(plan, validated_result, catalog, locale=locale)
        return {
            "status": "valid",
            "answer": expected["summary"],
            "warnings": expected["warnings"],
            "validated_claims": [{**claim, "verified": True} for claim in expected["claims"]],
            "used_fallback": True,
        }
    return {
        "status": "valid",
        "answer": safe_display_text(draft["summary"]),
        "warnings": list(draft["warnings"]),
        "validated_claims": [
            {**claim, "text": safe_display_text(claim["text"]), "verified": True}
            for claim in draft["claims"]
        ],
        "used_fallback": False,
    }
