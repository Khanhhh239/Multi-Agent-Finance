"""End-to-end HTTP and Portal bridge tests for multi-batch encrypted training."""
from copy import deepcopy
from pathlib import Path
import json
import secrets
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from finance_input import AccessScope
from experiments.he_training import TARGET
from experiments.he_training.batch_store import BatchCloudStore
from experiments.he_training.circuit import oracle
from experiments.he_training.protocol import canonical, strict_json
from portal.agent2_bridge import PUBLIC, allowed_path
from sme_fraud.batch_training_api import BatchTrainingManager
from sme_fraud.label_packets import LabelStore
from sme_fraud.review_server import make_server
from sme_fraud.snapshots import SnapshotStore
from batch_training_support import native_batches
from test_batch_training import FakeEnterprise
from training_snapshot_support import commit


class MapAuthorizer:
    configured = True
    mode = "local"
    portal_url = None

    def __init__(self, scopes):
        self.scopes = scopes

    def authorize(self, header, company_id):
        scope = self.scopes.get((header, company_id))
        if scope is None:
            from sme_fraud.auth import AuthError
            raise AuthError(403, "ACCESS_DENIED", "Không có quyền truy cập doanh nghiệp.", "Kiểm tra tài khoản và doanh nghiệp.")
        return scope

    def describe(self, header):
        companies = sorted({cid for (hdr, cid) in self.scopes if hdr == header})
        if not companies:
            from sme_fraud.auth import AuthError
            raise AuthError(401, "AUTH_REQUIRED", "Chưa đăng nhập.", "Đăng nhập để tiếp tục.")
        sample = next(s for (hdr, _), s in self.scopes.items() if hdr == header)
        return dict(actor_id=sample.actor_id, tenant_id=sample.tenant_id, companies=companies)


class BatchTrainingPortalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

        self.scopes = {
            ("Bearer op-c001", "C001"): AccessScope("tenant-a", frozenset({"C001"}), "operator-c001", frozenset({"data.import", "evidence.verify", "model.fit"})),
            ("Bearer verifier-c001", "C001"): AccessScope("tenant-a", frozenset({"C001"}), "verifier-c001", frozenset({"data.import", "evidence.verify"})),
            ("Bearer fitter-c001", "C001"): AccessScope("tenant-a", frozenset({"C001"}), "fitter-c001", frozenset({"data.import", "model.fit"})),
            ("Bearer viewer-c001", "C001"): AccessScope("tenant-a", frozenset({"C001"}), "viewer-c001", frozenset({"data.import"})),
            ("Bearer op-c002", "C002"): AccessScope("tenant-a", frozenset({"C002"}), "operator-c002", frozenset({"data.import", "evidence.verify", "model.fit"})),
        }
        self.auth = MapAuthorizer(self.scopes)
        self.snapshots = SnapshotStore(self.root / "snapshots.sqlite3")
        self.labels = LabelStore(self.root / "labels.sqlite3", secrets.token_bytes(32))

        self.company_keys = {
            "C001": Ed25519PrivateKey.generate(),
            "C002": Ed25519PrivateKey.generate(),
        }
        self.worker_key = Ed25519PrivateKey.generate()
        self.worker_pub = self.worker_key.public_key().public_bytes_raw().hex()
        self.grants = {
            ("tenant-a", cid): dict(
                active=True,
                batch_training=True,
                node_verify_key=self.company_keys[cid].public_key().public_bytes_raw().hex(),
                key_epoch="batch-key-" + cid,
                target=TARGET,
                verification_mode="synthetic_expected",
            )
            for cid in ("C001", "C002")
        }
        self.calls = []
        self.fail_on = None
        self.cloud_store = BatchCloudStore(self.root / "cloud", self.grants, self.worker_key, "b" * 64, self._evaluate)
        self.addCleanup(lambda: self.cloud_store.close())

        def make_node(session_dir, scope, company, recheck):
            node = FakeEnterprise(session_dir, scope, self.company_keys[company], self.cloud_store)
            node.recheck = recheck
            return node, "http://127.0.0.1:9999", self.worker_pub

        self.manager = BatchTrainingManager(
            self.root / "batch-training.sqlite3",
            secrets.token_bytes(32),
            snapshot_store=self.snapshots,
            label_store=self.labels,
            enterprise_root=self.root / "enterprise",
            worker_url="http://127.0.0.1:9999",
            worker_verify_key=self.worker_pub,
            node_factory=make_node,
        )
        self.server = make_server(
            0,
            authorizer=self.auth,
            snapshot_store=self.snapshots,
            label_store=self.labels,
            batch_training=self.manager,
        )
        self.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._stop_server)

    def _stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def _evaluate(self, x, y, w, body):
        self.calls.append((body["company_id"], strict_json(x), strict_json(y), strict_json(w)))
        if self.fail_on == len(self.calls):
            raise RuntimeError("simulated worker crash mid-update")
        return canonical(oracle(strict_json(x), strict_json(y), strict_json(w)))

    def _restart_cloud_store(self):
        self.cloud_store.close()
        self.cloud_store = BatchCloudStore(self.root / "cloud", self.grants, self.worker_key, "b" * 64, self._evaluate)

    def _http(self, method, path, *, token="op-c001", body=None, idem_key=None):
        headers = {"Host": f"127.0.0.1:{self.port}"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        raw = None
        if body is not None:
            raw = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
            headers["Idempotency-Key"] = idem_key or ("idem_" + secrets.token_hex(12))
        req = Request(f"http://127.0.0.1:{self.port}{path}", data=raw, headers=headers, method=method)
        try:
            with urlopen(req, timeout=15) as resp:
                ctype = resp.headers.get("Content-Type", "")
                payload = resp.read()
                return resp.status, (json.loads(payload.decode("utf-8")) if "application/json" in ctype else payload.decode("utf-8"))
        except HTTPError as exc:
            payload = exc.read().decode("utf-8")
            return exc.code, json.loads(payload)

    @staticmethod
    def _err_code(err):
        if isinstance(err, dict) and "errors" in err and err["errors"]:
            return err["errors"][0]["code"]
        return err.get("error", {}).get("code")

    def _commit_company_snapshot(self, company, scope_token):
        scope = self.scopes[(f"Bearer {scope_token}", company)]
        data, req = native_batches(company, scope.tenant_id)
        req["snapshot_id"] = commit(self.snapshots, data, scope)
        return req

    def _label_and_lock_packet(self, company, token, packet_id, outcome):
        status, pkt = self._http("GET", f"/api/v1/companies/{company}/label-packets/{packet_id}", token=token)
        self.assertEqual(status, 200)
        for case in pkt["cases"]:
            status, pkt = self._http(
                "POST",
                f"/api/v1/companies/{company}/label-packets/{packet_id}/save",
                token=token,
                body=dict(
                    expected_revision=pkt["revision"],
                    request_id=secrets.token_hex(16),
                    label=dict(
                        record_id=case["record_id"],
                        revision=case["revision"],
                        outcome=outcome,
                        explanation="Đã đối chiếu chứng từ gốc và xác nhận kết luận.",
                        evidence_ids=[case["evidence"][0]["evidence_id"]],
                        documents_checked=True,
                    ),
                ),
            )
            self.assertEqual(status, 200)
        status, pkt = self._http(
            "POST",
            f"/api/v1/companies/{company}/label-packets/{packet_id}/lock",
            token=token,
            body=dict(expected_revision=pkt["revision"], request_id=secrets.token_hex(16)),
        )
        self.assertEqual(status, 200)
        return pkt

    def test_portal_bridge_allowlist_and_static_assets(self):
        self.assertIn("/batch-training", PUBLIC)
        self.assertIn("/assets/batch-training.js", PUBLIC)
        self.assertTrue(allowed_path("/batch-training"))
        self.assertTrue(allowed_path("/assets/batch-training.js"))
        for action in (
            "",
            "/preview",
            "/create-labels",
            "/confirm",
            "/resume",
            "/receive",
            "/evaluate",
            "/approve",
            "/shadow",
            "/shadow-runs",
            "/shadow-runs/check",
            "/shadow-runs/shrun_1_0123456789abcdef",
        ):
            self.assertTrue(allowed_path(f"/api/v1/companies/C001/batch-training{action}"))
        self.assertFalse(allowed_path("/api/v1/companies/C001/batch-training/delete"))
        self.assertFalse(allowed_path("/api/v1/companies/C001/batch-training/shadow-runs/invalid"))
        code, html = self._http("GET", "/batch-training", token=None)
        self.assertEqual(code, 200)
        self.assertIn("Bước 1. Chọn dữ liệu và xem kế hoạch", html)
        self.assertIn("Bước 7. Phê duyệt dùng shadow", html)
        self.assertIn("Bước 8. Chấm đối chiếu shadow trên snapshot giao dịch mới và lịch sử lần chạy", html)
        code, js = self._http("GET", "/assets/batch-training.js", token=None)
        self.assertEqual(code, 200)
        self.assertIn("/batch-training", js)
        self.assertIn("/shadow-runs", js)

    def test_seven_step_portal_workflow_interruption_recovery_and_company_isolation(self):
        req_c001 = self._commit_company_snapshot("C001", "op-c001")
        req_c002 = self._commit_company_snapshot("C002", "op-c002")

        # Cross-company snapshot access blocked
        cross_req = deepcopy(req_c002)
        code, err = self._http("POST", "/api/v1/companies/C001/batch-training/preview", token="op-c001", body=dict(expected_revision=0, request=cross_req))
        self.assertEqual(code, 404)
        self.assertEqual(self._err_code(err), "SNAPSHOT_NOT_FOUND")

        # Overlapping train/evaluation rows blocked
        overlap_req = deepcopy(req_c001)
        overlap_req["evaluation_batches"][0][0] = overlap_req["training_batches"][0][0]
        code, err = self._http("POST", "/api/v1/companies/C001/batch-training/preview", token="op-c001", body=dict(expected_revision=0, request=overlap_req))
        self.assertEqual(code, 400)
        self.assertEqual(self._err_code(err), "TRAIN_EVALUATION_OVERLAP_OR_DUPLICATE")

        # Step 1: Valid plan preview for C001
        code, st1 = self._http("POST", "/api/v1/companies/C001/batch-training/preview", token="op-c001", body=dict(expected_revision=0, request=req_c001))
        self.assertEqual(code, 201)
        self.assertEqual(st1["revision"], 1)
        self.assertEqual(st1["session"]["phase"], "plan_ready")
        plan_sha_c001 = st1["session"]["plan_sha256"]
        self.assertEqual(st1["session"]["plan_summary"]["training_rows"], 8)
        self.assertEqual(st1["session"]["plan_summary"]["evaluation_rows"], 4)

        # Step 2: Creating labels requires evidence.verify
        code, err = self._http(
            "POST",
            "/api/v1/companies/C001/batch-training/create-labels",
            token="fitter-c001",
            body=dict(expected_revision=1, expected_plan_sha256=plan_sha_c001),
        )
        self.assertEqual(code, 403)
        self.assertEqual(self._err_code(err), "LABEL_VERIFY_DENIED")

        code, st2 = self._http(
            "POST",
            "/api/v1/companies/C001/batch-training/create-labels",
            token="verifier-c001",
            body=dict(expected_revision=1, expected_plan_sha256=plan_sha_c001),
        )
        self.assertEqual(code, 201)
        self.assertEqual(st2["revision"], 2)
        train_pkts = [p for p in st2["session"]["packets"] if p["partition"] == "training"]
        eval_pkts = [p for p in st2["session"]["packets"] if p["partition"] == "evaluation"]
        self.assertEqual(len(train_pkts), 2)
        self.assertEqual(len(eval_pkts), 1)

        # Step 3 blockers: missing labels, single-class labels, unlocked/reopened packets, stale plan
        code, err = self._http(
            "POST",
            "/api/v1/companies/C001/batch-training/confirm",
            token="fitter-c001",
            body=dict(expected_revision=2, expected_plan_sha256=plan_sha_c001, epochs=1),
        )
        self.assertEqual(code, 409)
        self.assertEqual(self._err_code(err), "BATCH_LABELS_INCOMPLETE")

        # Label both batches with the SAME class -> BOTH_LABEL_CLASSES_REQUIRED
        p0 = self._label_and_lock_packet("C001", "verifier-c001", train_pkts[0]["packet_id"], "verified_fraud")
        p1 = self._label_and_lock_packet("C001", "verifier-c001", train_pkts[1]["packet_id"], "verified_fraud")
        code, err = self._http(
            "POST",
            "/api/v1/companies/C001/batch-training/confirm",
            token="fitter-c001",
            body=dict(expected_revision=2, expected_plan_sha256=plan_sha_c001, epochs=1),
        )
        self.assertEqual(code, 409)
        self.assertEqual(self._err_code(err), "BOTH_LABEL_CLASSES_REQUIRED")

        # Reopen batch 1 to fix to verified_non_fraud, but test confirm while still unlocked -> LABEL_PACKET_NOT_LOCKED
        code, reopened = self._http(
            "POST",
            f"/api/v1/companies/C001/label-packets/{train_pkts[1]['packet_id']}/reopen",
            token="verifier-c001",
            body=dict(expected_revision=p1["revision"], request_id=secrets.token_hex(16)),
        )
        self.assertEqual(code, 200)
        stale_locks = [
            dict(packet_id=p0["packet_id"], revision=p0["revision"], lock_sha256=p0["lock_sha256"]),
            dict(packet_id=p1["packet_id"], revision=p1["revision"], lock_sha256=p1["lock_sha256"]),
        ]
        code, err = self._http(
            "POST",
            "/api/v1/companies/C001/batch-training/confirm",
            token="fitter-c001",
            body=dict(expected_revision=2, expected_plan_sha256=plan_sha_c001, epochs=1, locks=stale_locks),
        )
        self.assertEqual(code, 409)
        self.assertEqual(self._err_code(err), "LABEL_PACKET_NOT_LOCKED")

        # Save batch 1 as verified_non_fraud and lock it
        p1_new = self._label_and_lock_packet("C001", "verifier-c001", train_pkts[1]["packet_id"], "verified_non_fraud")
        # Also lock evaluation holdout labels for inspection only
        self._label_and_lock_packet("C001", "verifier-c001", eval_pkts[0]["packet_id"], "verified_non_fraud")

        # Passing the old revision pin for batch 1 is rejected with LABEL_PACKET_REVISION_STALE
        code, err = self._http(
            "POST",
            "/api/v1/companies/C001/batch-training/confirm",
            token="fitter-c001",
            body=dict(expected_revision=2, expected_plan_sha256=plan_sha_c001, epochs=1, locks=stale_locks),
        )
        self.assertEqual(code, 409)
        self.assertEqual(self._err_code(err), "LABEL_PACKET_REVISION_STALE")

        # Stale plan_sha256 rejected with BATCH_PREVIEW_STALE
        code, err = self._http(
            "POST",
            "/api/v1/companies/C001/batch-training/confirm",
            token="fitter-c001",
            body=dict(expected_revision=2, expected_plan_sha256="0" * 64, epochs=1),
        )
        self.assertEqual(code, 409)
        self.assertEqual(self._err_code(err), "BATCH_PREVIEW_STALE")

        # Step 3 & Step 4: Simulate worker crash on update #2 of 4 (2 batches * 2 epochs)
        self.fail_on = 2
        idem_confirm = "idem_confirm_c001_v1"
        code, st3 = self._http(
            "POST",
            "/api/v1/companies/C001/batch-training/confirm",
            token="fitter-c001",
            idem_key=idem_confirm,
            body=dict(expected_revision=2, expected_plan_sha256=plan_sha_c001, epochs=2),
        )
        self.assertEqual(code, 201)
        self.assertEqual(st3["session"]["phase"], "interrupted")
        job_id_c001 = st3["session"]["job_id"]
        dataset_id_c001 = st3["session"]["dataset_id"]
        self.assertTrue(job_id_c001.startswith("btr_"))

        # Retry with same Idempotency-Key returns identical receipt; different body -> 409 IDEMPOTENCY_CONFLICT
        code_retry, st3_retry = self._http(
            "POST",
            "/api/v1/companies/C001/batch-training/confirm",
            token="fitter-c001",
            idem_key=idem_confirm,
            body=dict(expected_revision=2, expected_plan_sha256=plan_sha_c001, epochs=2),
        )
        self.assertEqual(code_retry, 201)
        self.assertEqual(st3_retry["session"]["job_id"], job_id_c001)
        code_conflict, err_conflict = self._http(
            "POST",
            "/api/v1/companies/C001/batch-training/confirm",
            token="fitter-c001",
            idem_key=idem_confirm,
            body=dict(expected_revision=2, expected_plan_sha256=plan_sha_c001, epochs=1),
        )
        self.assertEqual(code_conflict, 409)
        self.assertEqual(self._err_code(err_conflict), "IDEMPOTENCY_CONFLICT")

        # Early receive before completion is strictly blocked
        code, err = self._http(
            "POST",
            "/api/v1/companies/C001/batch-training/receive",
            token="fitter-c001",
            body=dict(expected_revision=st3["revision"]),
        )
        self.assertEqual(code, 409)
        self.assertEqual(self._err_code(err), "BATCH_TRAINING_NOT_COMPLETED")

        # Simulate worker restart and page reload (GET status)
        self.fail_on = None
        self._restart_cloud_store()
        code, reloaded = self._http("GET", "/api/v1/companies/C001/batch-training", token="viewer-c001")
        self.assertEqual(code, 200)
        self.assertEqual(reloaded["session"]["job_id"], job_id_c001)
        self.assertEqual(reloaded["session"]["dataset_id"], dataset_id_c001)
        self.assertEqual(reloaded["session"]["worker_job"]["completed_updates"], 1)
        self.assertEqual(reloaded["session"]["worker_job"]["total_updates"], 4)

        # Step 4 Resume: continues from update #2 without re-running update #1
        code, st4 = self._http(
            "POST",
            "/api/v1/companies/C001/batch-training/resume",
            token="fitter-c001",
            body=dict(expected_revision=reloaded["revision"]),
        )
        self.assertEqual(code, 200)
        self.assertEqual(st4["session"]["phase"], "completed_waiting_receive")
        self.assertEqual(st4["session"]["job_id"], job_id_c001)
        self.assertEqual(st4["session"]["worker_job"]["completed_updates"], 4)
        # Update #1 ran once before crash, failed on #2, then resumed #2, #3, #4 -> 5 calls total (4 successful updates)
        self.assertEqual(len(self.calls), 5)

        # Step 5: Receive and validate candidate model
        code, st5 = self._http(
            "POST",
            "/api/v1/companies/C001/batch-training/receive",
            token="viewer-c001",
            body=dict(expected_revision=st4["revision"]),
        )
        self.assertEqual(code, 200)
        self.assertEqual(st5["session"]["phase"], "model_received")
        cand_c001 = st5["session"]["candidate"]
        self.assertEqual(cand_c001["status_label"], "Model ứng viên đã nhận và kiểm tra kỹ thuật")
        self.assertEqual(cand_c001["validation"], "quantized_batch_oracle_exact")
        self.assertEqual(cand_c001["weights_code"], [1, 1, -1])
        self.assertFalse(cand_c001["approved_for_shadow"])
        self.assertFalse(cand_c001["operational_activation"])

        # Shadow use before approval is blocked even after model is received
        code, err = self._http(
            "POST",
            "/api/v1/companies/C001/batch-training/shadow",
            token="viewer-c001",
            body=dict(expected_revision=st5["revision"]),
        )
        self.assertEqual(code, 409)
        self.assertEqual(self._err_code(err), "BATCH_MODEL_NOT_APPROVED")

        # Approval before holdout evaluation is blocked
        code, err = self._http(
            "POST",
            "/api/v1/companies/C001/batch-training/approve",
            token="fitter-c001",
            body=dict(expected_revision=st5["revision"], reason="Trying to approve before holdout evaluation."),
        )
        self.assertEqual(code, 409)
        self.assertEqual(self._err_code(err), "BATCH_HOLDOUT_EVALUATION_REQUIRED")

        # Step 6: Evaluate on locked holdout set
        code, st6 = self._http(
            "POST",
            "/api/v1/companies/C001/batch-training/evaluate",
            token="viewer-c001",
            body=dict(expected_revision=st5["revision"], use_locked_evaluation_labels=True),
        )
        self.assertEqual(code, 200)
        self.assertEqual(st6["session"]["phase"], "holdout_evaluated")
        ev_c001 = st6["session"]["evaluation"]
        self.assertTrue(ev_c001["held_out_from_training"])
        self.assertTrue(ev_c001["uncalibrated"])
        self.assertIsNone(ev_c001["accuracy"])
        self.assertFalse(ev_c001["labels_used_for_fit"])
        self.assertEqual(ev_c001["evaluation_rows"], 4)

        # Still blocked from shadow before Step 7 approval
        code, err = self._http(
            "POST",
            "/api/v1/companies/C001/batch-training/shadow",
            token="viewer-c001",
            body=dict(expected_revision=st6["revision"]),
        )
        self.assertEqual(code, 409)
        self.assertEqual(self._err_code(err), "BATCH_MODEL_NOT_APPROVED")

        # Step 7: Approve for shadow evaluation (requires model.fit + valid reason + matching hashes)
        code, err = self._http(
            "POST",
            "/api/v1/companies/C001/batch-training/approve",
            token="verifier-c001",
            body=dict(expected_revision=st6["revision"], reason="Verifier without model.fit cannot approve."),
        )
        self.assertEqual(code, 403)
        self.assertEqual(self._err_code(err), "MODEL_FIT_DENIED")

        code, st7 = self._http(
            "POST",
            "/api/v1/companies/C001/batch-training/approve",
            token="fitter-c001",
            body=dict(
                expected_revision=st6["revision"],
                reason="Đã kiểm tra parity kỹ thuật và điểm holdout; duyệt chạy đối chiếu shadow.",
                expected_model_cipher_sha256=cand_c001["model_cipher_sha256"],
                expected_plan_sha256=plan_sha_c001,
                expected_evaluation_sha256=st6["session"]["evaluation_sha256"],
            ),
        )
        self.assertEqual(code, 201)
        self.assertEqual(st7["session"]["phase"], "shadow_approved")
        app_c001 = st7["session"]["approval"]
        self.assertEqual(app_c001["actor_id"], "fitter-c001")
        self.assertTrue(app_c001["shadow_only"])
        self.assertFalse(app_c001["operational_activation"])
        self.assertFalse(app_c001["active_model_replaced"])
        self.assertFalse(app_c001["operational_queue_changed"])

        # Step 7b: Shadow scoring now succeeds
        code, st7_shadow = self._http(
            "POST",
            "/api/v1/companies/C001/batch-training/shadow",
            token="viewer-c001",
            body=dict(expected_revision=st7["revision"]),
        )
        self.assertEqual(code, 200)
        sh_c001 = st7_shadow["session"]["shadow"]
        self.assertTrue(sh_c001["shadow_only"])
        self.assertFalse(sh_c001["active_model_replaced"])
        self.assertFalse(sh_c001["operational_queue_changed"])
        self.assertEqual(len(sh_c001["rows"]), 4)

        # Now run C002 with opposite labels and verify complete isolation from C001
        code, c2_s0 = self._http("GET", "/api/v1/companies/C002/batch-training", token="op-c002")
        self.assertEqual(code, 200)
        self.assertEqual(c2_s0["revision"], 0)
        self.assertIsNone(c2_s0["session"])

        code, c2_s1 = self._http("POST", "/api/v1/companies/C002/batch-training/preview", token="op-c002", body=dict(expected_revision=0, request=req_c002))
        self.assertEqual(code, 201)
        plan_sha_c002 = c2_s1["session"]["plan_sha256"]
        self.assertNotEqual(plan_sha_c002, plan_sha_c001)

        code, c2_s2 = self._http(
            "POST",
            "/api/v1/companies/C002/batch-training/create-labels",
            token="op-c002",
            body=dict(expected_revision=c2_s1["revision"], expected_plan_sha256=plan_sha_c002),
        )
        self.assertEqual(code, 201)
        c2_train_pkts = [p for p in c2_s2["session"]["packets"] if p["partition"] == "training"]
        # Opposite class order for C002: batch 0 = non_fraud, batch 1 = fraud
        self._label_and_lock_packet("C002", "op-c002", c2_train_pkts[0]["packet_id"], "verified_non_fraud")
        self._label_and_lock_packet("C002", "op-c002", c2_train_pkts[1]["packet_id"], "verified_fraud")

        code, c2_s3 = self._http(
            "POST",
            "/api/v1/companies/C002/batch-training/confirm",
            token="op-c002",
            body=dict(expected_revision=c2_s2["revision"], expected_plan_sha256=plan_sha_c002, epochs=2),
        )
        self.assertEqual(code, 201)
        self.assertEqual(c2_s3["session"]["phase"], "completed_waiting_receive")
        self.assertNotEqual(c2_s3["session"]["job_id"], job_id_c001)

        code, c2_s5 = self._http(
            "POST",
            "/api/v1/companies/C002/batch-training/receive",
            token="op-c002",
            body=dict(expected_revision=c2_s3["revision"]),
        )
        self.assertEqual(code, 200)
        self.assertEqual(c2_s5["session"]["candidate"]["weights_code"], [-1, -1, 1])

        # Verify C001 state is completely untouched by C002
        code, c1_final = self._http("GET", "/api/v1/companies/C001/batch-training", token="viewer-c001")
        self.assertEqual(code, 200)
        self.assertEqual(c1_final["session"]["job_id"], job_id_c001)
        self.assertEqual(c1_final["session"]["candidate"]["weights_code"], [1, 1, -1])
        self.assertEqual(c1_final["session"]["phase"], "shadow_approved")

    def test_real_portal_proxy_batch_training_end_to_end(self):
        from test_portal_auth import PortalHarness, portal
        with PortalHarness() as h:
            h.agent.shutdown()
            h.agent.server_close()
            labels = LabelStore(h.root / "labels.sqlite3", secrets.token_bytes(32))
            tenant_id = h.policy["tenant_id"]
            grants = {
                (tenant_id, "C001"): dict(
                    active=True,
                    batch_training=True,
                    node_verify_key=self.company_keys["C001"].public_key().public_bytes_raw().hex(),
                    key_epoch="batch-key-C001",
                    target=TARGET,
                    verification_mode="synthetic_expected",
                )
            }
            cloud = BatchCloudStore(h.root / "cloud", grants, self.worker_key, "b" * 64, self._evaluate)
            h.stack.callback(cloud.close)

            def make_portal_node(session_dir, scope, company, recheck):
                node = FakeEnterprise(session_dir, scope, self.company_keys[company], cloud)
                node.recheck = recheck
                return node, "http://127.0.0.1:9999", self.worker_pub

            mgr = BatchTrainingManager(
                h.root / "batch-training.sqlite3",
                secrets.token_bytes(32),
                snapshot_store=h.store,
                label_store=labels,
                enterprise_root=h.root / "enterprise",
                worker_url="http://127.0.0.1:9999",
                worker_verify_key=self.worker_pub,
                node_factory=make_portal_node,
            )
            h.agent = make_server(0, h.authorizer, h.store, label_store=labels, batch_training=mgr)
            portal.CFG["agents"]["agent2"]["port"] = h.agent.server_port
            t = threading.Thread(target=h.agent.serve_forever, daemon=True)
            t.start()
            h.threads.append(t)

            self.assertEqual(h.request("/agent2/batch-training")[0], 200)
            self.assertEqual(h.request("/agent2/assets/batch-training.js")[0], 200)

            sc = AccessScope(tenant_id, frozenset({"C001"}), "portal-reviewer", frozenset({"data.import", "evidence.verify", "model.fit"}))
            data, req = native_batches("C001", tenant_id)
            req["snapshot_id"] = commit(h.store, data, sc)

            url = h.url("batch-training")
            code, init_state = h.request(url)
            self.assertEqual(code, 200)
            self.assertEqual(len(init_state["snapshots"]), 1)

            code, st1 = h.request(url + "/preview", dict(expected_revision=0, request=req), headers={"Idempotency-Key": "idem-portal-prev-1"})
            self.assertEqual(code, 201, st1)
            plan_sha = st1["session"]["plan_sha256"]

            # Without evidence.verify, create-labels is denied via Portal bridge
            code, _ = h.request(url + "/create-labels", dict(expected_revision=1, expected_plan_sha256=plan_sha), headers={"Idempotency-Key": "idem-portal-lbl-0"})
            self.assertEqual(code, 403)

            h.policy["memberships"][0]["permissions"] = ["data.import", "evidence.verify", "model.fit"]
            h.write_policy()

            code, st2 = h.request(url + "/create-labels", dict(expected_revision=1, expected_plan_sha256=plan_sha), headers={"Idempotency-Key": "idem-portal-lbl-1"})
            self.assertEqual(code, 201, st2)
            for idx, pkt_info in enumerate([p for p in st2["session"]["packets"] if p["partition"] == "training"]):
                lurl = h.url("label-packets/" + pkt_info["packet_id"])
                _, pkt = h.request(lurl)
                outcome = "verified_fraud" if idx == 0 else "verified_non_fraud"
                for case in pkt["cases"]:
                    _, pkt = h.request(
                        lurl + "/save",
                        dict(
                            expected_revision=pkt["revision"],
                            request_id=secrets.token_hex(16),
                            label=dict(
                                record_id=case["record_id"],
                                revision=case["revision"],
                                outcome=outcome,
                                explanation="Đã đối chiếu chứng từ qua Portal.",
                                evidence_ids=[case["evidence"][0]["evidence_id"]],
                                documents_checked=True,
                            ),
                        ),
                    )
                h.request(lurl + "/lock", dict(expected_revision=pkt["revision"], request_id=secrets.token_hex(16)))

            code, st3 = h.request(url + "/confirm", dict(expected_revision=2, expected_plan_sha256=plan_sha, epochs=1), headers={"Idempotency-Key": "idem-portal-cfm-1"})
            self.assertEqual(code, 201, st3)
            self.assertEqual(st3["session"]["phase"], "completed_waiting_receive")

            code, st5 = h.request(url + "/receive", dict(expected_revision=st3["revision"]), headers={"Idempotency-Key": "idem-portal-rcv-1"})
            self.assertEqual(code, 200, st5)
            self.assertEqual(st5["session"]["candidate"]["status_label"], "Model ứng viên đã nhận và kiểm tra kỹ thuật")

            code, st6 = h.request(url + "/evaluate", dict(expected_revision=st5["revision"]), headers={"Idempotency-Key": "idem-portal-evl-1"})
            self.assertEqual(code, 200, st6)
            self.assertTrue(st6["session"]["evaluation"]["held_out_from_training"])

            code, st7 = h.request(
                url + "/approve",
                dict(
                    expected_revision=st6["revision"],
                    reason="Phê duyệt chạy đối chiếu shadow qua Portal sau khi kiểm tra holdout.",
                    expected_model_cipher_sha256=st5["session"]["candidate"]["model_cipher_sha256"],
                    expected_plan_sha256=plan_sha,
                    expected_evaluation_sha256=st6["session"]["evaluation_sha256"],
                ),
                headers={"Idempotency-Key": "idem-portal-app-1"},
            )
            self.assertEqual(code, 201, st7)
            self.assertEqual(st7["session"]["approval"]["actor_id"], "portal-reviewer")

            code, st_sh = h.request(url + "/shadow", dict(expected_revision=st7["revision"]), headers={"Idempotency-Key": "idem-portal-shd-1"})
            self.assertEqual(code, 200, st_sh)
            self.assertTrue(st_sh["session"]["shadow"]["shadow_only"])
            self.assertFalse(st_sh["session"]["shadow"]["active_model_replaced"])
            self.assertEqual(len(st_sh["approved_models"]), 1)

            model_run_id = st_sh["approved_models"][0]["model_run_id"]
            code, chk = h.request(
                url + "/shadow-runs/check",
                dict(model_run_id=model_run_id, snapshot_id=req["snapshot_id"], as_of=req["as_of"]),
                headers={"Idempotency-Key": "idem-portal-shchk-1"},
            )
            self.assertEqual(code, 200, chk)
            self.assertTrue(chk["check"]["compatibility"]["compatible"])

            code, sh_run = h.request(
                url + "/shadow-runs",
                dict(model_run_id=model_run_id, snapshot_id=req["snapshot_id"], as_of=req["as_of"]),
                headers={"Idempotency-Key": "idem-portal-shrun-1"},
            )
            self.assertEqual(code, 201, sh_run)
            self.assertEqual(sh_run["shadow_run"]["summary"]["total_rows"], 12)
            self.assertEqual(sh_run["shadow_run"]["summary"]["scored_rows"], 12)

            code, sh_get = h.request(url + "/shadow-runs/" + sh_run["shadow_run"]["shadow_run_id"])
            self.assertEqual(code, 200, sh_get)
            self.assertEqual(sh_get["shadow_run"]["shadow_run_id"], sh_run["shadow_run"]["shadow_run_id"])

    def _train_and_approve_company_model(self, company, token, *, batch0_outcome="verified_fraud", batch1_outcome="verified_non_fraud"):
        req = self._commit_company_snapshot(company, token)
        code, cur = self._http("GET", f"/api/v1/companies/{company}/batch-training", token=token)
        self.assertEqual(code, 200)
        code, st1 = self._http(
            "POST",
            f"/api/v1/companies/{company}/batch-training/preview",
            token=token,
            body=dict(expected_revision=cur["revision"], request=req),
        )
        self.assertEqual(code, 201, st1)
        plan_sha = st1["session"]["plan_sha256"]
        code, st2 = self._http(
            "POST",
            f"/api/v1/companies/{company}/batch-training/create-labels",
            token=token,
            body=dict(expected_revision=st1["revision"], expected_plan_sha256=plan_sha),
        )
        self.assertEqual(code, 201, st2)
        train_pkts = [p for p in st2["session"]["packets"] if p["partition"] == "training"]
        self._label_and_lock_packet(company, token, train_pkts[0]["packet_id"], batch0_outcome)
        self._label_and_lock_packet(company, token, train_pkts[1]["packet_id"], batch1_outcome)
        code, st3 = self._http(
            "POST",
            f"/api/v1/companies/{company}/batch-training/confirm",
            token=token,
            body=dict(expected_revision=st2["revision"], expected_plan_sha256=plan_sha, epochs=2),
        )
        self.assertEqual(code, 201, st3)
        code, st5 = self._http(
            "POST",
            f"/api/v1/companies/{company}/batch-training/receive",
            token=token,
            body=dict(expected_revision=st3["revision"]),
        )
        self.assertEqual(code, 200, st5)
        code, st6 = self._http(
            "POST",
            f"/api/v1/companies/{company}/batch-training/evaluate",
            token=token,
            body=dict(expected_revision=st5["revision"]),
        )
        self.assertEqual(code, 200, st6)
        code, st7 = self._http(
            "POST",
            f"/api/v1/companies/{company}/batch-training/approve",
            token=token,
            body=dict(
                expected_revision=st6["revision"],
                reason=f"Phê duyệt model {company} để chạy đối chiếu shadow trên snapshot giao dịch mới.",
                expected_model_cipher_sha256=st5["session"]["candidate"]["model_cipher_sha256"],
                expected_plan_sha256=plan_sha,
                expected_evaluation_sha256=st6["session"]["evaluation_sha256"],
            ),
        )
        self.assertEqual(code, 201, st7)
        return req, st7["approved_models"][0]

    def _build_custom_rule_snapshot(
        self,
        company,
        tenant,
        rows_spec,
        *,
        as_of="2025-09-10T00:00:00+07:00",
        coverage_observed_at="2025-09-01T00:00:00+07:00",
        is_simulated=True,
        extra_docs=None,
    ):
        from datetime import datetime, timedelta, timezone
        from sme_fraud.import_files import canonical, digest
        from sme_fraud.native_rule_demo import base, evidence, finish
        from sme_fraud.rule_snapshot import CONTRACT

        c = base()
        c.rows = []
        for idx, spec in enumerate(rows_spec):
            at = datetime.fromisoformat(spec["posted_at"])
            obs = spec.get("observed_at", at.isoformat())
            amount = spec["amount_vnd"]
            same = spec.get("same_approver", True)
            missing_approval = spec.get("missing_approval", False)
            late_approval_at = spec.get("late_approval_at")
            c.pay(
                at,
                amount,
                invoice_number=spec.get("invoice_number", f"INV_SH_{company}_{idx}"),
                invoice_gross_vnd=abs(amount),
                creator_id=c.maker["employee_id"],
                approver_id="" if missing_approval else (c.maker["employee_id"] if same else c.director["employee_id"]),
                approved_at=late_approval_at or (at - timedelta(minutes=1)).isoformat(),
                observed_at=obs,
            )
            if spec.get("transaction_id"):
                c.rows[-1]["transaction_id"] = spec["transaction_id"]
        if extra_docs:
            for dspec in extra_docs:
                evidence(
                    c,
                    "transaction_documents",
                    record_id=dspec["document_id"],
                    vendor_id=c.vendor["vendor_id"],
                    transaction_id=dspec["transaction_id"],
                    document_type=dspec.get("document_type", "invoice"),
                    invoice_number="INV_LATE",
                    invoice_gross_vnd=1_500_000,
                    status="verified",
                    evidence_id="SIM_LATE_DOC",
                    verifier_id=c.director["employee_id"],
                    verified_at=dspec["verified_at"],
                    observed_at=dspec["observed_at"],
                )
        source = finish(c, company)
        source["tenant_id"] = tenant
        source["as_of"] = as_of
        source["is_simulated"] = is_simulated
        source["coverage"]["transactions"]["record_count"] = len(source["tables"]["transactions"])
        source["coverage"]["transactions"]["records_sha256"] = digest(canonical(source["tables"]["transactions"]))
        for coverage in source["coverage"].values():
            coverage.update(observed_at=coverage_observed_at, covered_through=as_of)
        return dict(
            contract_version=CONTRACT,
            tenant_id=tenant,
            company_id=company,
            source=source,
            candidate_transaction_ids=[r["transaction_id"] for r in source["tables"]["transactions"]],
        )

    def test_shadow_runs_on_new_snapshots_edge_cases_and_history(self):
        from training_snapshot_support import canonical_source

        scope_c001 = self.scopes[("Bearer op-c001", "C001")]
        scope_c002 = self.scopes[("Bearer op-c002", "C002")]

        # 1. Start a C001 run up to holdout_evaluated (NOT approved yet) and verify shadow-runs rejects it
        req_unapproved = self._commit_company_snapshot("C001", "op-c001")
        _, s1 = self._http("POST", "/api/v1/companies/C001/batch-training/preview", token="op-c001", body=dict(expected_revision=0, request=req_unapproved))
        plan_sha = s1["session"]["plan_sha256"]
        _, s2 = self._http("POST", "/api/v1/companies/C001/batch-training/create-labels", token="op-c001", body=dict(expected_revision=s1["revision"], expected_plan_sha256=plan_sha))
        for i, p in enumerate([pk for pk in s2["session"]["packets"] if pk["partition"] == "training"]):
            self._label_and_lock_packet("C001", "op-c001", p["packet_id"], "verified_fraud" if i == 0 else "verified_non_fraud")
        _, s3 = self._http("POST", "/api/v1/companies/C001/batch-training/confirm", token="op-c001", body=dict(expected_revision=s2["revision"], expected_plan_sha256=plan_sha, epochs=2))
        _, s5 = self._http("POST", "/api/v1/companies/C001/batch-training/receive", token="op-c001", body=dict(expected_revision=s3["revision"]))
        _, s6 = self._http("POST", "/api/v1/companies/C001/batch-training/evaluate", token="op-c001", body=dict(expected_revision=s5["revision"]))
        unapproved_run_id = s6["session"]["run_id"]
        self.assertEqual(s6["approved_models"], [])

        # Missing model_run_id rejected
        code, err = self._http(
            "POST",
            "/api/v1/companies/C001/batch-training/shadow-runs",
            token="op-c001",
            body=dict(model_run_id="", snapshot_id=req_unapproved["snapshot_id"], as_of=req_unapproved["as_of"]),
        )
        self.assertEqual(code, 400)
        self.assertEqual(self._err_code(err), "SHADOW_MODEL_SELECTION_REQUIRED")

        # Manual features x rejected on business shadow-runs endpoint
        code, err = self._http(
            "POST",
            "/api/v1/companies/C001/batch-training/shadow-runs",
            token="op-c001",
            body=dict(model_run_id=unapproved_run_id, snapshot_id=req_unapproved["snapshot_id"], as_of=req_unapproved["as_of"], x=[[1, 1]]),
        )
        self.assertEqual(code, 400)
        self.assertEqual(self._err_code(err), "SHADOW_MANUAL_FEATURES_FORBIDDEN")

        # Unapproved model rejected with 409 BATCH_MODEL_NOT_APPROVED
        code, err = self._http(
            "POST",
            "/api/v1/companies/C001/batch-training/shadow-runs",
            token="op-c001",
            body=dict(model_run_id=unapproved_run_id, snapshot_id=req_unapproved["snapshot_id"], as_of=req_unapproved["as_of"]),
        )
        self.assertEqual(code, 409)
        self.assertEqual(self._err_code(err), "BATCH_MODEL_NOT_APPROVED")

        # Now approve C001 model and train+approve C002 model (opposite weights)
        code, s7 = self._http(
            "POST",
            "/api/v1/companies/C001/batch-training/approve",
            token="op-c001",
            body=dict(
                expected_revision=s6["revision"],
                reason="Phê duyệt model C001 dùng chấm đối chiếu shadow trên snapshot mới.",
                expected_model_cipher_sha256=s5["session"]["candidate"]["model_cipher_sha256"],
                expected_plan_sha256=plan_sha,
                expected_evaluation_sha256=s6["session"]["evaluation_sha256"],
            ),
        )
        self.assertEqual(code, 201, s7)
        model_c001 = s7["approved_models"][0]
        self.assertEqual(model_c001["weights_code"], [1, 1, -1])

        req_c002, model_c002 = self._train_and_approve_company_model(
            "C002",
            "op-c002",
            batch0_outcome="verified_non_fraud",
            batch1_outcome="verified_fraud",
        )
        self.assertEqual(model_c002["weights_code"], [-1, -1, 1])

        # 2. Cross-company model & snapshot isolation
        code, err = self._http(
            "POST",
            "/api/v1/companies/C001/batch-training/shadow-runs",
            token="op-c001",
            body=dict(model_run_id=model_c002["model_run_id"], snapshot_id=req_unapproved["snapshot_id"], as_of=req_unapproved["as_of"]),
        )
        self.assertEqual(code, 404)
        self.assertEqual(self._err_code(err), "SHADOW_MODEL_NOT_FOUND")

        code, err = self._http(
            "POST",
            "/api/v1/companies/C001/batch-training/shadow-runs",
            token="op-c001",
            body=dict(model_run_id=model_c001["model_run_id"], snapshot_id=req_c002["snapshot_id"], as_of=req_c002["as_of"]),
        )
        self.assertEqual(code, 404)
        self.assertEqual(self._err_code(err), "SNAPSHOT_NOT_FOUND")

        # 3. Re-scoring training snapshot marks seen_in_training (8) and seen_in_evaluation (4)
        code, train_snap_run = self._http(
            "POST",
            "/api/v1/companies/C001/batch-training/shadow-runs",
            token="viewer-c001",
            body=dict(model_run_id=model_c001["model_run_id"], snapshot_id=req_unapproved["snapshot_id"], as_of=req_unapproved["as_of"]),
            idem_key="idem_c001_train_snap_1",
        )
        self.assertEqual(code, 201, train_snap_run)
        sr0 = train_snap_run["shadow_run"]
        self.assertTrue(sr0["snapshot"]["same_as_training_snapshot"])
        self.assertEqual(sr0["summary"]["total_rows"], 12)
        self.assertEqual(sr0["summary"]["scored_rows"], 12)
        self.assertEqual(sr0["summary"]["seen_in_training_rows"], 8)
        self.assertEqual(sr0["summary"]["seen_in_evaluation_rows"], 4)
        self.assertEqual(sr0["summary"]["new_transaction_rows"], 0)

        # 4. New snapshot with 7 transactions (not a multiple of 4):
        #    - 4 new valid rows with all 4 feature combinations (0,0), (1,0), (0,1), (1,1)
        #    - 1 row missing approver_id/approved_at -> FEATURE_MISSING (unavailable, score=None)
        #    - 1 row with posted_at after cutoff_1 -> ROW_NOT_AVAILABLE_AT_AS_OF (unavailable, score=None)
        #    - 1 row reusing a training transaction ID -> seen_in_training
        train_tx_id = model_c001["training_row_ids"][0]
        mixed_spec = [
            dict(transaction_id="TX_NEW_00", posted_at="2025-09-01T09:00:00+07:00", amount_vnd=1_500_000, same_approver=False),
            dict(transaction_id="TX_NEW_10", posted_at="2025-09-01T10:00:00+07:00", amount_vnd=2_000_000, same_approver=False),
            dict(transaction_id="TX_NEW_01", posted_at="2025-09-01T11:00:00+07:00", amount_vnd=1_500_000, same_approver=True),
            dict(transaction_id="TX_NEW_11", posted_at="2025-09-01T12:00:00+07:00", amount_vnd=3_000_000, same_approver=True),
            dict(transaction_id="TX_MISSING_APP", posted_at="2025-09-01T13:00:00+07:00", amount_vnd=4_000_000, missing_approval=True),
            dict(transaction_id=train_tx_id, posted_at="2025-09-01T14:00:00+07:00", amount_vnd=1_000_000, same_approver=True),
            dict(transaction_id="TX_AFTER_CUTOFF", posted_at="2025-09-05T09:00:00+07:00", amount_vnd=5_000_000, same_approver=True),
        ]
        mixed_bundle = self._build_custom_rule_snapshot("C001", scope_c001.tenant_id, mixed_spec, as_of="2025-09-10T00:00:00+07:00")
        snap_mixed_id = commit(self.snapshots, mixed_bundle, scope_c001, key="mixed-snap-c001")
        cutoff_1 = "2025-09-02T00:00:00+07:00"

        code, chk_mixed = self._http(
            "POST",
            "/api/v1/companies/C001/batch-training/shadow-runs/check",
            token="viewer-c001",
            body=dict(model_run_id=model_c001["model_run_id"], snapshot_id=snap_mixed_id, as_of=cutoff_1),
        )
        self.assertEqual(code, 200, chk_mixed)
        self.assertTrue(chk_mixed["check"]["compatibility"]["compatible"])
        self.assertEqual(chk_mixed["check"]["summary"]["total_rows"], 7)
        self.assertEqual(chk_mixed["check"]["summary"]["eligible_rows"], 5)
        self.assertEqual(chk_mixed["check"]["summary"]["unavailable_rows"], 2)
        self.assertEqual(chk_mixed["check"]["summary"]["post_cutoff_rows"], 1)
        self.assertEqual(chk_mixed["check"]["summary"]["missing_feature_rows"], 1)

        code, run_mixed = self._http(
            "POST",
            "/api/v1/companies/C001/batch-training/shadow-runs",
            token="viewer-c001",
            body=dict(model_run_id=model_c001["model_run_id"], snapshot_id=snap_mixed_id, as_of=cutoff_1),
            idem_key="idem_c001_mixed_run_1",
        )
        self.assertEqual(code, 201, run_mixed)
        self.assertFalse(run_mixed["reused_existing"])
        sr_mixed = run_mixed["shadow_run"]
        self.assertEqual(sr_mixed["status"], "completed_with_unavailable_rows")
        self.assertEqual(sr_mixed["summary"]["total_rows"], 7)
        self.assertEqual(sr_mixed["summary"]["scored_rows"], 5)
        self.assertEqual(sr_mixed["summary"]["unavailable_rows"], 2)
        self.assertEqual(sr_mixed["summary"]["new_transaction_rows"], 6)
        self.assertEqual(sr_mixed["summary"]["seen_in_training_rows"], 1)
        self.assertFalse(sr_mixed["batch_execution"]["training_four_row_limit_applied"])
        self.assertFalse(sr_mixed["batch_execution"]["truncated_to_64"])
        self.assertEqual(sr_mixed["batch_execution"]["call_count"], 1)
        self.assertEqual(sr_mixed["disclosures"]["execution_location"], "enterprise_node_decrypted_candidate")
        self.assertFalse(sr_mixed["disclosures"]["cloud_he_inference_performed"])
        self.assertTrue(sr_mixed["disclosures"]["uncalibrated"])
        self.assertFalse(sr_mixed["disclosures"]["active_model_replaced"])
        self.assertFalse(sr_mixed["disclosures"]["operational_queue_changed"])

        by_id = {r["record_id"]: r for r in sr_mixed["rows"]}
        self.assertEqual(len(by_id), 7)
        # Missing feature row has score=None, status=unavailable, FEATURE_MISSING
        self.assertIsNone(by_id["TX_MISSING_APP"]["score"])
        self.assertEqual(by_id["TX_MISSING_APP"]["status"], "unavailable")
        self.assertIsNone(by_id["TX_MISSING_APP"]["features"]["creator_equals_approver"])
        self.assertEqual(by_id["TX_MISSING_APP"]["issues"][0]["code"], "FEATURE_MISSING")
        # Post-cutoff row has score=None, status=unavailable, ROW_NOT_AVAILABLE_AT_AS_OF
        self.assertIsNone(by_id["TX_AFTER_CUTOFF"]["score"])
        self.assertEqual(by_id["TX_AFTER_CUTOFF"]["status"], "unavailable")
        self.assertEqual(by_id["TX_AFTER_CUTOFF"]["issues"][0]["code"], "ROW_NOT_AVAILABLE_AT_AS_OF")
        # Seen-in-training row is tagged seen_in_training
        self.assertEqual(by_id[train_tx_id]["history_status"], "seen_in_training")
        self.assertFalse(by_id[train_tx_id]["is_new_transaction"])
        # Scored rows follow exact ordering: (1,1) > (1,0)==(0,1) > (0,0) for weights [1, 1, -1]
        self.assertGreater(by_id["TX_NEW_11"]["score"], by_id["TX_NEW_10"]["score"])
        self.assertAlmostEqual(by_id["TX_NEW_10"]["score"], by_id["TX_NEW_01"]["score"], places=9)
        self.assertGreater(by_id["TX_NEW_10"]["score"], by_id["TX_NEW_00"]["score"])

        # 5. Late document invariance: adding a document observed after cutoff_1 does not alter features or scores at cutoff_1
        late_spec = deepcopy(mixed_spec)
        late_docs = [
            dict(
                document_id="DOC_LATE_1",
                company_id="C001",
                transaction_id="TX_NEW_00",
                document_type="invoice",
                verified_at="2025-09-04T10:00:00+07:00",
                observed_at="2025-09-04T10:00:00+07:00",
            )
        ]
        late_bundle = self._build_custom_rule_snapshot(
            "C001",
            scope_c001.tenant_id,
            late_spec,
            as_of="2025-09-10T00:00:00+07:00",
            extra_docs=late_docs,
        )
        snap_late_id = commit(self.snapshots, late_bundle, scope_c001, key="late-snap-c001")
        code, run_late = self._http(
            "POST",
            "/api/v1/companies/C001/batch-training/shadow-runs",
            token="viewer-c001",
            body=dict(model_run_id=model_c001["model_run_id"], snapshot_id=snap_late_id, as_of=cutoff_1),
            idem_key="idem_c001_late_run_1",
        )
        self.assertEqual(code, 201, run_late)
        for r_orig, r_late in zip(sr_mixed["rows"], run_late["shadow_run"]["rows"]):
            self.assertEqual(r_orig["record_id"], r_late["record_id"])
            self.assertEqual(r_orig["status"], r_late["status"])
            self.assertEqual(r_orig["features"], r_late["features"])
            self.assertEqual(r_orig["score"], r_late["score"])

        # 6. Idempotency: same Idempotency-Key OR same (model, snapshot_id, as_of) does not create duplicate run
        code, retry_same_idem = self._http(
            "POST",
            "/api/v1/companies/C001/batch-training/shadow-runs",
            token="viewer-c001",
            body=dict(model_run_id=model_c001["model_run_id"], snapshot_id=snap_mixed_id, as_of=cutoff_1),
            idem_key="idem_c001_mixed_run_1",
        )
        self.assertEqual(code, 200, retry_same_idem)
        self.assertTrue(retry_same_idem["reused_existing"])
        self.assertEqual(retry_same_idem["shadow_run"]["shadow_run_id"], sr_mixed["shadow_run_id"])

        code, retry_lost_resp = self._http(
            "POST",
            "/api/v1/companies/C001/batch-training/shadow-runs",
            token="viewer-c001",
            body=dict(model_run_id=model_c001["model_run_id"], snapshot_id=snap_mixed_id, as_of=cutoff_1),
            idem_key="idem_c001_mixed_run_second_key",
        )
        self.assertEqual(code, 200, retry_lost_resp)
        self.assertTrue(retry_lost_resp["reused_existing"])
        self.assertEqual(retry_lost_resp["shadow_run"]["shadow_run_id"], sr_mixed["shadow_run_id"])

        # Reusing idem_c001_mixed_run_1 with a different as_of raises 409 IDEMPOTENCY_CONFLICT
        code, err = self._http(
            "POST",
            "/api/v1/companies/C001/batch-training/shadow-runs",
            token="viewer-c001",
            body=dict(model_run_id=model_c001["model_run_id"], snapshot_id=snap_mixed_id, as_of="2025-09-10T00:00:00+07:00"),
            idem_key="idem_c001_mixed_run_1",
        )
        self.assertEqual(code, 409)
        self.assertEqual(self._err_code(err), "IDEMPOTENCY_CONFLICT")

        # Changing as_of to 2025-09-10T00:00:00+07:00 with a new key creates a new shadow run where TX_AFTER_CUTOFF is now scored!
        code, run_later_cutoff = self._http(
            "POST",
            "/api/v1/companies/C001/batch-training/shadow-runs",
            token="viewer-c001",
            body=dict(model_run_id=model_c001["model_run_id"], snapshot_id=snap_mixed_id, as_of="2025-09-10T00:00:00+07:00"),
            idem_key="idem_c001_mixed_run_later_cutoff",
        )
        self.assertEqual(code, 201, run_later_cutoff)
        self.assertFalse(run_later_cutoff["reused_existing"])
        self.assertNotEqual(run_later_cutoff["shadow_run"]["shadow_run_id"], sr_mixed["shadow_run_id"])
        self.assertEqual(run_later_cutoff["shadow_run"]["summary"]["scored_rows"], 6)
        self.assertEqual(run_later_cutoff["shadow_run"]["summary"]["post_cutoff_rows"], 0)

        # 7. Snapshot with > 64 rows (70 rows) is chunked into 2 calls (64 + 6), never truncated
        large_spec = [
            dict(
                transaction_id=f"TX_LARGE_{i:03d}",
                posted_at=f"2025-09-01T{(i // 60):02d}:{(i % 60):02d}:00+07:00",
                amount_vnd=1_000_000 if i % 2 == 0 else 1_250_000,
                same_approver=(i % 3 == 0),
            )
            for i in range(70)
        ]
        large_bundle = self._build_custom_rule_snapshot("C001", scope_c001.tenant_id, large_spec, as_of="2025-09-10T00:00:00+07:00")
        snap_large_id = commit(self.snapshots, large_bundle, scope_c001, key="large-70-c001")
        code, run_large = self._http(
            "POST",
            "/api/v1/companies/C001/batch-training/shadow-runs",
            token="viewer-c001",
            body=dict(model_run_id=model_c001["model_run_id"], snapshot_id=snap_large_id, as_of="2025-09-10T00:00:00+07:00"),
            idem_key="idem_c001_large_70",
        )
        self.assertEqual(code, 201, run_large)
        sr_large = run_large["shadow_run"]
        self.assertEqual(sr_large["summary"]["total_rows"], 70)
        self.assertEqual(sr_large["summary"]["scored_rows"], 70)
        self.assertEqual(sr_large["batch_execution"]["call_count"], 2)
        self.assertEqual([c["row_count"] for c in sr_large["batch_execution"]["chunks"]], [64, 6])
        self.assertFalse(sr_large["batch_execution"]["truncated_to_64"])

        # 8. Incompatible snapshot contract (canonical 1.0.0 vs model trained on agent2-rule-snapshot/1.0.0)
        canon_data = canonical_source("C001", scope_c001.tenant_id)
        snap_canon_id = commit(self.snapshots, canon_data, scope_c001, key="canon-c001")
        code, run_incompat = self._http(
            "POST",
            "/api/v1/companies/C001/batch-training/shadow-runs",
            token="viewer-c001",
            body=dict(model_run_id=model_c001["model_run_id"], snapshot_id=snap_canon_id, as_of="2026-10-02T00:00:00+07:00"),
            idem_key="idem_c001_incompat_canon",
        )
        self.assertEqual(code, 201, run_incompat)
        sr_incompat = run_incompat["shadow_run"]
        self.assertEqual(sr_incompat["status"], "incompatible_model")
        self.assertFalse(sr_incompat["compatibility"]["compatible"])
        mismatch_fields = {m["field"] for m in sr_incompat["compatibility"]["mismatches"]}
        self.assertIn("source_contract_version", mismatch_fields)
        self.assertIn("source_contract_fingerprint", mismatch_fields)
        self.assertIn("mapping_fingerprint", mismatch_fields)
        self.assertEqual(sr_incompat["summary"]["total_rows"], 4)
        self.assertEqual(sr_incompat["summary"]["scored_rows"], 0)
        self.assertEqual(sr_incompat["summary"]["incompatible_rows"], 4)
        self.assertTrue(all(r["status"] == "incompatible_model" and r["score"] is None for r in sr_incompat["rows"]))

        # 9. Verify C002 shadow run and complete history isolation between C001 and C002
        c002_spec = [
            dict(transaction_id="C002_NEW_00", posted_at="2025-09-01T09:00:00+07:00", amount_vnd=1_500_000, same_approver=False),
            dict(transaction_id="C002_NEW_11", posted_at="2025-09-01T10:00:00+07:00", amount_vnd=2_000_000, same_approver=True),
        ]
        c002_bundle = self._build_custom_rule_snapshot("C002", scope_c002.tenant_id, c002_spec, as_of="2025-09-10T00:00:00+07:00")
        snap_c002_new = commit(self.snapshots, c002_bundle, scope_c002, key="c002-new-snap")
        code, run_c002 = self._http(
            "POST",
            "/api/v1/companies/C002/batch-training/shadow-runs",
            token="op-c002",
            body=dict(model_run_id=model_c002["model_run_id"], snapshot_id=snap_c002_new, as_of="2025-09-10T00:00:00+07:00"),
            idem_key="idem_c002_new_run_1",
        )
        self.assertEqual(code, 201, run_c002)
        c2_rows = {r["record_id"]: r for r in run_c002["shadow_run"]["rows"]}
        # C002 has weights [-1, -1, 1], so (0,0) has a HIGHER score than (1,1)!
        self.assertGreater(c2_rows["C002_NEW_00"]["score"], c2_rows["C002_NEW_11"]["score"])

        # C001 cannot read C002's shadow_run_id
        code, err = self._http(
            "GET",
            f"/api/v1/companies/C001/batch-training/shadow-runs/{run_c002['shadow_run']['shadow_run_id']}",
            token="viewer-c001",
        )
        self.assertEqual(code, 404)
        self.assertEqual(self._err_code(err), "SHADOW_RUN_NOT_FOUND")

        # C001 history has all 6 saved runs intact
        code, c1_list = self._http("GET", "/api/v1/companies/C001/batch-training/shadow-runs", token="viewer-c001")
        self.assertEqual(code, 200)
        self.assertEqual(len(c1_list["shadow_runs"]), 6)
        self.assertTrue(all(r["company_id"] == "C001" for r in c1_list["shadow_runs"]))


if __name__ == "__main__":
    unittest.main()
