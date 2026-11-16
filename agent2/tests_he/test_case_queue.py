"""Comprehensive acceptance, concurrency, crash-recovery, isolation, and RBAC tests for Agent2 R3 Case Queue."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import http.client
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from finance_input import AccessScope
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
    validate_policy,
)
from sme_fraud.case_queue_store import APPLICATION_ID, CaseQueueStore
from sme_fraud.import_files import ImportFailure, canonical
from sme_fraud.review_server import make_server
from sme_fraud.rule35_ml_eval_demo import _add_clean_payment, _finalize, _seed_baseline_tables, base
from sme_fraud.rule_snapshot import analyze as analyze_rule_snapshot
from sme_fraud.selection_comparison import BUDGET as SELECTION_BENCHMARK_BUDGET
from sme_fraud.snapshots import SnapshotStore

TZ = timezone(timedelta(hours=7))


def _write_auth_file(path: Path, director_token: str, accountant_token: str, c001_only_token: str) -> None:
    exp = (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat()
    doc = {
        "policy_version": "1.0.0",
        "principals": [
            {
                "actor_id": "dir-1",
                "tenant_id": "demo",
                "token_sha256": hashlib.sha256(director_token.encode()).hexdigest(),
                "status": "active",
                "expires_at": exp,
                "memberships": [
                    {
                        "company_id": c,
                        "role": "director",
                        "status": "active",
                        "permissions": ["data.import", "evidence.verify", "model.fit"],
                    }
                    for c in ("C001", "C002")
                ],
            },
            {
                "actor_id": "acc-1",
                "tenant_id": "demo",
                "token_sha256": hashlib.sha256(accountant_token.encode()).hexdigest(),
                "status": "active",
                "expires_at": exp,
                "memberships": [
                    {
                        "company_id": c,
                        "role": "accountant",
                        "status": "active",
                        "permissions": ["data.import"],
                    }
                    for c in ("C001", "C002")
                ],
            },
            {
                "actor_id": "acc-c001",
                "tenant_id": "demo",
                "token_sha256": hashlib.sha256(c001_only_token.encode()).hexdigest(),
                "status": "active",
                "expires_at": exp,
                "memberships": [
                    {
                        "company_id": "C001",
                        "role": "accountant",
                        "status": "active",
                        "permissions": ["data.import"],
                    }
                ],
            },
        ],
    }
    path.write_bytes(canonical(doc))


def _make_record(
    tx_id: str,
    *,
    company_id: str = "C001",
    tenant_id: str = "demo",
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
    ml_raw: float | None = None,
    cal_prob: float | None = None,
    weak_links: list[dict] | None = None,
    prior_txs: list[str] | None = None,
    rule_score_override: float | None = None,
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
        "tenant_id": tenant_id,
        "company_id": company_id,
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
        "rule_score": rule_score_override if rule_score_override is not None else (float(points) if hits else 0.0),
        "hard_trigger": hard_trigger,
        "ml_normalized_score": ml_norm,
        "ml_raw_score": ml_raw,
        "calibrated_fraud_probability": cal_prob,
        "calibration_status": "calibrated" if cal_prob is not None else "uncalibrated",
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


def _commit_snapshot(store: SnapshotStore, scope: AccessScope, data: dict, prefix: str) -> dict:
    draft = store.upload(scope, canonical(data), f"{prefix}.json", f"{prefix}-u")
    prev = store.preview(scope, draft["import_id"], 1)
    assert prev["status"] != "rejected", prev["errors"]
    req = {k: prev[k] for k in ("preview_id", "source_hash", "mapping_hash", "report_hash", "context_hash")}
    req.update(expected_revision=prev["revision"], acknowledge=True)
    return store.commit(scope, draft["import_id"], req, f"{prefix}-c")["snapshot"]


class CaseQueueAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = CaseQueueStore(self.root / "case-queue.sqlite3")
        self.scope_c001 = AccessScope("demo", frozenset({"C001"}), "acc-1", frozenset({"data.import"}))
        self.scope_c002 = AccessScope("demo", frozenset({"C002"}), "acc-1", frozenset({"data.import"}))
        self.snap_base = {
            "snapshot_id": "snp_" + "a" * 32,
            "run_id": "run_001",
            "analysis_id": "ana_001",
        }

    def tearDown(self):
        self.tmp.cleanup()

    def test_01_schemas_policy_fixture_and_open_decisions(self):
        policy = default_fixture_policy(budget_limit=3, min_case_score=7.0)
        validate_policy(policy)
        self.assertFalse(policy["fixture_declaration"]["approved_for_production"])
        self.assertEqual(policy["budget"]["unit"], "case")
        self.assertEqual(policy["budget"]["benchmark_transaction_cap_preserved"], 5)
        self.assertEqual(SELECTION_BENCHMARK_BUDGET, 5)
        self.assertEqual(sorted(OPEN_CASE_QUEUE_DECISIONS.keys()), ["D-04", "D-05", "D-06", "D-07"])

        bad_prod = deepcopy(policy)
        bad_prod["fixture_declaration"]["approved_for_production"] = True
        with self.assertRaises(ImportFailure):
            validate_policy(bad_prod)

        bad_cap = deepcopy(policy)
        bad_cap["budget"]["benchmark_transaction_cap_preserved"] = 3
        with self.assertRaises(ImportFailure):
            validate_policy(bad_cap)

    def test_02_r3_02_hd78_t096_prior_evidence_vs_t105_candidate(self):
        t096 = _make_record(
            "T096",
            invoice_number="HD78",
            invoice_gross_vnd=10_000_000,
            amount_vnd=10_000_000,
            is_candidate=False,
            points=0.0,
            rule_id="",
            event_at="2026-11-01T09:00:00+07:00",
        )
        t105 = _make_record(
            "T105",
            invoice_number="HD78",
            invoice_gross_vnd=10_000_000,
            amount_vnd=5_000_000,
            is_candidate=True,
            points=9.0,
            rule_id="P1",
            prior_txs=["T096"],
            event_at="2026-11-05T14:00:00+07:00",
        )
        bundle = build_case_bundle_from_records(
            tenant_id="demo",
            company_id="C001",
            snapshot_binding=self.snap_base,
            records=[t105],
            prior_evidence_transactions=[t096],
        )
        policy = default_fixture_policy(budget_limit=3, min_case_score=7.0)
        res = self.store.evaluate_and_enqueue(
            self.scope_c001, bundle, policy=policy, mode="active", period_key="2026-W45", idempotency_key="hd78-1"
        )
        self.assertEqual(res["budget_status"]["reserved_count"], 1)
        q = self.store.get_queue_state(self.scope_c001, mode="active", redaction="technical")
        self.assertEqual(len(q["items"]), 1)
        case_obj = q["items"][0]["case"]
        validate_against_schema(case_obj, "coalesced_case")
        self.assertEqual(case_obj["candidate_ids"], ["T105"])
        self.assertEqual(case_obj["evidence_tx_ids"], ["T096"])
        self.assertEqual(case_obj["score_breakdown"]["evidence_bonus_applied"], 0.0)
        self.assertEqual(case_obj["case_score"], 9.0)
        fin = case_obj["financial_summary"]
        self.assertEqual(fin["related_amount_vnd"], 15_000_000)
        self.assertEqual(fin["discrepancy_amount_vnd"], 5_000_000)
        self.assertEqual(fin["net_settled_vnd"], 15_000_000)
        self.assertIsNone(fin["confirmed_loss_vnd"])

    def test_03_r3_01_three_candidates_same_obligation_coalesce_to_one_case(self):
        recs = [
            _make_record("TX_A1", invoice_number="HD-COAL-01", invoice_gross_vnd=20_000_000, amount_vnd=8_000_000, points=6.5, event_at="2026-11-02T09:00:00+07:00"),
            _make_record("TX_A2", invoice_number="HD-COAL-01", invoice_gross_vnd=20_000_000, amount_vnd=8_000_000, points=8.2, event_at="2026-11-03T11:00:00+07:00"),
            _make_record("TX_A3", invoice_number="HD-COAL-01", invoice_gross_vnd=20_000_000, amount_vnd=9_000_000, points=7.4, event_at="2026-11-04T15:00:00+07:00"),
        ]
        bundle = build_case_bundle_from_records(
            tenant_id="demo", company_id="C001", snapshot_binding=self.snap_base, records=recs
        )
        res = self.store.evaluate_and_enqueue(
            self.scope_c001, bundle, policy=default_fixture_policy(budget_limit=3, min_case_score=7.0), mode="active", period_key="2026-W45", idempotency_key="coal-3tx"
        )
        self.assertEqual(res["counts"]["total_cases"], 1)
        self.assertEqual(res["budget_status"]["reserved_count"], 1)
        q = self.store.get_queue_state(self.scope_c001, mode="active", redaction="technical")
        c = q["items"][0]["case"]
        self.assertEqual(c["candidate_ids"], ["TX_A1", "TX_A2", "TX_A3"])
        self.assertEqual(c["case_score"], 8.2)

    def test_04_r3_01_same_vendor_bank_weak_graph_never_merges_obligations(self):
        shared_links = [{"kind": "shared_recipient_account", "vendor_id": "V_SHARED", "recipient_account": "99990001"}]
        r1 = _make_record("TX_OB1", invoice_number="HD-OB-01", invoice_gross_vnd=10_000_000, amount_vnd=12_000_000, vendor_id="V_SHARED", recipient_account="99990001", points=8.5, weak_links=shared_links)
        r2 = _make_record("TX_OB2", invoice_number="HD-OB-02", invoice_gross_vnd=10_000_000, amount_vnd=13_000_000, vendor_id="V_SHARED", recipient_account="99990001", points=8.8, weak_links=shared_links)
        bundle = build_case_bundle_from_records(
            tenant_id="demo", company_id="C001", snapshot_binding=self.snap_base, records=[r1, r2]
        )
        res = self.store.evaluate_and_enqueue(
            self.scope_c001, bundle, policy=default_fixture_policy(budget_limit=3), mode="active", period_key="2026-W45", idempotency_key="ind-ob"
        )
        self.assertEqual(res["counts"]["total_cases"], 2)
        self.assertEqual(res["budget_status"]["reserved_count"], 2)
        q = self.store.get_queue_state(self.scope_c001, mode="active", redaction="technical")
        self.assertEqual(len({it["case_id"] for it in q["items"]}), 2)
        for it in q["items"]:
            self.assertEqual(len(it["case"]["weak_graph_context"]["links"]), 1)

    def test_05_r3_01_r3_04_stable_case_id_and_material_change_suppression(self):
        r1 = _make_record("TX_S1", invoice_number="HD-STAB", invoice_gross_vnd=10_000_000, amount_vnd=12_000_000, points=8.0, ml_norm=0.4)
        policy = default_fixture_policy(budget_limit=3, min_case_score=7.0, min_score_delta=0.25, ml_weight=2.0)
        b1 = build_case_bundle_from_records(
            tenant_id="demo", company_id="C001", snapshot_binding=self.snap_base, records=[r1]
        )
        res1 = self.store.evaluate_and_enqueue(
            self.scope_c001, b1, policy=policy, mode="active", period_key="2026-W45", idempotency_key="stab-1"
        )
        cid = res1["decisions"][0]["case_id"]

        # Rerun with changed snapshot_id, run_id, analysis_id, and sub-threshold ML score jitter (+0.05 -> delta=0.10 < 0.25)
        r1_noise = deepcopy(r1)
        r1_noise["ml_normalized_score"] = 0.45
        b2 = build_case_bundle_from_records(
            tenant_id="demo",
            company_id="C001",
            snapshot_binding={"snapshot_id": "snp_" + "b" * 32, "run_id": "run_999", "analysis_id": "ana_999"},
            records=[r1_noise],
        )
        res2 = self.store.evaluate_and_enqueue(
            self.scope_c001, b2, policy=policy, mode="active", period_key="2026-W45", idempotency_key="stab-2"
        )
        self.assertEqual(res2["decisions"][0]["case_id"], cid)
        self.assertEqual(res2["decisions"][0]["decision"], "already_notified")
        self.assertFalse(res2["decisions"][0]["is_material_change"])
        self.assertEqual(res2["budget_status"]["reserved_count"], 1)

        # Now add a second overpaying candidate transaction -> material change triggers revision 3 & new delivery
        r2 = _make_record("TX_S2", invoice_number="HD-STAB", invoice_gross_vnd=10_000_000, amount_vnd=3_000_000, points=9.0, event_at="2026-11-06T10:00:00+07:00")
        b3 = build_case_bundle_from_records(
            tenant_id="demo",
            company_id="C001",
            snapshot_binding={"snapshot_id": "snp_" + "c" * 32, "run_id": "run_1000"},
            records=[r2, r1],
        )
        res3 = self.store.evaluate_and_enqueue(
            self.scope_c001, b3, policy=policy, mode="active", period_key="2026-W45", idempotency_key="stab-3"
        )
        self.assertEqual(res3["decisions"][0]["case_id"], cid)
        self.assertTrue(res3["decisions"][0]["is_material_change"])
        self.assertEqual(res3["decisions"][0]["decision"], "selected")
        self.assertEqual(res3["budget_status"]["reserved_count"], 2)

    def test_06_r3_03_budget_b3_with_5_qualifying_defers_2(self):
        recs = [
            _make_record(f"TX_Q{i}", invoice_number=f"HD-Q{i}", invoice_gross_vnd=10_000_000, amount_vnd=12_000_000, points=7.0 + i, event_at=f"2026-11-0{i}T09:00:00+07:00")
            for i in range(1, 6)
        ]
        bundle = build_case_bundle_from_records(
            tenant_id="demo", company_id="C001", snapshot_binding=self.snap_base, records=recs
        )
        res = self.store.evaluate_and_enqueue(
            self.scope_c001, bundle, policy=default_fixture_policy(budget_limit=3, min_case_score=7.0), mode="active", period_key="2026-W45", idempotency_key="b3-q5"
        )
        self.assertEqual(res["budget_status"]["reserved_count"], 3)
        self.assertEqual(res["budget_status"]["remaining"], 0)
        selected = [d for d in res["decisions"] if d["decision"] == "selected"]
        deferred = [d for d in res["decisions"] if d["decision"] == "budget_deferred"]
        self.assertEqual(len(selected), 3)
        self.assertEqual(len(deferred), 2)
        self.assertTrue(all(d["backlog_reason_code"] == "budget_exhausted" for d in deferred))

    def test_07_r3_03_zero_qualifying_never_pads_and_gates_unscorable_evidence(self):
        recs = [
            _make_record("TX_LOW1", invoice_number="HD-LOW1", points=3.0),
            _make_record("TX_LOW2", invoice_number="HD-LOW2", points=5.5),
            _make_record("TX_UNSC", invoice_number="HD-UNSC", scorable=False, points=0.0),
            _make_record("TX_GAP", invoice_number="HD-GAP", points=9.0, evidence_sufficient=False, has_blocking_source_gap=True),
        ]
        bundle = build_case_bundle_from_records(
            tenant_id="demo", company_id="C001", snapshot_binding=self.snap_base, records=recs
        )
        res = self.store.evaluate_and_enqueue(
            self.scope_c001, bundle, policy=default_fixture_policy(budget_limit=3, min_case_score=7.0), mode="active", period_key="2026-W45", idempotency_key="zero-q"
        )
        self.assertEqual(res["counts"]["queued_or_reserved"], 0)
        self.assertEqual(res["budget_status"]["reserved_count"], 0)
        by_ob = {d["obligation_id"]: d for d in res["decisions"]}
        self.assertEqual(by_ob["invoice:V01:HDLOW1"]["decision"], "below_threshold")
        self.assertEqual(by_ob["tx:TX_UNSC"]["decision"], "unscorable")
        self.assertEqual(by_ob["invoice:V01:HDGAP"]["decision"], "need_evidence")

    def test_08_r3_03_mandatory_route_prioritized_without_violating_budget(self):
        recs = [
            _make_record("TX_P1", invoice_number="HD-HIGH", points=10.0, rule_id="P1"),
            _make_record("TX_C3", invoice_number="HD-C3", points=7.5, rule_id="C3"),
        ]
        bundle = build_case_bundle_from_records(
            tenant_id="demo", company_id="C001", snapshot_binding=self.snap_base, records=recs
        )
        policy = default_fixture_policy(budget_limit=1, min_case_score=7.0, mandatory_rules=["C3"])
        res = self.store.evaluate_and_enqueue(
            self.scope_c001, bundle, policy=policy, mode="active", period_key="2026-W45", idempotency_key="mand-1"
        )
        self.assertEqual(res["budget_status"]["reserved_count"], 1)
        by_ob = {d["obligation_id"]: d for d in res["decisions"]}
        self.assertEqual(by_ob["invoice:V01:HDC3"]["decision"], "mandatory_route")
        self.assertEqual(by_ob["invoice:V01:HDHIGH"]["decision"], "budget_deferred")

    def test_09_r3_04_concurrent_workers_and_retries_zero_dup_zero_overbudget(self):
        recs = [
            _make_record(f"TX_M{i}", invoice_number=f"HD-M{i}", points=7.5 + i * 0.2)
            for i in range(6)
        ]
        bundle = build_case_bundle_from_records(
            tenant_id="demo", company_id="C001", snapshot_binding=self.snap_base, records=recs
        )
        policy = default_fixture_policy(budget_limit=3, min_case_score=7.0)

        def _worker(idx: int):
            idem = "shared-idem-0" if idx < 6 else f"distinct-idem-{idx}"
            return self.store.evaluate_and_enqueue(
                self.scope_c001, bundle, policy=policy, mode="active", period_key="2026-W45", idempotency_key=idem
            )

        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(_worker, range(14)))
        self.assertEqual(len(results), 14)

        q = self.store.get_queue_state(self.scope_c001, mode="active")
        self.assertEqual(len(q["items"]), 3)
        self.assertEqual(q["budget_periods"][0]["reserved_count"], 3)
        self.assertEqual(q["unacked_outbox_count"], 0)

        # Same idempotency key with modified payload must raise 409 conflict
        bundle_diff = deepcopy(bundle)
        bundle_diff["records"][0]["amount_vnd"] += 100_000
        with self.assertRaises(ImportFailure) as ctx:
            self.store.evaluate_and_enqueue(
                self.scope_c001, bundle_diff, policy=policy, mode="active", period_key="2026-W45", idempotency_key="shared-idem-0"
            )
        self.assertEqual(ctx.exception.status, 409)

    def test_10_r3_04_crash_recovery_at_all_three_boundaries(self):
        policy = default_fixture_policy(budget_limit=3, min_case_score=7.0)
        r1 = _make_record("TX_CR1", invoice_number="HD-CR1", points=8.5)
        b1 = build_case_bundle_from_records(tenant_id="demo", company_id="C001", snapshot_binding=self.snap_base, records=[r1])

        def _fail_before_commit(stage, _payload):
            if stage == "before_reserve_commit":
                raise RuntimeError("crash_before_reserve_commit")

        with self.assertRaises(RuntimeError):
            self.store.evaluate_and_enqueue(
                self.scope_c001, b1, policy=policy, mode="active", period_key="2026-W45", idempotency_key="cr-1", fault_injector=_fail_before_commit
            )
        q0 = self.store.get_queue_state(self.scope_c001, mode="active")
        self.assertEqual(len(q0["items"]), 0)
        self.assertEqual(len(q0["budget_periods"]), 0)

        # Boundary 2: crash after_reserve_before_sink
        def _fail_after_reserve(stage, _payload):
            if stage == "after_reserve_before_sink":
                raise RuntimeError("crash_after_reserve_before_sink")

        with self.assertRaises(RuntimeError):
            self.store.evaluate_and_enqueue(
                self.scope_c001, b1, policy=policy, mode="active", period_key="2026-W45", idempotency_key="cr-1", fault_injector=_fail_after_reserve
            )
        q_mid = self.store.get_queue_state(self.scope_c001, mode="active")
        self.assertEqual(len(q_mid["items"]), 0)
        self.assertEqual(q_mid["budget_periods"][0]["reserved_count"], 1)
        self.assertEqual(q_mid["unacked_outbox_count"], 1)

        rec1 = self.store.recover_outbox(self.scope_c001, mode="active")
        self.assertEqual(rec1["acked"], 1)
        q_done = self.store.get_queue_state(self.scope_c001, mode="active")
        self.assertEqual(len(q_done["items"]), 1)
        self.assertEqual(q_done["budget_periods"][0]["reserved_count"], 1)
        self.assertEqual(q_done["unacked_outbox_count"], 0)

        # Boundary 3: crash after_sink_before_ack on second case
        r2 = _make_record("TX_CR2", invoice_number="HD-CR2", points=8.7)
        b2 = build_case_bundle_from_records(tenant_id="demo", company_id="C001", snapshot_binding=self.snap_base, records=[r2])

        def _fail_after_sink(stage, _payload):
            if stage == "after_sink_before_ack":
                raise RuntimeError("crash_after_sink_before_ack")

        with self.assertRaises(RuntimeError):
            self.store.evaluate_and_enqueue(
                self.scope_c001, b2, policy=policy, mode="active", period_key="2026-W45", idempotency_key="cr-2", fault_injector=_fail_after_sink
            )
        q_pre_ack = self.store.get_queue_state(self.scope_c001, mode="active")
        self.assertEqual(len(q_pre_ack["items"]), 2)
        self.assertEqual(q_pre_ack["unacked_outbox_count"], 1)

        rec2 = self.store.recover_outbox(self.scope_c001, mode="active")
        self.assertEqual(rec2["acked"], 1)
        q_final = self.store.get_queue_state(self.scope_c001, mode="active")
        self.assertEqual(len(q_final["items"]), 2)
        self.assertEqual(q_final["budget_periods"][0]["reserved_count"], 2)
        self.assertEqual(q_final["unacked_outbox_count"], 0)

    def test_11_r3_05_shadow_mode_isolated_from_active(self):
        recs = [_make_record(f"TX_SH{i}", invoice_number=f"HD-SH{i}", points=9.0) for i in range(4)]
        bundle = build_case_bundle_from_records(tenant_id="demo", company_id="C001", snapshot_binding=self.snap_base, records=recs)
        res = self.store.evaluate_and_enqueue(
            self.scope_c001, bundle, policy=default_fixture_policy(budget_limit=2), mode="shadow", period_key="2026-W45", idempotency_key="sh-1"
        )
        self.assertFalse(res["active_delivery"])
        self.assertEqual(res["queue_target"], "shadow_queue")
        self.assertEqual(len(self.store.get_queue_state(self.scope_c001, mode="shadow")["items"]), 2)
        act = self.store.get_queue_state(self.scope_c001, mode="active")
        self.assertEqual(len(act["items"]), 0)
        self.assertEqual(len(act["budget_periods"]), 0)

    def test_12_cross_company_c001_c002_isolation_same_ids(self):
        r_c1 = _make_record("TX_SAME", company_id="C001", invoice_number="HD-SAME", points=9.0)
        r_c2 = _make_record("TX_SAME", company_id="C002", invoice_number="HD-SAME", points=9.0)
        b_c1 = build_case_bundle_from_records(tenant_id="demo", company_id="C001", snapshot_binding=self.snap_base, records=[r_c1])
        b_c2 = build_case_bundle_from_records(tenant_id="demo", company_id="C002", snapshot_binding=self.snap_base, records=[r_c2])
        res1 = self.store.evaluate_and_enqueue(self.scope_c001, b_c1, mode="active", period_key="2026-W45", idempotency_key="c1-1")
        res2 = self.store.evaluate_and_enqueue(self.scope_c002, b_c2, mode="active", period_key="2026-W45", idempotency_key="c2-1")
        self.assertNotEqual(res1["decisions"][0]["case_id"], res2["decisions"][0]["case_id"])
        self.assertEqual(len(self.store.get_queue_state(self.scope_c001, mode="active")["items"]), 1)
        self.assertEqual(len(self.store.get_queue_state(self.scope_c002, mode="active")["items"]), 1)

    def test_13_rule_money_01_negative_adjustment_and_null_confirmed_loss(self):
        pos = _make_record("TX_POS", invoice_number="HD-ADJ", invoice_gross_vnd=8_000_000, amount_vnd=10_000_000, allocated_vnd=10_000_000, points=8.5, prior_txs=["TX_NEG"])
        neg_adj = _make_record(
            "TX_NEG",
            invoice_number="HD-ADJ",
            invoice_gross_vnd=8_000_000,
            amount_vnd=-1_500_000,
            allocated_vnd=-1_500_000,
            is_candidate=False,
            points=0.0,
            rule_id="",
        )
        bundle = build_case_bundle_from_records(
            tenant_id="demo",
            company_id="C001",
            snapshot_binding=self.snap_base,
            records=[pos],
            prior_evidence_transactions=[neg_adj],
        )
        cases = coalesce_cases(bundle, default_fixture_policy())
        self.assertEqual(len(cases), 1)
        fin = cases[0]["financial_summary"]
        self.assertEqual(fin["candidate_amount_vnd"], 10_000_000)
        self.assertEqual(fin["related_amount_vnd"], 8_500_000)
        self.assertEqual(fin["net_settled_vnd"], 8_500_000)
        self.assertEqual(fin["discrepancy_amount_vnd"], 500_000)
        self.assertIsNone(fin["confirmed_loss_vnd"])
        self.assertTrue(fin["contains_negative_adjustment"])

    def test_14_backlog_reevaluation_rollover_and_supplemental_evidence(self):
        recs = [
            _make_record("TX_W1", invoice_number="HD-W1", points=9.5),
            _make_record("TX_W2", invoice_number="HD-W2", points=8.5),
            _make_record("TX_WGAP", invoice_number="HD-WGAP", points=9.0, evidence_sufficient=False, has_blocking_source_gap=True),
        ]
        bundle = build_case_bundle_from_records(tenant_id="demo", company_id="C001", snapshot_binding=self.snap_base, records=recs)
        policy = default_fixture_policy(budget_limit=1, min_case_score=7.0)
        self.store.evaluate_and_enqueue(self.scope_c001, bundle, policy=policy, mode="active", period_key="2026-W45", idempotency_key="bl-0")

        bl = self.store.get_backlog(self.scope_c001, mode="active")
        self.assertFalse(bl["auto_expire"])
        self.assertEqual(len(bl["items"]), 2)
        self.assertTrue(all(it["expires_at"] is None for it in bl["items"]))

        # New period + supplemental evidence clears HD-WGAP
        cid_gap = next(it["case_id"] for it in bl["items"] if it["backlog_reason_code"] == "missing_evidence")
        reeval = self.store.reevaluate_backlog(
            self.scope_c001,
            policy=default_fixture_policy(budget_limit=2, min_case_score=7.0),
            mode="active",
            target_period_key="2026-W46",
            supplemental_sources={
                "by_case_id": {
                    cid_gap: {
                        "evidence_sufficient": True,
                        "has_blocking_source_gap": False,
                        "source_gaps": [],
                        "evidence_tx_ids": ["TX_SUPP_99"],
                    }
                }
            },
            idempotency_key="bl-re-1",
        )
        self.assertEqual(len(reeval["promoted"]), 2)
        self.assertEqual(len(self.store.get_backlog(self.scope_c001, mode="active")["items"]), 0)

    def test_15_closed_case_preserves_resolution_and_reopen_history(self):
        r1 = _make_record("TX_CL1", invoice_number="HD-CL1", points=8.5)
        b1 = build_case_bundle_from_records(tenant_id="demo", company_id="C001", snapshot_binding=self.snap_base, records=[r1])
        policy = default_fixture_policy(budget_limit=3, min_case_score=7.0)
        res1 = self.store.evaluate_and_enqueue(self.scope_c001, b1, policy=policy, mode="active", period_key="2026-W45", idempotency_key="cl-1")
        cid = res1["decisions"][0]["case_id"]

        with self.assertRaises(ImportFailure):
            self.store.update_case_workflow(self.scope_c001, mode="active", case_id=cid, new_status="closed", resolution=None)

        wf = self.store.update_case_workflow(
            self.scope_c001, mode="active", case_id=cid, new_status="closed", resolution="legitimate", reason="Hợp đồng điều chỉnh hợp lệ."
        )
        self.assertEqual(wf["case_workflow_status"], "closed")
        self.assertEqual(wf["case_resolution"], "legitimate")

        # Non-material rerun must stay closed without resending
        b_noise = build_case_bundle_from_records(
            tenant_id="demo", company_id="C001", snapshot_binding={"snapshot_id": "snp_" + "d" * 32, "run_id": "run_2"}, records=[r1]
        )
        res_noise = self.store.evaluate_and_enqueue(self.scope_c001, b_noise, policy=policy, mode="active", period_key="2026-W46", idempotency_key="cl-2")
        self.assertEqual(res_noise["decisions"][0]["decision"], "already_notified")
        det_still_closed = self.store.get_case_detail(self.scope_c001, cid, mode="active")
        self.assertEqual(det_still_closed["case_workflow_status"], "closed")
        self.assertEqual(det_still_closed["case_resolution"], "legitimate")

        # Material new violating tx reopens case preserving resolution history
        r2 = _make_record("TX_CL2", invoice_number="HD-CL1", amount_vnd=6_000_000, points=9.2, event_at="2026-11-12T10:00:00+07:00")
        b_mat = build_case_bundle_from_records(
            tenant_id="demo", company_id="C001", snapshot_binding={"snapshot_id": "snp_" + "e" * 32, "run_id": "run_3"}, records=[r1, r2]
        )
        res_reopen = self.store.evaluate_and_enqueue(self.scope_c001, b_mat, policy=policy, mode="active", period_key="2026-W46", idempotency_key="cl-3")
        self.assertEqual(res_reopen["decisions"][0]["decision"], "selected")
        det_reopened = self.store.get_case_detail(self.scope_c001, cid, mode="active", redaction="technical")
        self.assertEqual(det_reopened["case_workflow_status"], "in_review")
        self.assertIsNone(det_reopened["case_resolution"])
        self.assertEqual(det_reopened["reopen_count"], 1)
        self.assertTrue(any(h.get("previous_resolution") == "legitimate" for h in det_reopened["workflow_history"]))

    def test_16_real_snapshot_store_35_rules_bridge_integration(self):
        auth_path = self.root / "auth.json"
        _write_auth_file(auth_path, "dir-" + "x" * 32, "acc-" + "y" * 32, "c1-" + "z" * 32)
        auth = FileAuthorizer(auth_path)
        dir_scope = auth.authorize_director("Bearer dir-" + "x" * 32, "C001")
        snap_store = SnapshotStore(self.root / "snapshots.sqlite3")

        c = base()
        _seed_baseline_tables(c, "C001", 1, datetime(2026, 7, 1, 10, 0, tzinfo=TZ))
        _add_clean_payment(
            c, "T096", datetime(2026, 9, 1, 10, 0, tzinfo=TZ), 10_000_000, scale=1, company_id="C001",
            invoice_number="HD78", invoice_gross_vnd=10_000_000, doc=True,
        )
        _add_clean_payment(
            c, "T105", datetime(2026, 9, 5, 10, 0, tzinfo=TZ), 5_000_000, scale=1, company_id="C001",
            invoice_number="HD78", invoice_gross_vnd=10_000_000, doc=True,
        )
        raw_snap = _finalize(
            c,
            tenant_id="demo",
            company_id="C001",
            as_of="2026-09-10T18:00:00+07:00",
            candidate_ids=["T105"],
            source_id="real35-cq-test",
        )
        snap_meta = _commit_snapshot(snap_store, dir_scope, raw_snap, "real35")
        analysis = analyze_rule_snapshot(snap_store, dir_scope, snap_meta["snapshot_id"], "2026-09-10T18:00:00+07:00", technical=True)

        bundle = build_case_bundle_from_rule_analysis(analysis, raw_snap, scope=dir_scope, extra_scores={"T105": {"calibrated_fraud_probability": 0.91, "calibration_status": "calibrated"}})
        res = self.store.evaluate_and_enqueue(
            dir_scope, bundle, policy=default_fixture_policy(budget_limit=3, min_case_score=1.0), mode="active", period_key="2026-W37", idempotency_key="real-35-1"
        )
        q = self.store.get_queue_state(dir_scope, mode="active", redaction="technical")
        self.assertGreaterEqual(len(q["items"]), 1)
        hd78_items = [it for it in q["items"] if "HD78" in it["case"]["obligation_id"]]
        self.assertEqual(len(hd78_items), 1)
        self.assertIn("T105", hd78_items[0]["case"]["candidate_ids"])
        self.assertIn("T096", hd78_items[0]["case"]["evidence_tx_ids"])
        self.assertEqual(res["policy_summary"]["benchmark_transaction_cap_preserved"], 5)

    def test_17_sqlite_v1_to_v2_migration_preserves_fixture_data(self):
        v1_path = self.root / "v1_case_queue.sqlite3"
        conn = sqlite3.connect(v1_path)
        conn.execute(f"PRAGMA application_id = {APPLICATION_ID}")
        conn.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL, note TEXT NOT NULL)")
        conn.execute("INSERT INTO schema_migrations VALUES (1, '2026-10-01T00:00:00Z', 'v1')")
        conn.execute(
            "CREATE TABLE cases (mode_namespace TEXT NOT NULL, tenant_id TEXT NOT NULL, company_id TEXT NOT NULL, case_id TEXT NOT NULL, "
            "problem_family TEXT NOT NULL, obligation_id TEXT NOT NULL, current_revision INTEGER NOT NULL, case_workflow_status TEXT NOT NULL, "
            "case_resolution TEXT, latest_case_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
            "PRIMARY KEY (mode_namespace, tenant_id, company_id, case_id))"
        )
        dummy_case = coalesce_cases(
            build_case_bundle_from_records(
                tenant_id="demo",
                company_id="C001",
                snapshot_binding=self.snap_base,
                records=[_make_record("TX_V1", invoice_number="HD-V1", obligation_id="HD-V1", points=8.5)],
            ),
            default_fixture_policy(),
        )[0]
        legacy_cid = dummy_case["case_id"]
        conn.execute(
            "INSERT INTO cases VALUES ('active','demo','C001',?,'payment_invoice','HD-V1',1,'in_review',NULL,?,'2026-10-01T00:00:00Z','2026-10-01T00:00:00Z')",
            (legacy_cid, canonical(dummy_case).decode("utf-8")),
        )
        conn.commit()
        conn.close()

        migrated = CaseQueueStore(v1_path)
        vers = [v["version"] for v in migrated.schema_versions()]
        self.assertEqual(vers, [1, 2])
        det = migrated.get_case_detail(self.scope_c001, legacy_cid, mode="active")
        self.assertEqual(det["case"]["obligation_id"], "HD-V1")

    def test_18_http_api_rbac_accountant_redaction_and_cross_company_403(self):
        auth_path = self.root / "http_auth.json"
        dir_tok = "dir-tok-" + "a" * 32
        acc_tok = "acc-tok-" + "b" * 32
        c001_tok = "c1-tok-" + "c" * 32
        _write_auth_file(auth_path, dir_tok, acc_tok, c001_tok)
        auth = FileAuthorizer(auth_path)
        server = make_server(0, authorizer=auth, case_queue_store=self.store)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            port = server.server_address[1]
            r1 = _make_record("TX_HTTP1", invoice_number="HD-HTTP1", points=9.0, ml_norm=0.88, cal_prob=0.92)
            bundle = build_case_bundle_from_records(
                tenant_id="demo", company_id="C001", snapshot_binding=self.snap_base, records=[r1]
            )

            def _req(method: str, path: str, token: str, body: dict | None = None, headers: dict | None = None):
                c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                hdrs = {"Host": f"127.0.0.1:{port}", "Authorization": f"Bearer {token}"}
                raw = b""
                if body is not None:
                    raw = canonical(body)
                    hdrs["Content-Type"] = "application/json"
                    hdrs["Content-Length"] = str(len(raw))
                if headers:
                    hdrs.update(headers)
                c.request(method, path, body=raw if body is not None else None, headers=hdrs)
                resp = c.getresponse()
                data = json.loads(resp.read().decode("utf-8"))
                c.close()
                return resp.status, data

            # Accountant evaluates in review mode -> 200
            st, ev = _req(
                "POST",
                "/api/v1/companies/C001/case-queue/evaluate",
                acc_tok,
                {"mode": "active", "period_key": "2026-W45", "bundle": bundle},
                {"Idempotency-Key": "http-eval-1"},
            )
            self.assertEqual(st, 200)
            self.assertEqual(ev["redaction"], "review")

            # Accountant gets redacted queue view -> ML/score internals stripped
            st, q_acc = _req("GET", "/api/v1/companies/C001/case-queue/active", acc_tok)
            self.assertEqual(st, 200)
            self.assertTrue(q_acc["items"][0]["technical_fields_redacted"])
            self.assertNotIn("case_score", q_acc["items"][0]["case"])

            # Accountant blocked from technical view and custom policy override -> 403
            st_tech, _ = _req("GET", "/api/v1/companies/C001/case-queue/active/technical", acc_tok)
            self.assertEqual(st_tech, 403)
            st_pol, _ = _req(
                "POST",
                "/api/v1/companies/C001/case-queue/evaluate",
                acc_tok,
                {"mode": "active", "period_key": "2026-W45", "bundle": bundle, "policy": default_fixture_policy()},
                {"Idempotency-Key": "http-eval-pol"},
            )
            self.assertEqual(st_pol, 403)

            # Director sees technical view -> 200 with case_score
            st_dir, q_dir = _req("GET", "/api/v1/companies/C001/case-queue/active/technical", dir_tok)
            self.assertEqual(st_dir, 200)
            self.assertFalse(q_dir["items"][0]["technical_fields_redacted"])
            self.assertIn("case_score", q_dir["items"][0]["case"])

            # Cross-company C001-only token accessing C002 -> 403
            st_cross, _ = _req("GET", "/api/v1/companies/C002/case-queue/active", c001_tok)
            self.assertEqual(st_cross, 403)

            # Query strings blocked -> 400
            st_q, _ = _req("GET", "/api/v1/companies/C001/case-queue/active?mode=shadow", acc_tok)
            self.assertEqual(st_q, 400)
        finally:
            server.shutdown()
            server.server_close()

    def test_19_portal_bridge_allows_case_queue_paths(self):
        import importlib.util

        bridge_path = Path(__file__).resolve().parents[2] / "portal" / "agent2_bridge.py"
        spec = importlib.util.spec_from_file_location("portal_agent2_bridge_test", bridge_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        cid = stable_case_id("demo", "C001", "payment_invoice", "HD78")
        for p in (
            "/api/v1/companies/C001/case-queue/evaluate",
            "/api/v1/companies/C001/case-queue/recover",
            "/api/v1/companies/C001/case-queue/reevaluate-backlog",
            "/api/v1/companies/C001/case-queue/active",
            "/api/v1/companies/C001/case-queue/active/technical",
            "/api/v1/companies/C001/case-queue/shadow/periods/2026-W45",
            "/api/v1/companies/C001/case-queue/backlog",
            f"/api/v1/companies/C001/case-queue/cases/{cid}",
            f"/api/v1/companies/C001/case-queue/cases/{cid}/workflow",
        ):
            self.assertTrue(mod.allowed_path(p), f"Expected allowlist to accept {p}")
        self.assertFalse(mod.allowed_path("/api/v1/companies/C001/case-queue/unknown-route"))


if __name__ == "__main__":
    unittest.main()
