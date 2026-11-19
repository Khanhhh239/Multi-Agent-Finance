"""Candidate vs evidence separation, obligation-level case coalescing, and stable case identity."""
from __future__ import annotations

from copy import deepcopy
from datetime import timezone
import math

from .identity import normalize
from .import_files import canonical, digest, fail
from .rule_snapshot import SCOPE_RULES
from .rules import RULE_NAMES
from .snapshot_features import utc

BUNDLE_VERSION = "case-queue-bundle/1.0.0"
CASE_IDENTITY_VERSION = "case-identity/1.0.0"
MASTER_QUALITY_RULES = frozenset({"B5", "E3", "E4"})

RULE_PROBLEM_FAMILY = {
    "P1": "payment_invoice",
    "A6": "payment_invoice",
    "P2": "payment_invoice",
    "A1": "split_obligation",
    "A2": "split_obligation",
    "A3": "split_obligation",
    "A4": "split_obligation",
    "A5": "amount_deviation",
    "B1": "vendor_bank_identity",
    "B2": "vendor_bank_identity",
    "B3": "vendor_bank_identity",
    "B4": "vendor_bank_identity",
    "B6": "vendor_bank_identity",
    "B7": "vendor_bank_identity",
    "C1": "approval_controls",
    "C2": "approval_controls",
    "C3": "approval_controls",
    "C4": "approval_controls",
    "E1": "payroll_entitlement",
    "E2": "payroll_entitlement",
    "F1": "accounting_controls",
    "F2": "accounting_controls",
    "F3": "accounting_controls",
    "F4": "accounting_controls",
    "T1": "advance_lifecycle",
    "T2": "advance_lifecycle",
}

FAMILY_PRIORITY = {
    "payment_invoice": 90,
    "payroll_entitlement": 85,
    "advance_lifecycle": 80,
    "vendor_bank_identity": 75,
    "approval_controls": 70,
    "split_obligation": 65,
    "accounting_controls": 60,
    "amount_deviation": 40,
    "ml_anomaly": 30,
    "unscorable": 10,
}

OBLIGATION_RULES = frozenset({"P1", "A6", "P2", "A1", "A2", "A3", "A4", "T1", "T2", "E1", "E2"})


def _is_finite_number(val) -> bool:
    return isinstance(val, (int, float)) and not isinstance(val, bool) and math.isfinite(float(val))


def stable_case_id(tenant_id: str, company_id: str, problem_family: str, obligation_id: str) -> str:
    """Deterministic case ID independent of snapshot_id, run_id, analysis_id, or model_id."""
    return "case_" + digest(
        canonical([CASE_IDENTITY_VERSION, str(tenant_id), str(company_id), str(problem_family), str(obligation_id)])
    )[:32]


def _iso_utc(ts: str) -> str:
    return utc(ts).astimezone(timezone.utc).isoformat()


def _norm_token(value) -> str:
    if not isinstance(value, str):
        return ""
    return normalize(value)


def _is_weak_shared_only_obligation(obligation_id: str) -> bool:
    lowered = obligation_id.strip().lower()
    return lowered.startswith(("vendor:", "vendor_id:", "bank:", "recipient_account:", "weak_graph:"))


def _resolve_problem_family(record: dict) -> str:
    explicit = record.get("problem_family")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()

    actionable = list(record.get("actionable_hits") or [])
    if actionable:
        # Pick highest-weight actionable rule family deterministically (tie-break by rule priority/id).
        ranked = sorted(
            actionable,
            key=lambda h: (
                -float(h.get("points", 0) or 0),
                -int(bool(h.get("hard_trigger"))),
                -FAMILY_PRIORITY.get(RULE_PROBLEM_FAMILY.get(h["rule_id"], ""), 0),
                str(h["rule_id"]),
            ),
        )
        top_rid = ranked[0]["rule_id"]
        return RULE_PROBLEM_FAMILY.get(top_rid, "process_exception")

    if record.get("ml_available") or record.get("calibrated_probability") is not None:
        return "ml_anomaly"
    return "unscorable"


def _resolve_obligation_id(record: dict, problem_family: str, tx_lookup: dict[str, dict]) -> tuple[str, str]:
    """Resolve binding obligation identity and human-readable grouping rationale.

    Never collapses transactions merely because they share vendor_id, bank account,
    or weak entity graph links.
    """
    tid = str(record["transaction_id"])
    raw_tx = tx_lookup.get(tid) or {}
    explicit = record.get("obligation_id")
    if isinstance(explicit, str) and explicit.strip():
        cleaned = explicit.strip()
        if _is_weak_shared_only_obligation(cleaned):
            raise ValueError(
                f"Obligation ID '{cleaned}' cannot collapse purely on vendor/bank identity without an obligation"
            )
        return cleaned, f"Gộp theo định danh nghĩa vụ/vấn đề '{cleaned}' trong họ '{problem_family}'."

    vendor_id = str(record.get("vendor_id") or raw_tx.get("vendor_id") or "").strip()
    inv_norm = _norm_token(record.get("invoice_number") or raw_tx.get("invoice_number") or "")
    contract_id = str(record.get("contract_id") or raw_tx.get("contract_id") or "").strip()
    request_id = str(record.get("request_id") or raw_tx.get("request_id") or "").strip()
    po_id = str(record.get("purchase_order_id") or raw_tx.get("purchase_order_id") or "").strip()
    advance_id = str(record.get("advance_id") or raw_tx.get("advance_id") or "").strip()
    emp_id = str(record.get("employee_id") or raw_tx.get("employee_id") or "").strip()
    payroll_period = str(record.get("payroll_period") or raw_tx.get("payroll_period") or "").strip()

    if problem_family in ("payment_invoice", "split_obligation", "vendor_bank_identity", "approval_controls", "ml_anomaly"):
        if vendor_id and inv_norm:
            return (
                f"invoice:{vendor_id}:{inv_norm}",
                f"Cùng hóa đơn chuẩn hóa '{inv_norm}' của NCC '{vendor_id}' và cùng họ vấn đề '{problem_family}'.",
            )
        if inv_norm:
            return (
                f"invoice::{inv_norm}",
                f"Cùng số hóa đơn '{inv_norm}' và cùng họ vấn đề '{problem_family}'.",
            )
        if contract_id:
            prefix = f"{vendor_id}:{contract_id}" if vendor_id else contract_id
            return (
                f"contract:{prefix}",
                f"Cùng hợp đồng '{contract_id}' và cùng họ vấn đề '{problem_family}'.",
            )
        if request_id:
            return (
                f"request:{request_id}",
                f"Cùng đề nghị thanh toán '{request_id}' và cùng họ vấn đề '{problem_family}'.",
            )
        if po_id:
            return (
                f"po:{po_id}",
                f"Cùng đơn mua hàng '{po_id}' và cùng họ vấn đề '{problem_family}'.",
            )

    if problem_family == "advance_lifecycle" and advance_id:
        return f"advance:{advance_id}", f"Cùng hồ sơ tạm ứng '{advance_id}'."

    if problem_family == "payroll_entitlement" and emp_id and payroll_period:
        return (
            f"payroll:{emp_id}:{payroll_period}",
            f"Cùng kỳ lương '{payroll_period}' của nhân viên '{emp_id}'.",
        )

    return (
        f"tx:{tid}",
        f"Chưa có chứng từ/nghĩa vụ gộp chung (hoặc chỉ có quan hệ NCC/TK/đồ thị yếu); tách riêng theo giao dịch '{tid}'.",
    )


def build_case_bundle_from_records(
    *,
    tenant_id: str,
    company_id: str,
    snapshot_binding: dict,
    records: list[dict],
    prior_evidence_transactions: list[dict] | None = None,
    source_tables: dict[str, list[dict]] | None = None,
    method_versions: dict | None = None,
    model_pins: dict | None = None,
    simulated_data: bool = True,
) -> dict:
    """Build canonical case-queue-bundle/1.0.0 from normalized transaction records and evidence tables."""
    return dict(
        version=BUNDLE_VERSION,
        tenant_id=str(tenant_id),
        company_id=str(company_id),
        snapshot_binding=deepcopy(snapshot_binding),
        records=deepcopy(records),
        prior_evidence_transactions=deepcopy(prior_evidence_transactions or []),
        source_tables=deepcopy(source_tables or {}),
        method_versions=deepcopy(method_versions or {}),
        model_pins=deepcopy(model_pins or {}),
        simulated_data=bool(simulated_data),
    )


def build_case_bundle_from_rule_analysis(
    analysis: dict,
    raw_snapshot: dict | None = None,
    *,
    scope,
    ml_method: str | None = None,
    extra_scores: dict[str, dict] | None = None,
    ml_candidate_min_score: float = 0.65,
) -> dict:
    """Adapt snapshot-rule-analysis/1.0.0 (+ optional validation/calibration scores) into case-queue-bundle/1.0.0.

    Keeps historical prior payments strictly as evidence unless independently flagged.
    """
    if analysis.get("version") != "snapshot-rule-analysis/1.0.0" or analysis.get("view") != "technical":
        fail(
            409,
            "CASE_ANALYSIS_VERSION",
            "Cần kết quả phân tích 35 luật mức technical (snapshot-rule-analysis/1.0.0) để gộp vụ.",
            "Chạy analyze với view=technical trên snapshot nguồn đầy đủ.",
        )
    company = next(iter(scope.company_ids))
    if analysis.get("snapshot", {}).get("company_id") != company:
        fail(403, "ACCESS_DENIED", "Kết quả phân tích không thuộc doanh nghiệp hiện hành.", "Chọn đúng doanh nghiệp.")

    source_tables = {}
    simulated = True
    tx_lookup = {}
    if raw_snapshot is not None:
        if raw_snapshot.get("tenant_id") != scope.tenant_id or raw_snapshot.get("company_id") != company:
            fail(403, "ACCESS_DENIED", "Snapshot ngoài phạm vi doanh nghiệp.", "Chọn đúng doanh nghiệp.")
        source = raw_snapshot.get("source") or {}
        simulated = bool(source.get("is_simulated", True))
        source_tables = deepcopy(source.get("tables") or {})
        for tx in source_tables.get("transactions") or []:
            if isinstance(tx, dict) and tx.get("transaction_id"):
                tx_lookup[tx["transaction_id"]] = tx

    pins = dict((analysis.get("bridge_provenance") or {}).get("model_pins") or {})
    if ml_method is None:
        pinned = [m for m, p in pins.items() if m != "robust_z" and p is not None]
        if len(pinned) == 1:
            ml_method = pinned[0]
        elif pinned:
            ml_method = sorted(pinned)[0]

    batch_events_by_tx: dict[str, list[dict]] = {}
    for entry in analysis.get("catalogue_results") or []:
        rid = entry.get("rule_id")
        if rid in SCOPE_RULES or rid in MASTER_QUALITY_RULES:
            continue
        for ev in entry.get("groups") or []:
            if ev.get("status") != "evaluated" or ev.get("signal") is not True or ev.get("suppressed_reason"):
                continue
            if not (ev.get("points", 0) > 0 or ev.get("hard_trigger")):
                continue
            for tid in ev.get("transaction_ids") or []:
                batch_events_by_tx.setdefault(tid, []).append(
                    dict(
                        rule_id=rid,
                        points=ev.get("points", 0),
                        hard_trigger=int(bool(ev.get("hard_trigger"))),
                        event_id=ev.get("event_id"),
                        related_transaction_ids=list(ev.get("related_transaction_ids") or []),
                        evidence=deepcopy(ev.get("evidence") or {}),
                    )
                )

    candidate_ids_in_analysis = {str(r["transaction_id"]) for r in analysis.get("rows") or []}
    records = []
    extra_scores = extra_scores or {}

    for row in analysis.get("rows") or []:
        tid = str(row["transaction_id"])
        rev = int(row.get("revision", 1))
        raw_tx = tx_lookup.get(tid) or {}
        tx_visible = row.get("availability", {}).get("available", True) is not False

        actionable_hits = []
        context_hits = []
        master_hits = []
        source_gaps = []
        evidence_refs = []
        related_prior_tx_ids = set()

        for entry in (row.get("rule_coverage") or {}).get("rules") or []:
            rid = entry["rule_id"]
            if rid in SCOPE_RULES:
                continue
            if rid in MASTER_QUALITY_RULES:
                if entry.get("status") == "evaluated_hit":
                    master_hits.append(rid)
                continue
            if entry.get("status") == "unavailable":
                source_gaps.append(
                    dict(
                        rule_id=rid,
                        reason=entry.get("reason") or "source_or_scope_unavailable",
                        gaps=deepcopy(entry.get("gaps") or []),
                        blocking=False,
                    )
                )
            elif entry.get("status") == "evaluated_hit":
                for h in entry.get("hits") or []:
                    if h.get("suppressed_reason"):
                        continue
                    for rtid in h.get("related_transaction_ids") or []:
                        if rtid != tid:
                            related_prior_tx_ids.add(str(rtid))
                    for eid in (h.get("evidence") or {}).get("related_transaction_ids") or []:
                        if eid != tid:
                            related_prior_tx_ids.add(str(eid))
                    if h.get("points", 0) > 0 or h.get("hard_trigger"):
                        actionable_hits.append(
                            dict(
                                rule_id=rid,
                                points=float(h.get("points", 0) or 0),
                                hard_trigger=bool(h.get("hard_trigger")),
                                evidence=deepcopy(h.get("evidence") or {}),
                                related_transaction_ids=list(h.get("related_transaction_ids") or []),
                                evidence_id=h.get("evidence_id"),
                            )
                        )
                    else:
                        context_hits.append(rid)

        for bev in batch_events_by_tx.get(tid, []):
            for rtid in bev.get("related_transaction_ids") or []:
                if rtid != tid:
                    related_prior_tx_ids.add(str(rtid))
            if not any(h["rule_id"] == bev["rule_id"] for h in actionable_hits):
                actionable_hits.append(
                    dict(
                        rule_id=bev["rule_id"],
                        points=float(bev.get("points", 0) or 0),
                        hard_trigger=bool(bev.get("hard_trigger")),
                        evidence=bev.get("evidence") or {},
                        related_transaction_ids=bev.get("related_transaction_ids") or [],
                        evidence_id=bev.get("event_id"),
                    )
                )

        ml_branch = (row.get("methods") or {}).get(ml_method) if ml_method else None
        ml_available = bool(
            tx_visible and ml_branch and ml_branch.get("available") is True and (
                _is_finite_number(ml_branch.get("raw_score")) or _is_finite_number(ml_branch.get("score"))
            )
        )
        ml_raw = float(ml_branch["raw_score"]) if (ml_available and _is_finite_number(ml_branch.get("raw_score"))) else None

        extra = extra_scores.get(tid) or {}
        ml_norm = extra.get("ml_normalized_score")
        if ml_norm is None and ml_available:
            if _is_finite_number(ml_branch.get("percentile")):
                ml_norm = float(ml_branch["percentile"])
            elif _is_finite_number(ml_branch.get("score")) and ml_branch.get("score_kind") == "empirical_midrank":
                ml_norm = float(ml_branch["score"])
        cal_prob = extra.get("calibrated_fraud_probability")
        cal_status = extra.get("calibration_status", "uncalibrated")

        lr_branch = (row.get("methods") or {}).get("supervised_lr")
        lr_available = bool(
            tx_visible and isinstance(lr_branch, dict) and lr_branch.get("available") is True and _is_finite_number(lr_branch.get("score"))
        )
        lr_score = float(lr_branch["score"]) if lr_available else None
        lr_prob = float(lr_branch["probability"]) if (lr_available and _is_finite_number(lr_branch.get("probability"))) else None
        lr_pred = int(lr_branch["prediction"]) if (lr_available and lr_branch.get("prediction") in (0, 1)) else None
        lr_thresh = float(lr_branch["threshold"]) if (lr_available and _is_finite_number(lr_branch.get("threshold"))) else None
        lr_ver = str(lr_branch.get("model_version")) if (lr_available and lr_branch.get("model_version")) else None

        for ref in (row.get("feature_evidence") or {}).get("records") or []:
            evidence_refs.append(
                dict(
                    table=ref.get("table", "source"),
                    record_id=str(ref.get("record_id") or ref.get("source_sha256") or tid),
                    revision=ref.get("revision"),
                    role="obligation_source" if ref.get("table") in ("transaction_documents", "invoices") else "supporting_document",
                )
            )
        graph_data = row.get("graph") or {}
        weak_graph = dict(
            available=bool(graph_data.get("available")),
            links=deepcopy(graph_data.get("links") or []),
            findings=deepcopy(graph_data.get("findings") or []),
            master_quality_rules=sorted(set(master_hits)),
        )

        max_rule_pts = max((float(h["points"]) for h in actionable_hits), default=0.0)
        rule_points_total = sum(float(h["points"]) for h in actionable_hits)
        has_hard = any(bool(h["hard_trigger"]) for h in actionable_hits)
        has_ml_signal = _is_finite_number(ml_norm) and float(ml_norm) >= ml_candidate_min_score
        has_lr_signal = lr_available and lr_pred == 1 and (lr_score or 0.0) > 0.0
        is_candidate = bool(actionable_hits or has_hard or has_ml_signal or has_lr_signal or not tx_visible)

        records.append(
            dict(
                transaction_id=tid,
                revision=rev,
                vendor_id=raw_tx.get("vendor_id", ""),
                employee_id=raw_tx.get("employee_id", ""),
                invoice_number=raw_tx.get("invoice_number", ""),
                invoice_gross_vnd=raw_tx.get("invoice_gross_vnd"),
                contract_id=raw_tx.get("contract_id", ""),
                request_id=raw_tx.get("request_id", ""),
                purchase_order_id=raw_tx.get("purchase_order_id", ""),
                advance_id=raw_tx.get("advance_id", ""),
                payroll_period=raw_tx.get("payroll_period", ""),
                recipient_account=raw_tx.get("recipient_account", ""),
                amount_vnd=int(row["amount_vnd"]),
                event_at=_iso_utc(row["event_at"]),
                knowledge_at=_iso_utc(row["knowledge_at"]),
                tx_visible=tx_visible,
                scorable=bool(tx_visible and (actionable_hits or _is_finite_number(ml_norm) or lr_available)),
                is_candidate=is_candidate,
                role="candidate" if is_candidate else "evidence_only",
                actionable_hits=actionable_hits,
                context_rules=sorted(set(context_hits)),
                master_quality_rules=sorted(set(master_hits)),
                rule_score=rule_points_total if actionable_hits else max_rule_pts,
                hard_trigger=has_hard,
                ml_method=ml_method,
                ml_available=ml_available,
                ml_raw_score=ml_raw,
                ml_normalized_score=float(ml_norm) if _is_finite_number(ml_norm) else None,
                lr_available=lr_available,
                lr_score=lr_score,
                lr_probability=lr_prob,
                lr_prediction=lr_pred,
                lr_threshold=lr_thresh,
                lr_model_version=lr_ver,
                calibrated_fraud_probability=float(cal_prob) if _is_finite_number(cal_prob) else None,
                calibration_status=cal_status,
                related_evidence_tx_ids=sorted(related_prior_tx_ids),
                evidence_refs=evidence_refs,
                weak_graph_context=weak_graph,
                source_gaps=source_gaps,
                has_blocking_source_gap=any(g.get("blocking") for g in source_gaps) or not tx_visible,
            )
        )

    prior_evidence = []
    for tid, tx in sorted(tx_lookup.items()):
        if tid not in candidate_ids_in_analysis:
            prior_evidence.append(
                dict(
                    transaction_id=tid,
                    revision=int(tx.get("revision", 1)),
                    vendor_id=tx.get("vendor_id", ""),
                    invoice_number=tx.get("invoice_number", ""),
                    invoice_gross_vnd=tx.get("invoice_gross_vnd"),
                    contract_id=tx.get("contract_id", ""),
                    advance_id=tx.get("advance_id", ""),
                    amount_vnd=int(tx.get("amount_vnd", 0)),
                    event_at=_iso_utc(tx["posted_at"]),
                    knowledge_at=_iso_utc(tx["observed_at"]),
                    role="prior_payment_evidence",
                )
            )

    return build_case_bundle_from_records(
        tenant_id=scope.tenant_id,
        company_id=company,
        snapshot_binding=dict(analysis["snapshot"], as_of=analysis["as_of"], analysis_id=analysis["analysis_id"]),
        records=records,
        prior_evidence_transactions=prior_evidence,
        source_tables=source_tables,
        method_versions=(analysis.get("bridge_provenance") or {}).get("method_versions") or {},
        model_pins=pins,
        simulated_data=simulated,
    )


def _compute_candidate_score(rec: dict, policy: dict) -> float | None:
    scoring = policy["scoring"]
    scorable = rec.get("scorable")
    if scorable is False or not rec.get("tx_visible", True):
        return None
    rule_pts = rec.get("rule_score")
    ml_val = rec.get("ml_normalized_score")
    if ml_val is None and _is_finite_number(rec.get("ml_raw_score")):
        ml_val = float(rec["ml_raw_score"])
    cal_prob = rec.get("calibrated_fraud_probability")
    lr_val = rec.get("lr_score") if rec.get("lr_available") else None

    has_rule = _is_finite_number(rule_pts) and (bool(rec.get("actionable_hits")) or float(rule_pts) > 0)
    has_ml = _is_finite_number(ml_val)
    has_cal = _is_finite_number(cal_prob) and float(scoring["calibrated_weight"]) > 0
    has_lr = _is_finite_number(lr_val) and float(scoring["calibrated_weight"]) > 0
    if not (has_rule or has_ml or has_cal or has_lr or rec.get("rules_evaluated_no_hit")):
        if scorable is None and not rec.get("ml_available") and not rec.get("lr_available") and not rec.get("actionable_hits"):
            return None

    total = 0.0
    if _is_finite_number(rule_pts):
        total += float(scoring["rule_weight"]) * float(rule_pts)
    if _is_finite_number(ml_val):
        total += float(scoring["ml_weight"]) * float(ml_val)
    if _is_finite_number(cal_prob):
        total += float(scoring["calibrated_weight"]) * float(cal_prob)
    elif _is_finite_number(lr_val):
        total += float(scoring["calibrated_weight"]) * float(lr_val)
    return round(total, 6)


def _compute_financial_summary(
    candidates: list[dict],
    evidence_txs: list[dict],
    allocations: list[dict],
    obligation_id: str,
    inv_lookup: dict[tuple[str, str], dict],
) -> dict:
    seen_tx: dict[str, int] = {}
    for rec in candidates:
        seen_tx[str(rec["transaction_id"])] = int(rec.get("amount_vnd", 0))
    candidate_amount = sum(seen_tx.values())

    ev_seen: dict[str, int] = {}
    for ev_tx in evidence_txs:
        tid = str(ev_tx["transaction_id"])
        if tid not in seen_tx:
            ev_seen[tid] = int(ev_tx.get("amount_vnd", 0))

    # Deduplicated exposure across candidates and direct prior obligation evidence, preserving negative signs.
    all_tx_amounts = {**seen_tx, **ev_seen}
    related_amount = sum(all_tx_amounts.values())
    has_negative = any(amt < 0 for amt in all_tx_amounts.values())

    cand_ids = set(seen_tx)
    ev_ids = set(ev_seen)

    gross_candidates = []
    if obligation_id.startswith("invoice:"):
        parts = obligation_id.split(":", 2)
        if len(parts) == 3:
            inv_rec = inv_lookup.get((parts[1], parts[2]))
            if inv_rec and inv_rec.get("amount_vnd") is not None:
                gross_candidates.append(int(inv_rec["amount_vnd"]))
    for rec in candidates + evidence_txs:
        if rec.get("invoice_gross_vnd") is not None:
            gross_candidates.append(int(rec["invoice_gross_vnd"]))
        for h in rec.get("actionable_hits") or []:
            g = (h.get("evidence") or {}).get("invoice_gross_vnd")
            if g is not None:
                gross_candidates.append(int(g))
    consistent_gross = sorted(set(g for g in gross_candidates if g > 0))
    obligation_gross = consistent_gross[0] if len(consistent_gross) == 1 else None

    # Use explicit allocations deduplicated by (allocation_id/record_id, revision) when supplied.
    relevant_allocs: dict[str, dict] = {}
    for alloc in allocations:
        aid = str(alloc.get("allocation_id") or alloc.get("record_id") or "")
        tx_ref = alloc.get("transaction_id") or (alloc.get("transaction_ref") or {}).get("record_id")
        if tx_ref and (str(tx_ref) in cand_ids or str(tx_ref) in ev_ids):
            if aid:
                relevant_allocs[aid] = alloc
            has_negative = has_negative or int(alloc.get("amount_vnd", 0)) < 0

    if relevant_allocs:
        prior_alloc = sum(
            int(a["amount_vnd"])
            for a in relevant_allocs.values()
            if str(a.get("transaction_id") or (a.get("transaction_ref") or {}).get("record_id")) in ev_ids
        )
        cand_alloc = sum(
            int(a["amount_vnd"])
            for a in relevant_allocs.values()
            if str(a.get("transaction_id") or (a.get("transaction_ref") or {}).get("record_id")) in cand_ids
        )
        net_settled = prior_alloc + cand_alloc
    elif obligation_id.startswith("invoice:"):
        prior_alloc = sum(ev_seen.values()) if ev_seen else 0
        cand_alloc = candidate_amount
        net_settled = prior_alloc + cand_alloc
    else:
        prior_alloc = None
        cand_alloc = None
        net_settled = None

    discrepancy = (
        int(net_settled - obligation_gross)
        if net_settled is not None and obligation_gross is not None
        else None
    )

    return dict(
        currency="VND",
        obligation_gross_vnd=obligation_gross,
        prior_evidence_allocated_vnd=prior_alloc,
        candidate_amount_vnd=int(candidate_amount),
        candidate_allocated_vnd=cand_alloc,
        net_settled_vnd=net_settled,
        related_amount_vnd=int(related_amount),
        discrepancy_amount_vnd=discrepancy,
        confirmed_loss_vnd=None,
        recovered_vnd=None,
        contains_negative_adjustment=has_negative,
    )


def coalesce_cases(bundle: dict, policy: dict) -> list[dict]:
    """Coalesce candidate findings by (tenant, company, problem_family, obligation_id).

    Separates candidates from prior-payment / supporting evidence, preserves signed
    VND adjustments, computes max candidate score (D-05), and creates stable case IDs.
    """
    tenant_id = str(bundle["tenant_id"])
    company_id = str(bundle["company_id"])
    snapshot_binding = deepcopy(bundle.get("snapshot_binding") or {})
    records = list(bundle.get("records") or [])
    prior_txs = list(bundle.get("prior_evidence_transactions") or [])
    source_tables = bundle.get("source_tables") or {}
    allocations = list(source_tables.get("payment_allocations") or [])
    invoices_table = list(source_tables.get("invoices") or [])

    inv_lookup: dict[tuple[str, str], dict] = {}
    for inv in invoices_table:
        if isinstance(inv, dict) and inv.get("kind", "invoice") == "invoice":
            vid = str(inv.get("vendor_id") or (inv.get("vendor_ref") or {}).get("record_id") or "").strip()
            num = _norm_token(inv.get("number") or inv.get("invoice_number") or "")
            if vid and num:
                inv_lookup[(vid, num)] = inv

    all_tx_by_id: dict[str, dict] = {}
    for tx in list(source_tables.get("transactions") or []) + prior_txs + records:
        if isinstance(tx, dict) and tx.get("transaction_id"):
            tid = str(tx["transaction_id"])
            if tid not in all_tx_by_id:
                all_tx_by_id[tid] = tx

    # Partition strictly into candidates vs evidence-only transactions.
    # A prior transaction explicitly flagged role='evidence_only' or is_candidate=False NEVER becomes a candidate.
    candidate_records: list[dict] = []
    evidence_tx_by_id: dict[str, dict] = {
        str(tx["transaction_id"]): deepcopy(tx) for tx in prior_txs if tx.get("transaction_id")
    }
    for rec in records:
        tid = str(rec["transaction_id"])
        role = rec.get("role")
        is_explicit_evidence = role in ("evidence_only", "prior_payment_evidence", "evidence") or rec.get("is_candidate") is False
        has_actionable = bool(rec.get("actionable_hits")) or bool(rec.get("hard_trigger"))
        has_ml_signal = rec.get("is_candidate") is True or (
            _is_finite_number(rec.get("ml_normalized_score")) and rec.get("role") == "candidate"
        )
        unscorable_gap = not rec.get("tx_visible", True) or rec.get("scorable") is False or bool(rec.get("has_blocking_source_gap"))
        if is_explicit_evidence:
            evidence_tx_by_id[tid] = deepcopy(rec)
            continue
        if rec.get("is_candidate") is True or has_actionable or has_ml_signal or unscorable_gap:
            candidate_records.append(rec)
        else:
            # Non-flagged transaction stays eligible ONLY as evidence context, never auto-promoted to candidate.
            evidence_tx_by_id[tid] = deepcopy(rec)

    cand_id_set = {str(r["transaction_id"]) for r in candidate_records}

    # Index obligation docs/allocations by invoice/tx for attachment to case source_links.
    docs_by_tx: dict[str, list[dict]] = {}
    for tname in ("transaction_documents", "supporting_documents"):
        for doc in source_tables.get(tname) or []:
            ref_tx = doc.get("transaction_id") or ((doc.get("links") or [{}])[0].get("record_id") if doc.get("links") else None)
            if ref_tx:
                docs_by_tx.setdefault(str(ref_tx), []).append((tname, doc))

    grouped: dict[tuple[str, str, str, str], dict] = {}
    for rec in candidate_records:
        tid = str(rec["transaction_id"])
        family = _resolve_problem_family(rec)
        obligation_id, grouping_reason = _resolve_obligation_id(rec, family, all_tx_by_id)
        key = (tenant_id, company_id, family, obligation_id)
        bucket = grouped.setdefault(
            key,
            dict(
                tenant_id=tenant_id,
                company_id=company_id,
                problem_family=family,
                obligation_id=obligation_id,
                grouping_reasons=set(),
                candidates=[],
            ),
        )
        bucket["grouping_reasons"].add(grouping_reason)
        bucket["candidates"].append(rec)

    # Also attach any non-candidate transactions sharing exact invoice/obligation of a group strictly as evidence_txs.
    cases_out = []
    for (tid_tenant, tid_comp, family, obligation_id), bucket in sorted(grouped.items()):
        cands = sorted(bucket["candidates"], key=lambda r: (_iso_utc(r["event_at"]), str(r["transaction_id"]), int(r.get("revision", 1))))
        cid_list = [str(r["transaction_id"]) for r in cands]
        cand_revs = [dict(record_id=str(r["transaction_id"]), revision=int(r.get("revision", 1))) for r in cands]

        attached_ev_txs: dict[str, dict] = {}
        for r in cands:
            for rtid in r.get("related_evidence_tx_ids") or []:
                rtid_s = str(rtid)
                if rtid_s not in cand_id_set and rtid_s in all_tx_by_id:
                    attached_ev_txs[rtid_s] = all_tx_by_id[rtid_s]
            for h in r.get("actionable_hits") or []:
                for rtid in h.get("related_transaction_ids") or []:
                    rtid_s = str(rtid)
                    if rtid_s not in cand_id_set and rtid_s in all_tx_by_id:
                        attached_ev_txs[rtid_s] = all_tx_by_id[rtid_s]

        # Match any prior evidence txs bound directly to this exact invoice/advance/obligation.
        if obligation_id.startswith("invoice:"):
            parts = obligation_id.split(":", 2)
            target_vid, target_inv = parts[1], parts[2]
            for ev_tid, ev_tx in evidence_tx_by_id.items():
                if ev_tid in cand_id_set:
                    continue
                ev_vid = str(ev_tx.get("vendor_id") or "").strip()
                ev_inv = _norm_token(ev_tx.get("invoice_number") or "")
                if ev_inv and ev_inv == target_inv and (not target_vid or ev_vid == target_vid):
                    attached_ev_txs[ev_tid] = ev_tx
        elif obligation_id.startswith("advance:"):
            target_adv = obligation_id.split(":", 1)[1]
            for ev_tid, ev_tx in evidence_tx_by_id.items():
                if ev_tid not in cand_id_set and str(ev_tx.get("advance_id") or "").strip() == target_adv:
                    attached_ev_txs[ev_tid] = ev_tx

        evidence_tx_list = [attached_ev_txs[k] for k in sorted(attached_ev_txs)]
        evidence_tx_ids = sorted(attached_ev_txs)

        source_links_by_key: dict[tuple[str, str, int | None, str], dict] = {}
        evidence_ids = set()

        def add_link(table: str, record_id: str, revision: int | None, role: str, extra: dict | None = None):
            k = (table, record_id, revision, role)
            item = dict(table=table, record_id=record_id, revision=revision, role=role)
            if extra:
                item.update(extra)
            source_links_by_key[k] = item
            evidence_ids.add(f"{table}:{record_id}")

        for r in cands:
            add_link("transactions", str(r["transaction_id"]), int(r.get("revision", 1)), "candidate")
            for ref in r.get("evidence_refs") or []:
                add_link(
                    str(ref.get("table", "source")),
                    str(ref["record_id"]),
                    ref.get("revision"),
                    str(ref.get("role", "supporting_document")),
                )
            for eid in r.get("explicit_evidence_ids") or []:
                evidence_ids.add(str(eid))
            for tname, doc in docs_by_tx.get(str(r["transaction_id"]), []):
                doc_id = str(doc.get("document_id") or doc.get("record_id") or doc.get("evidence_id") or "")
                if doc_id:
                    add_link(tname, doc_id, doc.get("revision"), "supporting_document")

        for ev_tid, ev_tx in attached_ev_txs.items():
            add_link("transactions", ev_tid, int(ev_tx.get("revision", 1)), "prior_payment_evidence")
            for tname, doc in docs_by_tx.get(ev_tid, []):
                doc_id = str(doc.get("document_id") or doc.get("record_id") or doc.get("evidence_id") or "")
                if doc_id:
                    add_link(tname, doc_id, doc.get("revision"), "supporting_document")

        if obligation_id.startswith("invoice:"):
            parts = obligation_id.split(":", 2)
            inv_rec = inv_lookup.get((parts[1], parts[2]))
            if inv_rec:
                add_link("invoices", str(inv_rec.get("record_id") or inv_rec.get("invoice_id") or parts[2]), inv_rec.get("revision"), "obligation_source")
            else:
                add_link("obligations", obligation_id, None, "obligation_source")
        elif obligation_id:
            add_link("obligations", obligation_id, None, "obligation_source")

        for alloc in allocations:
            tx_ref = str(alloc.get("transaction_id") or (alloc.get("transaction_ref") or {}).get("record_id") or "")
            if tx_ref in cand_id_set or tx_ref in attached_ev_txs:
                aid = str(alloc.get("allocation_id") or alloc.get("record_id") or "")
                if aid:
                    add_link("payment_allocations", aid, alloc.get("revision"), "allocation_source")

        # Scoring: D-05 max_candidate_score; evidence NEVER increases score.
        cand_scores = []
        cand_cal_probs = []
        for r in cands:
            s = _compute_candidate_score(r, policy)
            if s is not None:
                cand_scores.append((s, str(r["transaction_id"])))
            if _is_finite_number(r.get("calibrated_fraud_probability")) and r.get("calibration_status") == "calibrated":
                cand_cal_probs.append(float(r["calibrated_fraud_probability"]))

        scorable = bool(cand_scores)
        case_score = max(s for s, _ in cand_scores) if scorable else None
        cal_prob = max(cand_cal_probs) if cand_cal_probs else None

        actionable_rules = sorted({h["rule_id"] for r in cands for h in (r.get("actionable_hits") or [])})
        context_rules = sorted({c for r in cands for c in (r.get("context_rules") or [])})
        master_rules = sorted({m for r in cands for m in (r.get("master_quality_rules") or [])})
        hard_trigger = any(bool(r.get("hard_trigger")) for r in cands)

        all_gaps = []
        seen_gap_keys = set()
        for r in cands:
            for g in r.get("source_gaps") or []:
                gk = (g.get("rule_id"), g.get("reason"))
                if gk not in seen_gap_keys:
                    seen_gap_keys.add(gk)
                    all_gaps.append(deepcopy(g))

        has_blocking_gap = any(bool(r.get("has_blocking_source_gap")) for r in cands) or any(
            bool(g.get("blocking")) for g in all_gaps
        )
        explicit_ev_suff = [r.get("evidence_sufficient") for r in cands if r.get("evidence_sufficient") is not None]
        if explicit_ev_suff:
            evidence_sufficient = all(explicit_ev_suff) and not has_blocking_gap
        else:
            evidence_sufficient = not has_blocking_gap

        weak_links = []
        seen_weak = set()
        for r in cands:
            wg = r.get("weak_graph_context") or {}
            for lk in wg.get("links") or []:
                lk_dig = digest(canonical(lk))
                if lk_dig not in seen_weak:
                    seen_weak.add(lk_dig)
                    weak_links.append(deepcopy(lk))

        financial_summary = _compute_financial_summary(cands, evidence_tx_list, allocations, obligation_id, inv_lookup)
        cid_stable = stable_case_id(tid_tenant, tid_comp, family, obligation_id)

        quantized_score = (
            round(float(case_score), 6) if case_score is not None else None
        )
        material_payload = dict(
            tenant_id=tid_tenant,
            company_id=tid_comp,
            problem_family=family,
            obligation_id=obligation_id,
            candidate_ids=sorted(cid_list),
            candidate_revisions=sorted(cand_revs, key=lambda x: (x["record_id"], x["revision"])),
            evidence_tx_ids=sorted(evidence_tx_ids),
            actionable_rule_ids=actionable_rules,
            hard_trigger=hard_trigger,
            scorable=scorable,
            evidence_sufficient=evidence_sufficient,
            has_blocking_source_gap=has_blocking_gap,
            blocking_gap_reasons=sorted({str(g.get("reason")) for g in all_gaps if g.get("blocking")}),
            financial_core=dict(
                obligation_gross_vnd=financial_summary["obligation_gross_vnd"],
                net_settled_vnd=financial_summary["net_settled_vnd"],
                discrepancy_amount_vnd=financial_summary["discrepancy_amount_vnd"],
                candidate_amount_vnd=financial_summary["candidate_amount_vnd"],
            ),
            case_score_value=quantized_score,
        )

        cases_out.append(
            dict(
                case_id=cid_stable,
                tenant_id=tid_tenant,
                company_id=tid_comp,
                problem_family=family,
                obligation_id=obligation_id,
                grouping_key=f"{tid_tenant}|{tid_comp}|{family}|{obligation_id}",
                grouping_reason=" ".join(sorted(bucket["grouping_reasons"])),
                candidate_ids=sorted(cid_list),
                candidate_revisions=sorted(cand_revs, key=lambda x: (x["record_id"], x["revision"])),
                evidence_tx_ids=sorted(evidence_tx_ids),
                evidence_ids=sorted(evidence_ids),
                source_links=[
                    source_links_by_key[k]
                    for k in sorted(source_links_by_key, key=lambda item: (str(item[0]), str(item[1]), -1 if item[2] is None else int(item[2]), str(item[3])))
                ],
                weak_graph_context=dict(
                    note="Quan hệ đồ thị/NCC yếu chỉ làm bối cảnh; không tự gộp vụ hoặc tăng điểm.",
                    links=weak_links,
                    master_quality_rules=master_rules,
                ),
                actionable_rule_ids=actionable_rules,
                context_rule_ids=context_rules,
                master_quality_rule_ids=master_rules,
                hard_trigger=hard_trigger,
                scorable=scorable,
                case_score=case_score,
                calibrated_fraud_probability=cal_prob,
                score_breakdown=dict(
                    aggregation="max_candidate_score",
                    evidence_bonus_applied=0.0,
                    per_candidate=[
                        dict(
                            transaction_id=str(r["transaction_id"]),
                            rule_score=r.get("rule_score"),
                            ml_score=r.get("ml_normalized_score") if r.get("ml_normalized_score") is not None else r.get("ml_raw_score"),
                            lr_score=r.get("lr_score") if r.get("lr_available") else None,
                            lr_probability=r.get("lr_probability") if r.get("lr_available") else None,
                            lr_prediction=r.get("lr_prediction") if r.get("lr_available") else None,
                            lr_threshold=r.get("lr_threshold") if r.get("lr_available") else None,
                            lr_model_version=r.get("lr_model_version") if r.get("lr_available") else None,
                            candidate_score=_compute_candidate_score(r, policy),
                        )
                        for r in cands
                    ],
                ),
                evidence_sufficient=evidence_sufficient,
                has_blocking_source_gap=has_blocking_gap,
                source_gaps=all_gaps,
                financial_summary=financial_summary,
                first_candidate_event_at=min(_iso_utc(r["event_at"]) for r in cands),
                last_candidate_event_at=max(_iso_utc(r["event_at"]) for r in cands),
                snapshot_binding=deepcopy(snapshot_binding),
                method_versions=deepcopy(bundle.get("method_versions") or {}),
                model_pins=deepcopy(bundle.get("model_pins") or {}),
                material_fingerprint=digest(canonical(material_payload)),
            )
        )

    cases_out.sort(key=lambda c: (c["first_candidate_event_at"], c["case_id"]))
    return cases_out


def evaluate_material_change(prev_revision: dict | None, current_case: dict, policy: dict) -> tuple[bool, dict]:
    """Compare incoming coalesced case against previous revision to avoid non-material churn.

    Snapshot ID / run ID / row ordering / sub-threshold score noise alone NEVER trigger a resend.
    """
    if prev_revision is None:
        return True, dict(
            is_material_change=True,
            reasons=["initial_case_revision"],
            added_candidates=list(current_case["candidate_ids"]),
            removed_candidates=[],
            added_evidence=[],
            removed_evidence=[],
            score_delta=current_case["case_score"],
            financial_changed=False,
        )

    min_delta = float(policy["material_change"]["min_score_delta"])
    prev_cands = set(prev_revision.get("candidate_ids") or [])
    curr_cands = set(current_case["candidate_ids"])
    prev_ev_tx = set(prev_revision.get("evidence_tx_ids") or [])
    curr_ev_tx = set(current_case["evidence_tx_ids"])
    prev_rules = set(prev_revision.get("actionable_rule_ids") or [])
    curr_rules = set(current_case["actionable_rule_ids"])

    prev_fin = (prev_revision.get("financial_summary") or {})
    curr_fin = current_case["financial_summary"]
    fin_keys = ("obligation_gross_vnd", "net_settled_vnd", "discrepancy_amount_vnd", "candidate_amount_vnd")
    fin_changed = any(prev_fin.get(k) != curr_fin.get(k) for k in fin_keys)

    prev_gaps = sorted({str(g.get("reason")) for g in prev_revision.get("source_gaps") or [] if g.get("blocking")})
    curr_gaps = sorted({str(g.get("reason")) for g in current_case.get("source_gaps") or [] if g.get("blocking")})
    gap_changed = prev_gaps != curr_gaps or bool(prev_revision.get("evidence_sufficient")) != bool(current_case["evidence_sufficient"])

    prev_score = prev_revision.get("case_score")
    curr_score = current_case["case_score"]
    score_delta = (
        round(float(curr_score) - float(prev_score), 6)
        if _is_finite_number(prev_score) and _is_finite_number(curr_score)
        else None
    )
    material_score_shift = (
        (prev_score is None) != (curr_score is None)
        or (score_delta is not None and abs(score_delta) >= min_delta)
    )
    hard_changed = bool(prev_revision.get("hard_trigger")) != bool(current_case["hard_trigger"])

    reasons = []
    if prev_cands != curr_cands:
        reasons.append("candidate_membership_changed")
    if prev_ev_tx != curr_ev_tx:
        reasons.append("evidence_transactions_changed")
    if prev_rules != curr_rules:
        reasons.append("actionable_rules_changed")
    if fin_changed:
        reasons.append("obligation_or_financial_delta_changed")
    if gap_changed:
        reasons.append("source_sufficiency_changed")
    if hard_changed:
        reasons.append("hard_trigger_changed")
    if material_score_shift:
        reasons.append("material_score_delta")

    is_material = bool(reasons)
    return is_material, dict(
        is_material_change=is_material,
        reasons=reasons if reasons else ["non_material_snapshot_or_noise_delta_only"],
        added_candidates=sorted(curr_cands - prev_cands),
        removed_candidates=sorted(prev_cands - curr_cands),
        added_evidence=sorted(curr_ev_tx - prev_ev_tx),
        removed_evidence=sorted(prev_ev_tx - curr_ev_tx),
        score_delta=score_delta,
        financial_changed=fin_changed,
    )
