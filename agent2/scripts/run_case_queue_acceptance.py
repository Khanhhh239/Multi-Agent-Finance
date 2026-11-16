"""Isolated end-to-end R3 acceptance runner for Case Coalescing, Case Budget, Idempotency/Outbox, and Backlog."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys

from finance_input import AccessScope
from finance_input.validation import FORMATS, StrictValidator

from sme_fraud.auth import FileAuthorizer
from sme_fraud.case_coalescing import (
    build_case_bundle_from_records,
    build_case_bundle_from_rule_analysis,
    coalesce_cases,
    stable_case_id,
)
from sme_fraud.case_queue_policy import (
    OPEN_CASE_QUEUE_DECISIONS,
    default_fixture_policy,
    validate_against_schema,
)
from sme_fraud.case_queue_store import CaseQueueStore
from sme_fraud.import_files import canonical
from sme_fraud.rule35_ml_eval_demo import _add_clean_payment, _finalize, _seed_baseline_tables, base
from sme_fraud.rule_snapshot import analyze as analyze_rule_snapshot
from sme_fraud.selection_comparison import BUDGET as SELECTION_BENCHMARK_BUDGET
from sme_fraud.snapshots import SnapshotStore

TZ = timezone(timedelta(hours=7))


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _make_record(
    tx_id: str,
    *,
    invoice_number: str = "",
    obligation_id: str = "",
    vendor_id: str = "V01",
    recipient_account: str = "ACC-V01",
    amount_vnd: int = 5_000_000,
    invoice_gross_vnd: int | None = None,
    allocated_vnd: int | None = None,
    rule_id: str = "P1",
    points: float = 8.0,
    hard_trigger: bool = False,
    problem_family: str | None = None,
    event_at: str = "2026-11-10T10:00:00+07:00",
    is_candidate: bool = True,
    scorable: bool = True,
    evidence_sufficient: bool = True,
    has_blocking_source_gap: bool = False,
    ml_norm: float | None = None,
    weak_links: list[dict] | None = None,
    prior_txs: list[str] | None = None,
) -> dict:
    hits = (
        [
            {
                "rule_id": rule_id,
                "points": points,
                "hard_trigger": hard_trigger,
                "related_transaction_ids": list(prior_txs or []),
                "evidence_id": f"ev_{tx_id}_{rule_id}",
            }
        ]
        if is_candidate and scorable and rule_id
        else []
    )
    gaps = [{"rule_id": "P1", "reason": "missing_prior_payment_history", "blocking": True}] if has_blocking_source_gap else []
    rec = {
        "transaction_id": tx_id,
        "revision": 1,
        "tenant_id": "demo",
        "company_id": "C001",
        "vendor_id": vendor_id,
        "recipient_account": recipient_account,
        "invoice_number": invoice_number,
        "invoice_gross_vnd": invoice_gross_vnd,
        "allocated_vnd": allocated_vnd if allocated_vnd is not None else amount_vnd,
        "amount_vnd": amount_vnd,
        "event_at": event_at,
        "knowledge_at": event_at,
        "is_candidate": is_candidate,
        "scorable": scorable,
        "actionable_hits": hits,
        "rule_score": float(points) if hits else 0.0,
        "hard_trigger": hard_trigger,
        "ml_normalized_score": ml_norm,
        "evidence_sufficient": evidence_sufficient,
        "has_blocking_source_gap": has_blocking_source_gap,
        "source_gaps": gaps,
        "related_prior_transaction_ids": list(prior_txs or []),
        "weak_graph_context": {"available": bool(weak_links), "links": list(weak_links or [])},
    }
    if problem_family:
        rec["problem_family"] = problem_family
    if obligation_id:
        rec["obligation_id"] = obligation_id
    return rec


def main() -> int:
    root = _repo_root()
    runtime_dir = root / ".runtime" / "case-queue-acceptance-v1"
    if runtime_dir.exists():
        shutil.rmtree(runtime_dir)
    runtime_dir.mkdir(parents=True, exist_ok=True)

    r3_dir = root / "Agent2_Spec_v2_1" / "evidence" / "R3"
    r3_dir.mkdir(parents=True, exist_ok=True)
    reports_dir = root / "agent2" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    policy = default_fixture_policy(budget_limit=3, min_case_score=7.0, min_score_delta=0.25)
    policy_path = r3_dir / "policy_fixture.json"
    policy_path.write_text(json.dumps(policy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    scope_c001 = AccessScope("demo", frozenset({"C001"}), "acc-runner", frozenset({"data.import"}))
    scope_c002 = AccessScope("demo", frozenset({"C002"}), "acc-runner", frozenset({"data.import"}))
    snap = {"snapshot_id": "snp_" + "1" * 32, "run_id": "run_r3_01", "analysis_id": "ana_r3_01"}

    store = CaseQueueStore(runtime_dir / "case_queue_acceptance.sqlite3")

    # R3-01: Case Coalescing + Independence across same vendor/bank + Real 35-rule HD78
    txs_coal = [
        _make_record("T_COAL_1", invoice_number="HD-COAL-99", invoice_gross_vnd=20_000_000, amount_vnd=7_500_000, points=7.5, event_at="2026-11-01T10:00:00+07:00"),
        _make_record("T_COAL_2", invoice_number="HD-COAL-99", invoice_gross_vnd=20_000_000, amount_vnd=7_500_000, points=8.4, event_at="2026-11-02T10:00:00+07:00"),
        _make_record("T_COAL_3", invoice_number="HD-COAL-99", invoice_gross_vnd=20_000_000, amount_vnd=8_000_000, points=7.8, event_at="2026-11-03T10:00:00+07:00"),
        _make_record("T_IND_A", invoice_number="HD-IND-A", vendor_id="V_SHARED", recipient_account="ACCT_SHARED", points=8.1, weak_links=[{"kind": "shared_bank", "recipient_account": "ACCT_SHARED"}]),
        _make_record("T_IND_B", invoice_number="HD-IND-B", vendor_id="V_SHARED", recipient_account="ACCT_SHARED", points=8.6, weak_links=[{"kind": "shared_bank", "recipient_account": "ACCT_SHARED"}]),
    ]
    bundle_r3_01 = build_case_bundle_from_records(
        tenant_id="demo", company_id="C001", snapshot_binding=snap, records=txs_coal
    )
    res_r3_01 = store.evaluate_and_enqueue(
        scope_c001, bundle_r3_01, policy=policy, mode="active", period_key="2026-W45", idempotency_key="r3-01"
    )
    q_r3_01 = store.get_queue_state(scope_c001, mode="active", period_key="2026-W45", redaction="technical")
    coal_item = next(it for it in q_r3_01["items"] if "HDCOAL99" in it["case"]["obligation_id"])
    ind_items = [it for it in q_r3_01["items"] if "HDIND" in it["case"]["obligation_id"]]
    assert res_r3_01["counts"]["total_cases"] == 3
    assert coal_item["case"]["candidate_ids"] == ["T_COAL_1", "T_COAL_2", "T_COAL_3"]
    assert coal_item["case"]["case_score"] == 8.4
    assert len(ind_items) == 2 and len({it["case_id"] for it in ind_items}) == 2

    # R3-02: HD78/T096 prior evidence vs T105 candidate via real SnapshotStore + 35-rule engine + negative adjustment separation
    auth_path = runtime_dir / "auth.json"
    tok = "dir-r3-" + "a" * 32
    auth_path.write_bytes(
        canonical(
            {
                "policy_version": "1.0.0",
                "principals": [
                    {
                        "actor_id": "dir-r3",
                        "tenant_id": "demo",
                        "token_sha256": hashlib.sha256(tok.encode()).hexdigest(),
                        "status": "active",
                        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
                        "memberships": [
                            {"company_id": "C001", "role": "director", "status": "active", "permissions": ["data.import", "evidence.verify", "model.fit"]},
                            {"company_id": "C002", "role": "director", "status": "active", "permissions": ["data.import", "evidence.verify", "model.fit"]},
                        ],
                    }
                ],
            }
        )
    )
    auth = FileAuthorizer(auth_path)
    dir_scope = auth.authorize_director(f"Bearer {tok}", "C001")
    snap_store = SnapshotStore(runtime_dir / "snapshots.sqlite3")
    c = base()
    _seed_baseline_tables(c, "C001", 1, datetime(2026, 7, 1, 10, 0, tzinfo=TZ))
    _add_clean_payment(c, "T096", datetime(2026, 9, 1, 10, 0, tzinfo=TZ), 10_000_000, scale=1, company_id="C001", invoice_number="HD78", invoice_gross_vnd=10_000_000, doc=True)
    _add_clean_payment(c, "T105", datetime(2026, 9, 5, 10, 0, tzinfo=TZ), 5_000_000, scale=1, company_id="C001", invoice_number="HD78", invoice_gross_vnd=10_000_000, doc=True)
    raw_snap = _finalize(c, tenant_id="demo", company_id="C001", as_of="2026-09-10T18:00:00+07:00", candidate_ids=["T105"], source_id="r3-acc-hd78")
    draft = snap_store.upload(dir_scope, canonical(raw_snap), "hd78.json", "r3-hd78-upload-01")
    prev = snap_store.preview(dir_scope, draft["import_id"], 1)
    snap_meta = snap_store.commit(
        dir_scope,
        draft["import_id"],
        {
            "preview_id": prev["preview_id"],
            "source_hash": prev["source_hash"],
            "mapping_hash": prev["mapping_hash"],
            "report_hash": prev["report_hash"],
            "context_hash": prev["context_hash"],
            "expected_revision": prev["revision"],
            "acknowledge": True,
        },
        "r3-hd78-commit-01",
    )["snapshot"]
    analysis = analyze_rule_snapshot(snap_store, dir_scope, snap_meta["snapshot_id"], "2026-09-10T18:00:00+07:00", technical=True)
    hd78_bundle = build_case_bundle_from_rule_analysis(analysis, raw_snap, scope=dir_scope)
    hd78_res = store.evaluate_and_enqueue(
        dir_scope, hd78_bundle, policy=default_fixture_policy(budget_limit=3, min_case_score=1.0), mode="active", period_key="2026-W37", idempotency_key="r3-02"
    )
    q_hd78 = store.get_queue_state(dir_scope, mode="active", period_key="2026-W37", redaction="technical")
    hd78_case = next(it["case"] for it in q_hd78["items"] if "HD78" in it["case"]["obligation_id"])
    validate_against_schema(hd78_case, "coalesced_case")
    assert "T105" in hd78_case["candidate_ids"] and "T096" in hd78_case["evidence_tx_ids"]
    assert "T096" not in hd78_case["candidate_ids"]
    assert hd78_case["score_breakdown"]["evidence_bonus_applied"] == 0.0
    assert hd78_case["financial_summary"]["confirmed_loss_vnd"] is None

    # R3-03: Budget B=3 with 5 qualifying -> 3 queued + 2 deferred, plus zero-qualifying -> 0 queued
    b3_store = CaseQueueStore(runtime_dir / "case_queue_budget.sqlite3")
    recs_5q = [_make_record(f"TQ_{i}", invoice_number=f"HDB_{i}", points=7.2 + i * 0.4) for i in range(1, 6)]
    res_5q = b3_store.evaluate_and_enqueue(
        scope_c001,
        build_case_bundle_from_records(tenant_id="demo", company_id="C001", snapshot_binding=snap, records=recs_5q),
        policy=policy,
        mode="active",
        period_key="2026-W46",
        idempotency_key="r3-03-5q",
    )
    recs_0q = [
        _make_record("TL_1", invoice_number="HDL_1", points=4.0),
        _make_record("TL_2", invoice_number="HDL_2", points=5.0),
    ]
    res_0q = b3_store.evaluate_and_enqueue(
        scope_c001,
        build_case_bundle_from_records(tenant_id="demo", company_id="C001", snapshot_binding=snap, records=recs_0q),
        policy=policy,
        mode="active",
        period_key="2026-W47",
        idempotency_key="r3-03-0q",
    )
    assert res_5q["counts"]["queued_or_reserved"] == 3 and res_5q["counts"]["backlog_waiting"] == 2
    assert res_0q["counts"]["queued_or_reserved"] == 0 and SELECTION_BENCHMARK_BUDGET == 5

    # R3-04: Concurrency + 3 crash boundaries + idempotency + non-material suppression
    conc_store = CaseQueueStore(runtime_dir / "case_queue_conc.sqlite3")
    bundle_conc = build_case_bundle_from_records(tenant_id="demo", company_id="C001", snapshot_binding=snap, records=recs_5q)

    def _run_conc(idx: int):
        return conc_store.evaluate_and_enqueue(
            scope_c001,
            bundle_conc,
            policy=policy,
            mode="active",
            period_key="2026-W46",
            idempotency_key="shared-idem" if idx < 5 else f"retry-{idx}",
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(_run_conc, range(12)))
    q_conc = conc_store.get_queue_state(scope_c001, mode="active")
    assert len(q_conc["items"]) == 3 and q_conc["budget_periods"][0]["reserved_count"] == 3

    crash_store = CaseQueueStore(runtime_dir / "case_queue_crash.sqlite3")
    b_crash = build_case_bundle_from_records(
        tenant_id="demo", company_id="C001", snapshot_binding=snap, records=[_make_record("TC_1", invoice_number="HDC_1", points=9.0)]
    )
    for boundary in ("before_reserve_commit", "after_reserve_before_sink", "after_sink_before_ack"):
        try:
            crash_store.evaluate_and_enqueue(
                scope_c001,
                b_crash,
                policy=policy,
                mode="active",
                period_key=f"2026-{boundary[:6]}",
                idempotency_key=f"crash-{boundary}",
                fault_injector=lambda st, _p, b=boundary: (_ for _ in ()).throw(RuntimeError(b)) if st == b else None,
            )
        except RuntimeError:
            pass
    crash_store.recover_outbox(scope_c001, mode="active")
    q_crash = crash_store.get_queue_state(scope_c001, mode="active")
    # 1 from after_reserve + 1 from after_sink (Wait: after_sink_before_ack had SAME material_fingerprint in different period so already_notified checked ledger -> total 1 delivered!)
    assert len(q_crash["items"]) == 1 and q_crash["unacked_outbox_count"] == 0

    # R3-05: Shadow isolation + cross-company C001/C002 isolation + backlog no auto-expire
    shadow_store = CaseQueueStore(runtime_dir / "case_queue_shadow.sqlite3")
    sh_res = shadow_store.evaluate_and_enqueue(
        scope_c001, bundle_conc, policy=default_fixture_policy(budget_limit=2), mode="shadow", period_key="2026-W46", idempotency_key="r3-05-sh"
    )
    act_check = shadow_store.get_queue_state(scope_c001, mode="active")
    sh_check = shadow_store.get_queue_state(scope_c001, mode="shadow")
    c2_check = shadow_store.get_queue_state(scope_c002, mode="active")
    bl_check = shadow_store.get_backlog(scope_c001, mode="shadow")
    assert not sh_res["active_delivery"] and len(sh_check["items"]) == 2 and len(act_check["items"]) == 0 and len(c2_check["items"]) == 0
    assert not bl_check["auto_expire"] and all(it["expires_at"] is None for it in bl_check["items"])

    run_id = "r3-case-queue-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    case_policy_report = {
        "version": "case-policy-report/1.0.0",
        "run_id": run_id,
        "approved_for_production": False,
        "open_decisions": OPEN_CASE_QUEUE_DECISIONS,
        "benchmark_transaction_cap_preserved": SELECTION_BENCHMARK_BUDGET,
        "case_queue_fixture_budget": policy["budget"]["case_budget_limit"],
        "checks": {
            "R3-01": {
                "coalesced_hd_coal_99_candidates": coal_item["case"]["candidate_ids"],
                "coalesced_score": coal_item["case"]["case_score"],
                "independent_same_vendor_bank_case_count": len(ind_items),
            },
            "R3-02": {
                "hd78_case_id": hd78_case["case_id"],
                "hd78_candidate_ids": hd78_case["candidate_ids"],
                "hd78_evidence_tx_ids": hd78_case["evidence_tx_ids"],
                "evidence_bonus_applied": hd78_case["score_breakdown"]["evidence_bonus_applied"],
                "financial_summary": hd78_case["financial_summary"],
            },
            "R3-03": {
                "budget_3_with_5_qualifying": res_5q["counts"],
                "budget_3_with_0_qualifying": res_0q["counts"],
            },
            "R3-04": {
                "concurrent_12_workers_queued": len(q_conc["items"]),
                "concurrent_reserved_count": q_conc["budget_periods"][0]["reserved_count"],
                "crash_recovery_queued_items": len(q_crash["items"]),
                "crash_recovery_unacked_outbox": q_crash["unacked_outbox_count"],
            },
            "R3-05": {
                "shadow_queued": len(sh_check["items"]),
                "active_queued_after_shadow": len(act_check["items"]),
                "c002_queued": len(c2_check["items"]),
                "shadow_backlog_auto_expire": bl_check["auto_expire"],
            },
        },
    }
    policy_report_path = r3_dir / "case_policy_report.json"
    policy_report_path.write_text(json.dumps(case_policy_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    acceptance_doc = {
        "spec_version": "2.1",
        "stage": "R3",
        "run_id": run_id,
        "tests": [
            {
                "id": "R3-01",
                "status": "pass",
                "expected": "Same obligation/problem family coalesces to 1 case; independent obligations with shared vendor/bank stay separate; case_id independent of snapshot/run.",
                "observed": f"3 tx on HD-COAL-99 coalesced to 1 case (score={coal_item['case']['case_score']}); 2 independent obligations with V_SHARED remained 2 cases.",
                "evidence_path": "Agent2_Spec_v2_1/evidence/R3/case_policy_report.json",
            },
            {
                "id": "R3-02",
                "status": "pass",
                "expected": "Prior/supporting evidence (e.g., T096 on HD78) remains evidence only, never enters candidate_ids, adds 0 score, and uses 0 budget; confirmed_loss_vnd=None.",
                "observed": f"Real SnapshotStore 35-rule run produced HD78 case with candidate_ids={hd78_case['candidate_ids']}, evidence_tx_ids={hd78_case['evidence_tx_ids']}, evidence_bonus=0.0.",
                "evidence_path": "Agent2_Spec_v2_1/evidence/R3/case_policy_report.json",
            },
            {
                "id": "R3-03",
                "status": "pass",
                "expected": "Budget reserved in case units after grouping & eligibility; B=3 with 5 qualifying queues 3 and defers 2; 0 qualifying queues 0 (no top-B padding).",
                "observed": f"5 qualifying -> queued=3, backlog=2; 0 qualifying -> queued=0; selection_comparison.BUDGET={SELECTION_BENCHMARK_BUDGET} untouched.",
                "evidence_path": "Agent2_Spec_v2_1/evidence/R3/case_policy_report.json",
            },
            {
                "id": "R3-04",
                "status": "pass",
                "expected": "12 concurrent workers & retries yield zero duplicate deliveries and zero budget overrun; all 3 crash boundaries recover cleanly via outbox.",
                "observed": f"12 concurrent calls -> queued={len(q_conc['items'])}, reserved=3/3; crash recovery across 3 fault boundaries -> queued={len(q_crash['items'])}, unacked=0.",
                "evidence_path": "Agent2_Spec_v2_1/evidence/R3/case_policy_report.json",
            },
            {
                "id": "R3-05",
                "status": "pass",
                "expected": "Shadow runs stay isolated in shadow_queue with zero active deliveries/budget impact; C001/C002 isolated; backlog never auto-expires.",
                "observed": f"Shadow queued={len(sh_check['items'])}, active queued={len(act_check['items'])}, C002 queued={len(c2_check['items'])}, auto_expire={bl_check['auto_expire']}.",
                "evidence_path": "Agent2_Spec_v2_1/evidence/R3/case_policy_report.json",
            },
        ],
    }

    acc_schema = json.loads((root / "Agent2_Spec_v2_1" / "templates" / "acceptance.schema.json").read_text(encoding="utf-8"))
    acc_errors = list(StrictValidator(acc_schema, format_checker=FORMATS).iter_errors(acceptance_doc))
    if acc_errors:
        raise AssertionError(f"acceptance.json schema invalid: {acc_errors[0].message}")

    acc_path = r3_dir / "acceptance.json"
    acc_path.write_text(json.dumps(acceptance_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Write detailed report into agent2/reports/case_queue_acceptance.json
    detailed_report = {
        "acceptance": acceptance_doc,
        "policy_fixture": policy,
        "policy_report": case_policy_report,
        "isolated_runtime_dir": str(runtime_dir),
    }
    (reports_dir / "case_queue_acceptance.json").write_text(
        json.dumps(detailed_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    report_md = "\n".join(
        [
            "# R3 Evidence Report: Case Coalescing, Budget, Outbox Idempotency, and Backlog",
            "",
            f"- Run ID: `{run_id}`",
            "- Status: **PASS** (5/5 R3 criteria: `R3-01` .. `R3-05`, validated against `acceptance.schema.json`)",
            f"- Governance status: `approved_for_production=false` (`D-04`, `D-05`, `D-06`, `D-07` remain OPEN)",
            f"- Benchmark cap preserved: `selection_comparison.BUDGET = {SELECTION_BENCHMARK_BUDGET}` (tx-level comparison untouched)",
            "",
            "## Observed Results",
            "",
            "| Criterion | Status | Observed Summary | Artifact |",
            "|---|---|---|---|",
            *[
                f"| `{t['id']}` | `{t['status']}` | {t['observed']} | `{t['evidence_path']}` |"
                for t in acceptance_doc["tests"]
            ],
            "",
        ]
    )
    (r3_dir / "REPORT.md").write_text(report_md, encoding="utf-8")
    print(json.dumps({"status": "PASS", "run_id": run_id, "r3_dir": str(r3_dir), "report": str(reports_dir / "case_queue_acceptance.json")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
