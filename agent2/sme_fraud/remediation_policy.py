"""Versioned DocumentRequirementPolicy, DocumentChecklist evaluation, multi-payment Reconciliation, and Draft 2020-12 schema checks.

D-08 and D-14 remain OPEN governance decisions: policies supplied here declare
approved_for_production=False, avoid arbitrary hardcoded SLA defaults (e.g., 7 days),
and separate rule/snapshot evidence from human verification.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from functools import lru_cache
import json
from pathlib import Path
from typing import Any

from finance_input.validation import FORMATS, StrictValidator

from .import_files import canonical, digest, fail

POLICY_SCHEMA_VERSION = "document_requirement_policy/1.0.0"
CHECKLIST_SCHEMA_VERSION = "document_checklist/1.0.0"
DOCUMENT_SCHEMA_VERSION = "evidence_document/1.0.0"
TASK_SCHEMA_VERSION = "action_task/1.0.0"
RECONCILIATION_SCHEMA_VERSION = "reconciliation_report/1.0.0"
BUSINESS_REPORT_SCHEMA_VERSION = "remediation_business_report/1.0.0"

CHECKLIST_ITEM_STATUSES = (
    "present",
    "missing",
    "pending_verification",
    "not_applicable",
    "unknown",
)
DOC_VERIFICATION_STATUSES = ("pending_verification", "present", "rejected")
ACTION_TASK_STATUSES = ("open", "in_progress", "waiting_external", "completed", "cancelled")
RECONCILIATION_STATUSES = (
    "matched",
    "partially_paid",
    "overpaid",
    "unmatched",
    "disputed",
    "unavailable",
)
ISSUE_TYPES = (
    "data_issue",
    "missing_document",
    "payment_discrepancy",
    "process_exception",
    "unexplained_anomaly",
)
ALLOWED_DOCUMENT_MIMES = ("application/pdf", "image/png", "image/jpeg")
MAX_DOCUMENT_BYTES = 2 * 1024 * 1024  # 2 MiB (matches ReviewStore MAX_ATT)

CHECKLIST_ITEM_STATUS_LABELS_VI = {
    "unknown": "Chưa có nguồn kiểm tra",
    "missing": "Đã xác nhận thiếu",
    "pending_verification": "Đã nhận, chưa xác minh",
    "present": "Đã xác minh",
    "not_applicable": "Không áp dụng",
}

ACTION_TASK_STATUS_LABELS_VI = {
    "open": "Mở mới",
    "in_progress": "Đang xử lý",
    "waiting_external": "Chờ bổ sung bên ngoài",
    "completed": "Đã hoàn tất",
    "cancelled": "Đã hủy",
}

OPEN_REMEDIATION_DECISIONS = {
    "D-08": {
        "decision_id": "D-08",
        "status": "OPEN",
        "topic": "Chuẩn nhãn kiểm định ML (ReviewLabel target/approval) độc lập với luồng xử lý khắc phục",
        "fixture_behavior": "Xác nhận hoàn tất ActionTask hoặc đóng vụ KHÔNG tự sinh ReviewLabel 0/1.",
    },
    "D-14": {
        "decision_id": "D-14",
        "status": "OPEN",
        "topic": "Chính sách hồ sơ bắt buộc theo loại vấn đề, SLA/hạn mặc định và thẩm quyền hoàn tất ActionTask",
        "fixture_behavior": "Dùng policy fixture theo từng nhóm vấn đề (approved_for_production=false); không tự bịa SLA mặc định (due_at do người giao việc nhập kèm múi giờ hoặc để null).",
    },
}

_SCHEMA_PATH = Path(__file__).with_name("remediation.schema.json")


@lru_cache(maxsize=1)
def load_schema() -> dict:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_against_schema(payload: dict, def_name: str) -> None:
    root = load_schema()
    schema_doc = {
        "$schema": root["$schema"],
        "$defs": root["$defs"],
        "$ref": f"#/$defs/{def_name}",
    }
    errors = list(StrictValidator(schema_doc, format_checker=FORMATS).iter_errors(payload))
    if errors:
        first = errors[0]
        path = ".".join(str(p) for p in first.path) or "$"
        fail(
            422,
            "REMEDIATION_SCHEMA_INVALID",
            f"Dữ liệu không khớp hợp đồng {def_name} tại {path}: {first.message}",
            "Kiểm tra các trường bắt buộc và enum trong remediation.schema.json.",
        )


def parse_iso_datetime(value: str | None, *, field_name: str = "datetime") -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        fail(422, "INVALID_DATETIME", f"Trường thời gian {field_name} phải là chuỗi ISO 8601 có múi giờ.", "Ví dụ: 2026-11-20T17:00:00+07:00.")
    raw = value.strip()
    if raw.endswith("Z"):
        raw_norm = raw[:-1] + "+00:00"
    else:
        raw_norm = raw
    try:
        dt = datetime.fromisoformat(raw_norm)
    except ValueError as exc:
        fail(422, "INVALID_DATETIME", f"Không đọc được thời gian ISO 8601 ở {field_name}: {value}.", "Dùng định dạng YYYY-MM-DDTHH:MM:SS+07:00.")
        raise exc
    if dt.tzinfo is None:
        fail(422, "TIMEZONE_REQUIRED", f"Trường {field_name} bắt buộc kèm múi giờ (timezone offset hoặc Z).", "Không dùng datetime naive.")
    return dt


def policy_hash(policy: dict) -> str:
    return digest(canonical(policy))


def default_document_requirement_policy(
    *,
    policy_id: str = "rem-policy-fixture-v1",
    policy_version: str = "1.0.0",
    effective_from: str = "2026-11-01T00:00:00+07:00",
) -> dict:
    """Return explicit non-production DocumentRequirementPolicy varied by problem family & rule."""
    policy = {
        "schema_version": POLICY_SCHEMA_VERSION,
        "policy_id": policy_id,
        "policy_version": policy_version,
        "effective_from": effective_from,
        "approved_for_production": False,
        "open_decision_gates": ["D-08", "D-14"],
        "sla_policy": {
            "default_due_days": None,
            "due_at_source": "explicit_or_null",
            "note": "D-14 OPEN: hệ thống không tự đặt hạn mặc định 7 ngày; due_at phải do người tạo/giao việc nhập rõ kèm múi giờ hoặc để null.",
        },
        "families": {
            "payment_invoice": {
                "family_label_vi": "Thanh toán & đối chiếu hóa đơn công nợ",
                "default_issue_type": "payment_discrepancy",
                "default_assignee_role": "ke_toan_cong_no",
                "requirements": [
                    {
                        "document_type": "invoice",
                        "title_vi": "Hóa đơn VAT / chứng từ công nợ gốc",
                        "requirement_level": "required",
                        "applicable_when": ["always"],
                        "required_sources": ["invoices"],
                        "requires_verification": True,
                        "blocks_task_completion_when_missing": True,
                    },
                    {
                        "document_type": "payment_allocation",
                        "title_vi": "Bảng phân bổ thanh toán theo hóa đơn",
                        "requirement_level": "required",
                        "applicable_when": ["always"],
                        "required_sources": ["payment_allocations", "bank_transactions"],
                        "requires_verification": True,
                        "blocks_task_completion_when_missing": True,
                    },
                    {
                        "document_type": "bank_transfer_receipt",
                        "title_vi": "Ủy nhiệm chi / sao kê chuyển khoản ngân hàng",
                        "requirement_level": "required",
                        "applicable_when": ["always"],
                        "required_sources": ["bank_transactions"],
                        "requires_verification": True,
                        "blocks_task_completion_when_missing": True,
                    },
                    {
                        "document_type": "credit_or_adjustment_note",
                        "title_vi": "Biên bản bù trừ / hoàn tiền / điều chỉnh hóa đơn",
                        "requirement_level": "conditional",
                        "applicable_when": ["overpaid_or_multiple_payments", "has_refund_or_adjustment"],
                        "required_sources": ["payment_allocations", "credit_notes"],
                        "requires_verification": True,
                        "blocks_task_completion_when_missing": True,
                    },
                    {
                        "document_type": "counterparty_reconciliation",
                        "title_vi": "Biên bản đối chiếu công nợ với nhà cung cấp",
                        "requirement_level": "conditional",
                        "applicable_when": ["overpaid_or_multiple_payments", "disputed"],
                        "required_sources": ["vendor_statements"],
                        "requires_verification": True,
                        "blocks_task_completion_when_missing": False,
                    },
                ],
            },
            "payroll_entitlement": {
                "family_label_vi": "Lương, phụ cấp & chế độ nhân sự",
                "default_issue_type": "process_exception",
                "default_assignee_role": "nhan_su_tien_luong",
                "requirements": [
                    {
                        "document_type": "hr_employment_record",
                        "title_vi": "Hồ sơ nhân sự / hợp đồng lao động còn hiệu lực",
                        "requirement_level": "required",
                        "applicable_when": ["always"],
                        "required_sources": ["employees"],
                        "requires_verification": True,
                        "blocks_task_completion_when_missing": True,
                    },
                    {
                        "document_type": "payroll_entitlement_decision",
                        "title_vi": "Quyết định hưởng chế độ / bảng định mức kỳ",
                        "requirement_level": "required",
                        "applicable_when": ["always"],
                        "required_sources": ["payroll_entitlements"],
                        "requires_verification": True,
                        "blocks_task_completion_when_missing": True,
                    },
                    {
                        "document_type": "timesheet_approval",
                        "title_vi": "Bảng chấm công đã ký duyệt",
                        "requirement_level": "required",
                        "applicable_when": ["always"],
                        "required_sources": ["timesheets"],
                        "requires_verification": True,
                        "blocks_task_completion_when_missing": True,
                    },
                    {
                        "document_type": "payroll_sheet",
                        "title_vi": "Bảng tính lương / phụ cấp chi tiết theo kỳ",
                        "requirement_level": "required",
                        "applicable_when": ["always"],
                        "required_sources": ["payroll_items"],
                        "requires_verification": True,
                        "blocks_task_completion_when_missing": True,
                    },
                    {
                        "document_type": "payroll_payment_voucher",
                        "title_vi": "Chứng từ chi lương / ủy nhiệm chi ngân hàng",
                        "requirement_level": "required",
                        "applicable_when": ["always"],
                        "required_sources": ["bank_transactions"],
                        "requires_verification": True,
                        "blocks_task_completion_when_missing": True,
                    },
                ],
            },
            "advance_lifecycle": {
                "family_label_vi": "Tạm ứng & thanh toán hoàn ứng",
                "default_issue_type": "missing_document",
                "default_assignee_role": "ke_toan_thanh_toan",
                "requirements": [
                    {
                        "document_type": "advance_request",
                        "title_vi": "Giấy đề nghị tạm ứng được phê duyệt",
                        "requirement_level": "required",
                        "applicable_when": ["always"],
                        "required_sources": ["advance_requests"],
                        "requires_verification": True,
                        "blocks_task_completion_when_missing": True,
                    },
                    {
                        "document_type": "advance_disbursement",
                        "title_vi": "Chứng từ chi tạm ứng",
                        "requirement_level": "required",
                        "applicable_when": ["always"],
                        "required_sources": ["bank_transactions"],
                        "requires_verification": True,
                        "blocks_task_completion_when_missing": True,
                    },
                    {
                        "document_type": "advance_settlement",
                        "title_vi": "Bảng thanh toán hoàn ứng & hóa đơn đính kèm",
                        "requirement_level": "required",
                        "applicable_when": ["always"],
                        "required_sources": ["advance_settlements"],
                        "requires_verification": True,
                        "blocks_task_completion_when_missing": True,
                    },
                ],
            },
            "vendor_bank_identity": {
                "family_label_vi": "Định danh nhà cung cấp & tài khoản thụ hưởng",
                "default_issue_type": "process_exception",
                "default_assignee_role": "kiem_soat_noi_bo",
                "requirements": [
                    {
                        "document_type": "vendor_master_kyc",
                        "title_vi": "Hồ sơ định danh nhà cung cấp / ĐKKD",
                        "requirement_level": "required",
                        "applicable_when": ["always"],
                        "required_sources": ["vendors"],
                        "requires_verification": True,
                        "blocks_task_completion_when_missing": True,
                    },
                    {
                        "document_type": "bank_account_confirmation",
                        "title_vi": "Xác nhận tài khoản ngân hàng / phụ lục đổi tài khoản",
                        "requirement_level": "required",
                        "applicable_when": ["always"],
                        "required_sources": ["vendor_bank_accounts"],
                        "requires_verification": True,
                        "blocks_task_completion_when_missing": True,
                    },
                    {
                        "document_type": "invoice",
                        "title_vi": "Hóa đơn hoặc hợp đồng khớp tên người thụ hưởng",
                        "requirement_level": "required",
                        "applicable_when": ["always"],
                        "required_sources": ["invoices"],
                        "requires_verification": True,
                        "blocks_task_completion_when_missing": True,
                    },
                ],
            },
            "approval_controls": {
                "family_label_vi": "Thẩm quyền & quy trình phê duyệt",
                "default_issue_type": "process_exception",
                "default_assignee_role": "phe_duyet_tai_chinh",
                "requirements": [
                    {
                        "document_type": "approval_log_and_policy",
                        "title_vi": "Nhật ký phê duyệt & quy chế phân cấp thẩm quyền",
                        "requirement_level": "required",
                        "applicable_when": ["always"],
                        "required_sources": ["approval_events", "approval_policies"],
                        "requires_verification": True,
                        "blocks_task_completion_when_missing": True,
                    },
                    {
                        "document_type": "payment_request_voucher",
                        "title_vi": "Đề nghị thanh toán có đủ chữ ký duyệt",
                        "requirement_level": "required",
                        "applicable_when": ["always"],
                        "required_sources": ["payment_requests"],
                        "requires_verification": True,
                        "blocks_task_completion_when_missing": True,
                    },
                ],
            },
            "split_obligation": {
                "family_label_vi": "Nghi vấn tách nhỏ nghĩa vụ / hóa đơn né ngưỡng",
                "default_issue_type": "process_exception",
                "default_assignee_role": "kiem_soat_noi_bo",
                "requirements": [
                    {
                        "document_type": "purchase_requisition_or_contract",
                        "title_vi": "Đề nghị mua sắm / hợp đồng tổng hợp",
                        "requirement_level": "required",
                        "applicable_when": ["always"],
                        "required_sources": ["contracts", "invoices"],
                        "requires_verification": True,
                        "blocks_task_completion_when_missing": True,
                    },
                    {
                        "document_type": "split_payment_bundle",
                        "title_vi": "Bảng kê các giao dịch / hóa đơn tách nhỏ cùng đối tượng",
                        "requirement_level": "required",
                        "applicable_when": ["always"],
                        "required_sources": ["bank_transactions", "payment_allocations"],
                        "requires_verification": True,
                        "blocks_task_completion_when_missing": True,
                    },
                ],
            },
            "accounting_controls": {
                "family_label_vi": "Kiểm soát hạch toán & khóa sổ",
                "default_issue_type": "data_issue",
                "default_assignee_role": "ke_toan_tong_hop",
                "requirements": [
                    {
                        "document_type": "general_ledger_voucher",
                        "title_vi": "Chứng từ ghi sổ & giải trình bút toán điều chỉnh",
                        "requirement_level": "required",
                        "applicable_when": ["always"],
                        "required_sources": ["gl_entries"],
                        "requires_verification": True,
                        "blocks_task_completion_when_missing": True,
                    },
                ],
            },
            "amount_deviation": {
                "family_label_vi": "Bất thường giá trị / đơn giá giao dịch",
                "default_issue_type": "unexplained_anomaly",
                "default_assignee_role": "ke_toan_cong_no",
                "requirements": [
                    {
                        "document_type": "invoice",
                        "title_vi": "Hóa đơn & bảng kê khối lượng/đơn giá",
                        "requirement_level": "required",
                        "applicable_when": ["always"],
                        "required_sources": ["invoices"],
                        "requires_verification": True,
                        "blocks_task_completion_when_missing": True,
                    },
                    {
                        "document_type": "price_quotation_comparison",
                        "title_vi": "Báo giá / hợp đồng đối chiếu đơn giá",
                        "requirement_level": "required",
                        "applicable_when": ["always"],
                        "required_sources": ["quotations"],
                        "requires_verification": True,
                        "blocks_task_completion_when_missing": False,
                    },
                ],
            },
            "ml_anomaly": {
                "family_label_vi": "Cảnh báo bất thường cần giải trình nguồn gốc",
                "default_issue_type": "unexplained_anomaly",
                "default_assignee_role": "kiem_soat_noi_bo",
                "requirements": [
                    {
                        "document_type": "supporting_transaction_voucher",
                        "title_vi": "Chứng từ gốc & bản giải trình nghiệp vụ giao dịch",
                        "requirement_level": "required",
                        "applicable_when": ["always"],
                        "required_sources": ["bank_transactions"],
                        "requires_verification": True,
                        "blocks_task_completion_when_missing": True,
                    },
                ],
            },
        },
        "rule_overrides": {
            "P1": {
                "additional_requirements": [],
                "note": "Ưu tiên đối chiếu hóa đơn gốc, phân bổ thanh toán lũy kế (T096+T105) và biên bản hoàn trả/bù trừ nếu chi vượt.",
            },
            "C3": {
                "additional_requirements": [
                    {
                        "document_type": "second_level_review_note",
                        "title_vi": "Biên bản rà soát hậu kiểm đối với khoản duyệt nhanh",
                        "requirement_level": "required",
                        "applicable_when": ["always"],
                        "required_sources": ["approval_events"],
                        "requires_verification": True,
                        "blocks_task_completion_when_missing": True,
                    }
                ],
                "note": "Áp dụng cho luật C3 (duyệt nhanh dưới ngưỡng thời gian).",
            },
        },
    }
    validate_against_schema(policy, "document_requirement_policy")
    return policy


def reconcile_obligation(
    obligation: dict[str, Any],
    transactions: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
    allocations: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
    adjustments: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
    *,
    company_id: str = "",
    as_of: str | None = None,
    available_sources: set[str] | list[str] | tuple[str, ...] | None = None,
    confirmed_loss_vnd: int | None = None,
    recovered_vnd: int | None = None,
    disputed: bool = False,
) -> dict[str, Any]:
    """Reconcile payments, refunds, reversals, credit notes, and M:N allocations on one obligation without double-counting.

    Rule links: R4-01, R4-02, RULE-MONEY-01.
    """
    ob_id = str(obligation.get("obligation_id") or obligation.get("invoice_id") or "").strip()
    if not ob_id:
        fail(422, "OBLIGATION_ID_REQUIRED", "Thiếu obligation_id để đối chiếu thanh toán.", "Cung cấp obligation_id hợp lệ.")
    cid = str(company_id or obligation.get("company_id") or "").strip() or "UNKNOWN"

    as_of_dt = parse_iso_datetime(as_of, field_name="as_of") if as_of else None
    raw_gross = obligation.get("gross_amount_vnd", obligation.get("obligation_amount_vnd", obligation.get("invoice_gross_vnd")))
    obligation_amount = int(raw_gross) if raw_gross is not None else None
    if obligation_amount is not None and obligation_amount < 0:
        fail(422, "NEGATIVE_OBLIGATION_AMOUNT", "Giá trị nghĩa vụ hóa đơn không được âm.", "Kiểm tra dữ liệu nguồn.")

    avail = set(available_sources) if available_sources is not None else None
    notes: list[str] = []

    if obligation_amount is None:
        report = {
            "schema_version": RECONCILIATION_SCHEMA_VERSION,
            "obligation_id": ob_id,
            "company_id": cid,
            "as_of": as_of,
            "status": "unavailable",
            "obligation_amount_vnd": None,
            "gross_allocated_payment_vnd": 0,
            "refund_and_reversal_vnd": 0,
            "adjustment_signed_vnd": 0,
            "net_settled_vnd": 0,
            "remaining_due_vnd": None,
            "overpaid_excess_vnd": None,
            "related_amount_vnd": None,
            "discrepancy_amount_vnd": None,
            "confirmed_loss_vnd": confirmed_loss_vnd,
            "recovered_vnd": recovered_vnd,
            "allocations": [],
            "deduplicated_tx_ids": [],
            "notes": ["Không có giá trị nghĩa vụ/hóa đơn gốc để đối chiếu (RULE-MONEY-01)."],
        }
        validate_against_schema(report, "reconciliation_report")
        return report

    if avail is not None and "bank_transactions" not in avail and not allocations and not transactions:
        report = {
            "schema_version": RECONCILIATION_SCHEMA_VERSION,
            "obligation_id": ob_id,
            "company_id": cid,
            "as_of": as_of,
            "status": "unavailable",
            "obligation_amount_vnd": obligation_amount,
            "gross_allocated_payment_vnd": 0,
            "refund_and_reversal_vnd": 0,
            "adjustment_signed_vnd": 0,
            "net_settled_vnd": 0,
            "remaining_due_vnd": None,
            "overpaid_excess_vnd": None,
            "related_amount_vnd": obligation_amount,
            "discrepancy_amount_vnd": None,
            "confirmed_loss_vnd": confirmed_loss_vnd,
            "recovered_vnd": recovered_vnd,
            "allocations": [],
            "deduplicated_tx_ids": [],
            "notes": ["Thiếu nguồn lịch sử thanh toán ngân hàng (bank_transactions); không suy đoán trạng thái khớp/thiếu."],
        }
        validate_against_schema(report, "reconciliation_report")
        return report

    tx_by_id: dict[str, dict] = {}
    for tx in transactions:
        tid = str(tx.get("transaction_id") or tx.get("tx_id") or "").strip()
        if tid:
            tx_by_id[tid] = tx

    def _within_as_of(ts: str | None) -> bool:
        if not ts or as_of_dt is None:
            return True
        return parse_iso_datetime(ts, field_name="tx_time") <= as_of_dt

    lines: list[dict[str, Any]] = []
    seen_alloc_keys: set[tuple[str, str, str]] = set()
    seen_tx_ids: list[str] = []
    seen_tx_set: set[str] = set()

    # Track unallocated ambiguous M:N transactions referencing multiple obligations without split amounts.
    ambiguous_multi_ob = False

    if allocations:
        for row in allocations:
            row_ob = str(row.get("obligation_id") or ob_id).strip()
            if row_ob != ob_id:
                continue
            tx_id = str(row.get("transaction_id") or row.get("tx_id") or "").strip()
            if not tx_id:
                continue
            alloc_id = str(row.get("allocation_id") or f"{tx_id}:{row_ob}").strip()
            kind = str(row.get("kind") or tx_by_id.get(tx_id, {}).get("kind") or "payment").strip().lower()
            if kind not in ("payment", "refund", "reversal", "credit_note", "adjustment", "fee"):
                kind = "payment"
            tx_time = str(row.get("tx_time") or row.get("allocated_at") or tx_by_id.get(tx_id, {}).get("event_at") or tx_by_id.get(tx_id, {}).get("tx_time") or as_of or "2026-11-01T00:00:00+07:00")
            if not _within_as_of(tx_time):
                notes.append(f"Bỏ qua phân bổ sau mốc as_of ({tx_id}, {tx_time}).")
                continue
            dedup_key = (alloc_id, tx_id, kind)
            if dedup_key in seen_alloc_keys:
                notes.append(f"Khử trùng bản ghi phân bổ lặp lại ({alloc_id}, {tx_id}).")
                continue
            seen_alloc_keys.add(dedup_key)

            raw_amt = int(row.get("allocated_amount_vnd", row.get("amount_vnd", 0)))
            if raw_amt < 0:
                if kind in ("refund", "reversal", "credit_note"):
                    amt = abs(raw_amt)
                else:
                    amt = 0
            else:
                amt = raw_amt

            if kind in ("refund", "reversal"):
                signed = -amt
            elif kind in ("credit_note", "adjustment", "fee"):
                if "signed_effect_vnd" in row and row["signed_effect_vnd"] is not None:
                    signed = int(row["signed_effect_vnd"])
                elif kind == "credit_note":
                    signed = -amt
                else:
                    signed = amt
            else:
                signed = amt

            lines.append(
                {
                    "tx_id": tx_id,
                    "allocation_id": alloc_id,
                    "kind": kind,
                    "allocated_amount_vnd": amt,
                    "signed_effect_vnd": signed,
                    "tx_time": tx_time,
                    "note": str(row.get("note") or ""),
                }
            )
            if tx_id not in seen_tx_set:
                seen_tx_set.add(tx_id)
                seen_tx_ids.append(tx_id)
    else:
        for tx in transactions:
            tx_id = str(tx.get("transaction_id") or tx.get("tx_id") or "").strip()
            if not tx_id:
                continue
            ob_list = tx.get("obligation_ids")
            if isinstance(ob_list, list) and len(ob_list) > 1 and ob_id in ob_list and tx.get("allocated_amount_vnd") is None:
                ambiguous_multi_ob = True
                notes.append(f"Giao dịch {tx_id} trả gộp nhiều nghĩa vụ {ob_list} nhưng chưa có allocated_amount_vnd; từ chối đếm trùng.")
                continue
            tx_ob = str(tx.get("obligation_id") or ob_id).strip()
            if ob_list and ob_id not in ob_list and tx_ob != ob_id:
                continue
            if not ob_list and tx_ob != ob_id:
                continue
            kind = str(tx.get("kind") or ("refund" if tx.get("direction") == "in" and tx.get("is_refund") else "payment")).strip().lower()
            if kind not in ("payment", "refund", "reversal", "credit_note", "adjustment", "fee"):
                kind = "payment"
            tx_time = str(tx.get("event_at") or tx.get("tx_time") or as_of or "2026-11-01T00:00:00+07:00")
            if not _within_as_of(tx_time):
                notes.append(f"Bỏ qua giao dịch sau mốc as_of ({tx_id}, {tx_time}).")
                continue
            dedup_key = (tx_id, tx_id, kind)
            if dedup_key in seen_alloc_keys:
                notes.append(f"Khử trùng giao dịch lặp lại ({tx_id}).")
                continue
            seen_alloc_keys.add(dedup_key)
            amt = abs(int(tx.get("allocated_amount_vnd", tx.get("amount_vnd", 0))))
            signed = -amt if kind in ("refund", "reversal", "credit_note") else amt
            lines.append(
                {
                    "tx_id": tx_id,
                    "allocation_id": f"{tx_id}:{ob_id}",
                    "kind": kind,
                    "allocated_amount_vnd": amt,
                    "signed_effect_vnd": signed,
                    "tx_time": tx_time,
                    "note": str(tx.get("note") or ""),
                }
            )
            if tx_id not in seen_tx_set:
                seen_tx_set.add(tx_id)
                seen_tx_ids.append(tx_id)

    for adj in adjustments:
        adj_ob = str(adj.get("obligation_id") or ob_id).strip()
        if adj_ob != ob_id:
            continue
        adj_id = str(adj.get("adjustment_id") or adj.get("tx_id") or digest(canonical(adj))[:12]).strip()
        tx_time = str(adj.get("tx_time") or adj.get("effective_at") or as_of or "2026-11-01T00:00:00+07:00")
        if not _within_as_of(tx_time):
            notes.append(f"Bỏ qua điều chỉnh sau mốc as_of ({adj_id}).")
            continue
        kind = str(adj.get("kind") or "credit_note").strip().lower()
        if kind not in ("credit_note", "adjustment", "fee", "refund", "reversal"):
            kind = "adjustment"
        dedup_key = (adj_id, adj_id, kind)
        if dedup_key in seen_alloc_keys:
            continue
        seen_alloc_keys.add(dedup_key)
        raw_signed = adj.get("signed_effect_vnd")
        if raw_signed is None:
            raw_amt = int(adj.get("amount_vnd", 0))
            signed = -abs(raw_amt) if kind in ("credit_note", "refund", "reversal") else raw_amt
        else:
            signed = int(raw_signed)
        lines.append(
            {
                "tx_id": adj_id,
                "allocation_id": adj_id,
                "kind": kind,
                "allocated_amount_vnd": abs(signed),
                "signed_effect_vnd": signed,
                "tx_time": tx_time,
                "note": str(adj.get("note") or ""),
            }
        )
        if adj_id not in seen_tx_set:
            seen_tx_set.add(adj_id)
            seen_tx_ids.append(adj_id)

    gross_payment = sum(ln["allocated_amount_vnd"] for ln in lines if ln["kind"] == "payment")
    refund_reversal = sum(ln["allocated_amount_vnd"] for ln in lines if ln["kind"] in ("refund", "reversal"))
    adjustment_signed = sum(ln["signed_effect_vnd"] for ln in lines if ln["kind"] in ("credit_note", "adjustment", "fee"))
    net_settled = gross_payment - refund_reversal
    effective_obligation = max(0, obligation_amount + adjustment_signed)

    if ambiguous_multi_ob or disputed:
        status = "disputed"
        remaining_due = max(0, effective_obligation - max(0, net_settled))
        overpaid_excess = max(0, net_settled - effective_obligation)
        discrepancy = abs(net_settled - effective_obligation) if not ambiguous_multi_ob else None
    elif net_settled == effective_obligation:
        status = "matched"
        remaining_due = 0
        overpaid_excess = 0
        discrepancy = 0
    elif net_settled > effective_obligation:
        status = "overpaid"
        remaining_due = 0
        overpaid_excess = net_settled - effective_obligation
        discrepancy = overpaid_excess
    elif net_settled <= 0:
        status = "unmatched"
        remaining_due = effective_obligation
        overpaid_excess = 0
        discrepancy = effective_obligation
    else:
        status = "partially_paid"
        remaining_due = effective_obligation - net_settled
        overpaid_excess = 0
        discrepancy = remaining_due

    report = {
        "schema_version": RECONCILIATION_SCHEMA_VERSION,
        "obligation_id": ob_id,
        "company_id": cid,
        "as_of": as_of,
        "status": status,
        "obligation_amount_vnd": obligation_amount,
        "gross_allocated_payment_vnd": gross_payment,
        "refund_and_reversal_vnd": refund_reversal,
        "adjustment_signed_vnd": adjustment_signed,
        "net_settled_vnd": net_settled,
        "remaining_due_vnd": remaining_due,
        "overpaid_excess_vnd": overpaid_excess,
        "related_amount_vnd": max(obligation_amount, gross_payment),
        "discrepancy_amount_vnd": discrepancy,
        "confirmed_loss_vnd": confirmed_loss_vnd,
        "recovered_vnd": recovered_vnd,
        "allocations": lines,
        "deduplicated_tx_ids": seen_tx_ids,
        "notes": notes,
    }
    validate_against_schema(report, "reconciliation_report")
    return report


def _is_requirement_applicable(
    rule: dict[str, Any],
    context: dict[str, Any],
) -> tuple[bool, str]:
    conditions = list(rule.get("applicable_when") or ["always"])
    if "always" in conditions:
        return True, "Bắt buộc theo chính sách nhóm vấn đề."
    recon_status = str(context.get("reconciliation_status") or "").lower()
    active_flags = set(str(f) for f in (context.get("applicability_flags") or []))
    if recon_status in ("overpaid", "disputed"):
        active_flags.add("overpaid_or_multiple_payments")
    if recon_status == "disputed":
        active_flags.add("disputed")
    if int(context.get("payment_count") or 0) > 1:
        active_flags.add("overpaid_or_multiple_payments")
    if context.get("has_refund_or_adjustment"):
        active_flags.add("has_refund_or_adjustment")
    if context.get("exceeds_split_threshold"):
        active_flags.add("exceeds_split_threshold")
    matched = [c for c in conditions if c in active_flags]
    if matched:
        return True, f"Áp dụng do điều kiện: {', '.join(matched)}."
    return False, f"Không phát sinh điều kiện áp dụng ({', '.join(conditions)})."


def evaluate_document_checklist(
    context: dict[str, Any],
    documents: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
    snapshot_tables: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
    *,
    available_sources: set[str] | list[str] | tuple[str, ...] | None = None,
    as_of: str | None = None,
    checked_by: str = "system_policy_eval",
    checked_at: str | None = None,
    human_overrides: dict[str, dict[str, Any]] | None = None,
    revision: int = 1,
) -> dict[str, Any]:
    """Evaluate per-family & per-rule DocumentChecklist distinguishing unknown vs missing vs pending vs present vs not_applicable."""
    pol = policy or default_document_requirement_policy()
    validate_against_schema(pol, "document_requirement_policy")

    tenant_id = str(context.get("tenant_id") or "default").strip() or "default"
    company_id = str(context.get("company_id") or "").strip()
    case_id = str(context.get("case_id") or "").strip()
    obligation_id = str(context.get("obligation_id") or case_id).strip()
    if not company_id or not case_id:
        fail(422, "CHECKLIST_SCOPE_REQUIRED", "Thiếu company_id hoặc case_id để đánh giá checklist.", "Truyền ngữ cảnh vụ việc hợp lệ.")

    problem_family = str(context.get("problem_family") or "payment_invoice").strip()
    families = pol["families"]
    if problem_family not in families:
        problem_family = "ml_anomaly"
    family_spec = families[problem_family]

    rule_ids = [str(r) for r in (context.get("rule_ids") or []) if str(r).strip()]
    specs_by_type: dict[str, dict[str, Any]] = {}
    ordered_types: list[str] = []
    for req in family_spec["requirements"]:
        dt = req["document_type"]
        specs_by_type[dt] = deepcopy(req)
        ordered_types.append(dt)
    for rid in rule_ids:
        override = pol.get("rule_overrides", {}).get(rid)
        if override:
            for req in override.get("additional_requirements") or []:
                dt = req["document_type"]
                if dt not in specs_by_type:
                    specs_by_type[dt] = deepcopy(req)
                    ordered_types.append(dt)

    tables = snapshot_tables or {}
    if available_sources is not None:
        avail_set = {str(s) for s in available_sources}
    else:
        avail_set = {str(k) for k, v in tables.items() if v is not None}

    docs_by_type: dict[str, list[dict[str, Any]]] = {}
    for doc in documents:
        if str(doc.get("company_id") or company_id) != company_id:
            continue
        dt = str(doc.get("document_type") or "").strip()
        if dt:
            docs_by_type.setdefault(dt, []).append(doc)

    now_iso = checked_at or datetime.now(timezone.utc).isoformat()
    overrides = human_overrides or {}
    record_presence = tables.get("document_records_by_type") if isinstance(tables.get("document_records_by_type"), dict) else {}

    items: list[dict[str, Any]] = []
    for dt in ordered_types:
        rule = specs_by_type[dt]
        applicable, app_reason = _is_requirement_applicable(rule, context)
        req_sources = [str(s) for s in (rule.get("required_sources") or [])]
        missing_sources = [s for s in req_sources if s not in avail_set]
        matched_docs = docs_by_type.get(dt, [])
        doc_ids = [str(d["document_id"]) for d in matched_docs]
        ev_ids: list[str] = []
        for d in matched_docs:
            ev_ids.append(f"{d['document_id']}@v{d.get('current_version', 1)}")

        override = overrides.get(dt)
        if not applicable:
            status = "not_applicable"
            source_used = "policy_eval"
            source_checked = len(missing_sources) == 0
            last_actor = checked_by
            note = app_reason
        elif override and override.get("item_status") in CHECKLIST_ITEM_STATUSES:
            ovr_status = str(override["item_status"])
            if ovr_status == "present" and not any(d.get("verification_status") == "present" for d in matched_docs):
                fail(
                    422,
                    "VERIFIED_EVIDENCE_REQUIRED",
                    f"Không thể đánh dấu Đã xác minh cho {dt} khi chưa có chứng từ đã xác minh.",
                    "Tải lên và xác minh chứng từ trước khi chốt present.",
                )
            status = ovr_status
            source_used = "human_verifier"
            source_checked = len(missing_sources) == 0
            last_actor = str(override.get("checked_by") or checked_by)
            note = str(override.get("note") or f"Xác nhận bởi người kiểm tra ({last_actor}).")
        elif any(d.get("verification_status") == "present" for d in matched_docs):
            status = "present"
            source_used = "document_store"
            source_checked = True
            last_actor = next(
                (str(v.get("verified_by") or checked_by) for d in matched_docs if d.get("verification_status") == "present" for v in d.get("versions", []) if v.get("verification_status") == "present"),
                checked_by,
            )
            note = "Chứng từ đính kèm đã được người có thẩm quyền xác minh."
        elif any(d.get("verification_status") == "pending_verification" for d in matched_docs):
            status = "pending_verification"
            source_used = "document_store"
            source_checked = True
            last_actor = checked_by
            note = "Đã nhận tệp chứng từ nhưng chưa xác minh nội dung/đối tượng."
        elif matched_docs and all(d.get("verification_status") == "rejected" for d in matched_docs):
            status = "missing"
            source_used = "human_verifier"
            source_checked = True
            last_actor = checked_by
            note = "Chứng từ đã nộp trước đó bị từ chối xác minh; vẫn cần bổ sung bản hợp lệ."
        elif missing_sources:
            status = "unknown"
            source_used = "policy_eval"
            source_checked = False
            last_actor = checked_by
            note = f"Chưa có nguồn dữ liệu để kiểm tra ({', '.join(missing_sources)})."
        else:
            rec_state = record_presence.get(dt)
            if rec_state == "present_verified":
                status = "pending_verification" if rule.get("requires_verification", True) else "present"
                source_used = "snapshot_source"
                note = "Có bản ghi từ nguồn snapshot nhưng chưa đính kèm/xác minh chứng từ gốc." if status == "pending_verification" else "Khớp từ nguồn snapshot đã kiểm tra."
            elif rec_state == "present_unverified":
                status = "pending_verification"
                source_used = "snapshot_source"
                note = "Có bản ghi từ nguồn dữ liệu nhưng chưa xác minh chứng từ."
            else:
                status = "missing"
                source_used = "snapshot_source"
                note = f"Đã kiểm tra nguồn ({', '.join(req_sources)}) nhưng chưa có chứng từ {dt}."
            source_checked = True
            last_actor = checked_by

        items.append(
            {
                "document_type": dt,
                "title_vi": rule["title_vi"],
                "requirement_level": rule["requirement_level"],
                "applicable": applicable,
                "applicability_reason": app_reason,
                "item_status": status,
                "status_label_vi": CHECKLIST_ITEM_STATUS_LABELS_VI[status],
                "decision_source": source_used,
                "evidence_ids": ev_ids,
                "document_ids": doc_ids,
                "source_checked": source_checked,
                "required_sources": req_sources,
                "missing_sources": missing_sources,
                "last_checked_at": now_iso,
                "checked_by": last_actor,
                "note": note,
            }
        )

    counts = {s: sum(1 for it in items if it["item_status"] == s) for s in CHECKLIST_ITEM_STATUSES}
    applicable_items = sum(1 for it in items if it["applicable"])
    ready = applicable_items > 0 and counts["missing"] == 0 and counts["pending_verification"] == 0 and counts["unknown"] == 0
    checklist_id = "chk_" + digest(canonical([tenant_id, company_id, case_id, obligation_id]))[:24]
    checklist = {
        "schema_version": CHECKLIST_SCHEMA_VERSION,
        "checklist_id": checklist_id,
        "tenant_id": tenant_id,
        "company_id": company_id,
        "case_id": case_id,
        "obligation_id": obligation_id,
        "problem_family": problem_family,
        "rule_ids": rule_ids,
        "policy_id": pol["policy_id"],
        "policy_version": pol["policy_version"],
        "as_of": as_of,
        "items": items,
        "summary": {
            "total_items": len(items),
            "applicable_items": applicable_items,
            "present": counts["present"],
            "missing": counts["missing"],
            "pending_verification": counts["pending_verification"],
            "unknown": counts["unknown"],
            "not_applicable": counts["not_applicable"],
            "ready_for_closure": ready,
        },
        "revision": revision,
        "updated_at": now_iso,
        "updated_by": checked_by,
    }
    validate_against_schema(checklist, "document_checklist")
    return checklist

