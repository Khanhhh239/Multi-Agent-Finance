"""Comprehensive R4 test suite for DocumentRequirementPolicy, Evidence Versioning, Reconciliation, ActionTask Lifecycle, Independence, RBAC, HTTP API, Migration, and UI."""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import http.client
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest

_REPO_ROOT = str(Path(__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from finance_input import AccessScope

from sme_fraud.auth import FileAuthorizer
from sme_fraud.case_coalescing import build_case_bundle_from_records
from sme_fraud.case_queue_policy import default_fixture_policy as default_cq_policy
from sme_fraud.case_queue_store import CaseQueueStore
from sme_fraud.import_files import ImportFailure, canonical
from sme_fraud.label_packets import LabelStore
from sme_fraud.remediation_policy import (
    CHECKLIST_ITEM_STATUSES,
    default_document_requirement_policy,
    evaluate_document_checklist,
    reconcile_obligation,
)
from sme_fraud.remediation_store import APPLICATION_ID, RemediationStore
from sme_fraud.review_server import make_server
from sme_fraud.rule35_ml_eval_demo import _add_clean_payment, _finalize, _seed_baseline_tables, base
from sme_fraud.snapshots import SnapshotStore

TZ = timezone(timedelta(hours=7))


def _scope(tenant="demo", company="C001", actor="acc_1", role="accountant", perms=("data.import",)):
    del role
    return AccessScope(tenant_id=tenant, company_ids=frozenset({company}), actor_id=actor, permissions=frozenset(perms))


TOK_OP = "tok-op-" + "a" * 32
TOK_VERIF = "tok-verif-" + "b" * 32
TOK_MLONLY = "tok-mlonly-" + "c" * 32
TOK_C002 = "tok-c002-" + "d" * 32


def _make_auth_policy(path: Path) -> Path:
    exp = (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat()

    def _tok_hash(tok: str) -> str:
        return hashlib.sha256(tok.encode("utf-8")).hexdigest()

    doc = {
        "policy_version": "1.0.0",
        "principals": [
            {
                "actor_id": "acc_op",
                "tenant_id": "demo",
                "token_sha256": _tok_hash(TOK_OP),
                "status": "active",
                "expires_at": exp,
                "memberships": [{"company_id": "C001", "role": "accountant", "status": "active", "permissions": ["data.import"]}],
            },
            {
                "actor_id": "dir_c1",
                "tenant_id": "demo",
                "token_sha256": _tok_hash(TOK_VERIF),
                "status": "active",
                "expires_at": exp,
                "memberships": [{"company_id": "C001", "role": "director", "status": "active", "permissions": ["data.import", "evidence.verify"]}],
            },
            {
                "actor_id": "ml_eng",
                "tenant_id": "demo",
                "token_sha256": _tok_hash(TOK_MLONLY),
                "status": "active",
                "expires_at": exp,
                "memberships": [{"company_id": "C001", "role": "accountant", "status": "active", "permissions": ["model.fit"]}],
            },
            {
                "actor_id": "dir_c2",
                "tenant_id": "demo",
                "token_sha256": _tok_hash(TOK_C002),
                "status": "active",
                "expires_at": exp,
                "memberships": [{"company_id": "C002", "role": "director", "status": "active", "permissions": ["data.import", "evidence.verify"]}],
            },
        ],
    }
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def _http(port: int, method: str, path: str, token: str | None = None, body: dict | None = None, headers: dict | None = None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    hdrs = {"Host": f"127.0.0.1:{port}"}
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    if headers:
        hdrs.update(headers)
    raw = None
    if body is not None:
        raw = json.dumps(body).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
        hdrs["Content-Length"] = str(len(raw))
    conn.request(method, path, body=raw, headers=hdrs)
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    ctype = resp.getheader("Content-Type", "")
    parsed = json.loads(data.decode("utf-8")) if "json" in ctype else data
    return resp.status, parsed


class RemediationTests(unittest.TestCase):
    def test_policy_variation_and_no_hardcoded_sla(self):
        policy = default_document_requirement_policy()
        self.assertFalse(policy["approved_for_production"])
        self.assertEqual(policy["open_decision_gates"], ["D-08", "D-14"])
        self.assertIsNone(policy["sla_policy"]["default_due_days"])

        pay_types = [r["document_type"] for r in policy["families"]["payment_invoice"]["requirements"]]
        payroll_types = [r["document_type"] for r in policy["families"]["payroll_entitlement"]["requirements"]]
        vendor_types = [r["document_type"] for r in policy["families"]["vendor_bank_identity"]["requirements"]]
        self.assertNotEqual(set(pay_types), set(payroll_types))
        self.assertNotEqual(set(pay_types), set(vendor_types))
        self.assertIn("timesheet_approval", payroll_types)
        self.assertIn("bank_account_confirmation", vendor_types)
        self.assertIn("payment_allocation", pay_types)

    def test_r4_01_multi_payment_allocation_and_overpayment(self):
        ob = {"obligation_id": "HD120", "gross_amount_vnd": 120_000_000}
        matched = reconcile_obligation(
            ob,
            allocations=[
                {"tx_id": "T1", "obligation_id": "HD120", "kind": "payment", "allocated_amount_vnd": 50_000_000, "tx_time": "2026-11-01T10:00:00+07:00"},
                {"tx_id": "T2", "obligation_id": "HD120", "kind": "payment", "allocated_amount_vnd": 70_000_000, "tx_time": "2026-11-02T10:00:00+07:00"},
            ],
            company_id="C001",
            as_of="2026-11-10T00:00:00+07:00",
        )
        self.assertEqual(matched["status"], "matched")
        self.assertEqual(matched["net_settled_vnd"], 120_000_000)
        self.assertEqual(matched["remaining_due_vnd"], 0)
        self.assertEqual(matched["overpaid_excess_vnd"], 0)

        overpaid = reconcile_obligation(
            {"obligation_id": "HD78", "gross_amount_vnd": 120_000_000},
            allocations=[
                {"tx_id": "T096", "obligation_id": "HD78", "kind": "payment", "allocated_amount_vnd": 120_000_000, "tx_time": "2026-11-01T10:00:00+07:00"},
                {"tx_id": "T105", "obligation_id": "HD78", "kind": "payment", "allocated_amount_vnd": 120_000_000, "tx_time": "2026-11-05T10:00:00+07:00"},
            ],
            company_id="C001",
        )
        self.assertEqual(overpaid["status"], "overpaid")
        self.assertEqual(overpaid["overpaid_excess_vnd"], 120_000_000)
        self.assertEqual(overpaid["discrepancy_amount_vnd"], 120_000_000)
        self.assertIsNone(overpaid["confirmed_loss_vnd"])
        self.assertIsNone(overpaid["recovered_vnd"])

        unavail = reconcile_obligation({"obligation_id": "HD_MISS", "gross_amount_vnd": 50_000_000}, available_sources=["invoices"], company_id="C001")
        self.assertEqual(unavail["status"], "unavailable")
        self.assertIsNone(unavail["discrepancy_amount_vnd"])

    def test_r4_02_refunds_cancellations_and_mn_allocations(self):
        # Single bank payment split M:N across HD-A (70) and HD-B (50), plus duplicate line ignored + refund reversal
        allocs = [
            {"allocation_id": "AL1", "tx_id": "T_BATCH", "obligation_id": "HD-A", "kind": "payment", "allocated_amount_vnd": 70_000_000, "tx_time": "2026-11-01T09:00:00+07:00"},
            {"allocation_id": "AL1", "tx_id": "T_BATCH", "obligation_id": "HD-A", "kind": "payment", "allocated_amount_vnd": 70_000_000, "tx_time": "2026-11-01T09:00:00+07:00"},
            {"allocation_id": "AL2", "tx_id": "T_BATCH", "obligation_id": "HD-B", "kind": "payment", "allocated_amount_vnd": 50_000_000, "tx_time": "2026-11-01T09:00:00+07:00"},
            {"allocation_id": "AL3", "tx_id": "T_DUP", "obligation_id": "HD-A", "kind": "payment", "allocated_amount_vnd": 70_000_000, "tx_time": "2026-11-02T09:00:00+07:00"},
            {"allocation_id": "AL4", "tx_id": "T_REF", "obligation_id": "HD-A", "kind": "refund", "allocated_amount_vnd": 70_000_000, "tx_time": "2026-11-04T09:00:00+07:00"},
        ]
        rep_a = reconcile_obligation({"obligation_id": "HD-A", "gross_amount_vnd": 70_000_000}, allocations=allocs, company_id="C001")
        self.assertEqual(rep_a["gross_allocated_payment_vnd"], 140_000_000)
        self.assertEqual(rep_a["refund_and_reversal_vnd"], 70_000_000)
        self.assertEqual(rep_a["net_settled_vnd"], 70_000_000)
        self.assertEqual(rep_a["status"], "matched")

        rep_cn = reconcile_obligation(
            {"obligation_id": "HD-CN", "gross_amount_vnd": 120_000_000},
            allocations=[{"allocation_id": "ALC1", "tx_id": "T_P", "obligation_id": "HD-CN", "kind": "payment", "allocated_amount_vnd": 100_000_000, "tx_time": "2026-11-01T09:00:00+07:00"}],
            adjustments=[{"adjustment_id": "CN20", "obligation_id": "HD-CN", "kind": "credit_note", "amount_vnd": 20_000_000, "tx_time": "2026-11-03T09:00:00+07:00"}],
            company_id="C001",
        )
        self.assertEqual(rep_cn["status"], "matched")
        self.assertEqual(rep_cn["remaining_due_vnd"], 0)

        # Ambiguous unsplit M:N transaction refuses double count -> disputed
        rep_ambig = reconcile_obligation(
            {"obligation_id": "HD-AMB", "gross_amount_vnd": 50_000_000},
            transactions=[{"transaction_id": "T_AMB", "obligation_ids": ["HD-AMB", "HD-OTHER"], "amount_vnd": 120_000_000, "event_at": "2026-11-01T09:00:00+07:00"}],
            company_id="C001",
        )
        self.assertEqual(rep_ambig["status"], "disputed")
        self.assertIsNone(rep_ambig["discrepancy_amount_vnd"])

    def test_r4_03_r4_04_checklist_five_statuses_versioning_and_verified_evidence_gate(self):
        with tempfile.TemporaryDirectory() as td:
            store = RemediationStore(Path(td) / "remediation.sqlite3")
            op = _scope(actor="acc_op", role="accountant", perms=("data.import",))
            verif = _scope(actor="dir_ver", role="director", perms=("data.import", "evidence.verify"))

            # 1. Missing sources -> unknown, conditional false -> not_applicable
            chk1 = store.evaluate_and_store_checklist(
                op,
                {"case_id": "case_hd78", "obligation_id": "HD78", "problem_family": "payment_invoice", "rule_ids": ["P1"], "as_of": "2026-11-05T12:00:00+07:00"},
                available_sources=[],
            )
            by_dt = {i["document_type"]: i for i in chk1["items"]}
            self.assertEqual(by_dt["invoice"]["item_status"], "unknown")
            self.assertEqual(by_dt["credit_or_adjustment_note"]["item_status"], "not_applicable")

            # 2. Sources checked -> missing; conditional true -> also evaluated (missing)
            chk2 = store.evaluate_and_store_checklist(
                op,
                {
                    "case_id": "case_hd78",
                    "obligation_id": "HD78",
                    "problem_family": "payment_invoice",
                    "rule_ids": ["P1"],
                    "as_of": "2026-11-05T12:00:00+07:00",
                    "reconciliation_status": "overpaid",
                    "payment_count": 2,
                },
                available_sources=["invoices", "payment_allocations", "bank_transactions", "credit_notes"],
            )
            by_dt2 = {i["document_type"]: i for i in chk2["items"]}
            self.assertEqual(by_dt2["invoice"]["item_status"], "missing")
            self.assertEqual(by_dt2["credit_or_adjustment_note"]["item_status"], "missing")

            # 3. Upload file -> MUST NOT self-verify -> pending_verification; uploading v2 increments version cleanly
            with self.assertRaises(ImportFailure) as cm_self:
                store.upload_document(
                    op,
                    case_id="case_hd78",
                    obligation_id="HD78",
                    document_type="credit_or_adjustment_note",
                    filename="bb_bu_tru.pdf",
                    mime="application/pdf",
                    content=b"%PDF-1.4 v1",
                    requested_verification_status="present",
                )
            self.assertEqual(cm_self.exception.code, "SELF_VERIFICATION_FORBIDDEN")

            up1 = store.upload_document(
                op,
                case_id="case_hd78",
                obligation_id="HD78",
                document_type="credit_or_adjustment_note",
                filename="bb_bu_tru_v1.pdf",
                mime="application/pdf",
                content=b"%PDF-1.4 v1 content",
                document_date="2026-11-05T10:00:00+07:00",
                idempotency_key="up-v1",
            )
            doc_id = up1["document"]["document_id"]
            self.assertEqual(up1["document"]["verification_status"], "pending_verification")
            self.assertEqual(up1["document"]["current_version"], 1)

            chk_pending = store.get_case_remediation(op, "case_hd78")["checklist"]
            self.assertEqual({i["document_type"]: i["item_status"] for i in chk_pending["items"]}["credit_or_adjustment_note"], "pending_verification")

            # Add v2 preserving v1 history
            up2 = store.upload_document(
                op,
                case_id="case_hd78",
                obligation_id="HD78",
                document_type="credit_or_adjustment_note",
                filename="bb_bu_tru_v2.pdf",
                mime="application/pdf",
                content=b"%PDF-1.4 v2 signed",
                document_id=doc_id,
                idempotency_key="up-v2",
            )
            self.assertEqual(up2["document"]["current_version"], 2)
            self.assertEqual(up2["document"]["versions"][1]["supersedes_version"], 1)
            self.assertEqual(len(up2["document"]["versions"]), 2)
            # Both v1 and v2 raw contents remain intact; oversized/bad mime rejected
            self.assertEqual(store.get_document(op, doc_id, version=1, include_bytes=True)["content"], b"%PDF-1.4 v1 content")
            self.assertEqual(store.get_document(op, doc_id, version=2, include_bytes=True)["content"], b"%PDF-1.4 v2 signed")
            with self.assertRaises(ImportFailure) as cm_mime:
                store.upload_document(op, case_id="case_hd78", document_type="invoice", filename="bad.exe", mime="application/octet-stream", content=b"MZ")
            self.assertEqual(cm_mime.exception.status, 415)
            with self.assertRaises(ImportFailure) as cm_big:
                store.upload_document(op, case_id="case_hd78", document_type="invoice", filename="big.pdf", mime="application/pdf", content=b"x" * (2 * 1024 * 1024 + 1))
            self.assertEqual(cm_big.exception.status, 413)

            # Create ActionTask on HD78
            task = store.create_task(
                op,
                case_id="case_hd78",
                obligation_id="HD78",
                task_type="reconcile_payment",
                issue_type="payment_discrepancy",
                title="Đối chiếu khoản trả trùng HD78 (T096+T105)",
                what_to_do="Xác nhận bù trừ/thu hồi 120tr từ nhà cung cấp.",
                reason="Phát hiện chi vượt hóa đơn HD78.",
                assignee_kind="department_role",
                assignee_key="ke_toan_cong_no",
                due_at="2026-11-25T17:00:00+07:00",
                require_evidence=True,
                required_document_types=["credit_or_adjustment_note"],
                idempotency_key="tsk-hd78-1",
            )["task"]

            # Submit with unverified doc -> confirm_complete MUST be blocked
            sub = store.submit_task(
                op,
                task_id=task["task_id"],
                expected_revision=1,
                result_summary="Đã tải biên bản hoàn trả v2.",
                document_ids=[doc_id],
            )
            with self.assertRaises(ImportFailure) as cm_unver:
                store.decide_task(
                    verif,
                    task_id=task["task_id"],
                    expected_revision=sub["revision"],
                    decision="confirm_complete",
                    note="Thử chốt khi chưa xác minh",
                )
            self.assertEqual(cm_unver.exception.code, "VERIFIED_EVIDENCE_REQUIRED")

            # Verify doc v2 -> now item becomes 'present'
            verified_doc = store.verify_document(verif, document_id=doc_id, decision="present", verification_note="Khớp dấu và sao kê hoàn tiền")
            self.assertEqual(verified_doc["verification_status"], "present")
            chk_present = store.get_case_remediation(op, "case_hd78")["checklist"]
            statuses_now = {i["document_type"]: i["item_status"] for i in chk_present["items"]}
            self.assertEqual(
                set(statuses_now.values()),
                {"missing", "present", "unknown"},
            )
            self.assertEqual(statuses_now["credit_or_adjustment_note"], "present")
            self.assertEqual(statuses_now["counterparty_reconciliation"], "unknown")

            # Request rework -> assign to another actor -> resubmit -> confirm complete -> reopen
            rw = store.decide_task(verif, task_id=task["task_id"], expected_revision=sub["revision"], decision="request_rework", note="Bổ sung giải trình kế toán trưởng")
            ass = store.assign_task(
                op,
                task_id=task["task_id"],
                expected_revision=rw["revision"],
                assignee_kind="server_actor",
                assignee_key="acc_op",
                due_at="2026-11-28T17:00:00+07:00",
                reason="Chuyển xử lý trực tiếp theo yêu cầu làm lại",
            )
            sub2 = store.submit_task(
                op,
                task_id=task["task_id"],
                expected_revision=ass["revision"],
                result_summary="Đã giải trình và đính kèm biên bản đã xác minh.",
                document_ids=[doc_id],
            )
            done = store.decide_task(verif, task_id=task["task_id"], expected_revision=sub2["revision"], decision="confirm_complete", note="Đã xác minh đủ chứng từ")
            self.assertEqual(done["status"], "completed")
            reopened = store.decide_task(verif, task_id=task["task_id"], expected_revision=done["revision"], decision="reopen", note="Phát sinh đối chiếu bổ sung quý 4")
            self.assertEqual(reopened["status"], "open")
            self.assertEqual(reopened["reopen_reason"], "Phát sinh đối chiếu bổ sung quý 4")
            self.assertGreaterEqual(len(reopened["history"]), 6)

    def test_r4_05_independence_of_case_task_ml_label_and_late_doc_temporal_isolation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            snaps = SnapshotStore(root / "snapshots.sqlite3")
            cq = CaseQueueStore(root / "case-queue.sqlite3")
            rem = RemediationStore(root / "remediation.sqlite3")
            labels = LabelStore(root / "verified-labels.sqlite3", HKDF(algorithm=hashes.SHA256(), length=32, salt=b"t", info=b"l").derive(b"k" * 32))

            sc_verif = _scope(actor="dir_c1", role="director", perms=("data.import", "evidence.verify"))
            op = _scope(actor="acc_1", role="accountant", perms=("data.import",))

            c = base()
            _seed_baseline_tables(c, "C001", 1, datetime(2026, 7, 1, 10, 0, tzinfo=TZ))
            _add_clean_payment(c, "P_CLEAN_01", datetime(2026, 9, 5, 10, 0, tzinfo=TZ), 10_000_000, scale=1, company_id="C001", invoice_number="INV-HD78", invoice_gross_vnd=10_000_000, doc=True)
            data = _finalize(c, tenant_id="demo", company_id="C001", as_of="2026-11-05T12:00:00+07:00", candidate_ids=["P_CLEAN_01"], source_id="r4-indep-v1")
            draft = snaps.upload(sc_verif, canonical(data), "r4-indep.json", "r4-upload-key-1")
            prev = snaps.preview(sc_verif, draft["import_id"], 1)
            self.assertNotEqual(prev["status"], "rejected", prev.get("errors"))
            req = {k: prev[k] for k in ("preview_id", "source_hash", "mapping_hash", "report_hash", "context_hash")}
            req.update(expected_revision=prev["revision"], acknowledge=True)
            snap_id = snaps.commit(sc_verif, draft["import_id"], req, "r4-commit-key-1")["snapshot"]["snapshot_id"]
            snap_before = snaps.get_snapshot(sc_verif, snap_id, data=True)
            snap_bytes_before = snap_before if isinstance(snap_before, bytes) else str(snap_before).encode("utf-8")
            snap_hash_before = hashlib.sha256(snap_bytes_before).hexdigest()

            bundle = build_case_bundle_from_records(
                tenant_id="demo",
                company_id="C001",
                snapshot_binding={
                    "snapshot_id": snap_id,
                    "run_id": "run_r4_1",
                    "analysis_id": "ana_r4_1",
                    "as_of": "2026-11-05T12:00:00+07:00",
                },
                records=[
                    {
                        "transaction_id": "T105",
                        "revision": 1,
                        "tenant_id": "demo",
                        "company_id": "C001",
                        "problem_family": "payment_invoice",
                        "obligation_id": "HD78",
                        "invoice_number": "INV-HD78",
                        "vendor_id": "V01",
                        "recipient_account": "ACC-V01",
                        "amount_vnd": 120_000_000,
                        "invoice_gross_vnd": 120_000_000,
                        "allocated_vnd": 120_000_000,
                        "event_at": "2026-11-05T09:00:00+07:00",
                        "knowledge_at": "2026-11-05T10:00:00+07:00",
                        "rule_score": 8.5,
                        "hard_trigger": False,
                        "actionable_hits": [{"rule_id": "P1", "points": 8.5, "hard_trigger": False, "evidence_id": "ev_t105"}],
                        "evidence_sufficient": True,
                        "has_blocking_source_gap": False,
                        "scorable": True,
                        "is_candidate": True,
                    }
                ],
            )
            enq = cq.evaluate_and_enqueue(
                sc_verif,
                bundle,
                policy=default_cq_policy(min_case_score=1.0),
                mode="active",
                period_key="2026-11",
                idempotency_key="cq-hd78",
            )
            case_id = enq["decisions"][0]["case_id"]

            # Create & keep open ActionTask on case_id
            tsk = rem.create_task(
                op,
                case_id=case_id,
                obligation_id="HD78",
                task_type="request_documents",
                issue_type="missing_document",
                title="Thu thập chứng từ hoàn ứng HD78",
                what_to_do="Tải lên chứng từ xác minh",
                reason="Cần đối chiếu hồ sơ",
                assignee_kind="department_role",
                assignee_key="ke_toan_cong_no",
                due_at="2026-11-25T17:00:00+07:00",
                required_document_types=["invoice"],
                idempotency_key="tsk-ind-1",
            )["task"]

            # Close Case independently -> ActionTask MUST stay active (waiting_external)
            closed_case = cq.update_case_workflow(sc_verif, mode="active", case_id=case_id, new_status="closed", resolution="legitimate", reason="Kế toán xác nhận hợp lệ")
            self.assertEqual(closed_case["case_workflow_status"], "closed")
            rem_state = rem.get_case_remediation(op, case_id)
            self.assertEqual(rem_state["tasks"][0]["status"], "waiting_external")

            # Upload LATE doc after snapshot as_of -> verify & confirm_complete ActionTask
            late_up = rem.upload_document(
                op,
                case_id=case_id,
                obligation_id="HD78",
                document_type="invoice",
                filename="inv_late.pdf",
                mime="application/pdf",
                content=b"%PDF-1.4 late arrival",
                document_date="2026-11-08T10:00:00+07:00",
                case_as_of="2026-11-05T12:00:00+07:00",
                idempotency_key="late-doc",
            )
            self.assertTrue(late_up["document"]["late_arrival_after_as_of"])
            self.assertFalse(late_up["document"]["mutates_snapshot_or_features"])
            rem.verify_document(sc_verif, document_id=late_up["document"]["document_id"], decision="present", verification_note="Xác nhận hóa đơn nộp muộn hợp lệ")
            sub = rem.submit_task(op, task_id=tsk["task_id"], expected_revision=1, result_summary="Đã nộp đủ hóa đơn", document_ids=[late_up["document"]["document_id"]])
            done = rem.decide_task(sc_verif, task_id=tsk["task_id"], expected_revision=sub["revision"], decision="confirm_complete", note="Đã xác nhận đủ chứng từ")
            self.assertEqual(done["status"], "completed")
            self.assertFalse(done["generates_ml_label"])
            self.assertFalse(done["mutates_case_status"])

            # Snapshot bytes/hash UNCHANGED and LabelStore has ZERO ML labels created
            snap_after = snaps.get_snapshot(sc_verif, snap_id, data=True)
            snap_bytes_after = snap_after if isinstance(snap_after, bytes) else str(snap_after).encode("utf-8")
            self.assertEqual(hashlib.sha256(snap_bytes_after).hexdigest(), snap_hash_before)
            self.assertEqual(labels.list(sc_verif), [])

    def test_r4_06_company_scope_no_dup_tasks_concurrency_filters_and_dedup_report(self):
        with tempfile.TemporaryDirectory() as td:
            store = RemediationStore(Path(td) / "remediation.sqlite3")
            acc1 = _scope(company="C001", actor="acc_1", role="accountant", perms=("data.import",))
            acc2 = _scope(company="C001", actor="acc_2", role="accountant", perms=("data.import",))
            c2 = _scope(company="C002", actor="dir_c2", role="director", perms=("data.import", "evidence.verify"))

            # Two accounts in C001 share scope & cannot create duplicate open tasks of same type
            r1 = store.create_task(
                acc1,
                case_id="case_shared_1",
                obligation_id="HD_S1",
                task_type="reconcile_payment",
                issue_type="payment_discrepancy",
                title="Rà công nợ HD_S1",
                what_to_do="Đối chiếu chứng từ",
                reason="Tạo lần đầu",
                assignee_kind="department_role",
                assignee_key="ke_toan_cong_no",
                due_at="2026-11-18T12:00:00+07:00",
                idempotency_key="k-acc1",
            )
            r2 = store.create_task(
                acc2,
                case_id="case_shared_1",
                obligation_id="HD_S1",
                task_type="reconcile_payment",
                issue_type="payment_discrepancy",
                title="Rà công nợ HD_S1",
                what_to_do="Đối chiếu chứng từ",
                reason="Tạo trùng từ user khác",
                assignee_kind="department_role",
                assignee_key="ke_toan_cong_no",
                due_at="2026-11-18T12:00:00+07:00",
                idempotency_key="k-acc2",
            )
            self.assertTrue(r1["created"])
            self.assertFalse(r2["created"])
            self.assertTrue(r2["deduplicated_existing"])
            self.assertEqual(r1["task"]["task_id"], r2["task"]["task_id"])
            self.assertEqual(len(store.get_case_remediation(acc2, "case_shared_1")["tasks"]), 1)

            # Parallel creation with unique keys still produces 1 task slot safely
            def _race(idx: int):
                return store.create_task(
                    acc1 if idx % 2 == 0 else acc2,
                    case_id="case_race",
                    obligation_id="HD_RACE",
                    task_type="request_documents",
                    issue_type="missing_document",
                    title="Xin hóa đơn gốc",
                    what_to_do="Bổ sung PDF",
                    reason="Kiểm tra song song",
                    assignee_kind="server_actor",
                    assignee_key="acc_1",
                    due_at="2026-11-15T12:00:00+07:00",
                    idempotency_key=f"race-{idx}",
                )

            with ThreadPoolExecutor(max_workers=6) as ex:
                results = list(ex.map(_race, range(6)))
            self.assertEqual(len({r["task"]["task_id"] for r in results}), 1)

            # Optimistic concurrency revision conflict on assign_task
            t_id = r1["task"]["task_id"]
            updated = store.assign_task(
                acc1,
                task_id=t_id,
                expected_revision=1,
                assignee_kind="server_actor",
                assignee_key="acc_2",
                reason="Cập nhật đầu tiên",
            )
            self.assertEqual(updated["revision"], 2)
            with self.assertRaises(ImportFailure) as cm_rev:
                store.assign_task(
                    acc2,
                    task_id=t_id,
                    expected_revision=1,
                    assignee_kind="server_actor",
                    assignee_key="acc_1",
                    reason="Ghi đè bản cũ",
                )
            self.assertEqual(cm_rev.exception.code, "REVISION_CONFLICT")

            # Add second allowed task + reconciliation link -> verify report deduplicates case & money
            recon = reconcile_obligation(
                {"obligation_id": "HD_S1", "gross_amount_vnd": 200_000_000},
                allocations=[{"tx_id": "T1", "obligation_id": "HD_S1", "kind": "payment", "allocated_amount_vnd": 250_000_000, "tx_time": "2026-11-01T10:00:00+07:00"}],
                company_id="C001",
            )
            store.evaluate_and_store_checklist(
                acc1,
                {"case_id": "case_shared_1", "obligation_id": "HD_S1", "problem_family": "payment_invoice"},
                available_sources=["invoices", "bank_transactions"],
                reconciliation=recon,
                issue_type="payment_discrepancy",
            )
            store.create_task(
                acc1,
                case_id="case_shared_1",
                obligation_id="HD_S1",
                task_type="verify_control",
                issue_type="process_exception",
                title="Rà soát thẩm quyền vượt hạn mức",
                what_to_do="Kiểm tra nhật ký duyệt",
                reason="Tác vụ bổ sung khác loại",
                assignee_kind="department_role",
                assignee_key="kiem_soat_noi_bo",
                due_at="2026-11-17T18:00:00+07:00",
                idempotency_key="second-distinct-task",
            )
            now_ref = "2026-11-17T00:00:00+07:00"
            self.assertEqual(len(store.list_tasks(acc1, filter_name="overdue", now=now_ref)["tasks"]), 1)
            self.assertGreaterEqual(len(store.list_tasks(acc1, filter_name="due_soon", now=now_ref)["tasks"]), 2)

            rep = store.build_business_report(acc1, now=now_ref)
            self.assertEqual(rep["case_counts"]["total_distinct_cases"], 2)
            self.assertEqual(rep["task_counts"]["total_tasks"], 3)
            self.assertEqual(rep["amounts_vnd"]["deduplicated_obligation_count"], 1)
            self.assertEqual(rep["amounts_vnd"]["related_amount_vnd"], 250_000_000)
            self.assertEqual(rep["amounts_vnd"]["discrepancy_amount_vnd"], 50_000_000)
            self.assertIsNone(rep["amounts_vnd"]["confirmed_loss_vnd"])

            # C002 is completely isolated from C001
            self.assertEqual(store.list_tasks(c2)["tasks"], [])
            self.assertEqual(store.build_business_report(c2)["case_counts"]["total_distinct_cases"], 0)

    def test_sqlite_migration_v1_to_v2_and_immutable_audit(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "mig.sqlite3"
            conn = sqlite3.connect(str(db))
            conn.execute(f"PRAGMA application_id = {APPLICATION_ID}")
            conn.executescript(
                """
                CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL, note TEXT NOT NULL);
                CREATE TABLE case_financial_links (
                    tenant_id TEXT NOT NULL, company_id TEXT NOT NULL, case_id TEXT NOT NULL,
                    obligation_id TEXT NOT NULL, issue_type TEXT NOT NULL, reconciliation_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL, PRIMARY KEY (tenant_id, company_id, case_id)
                );
                INSERT INTO schema_migrations VALUES (1, '2026-11-01T00:00:00+00:00', 'v1 fixture');
                """
            )
            conn.commit()
            conn.close()

            store = RemediationStore(db)
            vers = store.schema_versions()
            self.assertEqual([v["version"] for v in vers], [1, 2])
            op = _scope(actor="acc_1", perms=("data.import",))
            t = store.create_task(
                op,
                case_id="case_mig",
                obligation_id="HD_MIG",
                task_type="request_documents",
                issue_type="missing_document",
                title="Kiểm tra sau migrate",
                what_to_do="Nộp chứng từ",
                reason="Test reload",
                assignee_kind="department_role",
                assignee_key="ke_toan_cong_no",
                require_evidence=False,
                idempotency_key="mig-k1",
            )["task"]

            # Audit table is append-only
            conn = sqlite3.connect(str(db))
            with self.assertRaises(sqlite3.DatabaseError):
                conn.execute("UPDATE remediation_audit_events SET actor_id = 'hacker'")
            with self.assertRaises(sqlite3.DatabaseError):
                conn.execute("DELETE FROM remediation_audit_events")
            conn.close()

            reloaded = RemediationStore(db)
            self.assertEqual(reloaded.get_case_remediation(op, "case_mig")["tasks"][0]["task_id"], t["task_id"])

    def test_http_api_rbac_bridge_allowlist_and_ui_presence(self):
        from portal import agent2_bridge

        self.assertTrue(agent2_bridge.allowed_path("/api/v1/companies/C001/remediation/summary"))
        self.assertTrue(agent2_bridge.allowed_path("/api/v1/companies/C001/remediation/cases/case_" + "a" * 32))
        self.assertTrue(agent2_bridge.allowed_path("/api/v1/companies/C001/remediation/documents/doc_" + "a" * 24 + "/verify"))
        self.assertTrue(agent2_bridge.allowed_path("/api/v1/companies/C001/remediation/tasks/tsk_" + "a" * 24 + "/decision"))
        self.assertFalse(agent2_bridge.allowed_path("/api/v1/companies/../remediation/summary"))

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            auth = FileAuthorizer(_make_auth_policy(root / "access.json"))
            rem = RemediationStore(root / "rem.sqlite3")
            server = make_server(port=0, authorizer=auth, remediation_store=rem)
            port = server.server_port
            th = threading.Thread(target=server.serve_forever, daemon=True)
            th.start()
            try:
                # 1. model.fit-only actor DENIED on read & create & upload
                st_ml, _ = _http(port, "GET", "/api/v1/companies/C001/remediation/summary", TOK_MLONLY)
                self.assertEqual(st_ml, 403)
                st_ml_post, _ = _http(
                    port,
                    "POST",
                    "/api/v1/companies/C001/remediation/tasks",
                    TOK_MLONLY,
                    body={"case_id": "c1", "task_type": "request_documents", "issue_type": "missing_document", "title": "x", "what_to_do": "y", "reason": "z", "assignee_kind": "department_role", "assignee_key": "ke_toan_cong_no"},
                    headers={"Idempotency-Key": "ml-deny"},
                )
                self.assertEqual(st_ml_post, 403)

                # 2. C002 actor DENIED on C001
                st_c2, _ = _http(port, "GET", "/api/v1/companies/C001/remediation/summary", TOK_C002)
                self.assertEqual(st_c2, 403)

                # 3. Operator creates task + uploads doc -> verifier permissions checked
                st_t, res_t = _http(
                    port,
                    "POST",
                    "/api/v1/companies/C001/remediation/tasks",
                    TOK_OP,
                    body={
                        "case_id": "case_api_1",
                        "obligation_id": "HD_API",
                        "task_type": "remediate_issue",
                        "issue_type": "missing_document",
                        "title": "Bổ sung hóa đơn",
                        "what_to_do": "Tải lên PDF hóa đơn",
                        "reason": "Thiếu bản gốc",
                        "assignee_kind": "server_actor",
                        "assignee_key": "acc_op",
                        "due_at": "2026-11-28T17:00:00+07:00",
                        "require_evidence": True,
                        "required_document_types": ["invoice"],
                    },
                    headers={"Idempotency-Key": "api-t-1"},
                )
                self.assertEqual(st_t, 200)
                task_id = res_t["task"]["task_id"]

                b64 = base64.b64encode(b"%PDF-1.4 api doc").decode("ascii")
                st_u, res_u = _http(
                    port,
                    "POST",
                    "/api/v1/companies/C001/remediation/cases/case_api_1/documents",
                    TOK_OP,
                    body={
                        "obligation_id": "HD_API",
                        "document_type": "invoice",
                        "filename": "inv.pdf",
                        "mime": "application/pdf",
                        "content_base64": b64,
                    },
                    headers={"Idempotency-Key": "api-u-1"},
                )
                self.assertEqual(st_u, 200)
                doc_id = res_u["document"]["document_id"]

                # Operator CANNOT verify doc or confirm task completion -> 403
                st_v_deny, _ = _http(
                    port,
                    "POST",
                    f"/api/v1/companies/C001/remediation/documents/{doc_id}/verify",
                    TOK_OP,
                    body={"decision": "present", "verification_note": "Tự duyệt"},
                )
                self.assertEqual(st_v_deny, 403)

                # Verifier CAN verify doc -> operator submits -> verifier confirms completion
                st_v_ok, res_v = _http(
                    port,
                    "POST",
                    f"/api/v1/companies/C001/remediation/documents/{doc_id}/verify",
                    TOK_VERIF,
                    body={"decision": "present", "verification_note": "Hợp lệ"},
                )
                self.assertEqual(st_v_ok, 200)
                self.assertEqual(res_v["document"]["verification_status"], "present")

                st_sub, res_sub = _http(
                    port,
                    "POST",
                    f"/api/v1/companies/C001/remediation/tasks/{task_id}/submit",
                    TOK_OP,
                    body={"expected_revision": 1, "result_summary": "Đã nộp", "document_ids": [doc_id]},
                )
                self.assertEqual(st_sub, 200)

                st_conf_deny, _ = _http(
                    port,
                    "POST",
                    f"/api/v1/companies/C001/remediation/tasks/{task_id}/decision",
                    TOK_OP,
                    body={"expected_revision": 2, "decision": "confirm_complete", "note": "Thử tự chốt"},
                )
                self.assertEqual(st_conf_deny, 403)

                st_conf_ok, res_conf = _http(
                    port,
                    "POST",
                    f"/api/v1/companies/C001/remediation/tasks/{task_id}/decision",
                    TOK_VERIF,
                    body={"expected_revision": 2, "decision": "confirm_complete", "note": "Đã kiểm tra đầy đủ"},
                )
                self.assertEqual(st_conf_ok, 200)
                self.assertEqual(res_conf["task"]["status"], "completed")

                # Download raw content via GET & idempotency conflict check
                st_raw, raw_bytes = _http(port, "GET", f"/api/v1/companies/C001/remediation/documents/{doc_id}/content", TOK_OP)
                self.assertEqual(st_raw, 200)
                self.assertEqual(raw_bytes, b"%PDF-1.4 api doc")
                st_dup_err, _ = _http(
                    port,
                    "POST",
                    "/api/v1/companies/C001/remediation/tasks",
                    TOK_OP,
                    body={
                        "case_id": "case_api_other",
                        "obligation_id": "HD_OTHER",
                        "task_type": "remediate_issue",
                        "issue_type": "missing_document",
                        "title": "Khác payload nhưng trùng key",
                        "what_to_do": "Tải lên PDF hóa đơn",
                        "reason": "Thiếu bản gốc",
                        "assignee_kind": "server_actor",
                        "assignee_key": "acc_op",
                    },
                    headers={"Idempotency-Key": "api-t-1"},
                )
                self.assertEqual(st_dup_err, 409)
            finally:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
