"""Case queue policy fixture, eligibility assessment, deterministic ranking, and schema checks.

D-04, D-05, D-06, and D-07 remain open governance decisions. Policies created here are
explicitly marked approved_for_production=False and do NOT modify selection_comparison.BUDGET=5.
"""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path

from finance_input.validation import FORMATS, StrictValidator

from .import_files import canonical, digest, fail

POLICY_VERSION = "case-queue-policy/1.0.0"
REPORT_VERSION = "case-queue-report/1.0.0"
BENCHMARK_TRANSACTION_CAP = 5

WORKFLOW_STATUSES = ("new", "in_review", "waiting_evidence", "closed")
CASE_RESOLUTIONS = (None, "confirmed_risk", "legitimate", "inconclusive")
ALERT_DECISIONS = (
    "selected",
    "below_threshold",
    "need_evidence",
    "budget_deferred",
    "already_notified",
    "unscorable",
    "mandatory_route",
)
DELIVERY_STATUSES = ("pending", "sent", "failed")
BACKLOG_REASONS = (
    "budget_exhausted",
    "missing_evidence",
    "below_admission_threshold",
    "current_revision_already_sent",
    "unscorable_sources",
    "pending_business_decision",
    "waiting_external_evidence",
    "case_closed_no_material_change",
)

OPEN_CASE_QUEUE_DECISIONS = {
    "D-04": {
        "decision_id": "D-04",
        "status": "OPEN",
        "topic": "Ngưỡng phân rã điểm / threshold chính thức cho case admission",
        "fixture_behavior": "min_case_score configurable trong policy fixture (approved_for_production=false).",
    },
    "D-05": {
        "decision_id": "D-05",
        "status": "OPEN",
        "topic": "Hàm tổng hợp điểm cấp vụ từ candidate scores",
        "fixture_behavior": "Sử dụng max_candidate_score theo baseline spec; evidence không cộng điểm.",
    },
    "D-06": {
        "decision_id": "D-06",
        "status": "OPEN",
        "topic": "Định nghĩa thay đổi trọng yếu và luật mở lại vụ đã đóng",
        "fixture_behavior": "Thay đổi tập candidate, rule hit, trạng thái đủ nguồn, delta tài chính hoặc delta điểm >= min_score_delta.",
    },
    "D-07": {
        "decision_id": "D-07",
        "status": "OPEN",
        "topic": "Định mức ngân sách rà soát cấp vụ theo kỳ vận hành chính thức",
        "fixture_behavior": "Ngân sách cấp vụ theo kỳ (mặc định fixture B=3 case), tách biệt khỏi BUDGET=5 của benchmark giao dịch.",
    },
}

_SCHEMA_PATH = Path(__file__).with_name("case_queue.schema.json")


@lru_cache(maxsize=1)
def load_schema() -> dict:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_against_schema(payload: dict, def_name: str | None = None) -> None:
    root = load_schema()
    if def_name:
        schema_doc = {
            "$schema": root["$schema"],
            "$defs": root["$defs"],
            "$ref": f"#/$defs/{def_name}",
        }
    else:
        schema_doc = root
    errors = list(StrictValidator(schema_doc, format_checker=FORMATS).iter_errors(payload))
    if errors:
        first = errors[0]
        path = ".".join(str(p) for p in first.path) or "$"
        fail(
            422,
            "CASE_QUEUE_SCHEMA_INVALID",
            f"Dữ liệu không khớp schema case queue tại {path}: {first.message}",
            "Kiểm tra cấu trúc hợp đồng case-queue-policy/1.0.0 hoặc coalesced_case.",
        )


def default_fixture_policy(
    *,
    budget_limit: int = 3,
    min_case_score: float = 7.0,
    min_score_delta: float = 0.25,
    mandatory_rules: tuple[str, ...] | list[str] = (),
    require_sufficient_evidence: bool = True,
    rule_weight: float = 1.0,
    ml_weight: float = 2.0,
    calibrated_weight: float = 0.0,
    allow_hard_trigger_admission: bool = True,
    auto_reopen_closed_on_material: bool = True,
    policy_id: str = "fixture-case-queue-policy",
    policy_version: str = "fixture-1.0.0",
    period_kind: str = "calendar_week_vn",
) -> dict:
    """Construct an explicit unapproved-for-production fixture policy for R3 acceptance and testing."""
    policy = {
        "version": POLICY_VERSION,
        "policy_id": str(policy_id),
        "policy_version": str(policy_version),
        "fixture_declaration": {
            "is_experimental_fixture": True,
            "approved_for_production": False,
            "open_decision_gates": ["D-04", "D-05", "D-06", "D-07"],
            "note": (
                "Cấu hình thử nghiệm/nghiệm thu R3 (approved_for_production=false). "
                "Các quyết định D-04, D-05, D-06, D-07 vẫn mở; ngân sách thử nghiệm "
                "selection_comparison.BUDGET=5 cấp giao dịch được giữ tách biệt."
            ),
        },
        "budget": {
            "unit": "case",
            "case_budget_limit": int(budget_limit),
            "period_kind": str(period_kind),
            "benchmark_transaction_cap_preserved": BENCHMARK_TRANSACTION_CAP,
            "benchmark_separated": True,
        },
        "scoring": {
            "aggregation": "max_candidate_score",
            "evidence_adds_score": False,
            "rule_weight": float(rule_weight),
            "ml_weight": float(ml_weight),
            "calibrated_weight": float(calibrated_weight),
            "min_case_score": float(min_case_score),
            "allow_hard_trigger_admission": bool(allow_hard_trigger_admission),
            "require_sufficient_evidence": bool(require_sufficient_evidence),
            "mandatory_rules": sorted({str(r) for r in mandatory_rules if str(r).strip()}),
        },
        "material_change": {
            "min_score_delta": float(min_score_delta),
            "snapshot_change_only_is_material": False,
            "ordering_change_only_is_material": False,
            "auto_reopen_closed_on_material": bool(auto_reopen_closed_on_material),
        },
        "backlog": {
            "auto_expire_backlog": False,
            "retention_without_decision_indefinite": True,
        },
    }
    validate_policy(policy)
    return policy


def approved_pilot_policy(
    *,
    budget_limit: int = 5,
    min_case_score: float = 5.0,
    min_score_delta: float = 0.25,
    mandatory_rules: tuple[str, ...] | list[str] = ("P1",),
    require_sufficient_evidence: bool = True,
    rule_weight: float = 1.0,
    ml_weight: float = 2.0,
    calibrated_weight: float = 0.0,
    allow_hard_trigger_admission: bool = True,
    auto_reopen_closed_on_material: bool = True,
    policy_id: str = "owner-pilot-active-policy-v1",
    policy_version: str = "pilot-1.0.0",
    period_kind: str = "calendar_week_vn",
    decided_at: str = "2026-11-18",
) -> dict:
    """Construct the owner-approved Pilot Active case policy (D-04, D-05, D-06, D-07 locked 2026-11-18)."""
    policy = {
        "version": POLICY_VERSION,
        "policy_id": str(policy_id),
        "policy_version": str(policy_version),
        "fixture_declaration": {
            "is_experimental_fixture": False,
            "approved_for_production": True,
            "open_decision_gates": [],
            "owner_governance": {
                "decided_at": str(decided_at),
                "scope": "internal_pilot_active",
                "closed_decisions": ["D-04", "D-05", "D-06", "D-07"],
                "pilot_gate": "D-09-pilot-v1",
            },
            "note": (
                "Chính sách cấp vụ Pilot Active đã chốt chủ sở hữu (D-04: rule_weight=1.0, ml_weight=2.0, "
                "min_case_score=5.0; D-05: max_candidate_score không cộng điểm bằng chứng; D-06: B=5 vụ/tuần lịch VN, "
                "backlog không tự hết hạn; D-07: mandatory_rules=['P1']). Tách biệt khỏi BUDGET=5 của benchmark kỹ thuật."
            ),
        },
        "budget": {
            "unit": "case",
            "case_budget_limit": int(budget_limit),
            "period_kind": str(period_kind),
            "benchmark_transaction_cap_preserved": BENCHMARK_TRANSACTION_CAP,
            "benchmark_separated": True,
        },
        "scoring": {
            "aggregation": "max_candidate_score",
            "evidence_adds_score": False,
            "rule_weight": float(rule_weight),
            "ml_weight": float(ml_weight),
            "calibrated_weight": float(calibrated_weight),
            "min_case_score": float(min_case_score),
            "allow_hard_trigger_admission": bool(allow_hard_trigger_admission),
            "require_sufficient_evidence": bool(require_sufficient_evidence),
            "mandatory_rules": sorted({str(r) for r in mandatory_rules if str(r).strip()}),
        },
        "material_change": {
            "min_score_delta": float(min_score_delta),
            "snapshot_change_only_is_material": False,
            "ordering_change_only_is_material": False,
            "auto_reopen_closed_on_material": bool(auto_reopen_closed_on_material),
        },
        "backlog": {
            "auto_expire_backlog": False,
            "retention_without_decision_indefinite": True,
        },
    }
    validate_policy(policy)
    return policy


def validate_policy(policy: dict) -> dict:
    if not isinstance(policy, dict):
        fail(422, "POLICY_INVALID", "Policy phải là JSON object.", "Dùng default_fixture_policy() hoặc approved_pilot_policy().")
    validate_against_schema(policy, "policy")
    decl = policy["fixture_declaration"]
    if decl["approved_for_production"] is True:
        gov = decl.get("owner_governance") or {}
        if (
            decl.get("is_experimental_fixture") is not False
            or decl.get("open_decision_gates") != []
            or sorted(gov.get("closed_decisions") or []) != ["D-04", "D-05", "D-06", "D-07"]
            or gov.get("scope") != "internal_pilot_active"
            or gov.get("pilot_gate") != "D-09-pilot-v1"
        ):
            fail(
                422,
                "POLICY_GOVERNANCE_LOCKED",
                "Policy active bắt buộc đính kèm chứng nhận quản trị chủ sở hữu đầy đủ cho D-04..D-07 và D-09 pilot.",
                "Dùng approved_pilot_policy() hoặc giữ approved_for_production=false cho fixture.",
            )
    elif decl["approved_for_production"] is not False:
        fail(
            422,
            "POLICY_GOVERNANCE_LOCKED",
            "Chưa được bật approved_for_production=true khi D-04/D-05/D-06/D-07 chưa chốt.",
            "Giữ approved_for_production=false trên cấu hình fixture.",
        )
    if policy["budget"]["benchmark_transaction_cap_preserved"] != BENCHMARK_TRANSACTION_CAP:
        fail(
            422,
            "BENCHMARK_CAP_MISMATCH",
            "Không được ghi đè ngưỡng thử nghiệm BUDGET=5 giao dịch.",
            "Giữ benchmark_transaction_cap_preserved=5.",
        )
    return deepcopy(policy)


def policy_hash(policy: dict) -> str:
    return digest(canonical(policy))


def assess_case_eligibility(
    case: dict,
    *,
    existing_state: dict | None = None,
    delivery_match: dict | None = None,
    material_eval: dict | None = None,
    policy: dict,
) -> dict:
    """Classify a single coalesced case prior to atomic period budget reservation.

    Enforces deterministic precedence:
      1. Delivered non-material / matching ledger -> already_notified
      2. Closed case without permitted material reopen -> already_notified (case_closed_no_material_change)
      3. Manual waiting_evidence hold -> need_evidence (waiting_external_evidence)
      4. Unscorable sources -> unscorable (unscorable_sources)
      5. Blocking source gap or insufficient evidence -> need_evidence (missing_evidence)
      6. Fixture mandatory route override -> eligible (mandatory_route)
      7. Hard trigger (if permitted) or case_score >= min_case_score -> eligible (selected)
      8. Otherwise -> below_threshold (below_admission_threshold), never top-B padded
    """
    state = existing_state or {}
    workflow_status = state.get("case_workflow_status")
    has_prior_delivery = delivery_match is not None or bool(state.get("last_delivered_fingerprint"))
    is_material = bool(material_eval.get("is_material_change", True)) if material_eval is not None else True

    if delivery_match is not None or (has_prior_delivery and not is_material):
        reason_code = (
            "case_closed_no_material_change"
            if workflow_status == "closed"
            else "current_revision_already_sent"
        )
        return {
            "decision": "already_notified",
            "initial_decision": "already_notified",
            "eligible_for_budget": False,
            "is_mandatory": False,
            "reopen_closed": False,
            "in_backlog": False,
            "backlog_reason_code": reason_code,
            "reason_detail": (
                "Vụ việc đã đóng và không có thay đổi trọng yếu."
                if workflow_status == "closed"
                else "Fingerprint trọng yếu hiện tại đã được gửi trước đó; bỏ qua gửi trùng."
            ),
        }

    auto_reopen = bool(policy["material_change"]["auto_reopen_closed_on_material"])
    if workflow_status == "closed":
        if not is_material or not auto_reopen:
            return {
                "decision": "already_notified",
                "initial_decision": "already_notified",
                "eligible_for_budget": False,
                "is_mandatory": False,
                "reopen_closed": False,
                "in_backlog": workflow_status == "closed" and is_material and not auto_reopen,
                "backlog_reason_code": (
                    "pending_business_decision"
                    if (is_material and not auto_reopen)
                    else "case_closed_no_material_change"
                ),
                "reason_detail": (
                    "Vụ việc đã đóng có biến động nhưng policy fixture tắt tự động mở lại."
                    if (is_material and not auto_reopen)
                    else "Vụ việc đã đóng; không có thay đổi trọng yếu nên không mở lại."
                ),
            }

    reopen_closed = workflow_status == "closed" and is_material and auto_reopen

    if workflow_status == "waiting_evidence" and state.get("manual_waiting_hold"):
        # Manual hold stays in waiting_evidence until explicitly cleared or re-evaluated with supplemental evidence.
        if not state.get("supplemental_cleared"):
            return {
                "decision": "need_evidence",
                "initial_decision": "need_evidence",
                "eligible_for_budget": False,
                "is_mandatory": False,
                "reopen_closed": False,
                "in_backlog": True,
                "backlog_reason_code": "waiting_external_evidence",
                "reason_detail": "Vụ việc đang tạm giữ ở trạng thái chờ bổ sung chứng từ ngoài.",
            }

    if not case.get("scorable"):
        return {
            "decision": "unscorable",
            "initial_decision": "unscorable",
            "eligible_for_budget": False,
            "is_mandatory": False,
            "reopen_closed": reopen_closed,
            "in_backlog": True,
            "backlog_reason_code": "unscorable_sources",
            "reason_detail": "Thiếu hoặc hỏng dữ liệu chấm điểm nên không thể đánh giá vụ việc.",
        }

    require_ev = bool(policy["scoring"]["require_sufficient_evidence"])
    has_gap = bool(case.get("has_blocking_source_gap")) or not bool(case.get("evidence_sufficient"))
    if require_ev and has_gap:
        return {
            "decision": "need_evidence",
            "initial_decision": "need_evidence",
            "eligible_for_budget": False,
            "is_mandatory": False,
            "reopen_closed": reopen_closed,
            "in_backlog": True,
            "backlog_reason_code": "missing_evidence",
            "reason_detail": "Thiếu nguồn đối chiếu hoặc bằng chứng bắt buộc cho vụ việc.",
        }

    mandatory_rules = set(policy["scoring"].get("mandatory_rules") or [])
    case_rules = set(case.get("actionable_rule_ids") or [])
    matched_mandatory = sorted(mandatory_rules & case_rules)
    if matched_mandatory:
        return {
            "decision": "mandatory_route",
            "initial_decision": "mandatory_route",
            "eligible_for_budget": True,
            "is_mandatory": True,
            "reopen_closed": reopen_closed,
            "in_backlog": False,
            "backlog_reason_code": None,
            "reason_detail": f"Chuyển thẳng theo cấu hình fixture mandatory_rules: {', '.join(matched_mandatory)}.",
        }

    score = case.get("case_score")
    min_score = float(policy["scoring"]["min_case_score"])
    allow_hard = bool(policy["scoring"]["allow_hard_trigger_admission"])
    hard_trigger = bool(case.get("hard_trigger"))

    if (allow_hard and hard_trigger) or (score is not None and float(score) >= min_score):
        return {
            "decision": "selected",
            "initial_decision": "selected",
            "eligible_for_budget": True,
            "is_mandatory": False,
            "reopen_closed": reopen_closed,
            "in_backlog": False,
            "backlog_reason_code": None,
            "reason_detail": (
                "Đạt ngưỡng tiếp nhận theo hard_trigger."
                if (allow_hard and hard_trigger and (score is None or float(score) < min_score))
                else f"Đạt ngưỡng điểm vụ việc ({score:.4g} >= {min_score:.4g})."
            ),
        }

    return {
        "decision": "below_threshold",
        "initial_decision": "below_threshold",
        "eligible_for_budget": False,
        "is_mandatory": False,
        "reopen_closed": False,
        "in_backlog": True,
        "backlog_reason_code": "below_admission_threshold",
        "reason_detail": f"Điểm vụ việc ({score}) chưa đạt ngưỡng tối thiểu ({min_score}); không tự đôn cho đủ ngân sách.",
    }


def case_priority_key(case: dict, admission: dict) -> tuple:
    """Deterministic total order for allocating finite case budget."""
    score = float(case["case_score"]) if case.get("case_score") is not None else -1.0
    return (
        0 if admission.get("is_mandatory") else 1,
        0 if case.get("hard_trigger") else 1,
        -score,
        str(case.get("first_candidate_event_at") or ""),
        str(case["case_id"]),
    )

