"""Explain the existing triage policy without inventing collection uplift or rules."""

from collections import Counter
from decimal import Decimal, InvalidOperation, localcontext

PROTOCOL = "collection-ranking-v2"
POLICIES = {
    "amount": {
        "label": "Dư nợ lớn trước",
        "formula": "Dư nợ còn phải thu",
        "score_unit": "VND",
        "uses_probability": False,
    },
    "risk": {
        "label": "Nguy cơ chưa tất toán cao trước",
        "formula": "1 − xác suất tất toán 4 tuần theo lịch sử khách",
        "score_unit": "probability",
        "uses_probability": True,
    },
    "amount_at_risk": {
        "label": "Dư nợ × nguy cơ chưa tất toán",
        "formula": "Dư nợ × (1 − xác suất tất toán 4 tuần theo lịch sử khách)",
        "score_unit": "VND",
        "uses_probability": True,
    },
}


def _score(row, policy):
    amount = Decimal(str(row["outstanding"]))
    probability = Decimal(str(row["triage_probability_4w"]))
    if (
        not amount.is_finite()
        or amount < 0
        or not probability.is_finite()
        or not 0 <= probability <= 1
    ):
        raise ValueError("Dư nợ và xác suất xếp hạng không hợp lệ")
    # 18-digit source VND and any finite float probability, including subnormals.
    # Use the probability's canonical decimal representation, as exposed by JSON.
    with localcontext() as context:
        context.prec = 400
        if policy == "amount_at_risk":
            return amount * (1 - probability)
        if policy == "risk":
            return 1 - probability
    return amount


def _number(value, unit="VND"):
    """JSON-safe exact money; probabilities remain ordinary floating estimates."""
    if unit == "probability":
        return float(value)
    if value == value.to_integral_value():
        integer = int(value)
        return integer if abs(integer) <= 2**53 - 1 else str(integer)
    return format(value, "f").rstrip("0").rstrip(".")


def _selection(policy, requested_policy, evaluation, has_serving_model):
    if requested_policy != policy:
        return {
            "status": "unknown_policy_fallback",
            "message": "Chính sách không được hỗ trợ; dùng dư nợ lớn trước.",
        }
    if not has_serving_model:
        return {
            "status": "default",
            "message": "Chưa chọn phiên bản học; dùng chính sách "
            + POLICIES[policy]["label"].lower()
            + ".",
        }
    if evaluation and evaluation.get("status") == "insufficient_history":
        if policy != "amount":
            return {
                "status": "inconsistent_audit",
                "message": "Báo cáo thiếu lịch sử nhưng phiên bản lưu chính sách khác dư nợ; cần đối chiếu lại.",
            }
        return {
            "status": "insufficient_history",
            "message": "Chưa đủ lịch sử kiểm định chính sách; dùng dư nợ lớn trước.",
        }
    if (
        evaluation
        and evaluation.get("status") == "evaluated"
        and "accepted" in evaluation
    ):
        accepted = bool(evaluation.get("accepted"))
        if not accepted and policy != "amount":
            return {
                "status": "inconsistent_audit",
                "message": "Báo cáo không chấp nhận ứng viên nhưng phiên bản vẫn lưu chính sách khác dư nợ; cần đối chiếu lại.",
            }
        return {
            "status": "evaluated",
            "accepted": accepted,
            "message": "Chính sách được giữ qua kiểm định lịch sử."
            if accepted
            else "Ứng viên không vượt mốc kiểm định; dùng dư nợ lớn trước.",
            "metric": evaluation.get("metric"),
        }
    return {
        "status": "saved_without_audit",
        "message": "Dùng chính sách lưu trong phiên bản; chưa có báo cáo kiểm định chính sách đi kèm.",
    }


def rank_with_explanations(
    rows,
    *,
    policy,
    cutoff,
    evaluation=None,
    has_serving_model=False,
    model_asof=None,
    delay_days=0,
    delay_customer=None,
    eligibility=None,
    limit=30,
):
    """Retain descending score and the original snapshot order for exact ties.

    The live triage estimator is always a separate customer-history baseline
    fitted at the forecast cutoff, without the displayed forecast's delay shift.
    Dispute/promise flags are workflow context, not extra score adjustments.
    """
    requested_policy = policy
    policy = policy if policy in POLICIES else "amount"
    spec = POLICIES[policy]
    try:
        scored = sorted(
            ((row, _score(row, policy)) for row in rows),
            key=lambda pair: pair[1],
            reverse=True,
        )
    except InvalidOperation as exc:
        raise ValueError("Điểm xếp hạng thu nợ phải hữu hạn") from exc
    ranked = [row for row, _ in scored]
    scores = [score for _, score in scored]
    ties, seen = Counter(scores), Counter()
    selection = _selection(policy, requested_policy, evaluation, has_serving_model)
    rules = [
        "Loại hóa đơn đã ghi nhận xóa nợ tại ngày dự báo.",
        "Tạm loại hóa đơn có lần liên hệ hoặc tạm bỏ qua gần nhất chưa đủ 7 ngày.",
        "Tranh chấp, lời hứa và ngày quá hạn không cộng/trừ điểm riêng.",
        "Điểm giảm dần; khi bằng điểm giữ thứ tự bản ghi trong snapshot dữ liệu.",
    ]
    meta = {
        "protocol": PROTOCOL,
        "policy": policy,
        **spec,
        "cutoff": cutoff,
        "model_asof": model_asof,
        "model_version": None,
        "selection": selection,
        "eligible_count": len(ranked),
        "displayed_count": min(limit, len(ranked)),
        "limit": limit,
        "eligibility": eligibility or {},
        "business_rules": rules,
        "limitation": "Điểm phân luồng công nợ, không phải số tiền chắc chắn mất hoặc tiền tăng thêm do liên hệ khách.",
    }
    for i, row in enumerate(ranked[:limit]):
        score = scores[i]
        seen[score] += 1
        row["outstanding"] = _number(Decimal(str(row["outstanding"])))
        row["amount_at_risk_4w"] = _number(_score(row, "amount_at_risk"))
        date = row.get("promised_date")
        promise_state = (
            "none"
            if not date
            else "overdue"
            if date < cutoff
            else "due_today"
            if date == cutoff
            else "upcoming"
        )
        shifted = bool(
            delay_days and (not delay_customer or row["customer_id"] == delay_customer)
        )
        source = {
            "method": "customer",
            "label": "Lịch sử khách hàng tại ngày dự báo",
            "asof": cutoff,
            "model_version": None,
            "scenario_shift_applied": False,
            "used_in_score": spec["uses_probability"],
            "differs_from_displayed": bool(has_serving_model or shifted),
            "detail": "Ước lượng riêng từ dữ liệu đã biết tại ngày dự báo; không áp dụng kịch bản thu chậm.",
        }
        factors = [
            {
                "feature": "outstanding",
                "label": "Dư nợ còn phải thu",
                "value": row["outstanding"],
                "unit": "VND",
                "affects_score": policy != "risk",
                "message": "Tham gia điểm ưu tiên."
                if policy != "risk"
                else "Chỉ để đối chiếu; chính sách này chỉ xếp theo nguy cơ.",
            },
            {
                "feature": "unresolved_probability_4w",
                "label": "Nguy cơ chưa tất toán trong 4 tuần",
                "value": 1 - row["triage_probability_4w"],
                "unit": "probability",
                "affects_score": spec["uses_probability"],
                "message": "Tham gia điểm từ ước lượng lịch sử khách."
                if spec["uses_probability"]
                else "Chỉ để tham khảo; chính sách dư nợ không dùng xác suất.",
            },
            {
                "feature": "overdue_days",
                "label": "Số ngày quá hạn",
                "value": row["overdue_days"],
                "unit": "ngày",
                "affects_score": False,
                "message": "Không cộng điểm riêng; tuổi hóa đơn có thể ảnh hưởng ước lượng thanh toán.",
            },
            {
                "feature": "disputed",
                "label": "Tranh chấp",
                "value": bool(row.get("disputed")),
                "unit": "boolean",
                "affects_score": False,
                "message": "Cần xử lý tranh chấp; vẫn giữ trong danh sách và không đổi điểm."
                if row.get("disputed")
                else "Chưa ghi nhận tranh chấp tại ngày dự báo.",
            },
            {
                "feature": "promised_date",
                "label": "Lời hứa trả",
                "value": date,
                "unit": "date",
                "state": promise_state,
                "reliability": row.get("promise_reliability"),
                "affects_score": False,
                "message": "Kiểm tra lời hứa đã đến hạn; không đổi điểm."
                if promise_state in ("overdue", "due_today")
                else "Theo dõi ngày hứa; chưa đến hạn và không đổi điểm."
                if promise_state == "upcoming"
                else "Chưa có lời hứa được ghi nhận.",
            },
        ]

        def peer(index, reference_score=score):
            if not 0 <= index < len(ranked):
                return None
            with localcontext() as context:
                context.prec = 400
                difference = abs(reference_score - scores[index])
            return {
                "invoice_id": ranked[index]["invoice_id"],
                "rank": index + 1,
                "score": _number(scores[index], spec["score_unit"]),
                "score_difference": _number(difference, spec["score_unit"]),
                "tied": reference_score == scores[index],
            }

        row.update(
            collection_rank=i + 1,
            priority_score=_number(score, spec["score_unit"]),
            priority_score_unit=spec["score_unit"],
            priority_policy=policy,
        )
        row["reason"] = (
            "Chờ giải quyết tranh chấp"
            if row.get("disputed")
            else "Kiểm tra lời hứa đã đến hạn"
            if promise_state in ("overdue", "due_today")
            else spec["label"]
        )
        row["ranking_explanation"] = {
            "protocol": PROTOCOL,
            "cutoff": cutoff,
            "policy": policy,
            **spec,
            "rank": i + 1,
            "eligible_count": len(ranked),
            "score": _number(score, spec["score_unit"]),
            "selection": selection,
            "probability_source": source,
            "triage_probability_4w": row["triage_probability_4w"],
            "displayed_probability_4w": row["payment_probability_4w"],
            "displayed_model_version": None,
            "factors": factors,
            "tie_break": {
                "rule": "snapshot_order",
                "group_size": ties[score],
                "position": seen[score],
            },
            "previous": peer(i - 1),
            "next": peer(i + 1),
            "business_rules": rules,
            "limitation": meta["limitation"],
        }
    return ranked[:limit], meta
