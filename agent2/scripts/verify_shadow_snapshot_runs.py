from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
for extra in (ROOT, ROOT / "tests", ROOT / "tests_he", Path(__file__).resolve().parent, REPO):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from playwright.sync_api import sync_playwright

from experiments.he_training.batch_enterprise import BatchEnterprise
from experiments.he_training.protocol import atomic, strict_json
from finance_input import AccessScope
from sme_fraud.batch_training_api import BatchTrainingManager
from sme_fraud.import_files import canonical, digest
from sme_fraud.label_packets import LabelStore
from sme_fraud.native_rule_demo import base, evidence, finish
from sme_fraud.review_server import make_server
from sme_fraud.rule_snapshot import CONTRACT
from sme_fraud.snapshots import SnapshotStore
from test_portal_auth import PortalHarness, portal
from training_snapshot_support import canonical_source, commit

SOURCE_HE_ACCEPTANCE_DIR = REPO / ".runtime" / "he-training-batches-20261115" / "portal-he-acceptance-v1"
DEFAULT_BUILD_DIR = REPO / ".runtime" / "he-training-20261115" / "build-v3"
RUNTIME_DIR = REPO / ".runtime" / "he-training-batches-20261115" / "shadow-snapshot-runs-acceptance-v1"
PUBLIC_JSON_REPORT = ROOT / "reports" / "shadow_snapshot_runs_acceptance.json"
PUBLIC_MD_REPORT = ROOT / "docs" / "SHADOW_SNAPSHOT_RUNS_ACCEPTANCE.md"


def launch_browser(p):
    for channel in ("chrome", "msedge", None):
        try:
            return p.chromium.launch(headless=True, channel=channel) if channel else p.chromium.launch(headless=True)
        except Exception:
            continue
    raise RuntimeError("Could not launch Chromium/Chrome/Edge via Playwright")


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic(path, json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))


def build_rule_snapshot_bundle(
    company: str,
    tenant: str,
    rows_spec: list[dict],
    *,
    as_of: str = "2025-09-10T00:00:00+07:00",
    coverage_observed_at: str = "2025-09-01T00:00:00+07:00",
    is_simulated: bool = True,
    extra_docs: list[dict] | None = None,
) -> dict:
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


def run_acceptance() -> dict:
    if not SOURCE_HE_ACCEPTANCE_DIR.exists():
        raise RuntimeError(f"Missing real Concrete HE acceptance artifacts at {SOURCE_HE_ACCEPTANCE_DIR}")
    RUNTIME_DIR.mkdir(parents=True, exist_ok=False)
    # Shadow reads already decrypted, signed models at the enterprise. It does
    # not need to copy gigabytes of private FHE context or evaluation keys.
    shutil.copytree(SOURCE_HE_ACCEPTANCE_DIR / "enterprise", RUNTIME_DIR / "enterprise",
                    ignore=shutil.ignore_patterns("context.sealed", "evaluation.keys"))

    import secrets
    from batch_training_support import native_batches
    from experiments.he_training.protocol import sha, verify

    enterprise_root = RUNTIME_DIR / "enterprise"
    build_dir = DEFAULT_BUILD_DIR
    meta_c001 = strict_json((enterprise_root / "C001" / "enterprise.json").read_bytes())
    tenant_id = meta_c001["tenant_id"]

    with PortalHarness() as h:
        h.agent.shutdown()
        h.agent.server_close()
        actor_id = h.policy["actor_id"]
        h.policy["tenant_id"] = tenant_id
        h.policy["memberships"] = [
            dict(company_id="C001", role="director", status="active", permissions=["data.import", "evidence.verify", "model.fit"]),
            dict(company_id="C002", role="director", status="active", permissions=["data.import", "evidence.verify", "model.fit"]),
        ]
        h.write_policy()

        from contextlib import closing
        snapshots = SnapshotStore(RUNTIME_DIR / "snapshots.sqlite3")
        labels = LabelStore(RUNTIME_DIR / "labels.sqlite3", secrets.token_bytes(32))

        def make_real_enterprise_node(session_dir: Path, scope: AccessScope, company: str, recheck):
            node = BatchEnterprise(session_dir, build_dir, scope, recheck=recheck)
            return node, "http://127.0.0.1:0", "0" * 64

        manager = BatchTrainingManager(
            RUNTIME_DIR / "batch-training.sqlite3",
            secrets.token_bytes(32),
            snapshot_store=snapshots,
            label_store=labels,
            enterprise_root=enterprise_root,
            build=build_dir,
            worker_url="http://127.0.0.1:0",
            worker_verify_key="0" * 64,
            node_factory=make_real_enterprise_node,
        )

        scope_c001 = AccessScope(tenant_id, frozenset({"C001"}), actor_id, frozenset({"data.import", "evidence.verify", "model.fit"}))
        scope_c002 = AccessScope(tenant_id, frozenset({"C002"}), actor_id, frozenset({"data.import", "evidence.verify", "model.fit"}))

        replay_snapshots = {}
        # Seed the journal with the real Concrete FHE trained & approved sessions for C001 and C002
        # and re-insert their original training snapshots into snapshots store so training_snapshot_id is selectable too
        for cid, sc in (("C001", scope_c001), ("C002", scope_c002)):
            sess_parent = enterprise_root / "_sessions" / f"{tenant_id}_{cid}"
            sess_dir = next(p for p in sess_parent.iterdir() if p.is_dir())
            run_id = sess_dir.name
            node = BatchEnterprise(sess_dir, build_dir, sc)
            source = node.saved("batch-source.json")
            candidate = node.saved("batch-candidate.json")["candidate"]
            evaluation = node.saved("batch-evaluation.json")["evaluation"]
            raw_approval = strict_json((sess_dir / "batch-approval.json").read_bytes())
            approval_body = dict(
                verify(raw_approval, node.public_key),
                approval_sha256=sha(canonical(raw_approval)),
                approved_for_shadow=True,
            )
            prov = source["content"]["provenance"]
            orig_snap_meta = prov["snapshot"]
            snap_data, _ = native_batches(cid, tenant_id)
            replay_snapshots[cid] = commit(snapshots, snap_data, sc, key="replay-training-" + cid)
            with manager._tx(sc, None, "model.fit") as conn:
                from sme_fraud.batch_training_api import _summarize_plan
                manager._append(
                    conn,
                    tenant_id,
                    cid,
                    dict(
                        version="portal-batch-training/0.1.0",
                        tenant_id=tenant_id,
                        company_id=cid,
                        revision=1,
                        run_id=run_id,
                        phase="shadow_approved",
                        request=prov["request"],
                        plan_sha256=prov["plan_sha256"],
                        plan_summary=_summarize_plan(prov),
                        packets=[],
                        locks=[],
                        evaluation_locks=[],
                        epochs=2,
                        dataset_id=source["dataset_id"],
                        job_id=candidate["job_id"],
                        consent_sha256=candidate["consent_sha256"],
                        worker_job=dict(job_id=candidate["job_id"], status="completed", completed_updates=4, total_updates=4),
                        candidate=dict(candidate, candidate_sha256=sha(canonical(candidate)), approved_for_shadow=True),
                        evaluation=evaluation,
                        evaluation_sha256=sha(canonical(evaluation)),
                        approval=approval_body,
                        shadow=None,
                        last_error=None,
                        created_at="2026-11-15T10:05:00Z",
                        updated_at="2026-11-15T10:15:00Z",
                        updated_by=actor_id,
                    ),
                )
                if cid == "C001":
                    # Also append a second unapproved run for C001 so we can test 409 BATCH_MODEL_NOT_APPROVED
                    manager._append(
                        conn,
                        tenant_id,
                        cid,
                        dict(
                            version="portal-batch-training/0.1.0",
                            tenant_id=tenant_id,
                            company_id=cid,
                            revision=2,
                            run_id="btrun_2_unapproved_candidate",
                            phase="holdout_evaluated",
                            request=prov["request"],
                            plan_sha256=prov["plan_sha256"],
                            plan_summary=_summarize_plan(prov),
                            packets=[],
                            locks=[],
                            evaluation_locks=[],
                            epochs=2,
                            dataset_id=source["dataset_id"],
                            job_id=candidate["job_id"],
                            consent_sha256=candidate["consent_sha256"],
                            worker_job=dict(job_id=candidate["job_id"], status="completed", completed_updates=4, total_updates=4),
                            candidate=dict(candidate, candidate_sha256=sha(canonical(candidate)), approved_for_shadow=False),
                            evaluation=evaluation,
                            evaluation_sha256=sha(canonical(evaluation)),
                            approval=None,
                            shadow=None,
                            last_error=None,
                            created_at="2026-11-15T10:16:00Z",
                            updated_at="2026-11-15T10:16:00Z",
                            updated_by=actor_id,
                        ),
                    )

        st_c001 = manager.status(scope_c001)
        st_c002 = manager.status(scope_c002)
        model_c001 = st_c001["approved_models"][0]
        model_c002 = st_c002["approved_models"][0]
        train_tx_c001 = model_c001["training_row_ids"][0]
        eval_tx_c001 = model_c001["evaluation_row_ids"][0]

        # Commit additional snapshots for C001 and C002 to test all scenarios
        # 1. Mixed new snapshot for C001 (7 rows: 4 new valid, 1 missing feature, 1 post-cutoff, 1 seen_in_training)
        mixed_spec_c001 = [
            dict(transaction_id="C001_NEW_00", posted_at="2025-09-01T09:00:00+07:00", amount_vnd=1_500_000, same_approver=False),
            dict(transaction_id="C001_NEW_10", posted_at="2025-09-01T10:00:00+07:00", amount_vnd=2_000_000, same_approver=False),
            dict(transaction_id="C001_NEW_01", posted_at="2025-09-01T11:00:00+07:00", amount_vnd=1_500_000, same_approver=True),
            dict(transaction_id="C001_NEW_11", posted_at="2025-09-01T12:00:00+07:00", amount_vnd=3_000_000, same_approver=True),
            dict(transaction_id="C001_MISSING_APPROVER", posted_at="2025-09-01T13:00:00+07:00", amount_vnd=4_000_000, missing_approval=True),
            dict(transaction_id=train_tx_c001, posted_at="2025-09-01T14:00:00+07:00", amount_vnd=1_000_000, same_approver=True),
            dict(transaction_id="C001_AFTER_CUTOFF", posted_at="2025-09-05T09:00:00+07:00", amount_vnd=5_000_000, same_approver=True),
        ]
        snap_mixed_c001 = commit(
            snapshots,
            build_rule_snapshot_bundle("C001", tenant_id, mixed_spec_c001, as_of="2025-09-10T00:00:00+07:00"),
            scope_c001,
            key="accept-mixed-c001",
        )

        # 2. Late document snapshot for C001 (to verify invariance at cutoff 2025-09-02T00:00:00+07:00)
        late_spec_c001 = deepcopy(mixed_spec_c001)
        snap_late_c001 = commit(
            snapshots,
            build_rule_snapshot_bundle(
                "C001",
                tenant_id,
                late_spec_c001,
                as_of="2025-09-10T00:00:00+07:00",
                extra_docs=[
                    dict(
                        document_id="DOC_LATE_C001",
                        transaction_id="C001_NEW_00",
                        verified_at="2025-09-04T10:00:00+07:00",
                        observed_at="2025-09-04T10:00:00+07:00",
                    )
                ],
            ),
            scope_c001,
            key="accept-late-c001",
        )

        # 3. Large snapshot with 70 transactions (> 64 single-call limit) for C001
        large_spec_c001 = [
            dict(
                transaction_id=f"C001_BULK_{i:03d}",
                posted_at=f"2025-09-01T{(i // 60):02d}:{(i % 60):02d}:00+07:00",
                amount_vnd=1_000_000 if i % 2 == 0 else 1_250_000,
                same_approver=(i % 3 == 0),
            )
            for i in range(70)
        ]
        snap_large_c001 = commit(
            snapshots,
            build_rule_snapshot_bundle("C001", tenant_id, large_spec_c001, as_of="2025-09-10T00:00:00+07:00"),
            scope_c001,
            key="accept-large70-c001",
        )

        # 4. Incompatible canonical 1.0.0 snapshot for C001
        snap_incompat_c001 = commit(
            snapshots,
            canonical_source("C001", tenant_id),
            scope_c001,
            key="accept-canon-c001",
        )

        # 5. New snapshot for C002 (5 transactions)
        new_spec_c002 = [
            dict(transaction_id="C002_NEW_00", posted_at="2025-09-01T09:00:00+07:00", amount_vnd=1_500_000, same_approver=False),
            dict(transaction_id="C002_NEW_10", posted_at="2025-09-01T10:00:00+07:00", amount_vnd=2_000_000, same_approver=False),
            dict(transaction_id="C002_NEW_01", posted_at="2025-09-01T11:00:00+07:00", amount_vnd=1_500_000, same_approver=True),
            dict(transaction_id="C002_NEW_11", posted_at="2025-09-01T12:00:00+07:00", amount_vnd=3_000_000, same_approver=True),
            dict(transaction_id="C002_MISSING_APPROVER", posted_at="2025-09-01T13:00:00+07:00", amount_vnd=4_000_000, missing_approval=True),
        ]
        snap_new_c002 = commit(
            snapshots,
            build_rule_snapshot_bundle("C002", tenant_id, new_spec_c002, as_of="2025-09-10T00:00:00+07:00"),
            scope_c002,
            key="accept-new-c002",
        )

        h.agent = make_server(0, h.authorizer, snapshots, label_store=labels, batch_training=manager)
        portal.CFG["agents"]["agent2"]["port"] = h.agent.server_port
        srv_thread = threading.Thread(target=h.agent.serve_forever, daemon=True)
        srv_thread.start()
        h.threads.append(srv_thread)
        portal_base = f"http://127.0.0.1:{h.portal.server_port}"

        report: dict = dict(
            version="shadow-snapshot-runs-acceptance/1.0.0",
            verified_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            environment=dict(
                mode="portal_browser_and_real_enterprise_node_acceptance",
                browser_engine="Playwright Chromium",
                tenant_id=tenant_id,
                execution_location="enterprise_node_decrypted_candidate",
                cloud_he_inference_performed=False,
                manual_features_accepted_on_business_flow=False,
            ),
            cases={},
        )

        with sync_playwright() as p:
            pw_browser = launch_browser(p)
            context = pw_browser.new_context()
            page = context.new_page()
            page.add_init_script(f"window.sessionStorage.setItem('kt-session', {json.dumps(h.token)});")

            # Navigate to Portal /agent2/batch-training for C001
            page.goto(f"{portal_base}/agent2/batch-training#company=C001", wait_until="networkidle")
            page.wait_for_function("() => document.getElementById('bt-company')?.value === 'C001'", timeout=15000)

            # Verify Case 0: UI does NOT auto-select the latest model on initial load
            initial_model_val = page.locator("#bt-shadow-model").input_value()
            check_btn_disabled_initially = page.locator("#bt-shadow-check-btn").is_disabled()
            run_btn_disabled_initially = page.locator("#bt-shadow-run-btn").is_disabled()
            if initial_model_val != "" or not check_btn_disabled_initially or not run_btn_disabled_initially:
                raise AssertionError("UI must not auto-select a model before user explicitly chooses one")
            report["cases"]["0_explicit_model_selection_no_auto_select"] = dict(
                passed=True,
                initial_selected_model=initial_model_val,
                check_button_disabled_before_selection=check_btn_disabled_initially,
                run_button_disabled_before_selection=run_btn_disabled_initially,
            )

            # Case 1: Select C001 approved model + mixed snapshot (7 rows) at cutoff 2025-09-02T00:00:00+07:00
            cutoff_early = "2025-09-02T00:00:00+07:00"
            page.select_option("#bt-shadow-model", model_c001["model_run_id"])
            page.select_option("#bt-shadow-snapshot", snap_mixed_c001)
            page.fill("#bt-shadow-as-of", cutoff_early)

            # Click "Kiểm tra tương thích"
            page.click("#bt-shadow-check-btn")
            page.wait_for_function(
                "() => document.getElementById('bt-notice')?.textContent.includes('Kiểm tra tương thích đạt')",
                timeout=15000,
            )
            check_tech = json.loads(page.locator("#bt-step8-tech").text_content())

            # Click "Chạy chấm shadow và lưu kết quả"
            page.click("#bt-shadow-run-btn")
            page.wait_for_function(
                "() => document.getElementById('bt-notice')?.textContent.includes('Đã lưu lần chạy shadow')",
                timeout=15000,
            )
            run_mixed_doc = json.loads(page.locator("#bt-step8-tech").text_content())
            ui_table_rows = page.locator("#bt-shadow-run-table tbody tr").count()

            # Verify sorting toggle (score_desc vs row_asc) in UI
            first_row_score_desc = page.locator("#bt-shadow-run-table tbody tr").first.get_attribute("data-record-id")
            page.select_option("#bt-shadow-sort", "row_asc")
            first_row_asc = page.locator("#bt-shadow-run-table tbody tr").first.get_attribute("data-record-id")
            page.select_option("#bt-shadow-sort", "score_desc")

            # Verify F5 reload restores the exact saved shadow run without resetting or losing history
            page.reload(wait_until="networkidle")
            page.wait_for_function(
                "expected => document.getElementById('bt-shadow-history')?.value === expected",
                arg=run_mixed_doc["shadow_run_id"],
                timeout=15000,
            )
            reloaded_doc = json.loads(page.locator("#bt-step8-tech").text_content())

            report["cases"]["1_and_2_mixed_snapshot_missing_and_post_cutoff"] = dict(
                passed=(
                    check_tech["compatibility"]["compatible"] is True
                    and run_mixed_doc["summary"]["total_rows"] == 7
                    and run_mixed_doc["summary"]["scored_rows"] == 5
                    and run_mixed_doc["summary"]["unavailable_rows"] == 2
                    and run_mixed_doc["summary"]["post_cutoff_rows"] == 1
                    and run_mixed_doc["summary"]["missing_feature_rows"] == 1
                    and ui_table_rows == 7
                    and reloaded_doc["shadow_run_id"] == run_mixed_doc["shadow_run_id"]
                ),
                shadow_run_id=run_mixed_doc["shadow_run_id"],
                snapshot_id=snap_mixed_c001,
                as_of=cutoff_early,
                model_run_id=model_c001["model_run_id"],
                model_cipher_sha256=model_c001["model_cipher_sha256"],
                approval_sha256=model_c001["approval_sha256"],
                summary=run_mixed_doc["summary"],
                first_row_when_sorted_score_desc=first_row_score_desc,
                first_row_when_sorted_row_asc=first_row_asc,
                reloaded_shadow_run_id=reloaded_doc["shadow_run_id"],
                rows=[
                    dict(
                        record_id=r["record_id"],
                        status=r["status"],
                        history_status=r["history_status"],
                        features=r["features"],
                        score=r["score"],
                        score_rank=r["score_rank"],
                        issue_codes=[i["code"] for i in r["issues"]],
                    )
                    for r in run_mixed_doc["rows"]
                ],
            )

            # Case 3: Large snapshot (70 transactions > 64 single-call limit)
            page.select_option("#bt-shadow-snapshot", snap_large_c001)
            page.fill("#bt-shadow-as-of", "2025-09-10T00:00:00+07:00")
            page.click("#bt-shadow-run-btn")
            page.wait_for_function(
                "() => document.getElementById('bt-notice')?.textContent.includes('70/70 giao dịch đã chấm')",
                timeout=15000,
            )
            run_large_doc = json.loads(page.locator("#bt-step8-tech").text_content())
            report["cases"]["3_large_snapshot_over_64_rows_chunked"] = dict(
                passed=(
                    run_large_doc["summary"]["total_rows"] == 70
                    and run_large_doc["summary"]["scored_rows"] == 70
                    and run_large_doc["batch_execution"]["call_count"] == 2
                    and run_large_doc["batch_execution"]["truncated_to_64"] is False
                    and run_large_doc["batch_execution"]["training_four_row_limit_applied"] is False
                ),
                shadow_run_id=run_large_doc["shadow_run_id"],
                snapshot_id=snap_large_c001,
                batch_execution=run_large_doc["batch_execution"],
                summary=run_large_doc["summary"],
            )

            # Case 4: Training snapshot re-scored -> distinguishes seen_in_training (8) and seen_in_evaluation (4)
            train_snap_id = replay_snapshots["C001"]
            page.select_option("#bt-shadow-snapshot", train_snap_id)
            page.click("#bt-shadow-run-btn")
            page.wait_for_function(
                "() => document.getElementById('bt-notice')?.textContent.includes('12/12 giao dịch đã chấm')",
                timeout=15000,
            )
            run_train_snap_doc = json.loads(page.locator("#bt-step8-tech").text_content())
            report["cases"]["4_training_and_holdout_overlap_tagging"] = dict(
                passed=(
                    run_train_snap_doc["snapshot"]["same_as_training_snapshot"] is False
                    and run_train_snap_doc["summary"]["seen_in_training_rows"] == 8
                    and run_train_snap_doc["summary"]["seen_in_evaluation_rows"] == 4
                    and run_train_snap_doc["summary"]["new_transaction_rows"] == 0
                ),
                shadow_run_id=run_train_snap_doc["shadow_run_id"],
                snapshot_id=train_snap_id,
                summary=run_train_snap_doc["summary"],
            )

            # Case 6: Incompatible snapshot contract (canonical 1.0.0 vs rule snapshot model)
            page.select_option("#bt-shadow-snapshot", snap_incompat_c001)
            page.fill("#bt-shadow-as-of", "2026-10-02T00:00:00+07:00")
            page.click("#bt-shadow-check-btn")
            page.wait_for_function(
                "() => document.getElementById('bt-notice')?.textContent.includes('không tương thích hợp đồng')",
                timeout=15000,
            )
            incompat_check_doc = json.loads(page.locator("#bt-step8-tech").text_content())
            page.click("#bt-shadow-run-btn")
            page.wait_for_function(
                "() => document.getElementById('bt-step8-tech')?.textContent.includes('shrun_')",
                timeout=15000,
            )
            incompat_run_doc = json.loads(page.locator("#bt-step8-tech").text_content())
            report["cases"]["6_incompatible_model_contract_detected"] = dict(
                passed=(
                    incompat_check_doc["compatibility"]["compatible"] is False
                    and incompat_run_doc["status"] == "incompatible_model"
                    and incompat_run_doc["summary"]["total_rows"] == 4
                    and incompat_run_doc["summary"]["scored_rows"] == 0
                    and incompat_run_doc["summary"]["incompatible_rows"] == 4
                ),
                shadow_run_id=incompat_run_doc["shadow_run_id"],
                snapshot_id=snap_incompat_c001,
                mismatches=incompat_run_doc["compatibility"]["mismatches"],
                summary=incompat_run_doc["summary"],
            )

            # Case 7: Late document/approval invariance at past cutoff_early
            page.select_option("#bt-shadow-snapshot", snap_late_c001)
            page.fill("#bt-shadow-as-of", cutoff_early)
            page.click("#bt-shadow-run-btn")
            page.wait_for_function(
                "expected => document.getElementById('bt-step8-tech')?.textContent.includes(expected)",
                arg=snap_late_c001,
                timeout=15000,
            )
            run_late_doc = json.loads(page.locator("#bt-step8-tech").text_content())
            parity_with_mixed = [
                (a["record_id"], a["status"], a["features"], a["score"])
                == (b["record_id"], b["status"], b["features"], b["score"])
                for a, b in zip(run_mixed_doc["rows"], run_late_doc["rows"])
            ]
            report["cases"]["7_late_document_and_approval_invariance"] = dict(
                passed=all(parity_with_mixed) and len(parity_with_mixed) == 7,
                baseline_shadow_run_id=run_mixed_doc["shadow_run_id"],
                late_snapshot_shadow_run_id=run_late_doc["shadow_run_id"],
                as_of=cutoff_early,
                all_7_rows_identical_features_and_scores=all(parity_with_mixed),
            )

            # Case 8: Idempotency (re-running exact same model + snapshot + as_of returns existing run, no duplicate)
            history_count_before = page.locator("#bt-shadow-history option").count() - 1
            page.click("#bt-shadow-run-btn")
            page.wait_for_function(
                "() => document.getElementById('bt-notice')?.textContent.includes('không tạo bản ghi trùng')",
                timeout=15000,
            )
            history_count_after = page.locator("#bt-shadow-history option").count() - 1
            report["cases"]["8_idempotency_and_history_preservation"] = dict(
                passed=(history_count_before == history_count_after == 5),
                c001_saved_shadow_runs_count=history_count_after,
                duplicate_run_created=False,
            )

            # Case 5 & 9: Switch company to C002 in browser and verify C002 isolation + opposite model weights
            page.select_option("#bt-company", "C002")
            page.wait_for_function(
                "expected => Array.from(document.querySelectorAll('#bt-shadow-model option')).some(o => o.value === expected)",
                arg=model_c002["model_run_id"],
                timeout=15000,
            )
            c002_initial_model = page.locator("#bt-shadow-model").input_value()
            c002_initial_history_count = page.locator("#bt-shadow-history option").count() - 1

            page.select_option("#bt-shadow-model", model_c002["model_run_id"])
            page.select_option("#bt-shadow-snapshot", snap_new_c002)
            page.fill("#bt-shadow-as-of", "2025-09-10T00:00:00+07:00")
            page.click("#bt-shadow-run-btn")
            page.wait_for_function(
                "() => document.getElementById('bt-notice')?.textContent.includes('Đã lưu lần chạy shadow')",
                timeout=15000,
            )
            run_c002_doc = json.loads(page.locator("#bt-step8-tech").text_content())

            # Also verify API rejection for unapproved model, cross-company model/snapshot, and manual features
            unapp_code, unapp_err = h.request(
                "/agent2/api/v1/companies/C001/batch-training/shadow-runs",
                dict(model_run_id="btrun_2_unapproved_candidate", snapshot_id=snap_mixed_c001, as_of=cutoff_early),
                headers={"Idempotency-Key": "idem-accept-unapproved-model"},
            )
            cross_model_code, cross_model_err = h.request(
                "/agent2/api/v1/companies/C001/batch-training/shadow-runs",
                dict(model_run_id=model_c002["model_run_id"], snapshot_id=snap_mixed_c001, as_of=cutoff_early),
                headers={"Idempotency-Key": "idem-accept-cross-model"},
            )
            cross_snap_code, cross_snap_err = h.request(
                "/agent2/api/v1/companies/C001/batch-training/shadow-runs",
                dict(model_run_id=model_c001["model_run_id"], snapshot_id=snap_new_c002, as_of="2025-09-10T00:00:00+07:00"),
                headers={"Idempotency-Key": "idem-accept-cross-snap"},
            )
            manual_x_code, manual_x_err = h.request(
                "/agent2/api/v1/companies/C001/batch-training/shadow-runs",
                dict(model_run_id=model_c001["model_run_id"], snapshot_id=snap_mixed_c001, as_of=cutoff_early, x=[[1, 1]]),
                headers={"Idempotency-Key": "idem-accept-manual-x"},
            )

            c2_by_id = {r["record_id"]: r for r in run_c002_doc["rows"]}
            report["cases"]["5_and_9_company_isolation_and_security_guards"] = dict(
                passed=(
                    c002_initial_model == ""
                    and c002_initial_history_count == 0
                    and run_c002_doc["summary"]["total_rows"] == 5
                    and run_c002_doc["summary"]["scored_rows"] == 4
                    and run_c002_doc["summary"]["unavailable_rows"] == 1
                    and c2_by_id["C002_NEW_00"]["score"] > c2_by_id["C002_NEW_11"]["score"]
                    and unapp_code == 409
                    and unapp_err["errors"][0]["code"] == "BATCH_MODEL_NOT_APPROVED"
                    and cross_model_code == 404
                    and cross_snap_code == 404
                    and manual_x_code == 400
                ),
                c002_shadow_run_id=run_c002_doc["shadow_run_id"],
                c002_model_run_id=model_c002["model_run_id"],
                c002_weights_code=model_c002["weights_code"],
                c002_summary=run_c002_doc["summary"],
                unapproved_model_http_status=unapp_code,
                unapproved_model_error_code=unapp_err["errors"][0]["code"],
                cross_company_model_http_status=cross_model_code,
                cross_company_model_error_code=cross_model_err["errors"][0]["code"],
                cross_company_snapshot_http_status=cross_snap_code,
                cross_company_snapshot_error_code=cross_snap_err["errors"][0]["code"],
                manual_features_http_status=manual_x_code,
                manual_features_error_code=manual_x_err["errors"][0]["code"],
            )

            # Join the newly saved real-model shadow with all 35 local rules
            # through the director-only API. No FHE training/inference is run.
            benchmarks=[]
            for cid,doc in (("C001",run_large_doc),("C002",run_c002_doc)):
                status,bench=h.request(h.url('pipeline-benchmarks',cid),dict(shadow_run_id=doc['shadow_run_id']))
                assert status==200, (status,bench)
                assert bench['candidate_rows']==doc['summary']['total_rows']
                assert bench['fit_performed'] is False and bench['operational_queue_changed'] is False
                assert all(a['selected_count']<=5 for a in bench['comparison']['arms'])
                write_json(RUNTIME_DIR/(cid+'-benchmark.json'),bench)
                benchmarks.append(dict(company_id=cid,candidate_rows=bench['candidate_rows'],
                    eligible_rows=bench['eligible_rows'],report_sha256=bench['report_sha256'],
                    arms=[dict(name=a['name'],selected_count=a['selected_count']) for a in bench['comparison']['arms']]))
            # Replay before the locked source cutoff is supported by shadow,
            # while the existing 35-rule adapter requires its exact cutoff.
            status,cutoff_error=h.request(h.url('pipeline-benchmarks'),dict(shadow_run_id=run_mixed_doc['shadow_run_id']))
            assert status==422 and cutoff_error['errors'][0]['code']=='RULE_CUTOFF_MISMATCH'
            status,_=h.request(h.url('pipeline-benchmarks'),dict(shadow_run_id=run_large_doc['shadow_run_id'],x=[[1,1]]))
            assert status==400
            h.policy['memberships'][0]['role']='accountant';h.write_policy()
            status,_=h.request(h.url('pipeline-benchmarks'),dict(shadow_run_id=run_large_doc['shadow_run_id']))
            assert status==403
            h.policy['memberships'][0]['role']='director';h.write_policy()
            report['cases']['10_readonly_pipeline_benchmark']=dict(passed=True,companies=benchmarks,
                cutoff_mismatch_rejected=True,manual_scores_forbidden=True,director_only=True)
            pw_browser.close()

    report["all_passed"] = all(c["passed"] for c in report["cases"].values())
    write_json(PUBLIC_JSON_REPORT, report)
    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Isolated browser acceptance using previously trained real HE models.")
    parser.add_argument("--output", type=Path, help="New private runtime directory; existing evidence is never deleted")
    parser.add_argument("--report", type=Path, help="JSON report destination")
    args = parser.parse_args()
    if args.output: RUNTIME_DIR = args.output.resolve()
    if args.report: PUBLIC_JSON_REPORT = args.report.resolve()
    res = run_acceptance()
    print(json.dumps(dict(all_passed=res["all_passed"], cases={k: v["passed"] for k, v in res["cases"].items()}), indent=2))
