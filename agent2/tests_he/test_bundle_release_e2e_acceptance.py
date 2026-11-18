"""Comprehensive end-to-end tests for R5/R6 Bundle Acceptance: locked 35+ML comparison, shared review timing, fallback/backlog, rollback/HTTP restart, and release verdict."""
from __future__ import annotations

import hashlib
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_AGENT2_ROOT = _REPO_ROOT / "agent2"
for p in (str(_REPO_ROOT), str(_AGENT2_ROOT), str(_REPO_ROOT / "shared" / "finance_input" / "src"), str(_AGENT2_ROOT / "tests"), str(_AGENT2_ROOT / "tests_he")):
    if p not in sys.path:
        sys.path.insert(0, p)

from portal import agent2_bridge
from sme_fraud.auth import FileAuthorizer
from sme_fraud.bundle_release_acceptance import (
    OPEN_OWNER_GATES,
    build_release_readiness_decision,
    evaluate_fallback_and_backlog,
    run_full_acceptance,
    run_locked_35_vs_ml_and_reviews,
    run_staging_rollback_drill,
    setup_isolated_environment,
)
from sme_fraud.review_server import make_server


def _http_call(port: int, method: str, path: str, token: str, body: dict | None = None, headers: dict | None = None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
    hdrs = {"Host": f"127.0.0.1:{port}", "Authorization": f"Bearer {token}"}
    if headers:
        hdrs.update(headers)
    raw = None
    if body is not None:
        raw = json.dumps(body).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
        hdrs["Content-Length"] = str(len(raw))
    conn.request(method, path, body=raw, headers=hdrs)
    resp = conn.getresponse()
    payload = resp.read()
    conn.close()
    ctype = resp.getheader("Content-Type", "")
    parsed = json.loads(payload.decode("utf-8")) if "json" in ctype else payload
    return resp.status, parsed


class BundleReleaseE2EAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name)
        cls.env = setup_isolated_environment(cls.root / "runtime", clean=True)
        cls.part12 = run_locked_35_vs_ml_and_reviews(cls.env)
        cls.part3 = evaluate_fallback_and_backlog(cls.env)
        cls.part4 = run_staging_rollback_drill(cls.env, cls.part12["bundle_a_ids"])
        cls.decision = build_release_readiness_decision(cls.part12, cls.part3, cls.part4)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_01_locked_plan_and_35_rules_plus_ml_comparison_per_company(self):
        # Verify plans were locked prior to sealed_future_test inspection & use pinned models per company
        p1 = self.part12["locked_plans"]["C001"]
        p2 = self.part12["locked_plans"]["C002"]
        self.assertEqual(p1["pinned_ml_method"], "isolation_forest")
        self.assertEqual(p2["pinned_ml_method"], "ecod")
        self.assertTrue(p1["locked_before_test_inspection"])
        self.assertTrue(p1["history_excluded_from_candidates"])
        self.assertEqual(p1["budget"], 5)

        c1 = self.part12["comparison_companies"]["C001"]
        c2 = self.part12["comparison_companies"]["C002"]
        # C001: 3 rule slots -> 2 ML additions (reported honestly without post-hoc tweaking)
        self.assertEqual(c1["baseline_35_rules"]["metrics"]["selected"], 3)
        self.assertEqual(c1["combined_35_rules_plus_ml"]["metrics"]["selected"], 5)
        self.assertEqual(c1["ml_incremental_summary"]["added_count"], 2)
        self.assertEqual(
            c1["ml_incremental_summary"]["added_useful_transactions"] + c1["ml_incremental_summary"]["added_not_useful_transactions"],
            c1["ml_incremental_summary"]["added_count"],
        )
        self.assertGreater(c1["ml_incremental_summary"]["added_active_review_seconds"], 0)
        self.assertEqual(len(c1["shared_reviewed_once_ids"]), 3)

        # C002: 4 rule slots -> 1 ML addition (inconclusive transaction waiting for docs)
        self.assertEqual(c2["baseline_35_rules"]["metrics"]["selected"], 4)
        self.assertEqual(c2["combined_35_rules_plus_ml"]["metrics"]["selected"], 5)
        self.assertEqual(c2["ml_incremental_summary"]["added_count"], 1)
        self.assertEqual(c2["ml_incremental_summary"]["added_inconclusive_transactions"], 1)
        self.assertEqual(
            c2["ml_incremental_summary"]["added_useful_transactions"] + c2["ml_incremental_summary"]["added_not_useful_transactions"],
            c2["ml_incremental_summary"]["added_count"],
        )
        self.assertGreater(c2["ml_incremental_summary"]["added_active_review_seconds"], 0)
        self.assertEqual(len(c2["shared_reviewed_once_ids"]), 4)

        # Edge checks: full 5/5 from rules -> 0 ML added; <5 eligible -> no padding; history excluded
        for cid in ("C001", "C002"):
            ec = self.part12["edge_checks"][cid]
            self.assertEqual(ec["rules_fill_all_5_slots"]["ml_added"], 0)
            self.assertEqual(ec["rules_fill_all_5_slots"]["ml_addition_status"], "budget_full_no_slots")
            self.assertEqual(ec["under_5_candidates_no_padding"]["total_candidates"], 3)
            self.assertEqual(ec["under_5_candidates_no_padding"]["combined_selected"], 3)
            self.assertTrue(ec["history_high_control_id_absent"])

    def test_02_union_review_separates_waiting_time_and_label_semantics(self):
        for cid in ("C001", "C002"):
            comp = self.part12["comparison_companies"][cid]
            lbl = comp["label_boundaries"]
            self.assertFalse(lbl["confirmed_risk_is_verified_fraud"])
            self.assertFalse(lbl["inconclusive_included_in_precision_denominator"])
            self.assertIsNone(lbl["verified_fraud_precision"])
            self.assertEqual(lbl["eval_split_verified_labels_count"], 0)
            self.assertGreater(comp["ml_incremental_summary"]["separated_waiting_evidence_seconds"], 0)
            # Inconclusive cases are excluded from declared_issue_fraction / precision denominator
            ws_sum = comp["bundle_workspace_report_summary"]
            if ws_sum["outcomes"]["inconclusive"] > 0:
                self.assertEqual(
                    ws_sum["resolved_case_count"],
                    ws_sum["outcomes"]["confirmed_risk"] + ws_sum["outcomes"]["legitimate"],
                )

    def test_03_fallback_invariants_backlog_metrics_and_budget_proposal(self):
        for cid in ("C001", "C002"):
            fb = self.part3["by_company"][cid]
            inv = self.part3["invariants"][cid]
            self.assertEqual(
                fb["rule35_coverage"]["all_applicable_evaluated_rows"] + fb["rule35_coverage"]["partial_source_gap_rows"],
                25,
            )
            self.assertEqual(fb["rule35_coverage"]["all_unavailable_rows"], 0)
            msp = fb["missing_source_probe"]
            self.assertGreater(msp["partial_source_gap_rows"], 0)
            self.assertEqual(msp["partial_source_gap_rows"], 25)
            self.assertIn("B4", msp["unavailable_rule_ids"])
            self.assertIn("E1", msp["unavailable_rule_ids"])
            self.assertTrue(msp["unavailable_keep_null"])
            self.assertFalse(fb["cloud_he"]["available"])
            self.assertIn(fb["cloud_he"]["reason"], ("enterprise_local_requested", "bundle_he_executor_unavailable"))

            self.assertTrue(inv["missing_score_stays_null_never_zero"])
            self.assertTrue(inv["missing_model_never_borrows_other_or_autofits"])
            self.assertTrue(inv["missing_source_rules_stay_unavailable_never_zero"])
            self.assertTrue(inv["cloud_request_blocked_no_plaintext_fallback"])
            self.assertGreater(inv["degraded_fallback_triggered_to_rules_only_count"], 0)
            self.assertEqual(inv["degraded_fallback_used_id"], "fb_missing_unsup_rules_only_v1")

            bl = fb["backlog_k1"]
            self.assertFalse(bl["auto_expire"])
            self.assertIsNotNone(bl["closing_backlog_count"])

        prop = self.part3["case_budget_decision_proposal"]
        self.assertTrue(prop["distinct_from_tx_comparison_budget_5"])
        self.assertGreater(prop["measured_synthetic_avg_active_seconds_per_case"], 0)

    def test_04_rollback_preserves_inflight_b_outputs_reviews_tasks_quota_and_isolation(self):
        self.assertTrue(self.part4["cross_company_c001_c002_isolated"])
        for cid in ("C001", "C002"):
            rb = self.part4["companies"][cid]
            self.assertTrue(rb["runs"]["run_a_inflight"]["stayed_on_bundle_a"])
            self.assertTrue(rb["runs"]["run_a2_after_rollback"]["uses_bundle_a"])
            self.assertEqual(rb["pointer_revisions"]["activate_b_rev"], 2)
            self.assertEqual(rb["pointer_revisions"]["rollback_a_rev"], 3)
            self.assertEqual(rb["pointer_revisions"]["current_staging_bundle_id"], rb["bundle_a_id"])
            self.assertTrue(rb["b_result_still_readable_with_source"])
            self.assertGreaterEqual(rb["preserved_entities"]["b1_review_revision"], 1)
            self.assertTrue(rb["preserved_entities"]["b1_doc_sha256_intact"])
            self.assertGreater(rb["preserved_entities"]["b1_audit_events_count"], 0)
            self.assertTrue(rb["quota_and_dedup_preserved"]["active_queue_still_empty"])
            self.assertTrue(rb["quota_and_dedup_preserved"]["a2_already_notified_preserved"])
            self.assertTrue(rb["retry_reload_restart_no_duplicates"])
            self.assertTrue(rb["no_database_restore"])

    def test_05_http_server_restart_and_portal_bridge_after_rollback(self):
        # Spin up a real loopback HTTP server pointing at rolled-back stores, query B1/A2, restart server, retry
        svc = self.env["release_svc"]
        auth = self.env["auth"]
        snapshots = self.env["snapshots"]
        queue = self.env["queue_store"]
        rem = self.env["remediation"]
        c1_rb = self.part4["companies"]["C001"]
        run_b1 = c1_rb["runs"]["run_b1_k2"]["run_id"]
        run_a2 = c1_rb["runs"]["run_a2_after_rollback"]["run_id"]
        acc_tok = self.env["acc_token"]

        srv1 = make_server(
            port=0,
            authorizer=auth,
            snapshot_store=snapshots,
            analysis_resources=self.env["resources"],
            case_queue_store=queue,
            remediation_store=rem,
            release_service=svc,
        )
        t1 = threading.Thread(target=srv1.serve_forever, daemon=True)
        t1.start()
        try:
            st_b, rep_b = _http_call(srv1.server_port, "GET", f"/api/v1/companies/C001/pipeline-workspace/runs/{run_b1}/report", acc_tok)
            self.assertEqual(st_b, 200, rep_b)
            self.assertEqual(rep_b["bundle_id"], c1_rb["bundle_b_id"])
            st_c2_deny, _ = _http_call(srv1.server_port, "GET", f"/api/v1/companies/C002/pipeline-workspace/runs/{run_b1}/report", acc_tok)
            self.assertEqual(st_c2_deny, 404)
            # Bridge allowlist covers release & bundle-workspace & remediation routes
            self.assertTrue(agent2_bridge.allowed_path(f"/api/v1/companies/C001/pipeline-workspace/runs/{run_b1}/report"))
            self.assertTrue(agent2_bridge.allowed_path("/api/v1/companies/C001/pipeline-releases/switch"))
        finally:
            srv1.shutdown()
            srv1.server_close()

        # Simulate process restart with fresh service & server instances over the SAME SQLite databases
        srv2 = make_server(
            port=0,
            authorizer=auth,
            snapshot_store=snapshots,
            analysis_resources=self.env["resources"],
            case_queue_store=queue,
            remediation_store=rem,
            release_service=None,
        )
        t2 = threading.Thread(target=srv2.serve_forever, daemon=True)
        t2.start()
        try:
            st_rem, rem_rep = _http_call(srv2.server_port, "GET", f"/api/v1/companies/C001/remediation/tasks/filter/all", acc_tok)
            self.assertEqual(st_rem, 200, rem_rep)
            task_ids_c1 = [t["task_id"] for t in rem_rep["tasks"]]
            self.assertIn(c1_rb["preserved_entities"]["b1_task_id"], task_ids_c1)
            # C002 task ID must never appear in C001 task list
            c2_task_id = self.part4["companies"]["C002"]["preserved_entities"]["b1_task_id"]
            self.assertNotIn(c2_task_id, task_ids_c1)
        finally:
            srv2.shutdown()
            srv2.server_close()

    def test_06_release_readiness_decision_separates_staging_efficacy_and_blockers(self):
        self.assertEqual(self.decision["staging_technical"]["verdict"], "DAT_KY_THUAT_STAGING")
        self.assertTrue(self.decision["staging_technical"]["ready_for_isolated_staging_shadow"])
        self.assertEqual(self.decision["effectiveness_evidence"]["verdict"], "CHUA_DU_BANG_CHUNG_HIEU_QUA_THUC_TE")
        self.assertFalse(self.decision["effectiveness_evidence"]["proven_on_real_enterprise_data"])
        self.assertEqual(self.decision["production_release"]["verdict"], "BI_CHAN_BLOCKED")
        self.assertFalse(self.decision["production_release"]["approved_for_production"])
        reasons_text = json.dumps(self.decision["production_release"]["blocking_reasons"])
        for gate in OPEN_OWNER_GATES:
            self.assertIn(gate, reasons_text)

    def test_07_verified_label_precision_excludes_inconclusive_and_confirmed_risk(self):
        svc = self.env["release_svc"]
        labels = self.env["labels_store"]
        for cid in ("C001", "C002"):
            cenv = self.env["companies"][cid]
            comp = self.part12["comparison_companies"][cid]
            lbl = comp["label_boundaries"]
            ws = svc.workspace.report(cenv["scope_acc"], cenv["run_a1_id"])
            summary = ws["summary"]
            outcomes = summary["outcomes"]

            # Workspace has confirmed_risk ("Co van de can xu ly"), zero verified_fraud labels on K1,
            # and inconclusive cases are strictly excluded from precision/resolved denominators
            self.assertGreater(outcomes["confirmed_risk"], 0)
            self.assertEqual(summary["resolved_case_count"], outcomes["confirmed_risk"] + outcomes["legitimate"])
            self.assertEqual(summary["inconclusive_excluded_count"], outcomes["inconclusive"])
            self.assertFalse(lbl["confirmed_risk_is_verified_fraud"])
            self.assertFalse(lbl["inconclusive_included_in_precision_denominator"])
            self.assertIsNone(lbl["verified_fraud_precision"])
            self.assertEqual(lbl["eval_split_verified_labels_count"], 0)
            self.assertIsNone(self.decision["effectiveness_evidence"]["what_was_measured_on_fixtures"][cid]["verified_fraud_precision"])

            # Closing ActionTask / uploading docs / saving confirmed_risk never creates verified ML labels for K1
            pkts = labels.list(cenv["scope_dir"])
            self.assertEqual(len(pkts), 3)
            self.assertNotIn(cenv["ev1_man"]["snapshot_id"], json.dumps(pkts))

        # C002 combined comparison has 5 selected (4 confirmed_risk + 1 inconclusive) -> resolved denominator excludes inconclusive (4/4, not 4/5)
        c2_metrics = self.part12["comparison_companies"]["C002"]["combined_35_rules_plus_ml"]["metrics"]
        self.assertEqual(c2_metrics["selected"], 5)
        self.assertEqual(c2_metrics["inconclusive"], 1)
        self.assertEqual(c2_metrics["resolved"], 4)
        self.assertEqual(c2_metrics["declared_precision_resolved"], 1.0)
        self.assertEqual(c2_metrics["resolution_coverage"], 0.8)


if __name__ == "__main__":
    unittest.main()

