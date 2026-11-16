from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
for extra in (ROOT, ROOT / "tests", ROOT / "tests_he", Path(__file__).resolve().parent, REPO):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat
from playwright.sync_api import sync_playwright

from batch_training_support import native_batches
from demo_encrypted_training import start_worker, stop_worker
from demo_encrypted_training_batches import hard_kill
from experiments.he4.windows_bridge import linux_path
from experiments.he_training import TARGET
from experiments.he_training.batch_enterprise import BatchEnterprise
from experiments.he_training.protocol import atomic, canonical, sha, strict_json
from finance_input import AccessScope
from sme_fraud.batch_training_api import BatchTrainingManager
from sme_fraud.label_packets import LabelStore
from sme_fraud.review_server import make_server
from test_portal_auth import PortalHarness, portal
from training_snapshot_support import commit


def browser(p):
    for channel in ("chrome", "msedge", None):
        try:
            return p.chromium.launch(headless=True, channel=channel) if channel else p.chromium.launch(headless=True)
        except Exception:
            continue
    raise RuntimeError("Could not launch Chromium/Chrome/Edge via Playwright")


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic(path, json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))


DEFAULT_DEMO_CONTEXT_ROOT = REPO / ".runtime" / "he-training-20261115" / "native-demo-v1"
DEFAULT_BUILD_DIR = REPO / ".runtime" / "he-training-20261115" / "build-v3"
DEFAULT_RUNTIME_DIR = REPO / ".runtime" / "he-training-batches-20261115" / "portal-he-acceptance-v1"
PUBLIC_JSON_REPORT = ROOT / "reports" / "portal_he_batch_training_acceptance.json"
PUBLIC_MD_REPORT = ROOT / "docs" / "PORTAL_HE_BATCH_TRAINING_ACCEPTANCE.md"


def _link_or_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def _prepare_enterprise_base(demo_root: Path, runtime_root: Path, company: str) -> tuple[Path, dict]:
    src = demo_root / "enterprise" / company
    require_demo = strict_json((src / "dataset.json").read_bytes())
    if require_demo.get("simulated") is not True or not (src / "approval.json").is_file():
        raise RuntimeError(f"Reuse only completed synthetic demo contexts ({src})")
    dst = runtime_root / "enterprise" / company
    if dst.exists():
        shutil.rmtree(dst)
    (dst / "crypto").mkdir(parents=True, exist_ok=True)
    for name in ("enterprise.json", "wrapping.dpapi.json", "node-signing.dpapi.json"):
        shutil.copy2(src / name, dst / name)
    for name in ("context.sealed", "evaluation.keys"):
        _link_or_copy(src / "crypto" / name, dst / "crypto" / name)
    meta = strict_json((dst / "enterprise.json").read_bytes())
    return dst, meta


def _seed_session_from_base(base_dir: Path, session_dir: Path) -> None:
    if (session_dir / "enterprise.json").exists():
        return
    (session_dir / "crypto").mkdir(parents=True, exist_ok=True)
    for name in ("enterprise.json", "wrapping.dpapi.json", "node-signing.dpapi.json"):
        shutil.copy2(base_dir / name, session_dir / name)
    for name in ("context.sealed", "evaluation.keys"):
        _link_or_copy(base_dir / "crypto" / name, session_dir / "crypto" / name)


def _verify_and_lock_packets_in_browser(page, portal_base: str, company: str, packets: list[dict], outcomes_by_partition_batch: dict[tuple[str, int], str]) -> list[dict]:
    locked_evidence = []
    for pkt_idx, pkt in enumerate(packets):
        partition = pkt["partition"]
        batch_index = int(pkt["batch_index"])
        packet_id = pkt["packet_id"]
        outcome = outcomes_by_partition_batch[(partition, batch_index)]
        if pkt_idx == 0:
            page.goto(f"{portal_base}/agent2/label-verification#company={company}&packet={packet_id}", wait_until="networkidle")
        else:
            page.select_option("#lv-packets", packet_id)
        page.wait_for_function(
            "expected => document.getElementById('lv-packets')?.value === expected && document.querySelectorAll('#lv-cases button.case-choice').length === 4",
            arg=packet_id,
            timeout=15000,
        )
        for row_idx in range(4):
            page.locator("#lv-cases button.case-choice").nth(row_idx).click()
            page.wait_for_function(
                "() => !document.getElementById('lv-save').disabled",
                timeout=10000,
            )
            page.select_option("#lv-outcome", outcome)
            first_ev = page.locator("#lv-detail details[open] input.lv-evidence").first
            if not first_ev.is_checked():
                first_ev.check()
            if not page.locator("#lv-checked").is_checked():
                page.locator("#lv-checked").check()
            page.fill(
                "#lv-explanation",
                f"Nhãn synthetic kỳ vọng ({outcome}) dùng để nghiệm thu kỹ thuật luồng Portal HE batch cho {company} ({partition} batch #{batch_index + 1}).",
            )
            page.click("#lv-save")
            page.wait_for_function(
                "() => document.getElementById('lv-notice')?.textContent.includes('Đã lưu nhãn')",
                timeout=10000,
            )
        page.wait_for_function(
            "() => !document.getElementById('lv-lock').disabled",
            timeout=10000,
        )
        page.click("#lv-lock")
        page.wait_for_function(
            "() => document.getElementById('lv-notice')?.textContent.includes('Đã khóa đúng phiên bản nhãn')",
            timeout=10000,
        )
        status_text = page.locator("#lv-status").inner_text()
        locked_evidence.append(
            dict(
                partition=partition,
                batch_index=batch_index,
                packet_id=packet_id,
                synthetic_outcome=outcome,
                ui_status=status_text,
            )
        )
    return locked_evidence


def run_acceptance() -> dict:
    runtime = DEFAULT_RUNTIME_DIR
    if runtime.exists():
        shutil.rmtree(runtime)
    runtime.mkdir(parents=True, exist_ok=True)
    build_dir = DEFAULT_BUILD_DIR
    if not (build_dir / "client.specs.json").exists():
        raise RuntimeError(f"Missing Concrete build at {build_dir}")

    base_dirs: dict[str, Path] = {}
    metas: dict[str, dict] = {}
    for cid in ("C001", "C002"):
        base_dirs[cid], metas[cid] = _prepare_enterprise_base(DEFAULT_DEMO_CONTEXT_ROOT, runtime, cid)

    tenant_id = metas["C001"]["tenant_id"]
    build_sha256 = metas["C001"]["build_sha256"]

    cloud_dir = runtime / "cloud"
    cloud_dir.mkdir(parents=True, exist_ok=True)
    code_dir = cloud_dir / "code" / "experiments" / "he_training"
    code_dir.mkdir(parents=True, exist_ok=True)
    (code_dir.parent / "__init__.py").write_text("", encoding="utf-8")
    for mod_name in ("__init__.py", "protocol.py", "store.py", "worker.py", "batch_protocol.py", "batch_store.py"):
        shutil.copy2(ROOT / "experiments" / "he_training" / mod_name, code_dir / mod_name)
    public_build = cloud_dir / "build"
    public_build.mkdir(parents=True, exist_ok=True)
    for bname in ("manifest.json", "server.zip", "client.specs.json"):
        shutil.copy2(build_dir / bname, public_build / bname)

    wkey = Ed25519PrivateKey.generate()
    keyfile = cloud_dir / "worker-signing.key"
    keyfile.write_text(
        wkey.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption()).hex(),
        encoding="ascii",
    )
    config_path = cloud_dir / "worker-config.json"
    grants = []
    for cid in ("C001", "C002"):
        sc_init = AccessScope(
            tenant_id,
            frozenset({cid}),
            "synthetic-fit-operator",
            frozenset({"data.import", "model.fit"}),
        )
        node_init = BatchEnterprise(base_dirs[cid], build_dir, sc_init)
        eval_keys = cloud_dir / f"{cid}-evaluation.keys"
        _link_or_copy(base_dirs[cid] / "crypto" / "evaluation.keys", eval_keys)
        grants.append(
            dict(
                tenant_id=tenant_id,
                company_id=cid,
                active=True,
                batch_training=True,
                node_verify_key=node_init.public_key,
                key_epoch=node_init.meta["key_epoch"],
                target=TARGET,
                verification_mode="synthetic_expected",
                evaluation_keys_file=linux_path(eval_keys),
                evaluation_keys_sha256=sha(eval_keys.read_bytes()),
            )
        )
    atomic(
        config_path,
        canonical(
            dict(
                build=linux_path(public_build),
                state=linux_path(cloud_dir / "state"),
                worker_signing_key=linux_path(keyfile),
                grants=grants,
                batch_training=True,
            )
        ),
    )

    worker_proc, worker_ready, worker_url, worker_pub = start_worker(cloud_dir, config_path, 1)
    try:
        with PortalHarness() as h:
            h.agent.shutdown()
            h.agent.server_close()

            # Configure Portal policy with tenant_id="training-demo" and C001/C002 access
            actor_id = h.policy["actor_id"]
            h.policy["tenant_id"] = tenant_id
            h.policy["memberships"] = [
                dict(
                    company_id="C001",
                    role="director",
                    status="active",
                    permissions=["data.import", "evidence.verify", "model.fit"],
                ),
                dict(
                    company_id="C002",
                    role="director",
                    status="active",
                    permissions=["data.import", "evidence.verify", "model.fit"],
                ),
            ]
            h.write_policy()

            labels = LabelStore(runtime / "labels.sqlite3", secrets.token_bytes(32))

            mgr = BatchTrainingManager(
                runtime / "batch-training.sqlite3",
                secrets.token_bytes(32),
                snapshot_store=h.store,
                label_store=labels,
                enterprise_root=runtime / "enterprise",
                build=build_dir,
                worker_url=worker_url,
                worker_verify_key=worker_pub,
            )

            h.agent = make_server(0, h.authorizer, h.store, label_store=labels, batch_training=mgr)
            portal.CFG["agents"]["agent2"]["port"] = h.agent.server_port
            agent_thread = threading.Thread(target=h.agent.serve_forever, daemon=True)
            agent_thread.start()
            h.threads.append(agent_thread)

            # Commit synthetic snapshots for C001 and C002 (8 train rows = 2 batches x 4, 4 eval rows = 1 batch x 4)
            committed_requests: dict[str, dict] = {}
            for cid in ("C001", "C002"):
                sc = AccessScope(
                    tenant_id,
                    frozenset({cid}),
                    actor_id,
                    frozenset({"data.import", "evidence.verify", "model.fit"}),
                )
                snap_data, req_plan = native_batches(cid, tenant_id)
                req_plan["snapshot_id"] = commit(h.store, snap_data, sc)
                committed_requests[cid] = req_plan

            portal_base = f"http://127.0.0.1:{h.portal.server_port}"
            scenarios: dict[str, dict] = {}
            company_reports: dict[str, dict] = {}

            with sync_playwright() as p:
                b = browser(p)
                context = b.new_context()
                context.add_init_script(f"sessionStorage.setItem('kt-session', {json.dumps(h.token)});")
                page = context.new_page()

                # Open /agent2/batch-training#company=C001 with Portal session seeded
                page.goto(f"{portal_base}/agent2/batch-training#company=C001", wait_until="networkidle")
                page.wait_for_function(
                    "() => !document.getElementById('bt-workflow').hidden && document.getElementById('bt-company').value === 'C001'",
                    timeout=15000,
                )

                # --- C001 STEP 1: Preview & Pin Plan ---
                req_c001 = committed_requests["C001"]
                page.fill("#bt-train-start", req_c001["training_start"])
                page.fill("#bt-train-end", req_c001["training_end"])
                page.fill("#bt-eval-start", req_c001["evaluation_start"])
                page.fill("#bt-eval-end", req_c001["evaluation_end"])
                page.fill("#bt-as-of", req_c001["as_of"])
                page.click("#bt-step1-btn")
                page.wait_for_function(
                    "() => document.getElementById('bt-notice')?.textContent.includes('Đã kiểm tra và ghim kế hoạch dữ liệu')",
                    timeout=15000,
                )
                c001_step1_state = json.loads(page.locator("#bt-step1-tech").text_content())

                # --- C001 STEP 2: Create Label Packets & Lock Labels in Browser ---
                page.click("#bt-step2-btn")
                page.wait_for_function(
                    "() => document.querySelectorAll('#bt-label-packets-table tbody tr').length === 3",
                    timeout=15000,
                )
                c001_step2_pre = json.loads(page.locator("#bt-step2-tech").text_content())
                c001_packets = c001_step2_pre["training_packets"] + c001_step2_pre["evaluation_packets"]
                c001_outcomes = {
                    ("training", 0): "verified_fraud",
                    ("training", 1): "verified_non_fraud",
                    ("evaluation", 0): "verified_fraud",
                }
                c001_locked_ui = _verify_and_lock_packets_in_browser(page, portal_base, "C001", c001_packets, c001_outcomes)

                # Return to /agent2/batch-training#company=C001
                page.goto(f"{portal_base}/agent2/batch-training#company=C001", wait_until="networkidle")
                page.wait_for_function(
                    "() => !document.getElementById('bt-step3-btn').disabled",
                    timeout=15000,
                )
                page.select_option("#bt-epochs", "2")
                page.locator("#bt-epochs").dispatch_event("change")

                # --- SCENARIO 4: Mất phản hồi xác nhận (Server receives confirm, browser response dropped, then retry) ---
                dropped_confirm_captured: dict[str, object] = {}

                def intercept_confirm_once(route):
                    if not dropped_confirm_captured.get("intercepted"):
                        dropped_confirm_captured["intercepted"] = True
                        resp = route.fetch(timeout=300000)
                        dropped_confirm_captured["server_status"] = resp.status
                        dropped_confirm_captured["server_body"] = resp.json()
                        route.abort("failed")
                    else:
                        route.continue_()

                print("[C001] Step 3 / Scenario 4: Sending confirm (dropping browser response once)...", flush=True)
                page.route("**/api/v1/companies/C001/batch-training/confirm", intercept_confirm_once)
                page.click("#bt-step3-btn")
                page.wait_for_function(
                    "() => Boolean(document.getElementById('bt-notice')?.textContent)",
                    timeout=300000,
                )
                first_error_notice = page.locator("#bt-notice").inner_text()
                page.unroute("**/api/v1/companies/C001/batch-training/confirm", intercept_confirm_once)

                # Retry clicking confirm in browser after lost response
                print("[C001] Scenario 4: Retrying confirm in browser after dropped response...", flush=True)
                page.click("#bt-step3-btn")
                page.wait_for_function(
                    "() => document.getElementById('bt-progress-status')?.textContent.includes('btr_')",
                    timeout=120000,
                )
                c001_after_retry_tech = json.loads(page.locator("#bt-step4-tech").text_content())
                server_first_sess = dropped_confirm_captured["server_body"]["session"]
                c001_sessions_dir = runtime / "enterprise" / "_sessions" / f"{tenant_id}_C001"
                c001_session_dirs = sorted(p.name for p in c001_sessions_dir.iterdir() if p.is_dir())
                assert c001_after_retry_tech["job_id"] == server_first_sess["job_id"]
                assert c001_after_retry_tech["dataset_id"] == server_first_sess["dataset_id"]
                assert c001_after_retry_tech["worker_job"]["total_updates"] == 4
                assert len(c001_session_dirs) == 1
                scenarios["4_lost_confirm_response"] = dict(
                    passed=True,
                    company_id="C001",
                    first_server_status=dropped_confirm_captured["server_status"],
                    first_browser_error_notice=first_error_notice,
                    first_job_id=server_first_sess["job_id"],
                    retry_job_id=c001_after_retry_tech["job_id"],
                    first_dataset_id=server_first_sess["dataset_id"],
                    retry_dataset_id=c001_after_retry_tech["dataset_id"],
                    enterprise_session_count=len(c001_session_dirs),
                )

                # --- SCENARIO 2: Reload khi đang train (F5 during active real Concrete FHE training) ---
                before_reload_status = page.locator("#bt-progress-status").inner_text()
                before_reload_tech = json.loads(page.locator("#bt-step4-tech").text_content())
                page.reload(wait_until="networkidle")
                page.wait_for_function(
                    "expected => document.getElementById('bt-company')?.value === 'C001' && document.getElementById('bt-progress-status')?.textContent.includes(expected)",
                    arg=server_first_sess["job_id"],
                    timeout=15000,
                )
                after_reload_status = page.locator("#bt-progress-status").inner_text()
                after_reload_tech = json.loads(page.locator("#bt-step4-tech").text_content())
                assert after_reload_tech["job_id"] == before_reload_tech["job_id"]
                assert after_reload_tech["phase"] == "training"
                scenarios["2_reload_during_training"] = dict(
                    passed=True,
                    company_id="C001",
                    job_id=after_reload_tech["job_id"],
                    before_reload_status=before_reload_status,
                    after_reload_status=after_reload_status,
                    before_reload_completed_updates=before_reload_tech["worker_job"]["completed_updates"],
                    after_reload_completed_updates=after_reload_tech["worker_job"]["completed_updates"],
                )

                # --- SCENARIO 3: Mất kết nối trình duyệt (Browser offline then reconnect while worker continues) ---
                offline_before_tech = json.loads(page.locator("#bt-step4-tech").text_content())
                context.set_offline(True)
                time.sleep(0.8)
                context.set_offline(False)
                page.wait_for_function(
                    "expected => document.getElementById('bt-progress-status')?.textContent.includes(expected)",
                    arg=server_first_sess["job_id"],
                    timeout=15000,
                )
                offline_after_tech = json.loads(page.locator("#bt-step4-tech").text_content())
                assert offline_after_tech["job_id"] == offline_before_tech["job_id"]
                scenarios["3_browser_disconnect_reconnect"] = dict(
                    passed=True,
                    company_id="C001",
                    job_id=offline_after_tech["job_id"],
                    before_disconnect_completed_updates=offline_before_tech["worker_job"]["completed_updates"],
                    after_reconnect_completed_updates=offline_after_tech["worker_job"]["completed_updates"],
                    enterprise_session_count=len([p for p in c001_sessions_dir.iterdir() if p.is_dir()]),
                )

                # --- SCENARIO 5: Worker chết giữa chừng (Hard kill SIGKILL after checkpoint 1/4, restart worker, resume in UI) ---
                print("[C001] Scenario 5: Waiting for worker checkpoint (completed_updates>=1, inflight_update!=None)...", flush=True)
                sc_c001 = AccessScope(
                    tenant_id,
                    frozenset({"C001"}),
                    actor_id,
                    frozenset({"data.import", "evidence.verify", "model.fit"}),
                )
                c001_session_dir = c001_sessions_dir / c001_session_dirs[0]
                node_c001 = BatchEnterprise(c001_session_dir, build_dir, sc_c001)
                deadline = time.monotonic() + 300.0
                crash_checkpoint = None
                last_seen = None
                while time.monotonic() < deadline:
                    try:
                        live_wj, _ = node_c001.access_batches(worker_url, worker_pub, "status")
                        cur_tuple = (live_wj.get("completed_updates"), live_wj.get("inflight_update"), live_wj.get("status"))
                        if cur_tuple != last_seen:
                            print(f"[C001] Worker status: completed={cur_tuple[0]}, inflight={cur_tuple[1]}, status={cur_tuple[2]}", flush=True)
                            last_seen = cur_tuple
                        if live_wj.get("completed_updates", 0) >= 1 and live_wj.get("inflight_update") is not None:
                            crash_checkpoint = dict(
                                completed_updates=int(live_wj["completed_updates"]),
                                inflight_update=int(live_wj["inflight_update"]),
                                status=str(live_wj["status"]),
                            )
                            break
                        if live_wj.get("status") == "completed":
                            raise RuntimeError(f"Worker completed all updates before checkpoint kill: {live_wj}")
                    except RuntimeError:
                        raise
                    except Exception as exc:
                        print(f"[C001] Poll warning: {exc}", flush=True)
                    time.sleep(0.25)
                if crash_checkpoint is None:
                    raise RuntimeError("Worker did not reach checkpoint (completed_updates=1, inflight_update=1) within 300s")

                print(f"[C001] Scenario 5: Injecting SIGKILL at checkpoint {crash_checkpoint}...", flush=True)
                hard_kill(worker_proc, worker_ready, config_path)
                worker_proc = None

                # Wait for UI poll to detect interrupted state
                page.wait_for_function(
                    "() => document.getElementById('bt-progress-status')?.textContent.includes('Bị gián đoạn')",
                    timeout=30000,
                )
                interrupted_status_text = page.locator("#bt-progress-status").inner_text()
                interrupted_tech = json.loads(page.locator("#bt-step4-tech").text_content())

                # Restart real Concrete FHE worker on the same cloud directory and update manager
                print("[C001] Scenario 5: Restarting real Concrete FHE worker and resuming from UI...", flush=True)
                worker_proc, worker_ready, worker_url_2, worker_pub_2 = start_worker(cloud_dir, config_path, 2)
                mgr.set_worker(worker_url_2, worker_pub_2)

                # Click Step 4 button in browser to resume from checkpoint 1/4
                page.wait_for_function("() => !document.getElementById('bt-step4-btn').disabled", timeout=15000)
                page.click("#bt-step4-btn")
                page.wait_for_function(
                    "() => document.getElementById('bt-progress-counts')?.textContent.includes('4/4 bước cập nhật') && !document.getElementById('bt-step5-btn').disabled",
                    timeout=300000,
                )
                resumed_completed_tech = json.loads(page.locator("#bt-step4-tech").text_content())
                assert resumed_completed_tech["job_id"] == server_first_sess["job_id"]
                assert resumed_completed_tech["worker_job"]["completed_updates"] == 4
                assert resumed_completed_tech["worker_job"]["total_updates"] == 4
                scenarios["5_worker_crash_and_resume"] = dict(
                    passed=True,
                    company_id="C001",
                    job_id=resumed_completed_tech["job_id"],
                    checkpoint_before_kill=crash_checkpoint,
                    ui_interrupted_status=interrupted_status_text,
                    after_resume_completed_updates=resumed_completed_tech["worker_job"]["completed_updates"],
                    after_resume_total_updates=resumed_completed_tech["worker_job"]["total_updates"],
                    key_epoch=resumed_completed_tech["worker_job"]["key_epoch"],
                    build_sha256=resumed_completed_tech["worker_job"]["build_sha256"],
                    consent_sha256=resumed_completed_tech["consent_sha256"],
                )

                # --- C001 STEP 5: Receive & Validate Candidate Model ---
                print("[C001] Step 5/6/7: Receiving model, evaluating holdout, testing unapproved shadow block, approving and running shadow...", flush=True)
                page.click("#bt-step5-btn")
                page.wait_for_function(
                    "() => document.getElementById('bt-candidate-status')?.textContent.includes('Model ứng viên đã nhận và kiểm tra kỹ thuật')",
                    timeout=120000,
                )
                c001_cand = json.loads(page.locator("#bt-step5-tech").text_content())
                assert c001_cand["validation"] == "quantized_batch_oracle_exact"
                assert c001_cand["weights_code"] == [1, 1, -1]

                # --- C001 STEP 6: Evaluate on Locked Holdout ---
                page.click("#bt-step6-btn")
                page.wait_for_function(
                    "() => document.querySelectorAll('#bt-eval-table tbody tr').length === 4",
                    timeout=30000,
                )
                c001_eval = json.loads(page.locator("#bt-step6-tech").text_content())["evaluation"]
                assert c001_eval["held_out_from_training"] is True
                assert c001_eval["uncalibrated"] is True
                assert c001_eval["accuracy"] is None

                # --- SCENARIO 7: Shadow chưa được duyệt (Blocked before approval) ---
                step7_btn_label_before_approve = page.locator("#bt-step7-btn").inner_text()
                unapproved_shadow_attempt = page.evaluate(
                    """async () => {
                        const tok = sessionStorage.getItem('kt-session');
                        const stRes = await fetch('/agent2/api/v1/companies/C001/batch-training', {
                            headers: { 'X-Session': tok, 'X-Platform': '1' }
                        });
                        const st = await stRes.json();
                        const res = await fetch('/agent2/api/v1/companies/C001/batch-training/shadow', {
                            method: 'POST',
                            headers: {
                                'X-Session': tok,
                                'X-Platform': '1',
                                'Content-Type': 'application/json',
                                'Idempotency-Key': 'unapproved-shadow-' + Date.now()
                            },
                            body: JSON.stringify({ expected_revision: st.revision })
                        });
                        const body = await res.json();
                        const errObj = (body.errors && body.errors[0]) || body.error || {};
                        return { status: res.status, code: errObj.code, message: errObj.message };
                    }"""
                )
                assert unapproved_shadow_attempt["status"] == 409
                assert unapproved_shadow_attempt["code"] == "BATCH_MODEL_NOT_APPROVED"
                scenarios["7_shadow_blocked_before_approval"] = dict(
                    passed=True,
                    company_id="C001",
                    ui_button_label_before_approval=step7_btn_label_before_approve,
                    direct_shadow_http_status=unapproved_shadow_attempt["status"],
                    direct_shadow_error_code=unapproved_shadow_attempt["code"],
                    direct_shadow_error_message=unapproved_shadow_attempt["message"],
                )

                # --- SCENARIO 8: Shadow sau phê duyệt (Approve with pinned hashes, then run shadow) ---
                page.fill(
                    "#bt-approve-reason",
                    "Phê duyệt model ứng viên C001 chạy chế độ đối chiếu shadow sau khi kiểm tra oracle exact và tập holdout.",
                )
                page.click("#bt-step7-btn")
                page.wait_for_function(
                    "() => document.getElementById('bt-notice')?.textContent.includes('Đã phê duyệt model ứng viên cho chế độ đối chiếu shadow')",
                    timeout=15000,
                )
                page.click("#bt-step7-btn")
                page.wait_for_function(
                    "() => document.getElementById('bt-notice')?.textContent.includes('Đã chạy đối chiếu shadow trên tập giữ riêng')",
                    timeout=15000,
                )
                c001_step7_tech = json.loads(page.locator("#bt-step7-tech").text_content())
                assert c001_step7_tech["approval"]["approved_for_shadow"] is True
                assert c001_step7_tech["approval"]["operational_activation"] is False
                assert c001_step7_tech["shadow"]["shadow_only"] is True
                assert c001_step7_tech["shadow"]["active_model_replaced"] is False
                assert c001_step7_tech["shadow"]["operational_queue_changed"] is False
                scenarios["8_shadow_after_approval"] = dict(
                    passed=True,
                    company_id="C001",
                    approval_sha256=c001_step7_tech["approval"]["approval_sha256"],
                    pinned_model_cipher_sha256=c001_step7_tech["approval"]["model_cipher_sha256"],
                    pinned_plan_sha256=c001_step7_tech["approval"]["plan_sha256"],
                    pinned_evaluation_sha256=c001_step7_tech["approval"]["evaluation_sha256"],
                    shadow_only=c001_step7_tech["shadow"]["shadow_only"],
                    active_model_replaced=c001_step7_tech["shadow"]["active_model_replaced"],
                    operational_queue_changed=c001_step7_tech["shadow"]["operational_queue_changed"],
                )

                # --- SCENARIO 6 (Part A): Switch from C001 to C002 & reload before C002 has any session ---
                page.select_option("#bt-company", "C002")
                page.wait_for_function(
                    "() => document.getElementById('bt-company').value === 'C002' && document.getElementById('bt-overall-status')?.textContent.includes('Chưa có phiên huấn luyện batch nào')",
                    timeout=15000,
                )
                c002_empty_status = page.locator("#bt-overall-status").inner_text()
                page.reload(wait_until="networkidle")
                page.wait_for_function(
                    "() => document.getElementById('bt-company').value === 'C002' && document.getElementById('bt-overall-status')?.textContent.includes('Chưa có phiên huấn luyện batch nào')",
                    timeout=15000,
                )

                # --- SCENARIO 1: Full Normal Flow on C002 (all 7 steps end-to-end with real Concrete FHE worker) ---
                req_c002 = committed_requests["C002"]
                page.fill("#bt-train-start", req_c002["training_start"])
                page.fill("#bt-train-end", req_c002["training_end"])
                page.fill("#bt-eval-start", req_c002["evaluation_start"])
                page.fill("#bt-eval-end", req_c002["evaluation_end"])
                page.fill("#bt-as-of", req_c002["as_of"])
                page.click("#bt-step1-btn")
                page.wait_for_function(
                    "() => document.getElementById('bt-notice')?.textContent.includes('Đã kiểm tra và ghim kế hoạch dữ liệu')",
                    timeout=15000,
                )
                c002_step1_state = json.loads(page.locator("#bt-step1-tech").text_content())

                page.click("#bt-step2-btn")
                page.wait_for_function(
                    "() => document.querySelectorAll('#bt-label-packets-table tbody tr').length === 3",
                    timeout=15000,
                )
                c002_step2_pre = json.loads(page.locator("#bt-step2-tech").text_content())
                c002_packets = c002_step2_pre["training_packets"] + c002_step2_pre["evaluation_packets"]
                c002_outcomes = {
                    ("training", 0): "verified_non_fraud",
                    ("training", 1): "verified_fraud",
                    ("evaluation", 0): "verified_non_fraud",
                }
                c002_locked_ui = _verify_and_lock_packets_in_browser(page, portal_base, "C002", c002_packets, c002_outcomes)

                page.goto(f"{portal_base}/agent2/batch-training#company=C002", wait_until="networkidle")
                page.wait_for_function(
                    "() => !document.getElementById('bt-step3-btn').disabled",
                    timeout=15000,
                )
                print("[C002] Step 3/4: Confirming and running all 4 updates on real Concrete FHE worker...", flush=True)
                page.select_option("#bt-epochs", "2")
                page.locator("#bt-epochs").dispatch_event("change")
                page.click("#bt-step3-btn")
                page.wait_for_function(
                    "() => document.getElementById('bt-progress-counts')?.textContent.includes('4/4 bước cập nhật') && !document.getElementById('bt-step5-btn').disabled",
                    timeout=300000,
                )
                c002_step4_tech = json.loads(page.locator("#bt-step4-tech").text_content())

                print("[C002] Step 5/6/7: Receiving model, evaluating holdout, approving and running shadow...", flush=True)
                page.click("#bt-step5-btn")
                page.wait_for_function(
                    "() => document.getElementById('bt-candidate-status')?.textContent.includes('Model ứng viên đã nhận và kiểm tra kỹ thuật')",
                    timeout=120000,
                )
                c002_cand = json.loads(page.locator("#bt-step5-tech").text_content())
                assert c002_cand["validation"] == "quantized_batch_oracle_exact"
                assert c002_cand["weights_code"] == [-1, -1, 1]

                page.click("#bt-step6-btn")
                page.wait_for_function(
                    "() => document.querySelectorAll('#bt-eval-table tbody tr').length === 4",
                    timeout=30000,
                )
                c002_eval = json.loads(page.locator("#bt-step6-tech").text_content())["evaluation"]
                assert c002_eval["held_out_from_training"] is True
                assert c002_eval["uncalibrated"] is True
                assert c002_eval["accuracy"] is None

                page.fill(
                    "#bt-approve-reason",
                    "Phê duyệt model ứng viên C002 chạy chế độ đối chiếu shadow sau khi kiểm tra oracle exact và tập holdout.",
                )
                page.click("#bt-step7-btn")
                page.wait_for_function(
                    "() => document.getElementById('bt-notice')?.textContent.includes('Đã phê duyệt model ứng viên cho chế độ đối chiếu shadow')",
                    timeout=15000,
                )
                page.click("#bt-step7-btn")
                page.wait_for_function(
                    "() => document.getElementById('bt-notice')?.textContent.includes('Đã chạy đối chiếu shadow trên tập giữ riêng')",
                    timeout=15000,
                )
                c002_step7_tech = json.loads(page.locator("#bt-step7-tech").text_content())

                scenarios["1_normal_full_flow"] = dict(
                    passed=True,
                    companies_verified=["C001", "C002"],
                    c001_weights_code=c001_cand["weights_code"],
                    c002_weights_code=c002_cand["weights_code"],
                    c001_validation=c001_cand["validation"],
                    c002_validation=c002_cand["validation"],
                )

                # --- SCENARIO 6 (Part B): Switch between C001 and C002 + Reload to verify strict isolation ---
                page.select_option("#bt-company", "C001")
                page.wait_for_function(
                    "expected => document.getElementById('bt-company').value === 'C001' && document.getElementById('bt-progress-status')?.textContent.includes(expected)",
                    arg=resumed_completed_tech["job_id"],
                    timeout=15000,
                )
                page.reload(wait_until="networkidle")
                page.wait_for_function(
                    "expected => document.getElementById('bt-company').value === 'C001' && document.getElementById('bt-progress-status')?.textContent.includes(expected)",
                    arg=resumed_completed_tech["job_id"],
                    timeout=15000,
                )
                c001_check_step4 = json.loads(page.locator("#bt-step4-tech").text_content())
                c001_check_cand = json.loads(page.locator("#bt-step5-tech").text_content())

                page.select_option("#bt-company", "C002")
                page.wait_for_function(
                    "expected => document.getElementById('bt-company').value === 'C002' && document.getElementById('bt-progress-status')?.textContent.includes(expected)",
                    arg=c002_step4_tech["job_id"],
                    timeout=15000,
                )
                page.reload(wait_until="networkidle")
                page.wait_for_function(
                    "expected => document.getElementById('bt-company').value === 'C002' && document.getElementById('bt-progress-status')?.textContent.includes(expected)",
                    arg=c002_step4_tech["job_id"],
                    timeout=15000,
                )
                c002_check_step4 = json.loads(page.locator("#bt-step4-tech").text_content())
                c002_check_cand = json.loads(page.locator("#bt-step5-tech").text_content())

                assert c001_check_step4["job_id"] == resumed_completed_tech["job_id"]
                assert c002_check_step4["job_id"] == c002_step4_tech["job_id"]
                assert c001_check_step4["job_id"] != c002_check_step4["job_id"]
                assert c001_check_cand["weights_code"] == [1, 1, -1]
                assert c002_check_cand["weights_code"] == [-1, -1, 1]

                scenarios["6_company_switch_isolation"] = dict(
                    passed=True,
                    c002_initial_status_before_run=c002_empty_status,
                    c001_job_id=c001_check_step4["job_id"],
                    c002_job_id=c002_check_step4["job_id"],
                    c001_weights_code=c001_check_cand["weights_code"],
                    c002_weights_code=c002_check_cand["weights_code"],
                    cross_company_leakage=False,
                )

                # Collect full sanitized per-company reports via API
                for cid, locked_ui in (("C001", c001_locked_ui), ("C002", c002_locked_ui)):
                    sc = AccessScope(
                        tenant_id,
                        frozenset({cid}),
                        actor_id,
                        frozenset({"data.import", "evidence.verify", "model.fit"}),
                    )
                    st = mgr.status(sc)["session"]
                    cand = st["candidate"]
                    ev = st["evaluation"]
                    app = st["approval"]
                    shd = st["shadow"]
                    company_reports[cid] = dict(
                        company_id=cid,
                        tenant_id=tenant_id,
                        snapshot_id=st["request"]["snapshot_id"],
                        training_window=dict(
                            start=st["request"]["training_start"],
                            end=st["request"]["training_end"],
                        ),
                        evaluation_window=dict(
                            start=st["request"]["evaluation_start"],
                            end=st["request"]["evaluation_end"],
                        ),
                        as_of=st["request"]["as_of"],
                        plan_sha256=st["plan_sha256"],
                        training_rows=st["plan_summary"]["training_rows"],
                        evaluation_rows=st["plan_summary"]["evaluation_rows"],
                        training_batches=st["plan_summary"]["training_batch_count"],
                        evaluation_batches=st["plan_summary"]["evaluation_batch_count"],
                        epochs=st["epochs"],
                        total_updates=st["worker_job"]["total_updates"],
                        completed_updates=st["worker_job"]["completed_updates"],
                        synthetic_label_notice="Nhãn dùng trong nghiệm thu là nhãn synthetic kỳ vọng (synthetic_expected) để kiểm chứng kỹ thuật, không phải kết luận gian lận nghiệp vụ thật.",
                        locked_training_packets=st["locks"],
                        locked_evaluation_packets=st["evaluation_locks"],
                        browser_locked_packets=locked_ui,
                        dataset_id=st["dataset_id"],
                        job_id=st["job_id"],
                        consent_sha256=st["consent_sha256"],
                        key_epoch=st["worker_job"]["key_epoch"],
                        build_sha256=st["worker_job"]["build_sha256"],
                        worker_job_summary=dict(
                            status=st["worker_job"]["status"],
                            completed_updates=st["worker_job"]["completed_updates"],
                            total_updates=st["worker_job"]["total_updates"],
                            completed_epochs=st["worker_job"]["completed_epochs"],
                            batch_count=st["worker_job"]["batch_count"],
                            batch_manifest_sha256=st["worker_job"]["batch_manifest_sha256"],
                            training_commitment=st["worker_job"]["training_commitment"],
                            evaluation_commitment=st["worker_job"]["evaluation_commitment"],
                        ),
                        candidate_model=dict(
                            status_label=cand["status_label"],
                            validation=cand["validation"],
                            model_cipher_sha256=cand["model_cipher_sha256"],
                            weights_code=cand["weights_code"],
                            coefficients=cand.get("coefficients"),
                            intercept=cand.get("intercept"),
                            oracle_exact_match=(cand["validation"] == "quantized_batch_oracle_exact"),
                            approved_for_shadow=cand["approved_for_shadow"],
                            operational_activation=cand["operational_activation"],
                        ),
                        holdout_evaluation=dict(
                            evaluation_sha256=st["evaluation_sha256"],
                            evaluation_rows=ev["evaluation_rows"],
                            held_out_from_training=ev["held_out_from_training"],
                            uncalibrated=ev["uncalibrated"],
                            accuracy=ev["accuracy"],
                            holdout_labels=ev.get("holdout_labels"),
                            rows=[
                                dict(
                                    record_id=r["record_id"],
                                    batch_index=r["batch_index"],
                                    score=r["score"],
                                    verified_outcome=r.get("verified_outcome"),
                                )
                                for r in ev["rows"]
                            ],
                        ),
                        shadow_approval=dict(
                            approval_sha256=app["approval_sha256"],
                            actor_id=app["actor_id"],
                            approved_at=app["at"],
                            reason=app["reason"],
                            model_cipher_sha256=app["model_cipher_sha256"],
                            plan_sha256=app["plan_sha256"],
                            evaluation_sha256=app["evaluation_sha256"],
                            approved_for_shadow=app["approved_for_shadow"],
                            shadow_only=app["shadow_only"],
                            operational_activation=app["operational_activation"],
                        ),
                        shadow_scoring=dict(
                            shadow_only=shd["shadow_only"],
                            active_model_replaced=shd["active_model_replaced"],
                            operational_queue_changed=shd["operational_queue_changed"],
                            model_cipher_sha256=shd["model_cipher_sha256"],
                            evaluation_rows=shd["evaluation_rows"],
                            rows=shd["rows"],
                        ),
                    )

                context.close()
                b.close()

            # Verify cloud storage contains zero secret keys, plaintext snapshots, or label DBs
            cloud_files = [p.relative_to(cloud_dir).as_posix() for p in cloud_dir.rglob("*") if p.is_file()]
            forbidden_cloud = [
                f for f in cloud_files
                if "context.sealed" in f
                or "dpapi" in f
                or "labels.sqlite3" in f
                or "snapshots" in f
            ]
            assert not forbidden_cloud, f"Forbidden files found on cloud: {forbidden_cloud}"

            report = dict(
                version="portal-he-batch-training-acceptance/1.0.0",
                verified_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                environment=dict(
                    mode="isolated_local_portal_enterprise_real_concrete_worker",
                    concrete_fhe_worker="real_linux_concrete_2.9.0_no_mock",
                    browser_engine="Playwright Chromium",
                    tenant_id=tenant_id,
                    build_sha256=build_sha256,
                    synthetic_label_disclosure="Nhãn dùng trong nghiệm thu là nhãn synthetic kỳ vọng (synthetic_expected), không phải kết luận gian lận nghiệp vụ thật.",
                    cloud_secret_key_absent=True,
                    cloud_file_count=len(cloud_files),
                ),
                scenarios=scenarios,
                companies=company_reports,
            )
            write_json(runtime / "acceptance_report.json", report)
            write_json(PUBLIC_JSON_REPORT, report)
            return report
    finally:
        if worker_proc is not None:
            stop_worker(worker_proc, worker_ready, config_path)


if __name__ == "__main__":
    result = run_acceptance()
    print(json.dumps(
        dict(
            version=result["version"],
            scenarios={k: v["passed"] for k, v in result["scenarios"].items()},
            c001_job_id=result["companies"]["C001"]["job_id"],
            c002_job_id=result["companies"]["C002"]["job_id"],
            c001_weights=result["companies"]["C001"]["candidate_model"]["weights_code"],
            c002_weights=result["companies"]["C002"]["candidate_model"]["weights_code"],
        ),
        ensure_ascii=False,
        indent=2,
    ))
