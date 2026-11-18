"""Synchronize and activate the live/demo Portal runtime configured in portal/config.local.json.

Performs a full SHA-256 verified backup before touching any runtime file, then:
1. Upgrades HE4 node.json to he4-enterprise/1.1.0 + worker.json with build-c3-v1 and provisions missing C3 keys.
2. Commits compatible 35-rule snapshots (including a fast 4-candidate top demo snapshot) and fits models matching
   current rule-snapshot-point-in-time/1.0.0 contract (8114e628...) while keeping all historical rows/models intact.
3. Registers locked validation study packages and activates Staging Bundles supporting both Local Shadow and
   Cloud Ciphertext-Only HE for C001 & C002 in pipeline-releases.sqlite3, plus one ready-to-view initial shadow run.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import socket
import sys
import tempfile

_REPO_ROOT = Path(__file__).resolve().parents[2]
_AGENT2_ROOT = _REPO_ROOT / "agent2"
for p in (
    str(_REPO_ROOT),
    str(_AGENT2_ROOT),
    str(_REPO_ROOT / "shared" / "finance_input" / "src"),
    str(_AGENT2_ROOT / "tests"),
    str(_AGENT2_ROOT / "tests_he"),
):
    if p not in sys.path:
        sys.path.insert(0, p)

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from experiments.he4.coordinator import Settings as HE4Settings
from experiments.he4.preflight import check as he4_preflight_check
from experiments.he4.web import FourWorkbench
from experiments.he4.windows_bridge import CryptoBridge, linux_path
from experiments.he_inference.enterprise_server import load_node
from experiments.he_inference.key_manager import PROVIDER
from experiments.he_inference.node_job_store import JobStore
from experiments.he_inference.protocol import HEUnavailable, read_json
from experiments.he_inference.readiness import configuration as he1_configuration
from experiments.he_training.snapshot_adapter import VERSION as HE_ADAPTER_VERSION
from sme_fraud.analysis_resources import AnalysisResources, VERSION as BINDINGS_VERSION
from sme_fraud.auth import FileAuthorizer
from sme_fraud.bundle_he import BundleHE
from sme_fraud.bundle_release_acceptance import (
    TZ,
    _build_split_snapshot,
    _eval_k1_specs_and_review_profile,
    _val_cal_specs,
    commit_snapshot,
    make_auth_policy_file,
)
from sme_fraud.case_queue_policy import default_fixture_policy as default_cq_policy
from sme_fraud.case_queue_store import CaseQueueStore
from sme_fraud.he_workbench import HEWorkbench
from sme_fraud.import_files import canonical, digest
from sme_fraud.label_packets import LabelStore, TARGET as LABEL_TARGET, source_packet
from sme_fraud.method_jobs import run_fit_job
from sme_fraud.method_store import MethodStore
from sme_fraud.pipeline_release import ReleaseService
from sme_fraud.pipeline_release_store import ReleaseStore
from sme_fraud.release_shadow_plan import make_package
from sme_fraud.remediation_store import RemediationStore
from sme_fraud.rule35_ml_eval_demo import COMPANY_METHODS, fit_config
from sme_fraud.rule_snapshot import CONTRACT as RULE_SNAPSHOT_CONTRACT, analyze as analyze_rule_snapshot
from sme_fraud.rule_snapshot_features import feature_contract
from sme_fraud.snapshots import SnapshotStore
from sme_fraud.validation_study import (
    DEFAULT_OPEN_QUALITY_GATES,
    build_reference_distribution,
    extract_split_rows,
)


def _port_open(port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.25)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _live_demo_4_specs(company: str) -> list[dict]:
    """Compact 4-candidate snapshot (2026-W45) runnable quickly in BOTH Local Shadow and Real Concrete FHE."""
    return [
        {"id": f"{company}_DEMO_01_P1A", "pattern": "p1_pair_a", "day_offset": 1, "hour_offset": 9, "inv": f"INV_{company}_LIVE_P1"},
        {"id": f"{company}_DEMO_02_P1B", "pattern": "p1_pair_b", "day_offset": 1, "hour_offset": 14, "inv": f"INV_{company}_LIVE_P1"},
        {"id": f"{company}_DEMO_03_B1", "pattern": "b1_bank", "day_offset": 2, "hour_offset": 10},
        {"id": f"{company}_DEMO_04_ML", "pattern": "ml_outlier_high", "day_offset": 3, "hour_offset": 11, "amount": 95_400_000, "imbalance": 12_500_000},
    ]


def sync_live_runtime(*, allow_running: bool = False) -> dict:
    portal_cfg_path = _REPO_ROOT / "portal" / "config.local.json"
    if not portal_cfg_path.is_file():
        raise RuntimeError(f"Missing {portal_cfg_path}")
    portal_cfg = json.loads(portal_cfg_path.read_text(encoding="utf-8"))
    a2_cfg = portal_cfg["agents"]["agent2"]

    ports_to_check = [
        int(portal_cfg.get("port", 8800)),
        int(a2_cfg.get("port", 8766)),
        int(a2_cfg.get("he_worker", {}).get("port", 8868)),
        int(a2_cfg.get("he4_worker", {}).get("port", 8869)),
    ]
    if not allow_running:
        busy = [p for p in ports_to_check if _port_open(p)]
        if busy:
            raise RuntimeError(f"Ports currently open {busy}; stop running platform before syncing runtime.")

    snap_db_path = Path(a2_cfg["snapshot_db"]).resolve()
    model_db_path = Path(a2_cfg["model_db"]).resolve()
    bindings_path = Path(a2_cfg["analysis_bindings"]).resolve()
    access_path = Path(a2_cfg["access_file"]).resolve()
    he_node_path = Path(a2_cfg["env"]["AGENT2_HE_NODE_CONFIG"]).resolve()
    he_bindings_path = Path(a2_cfg["env"]["AGENT2_HE_BINDINGS"]).resolve()
    he4_node_path = Path(a2_cfg["env"]["AGENT2_HE4_CONFIG"]).resolve()
    he4_worker_cfg_path = Path(a2_cfg["he4_worker"]["config"]).resolve()
    build_c3_path = (_REPO_ROOT / ".runtime" / "he4" / "build-c3-v1").resolve()
    if not (build_c3_path / "manifest.json").is_file():
        raise RuntimeError(f"Missing Concrete C3 circuit build at {build_c3_path}")

    he4_node_before = json.loads(he4_node_path.read_text(encoding="utf-8"))
    jobs_dir = Path(he4_node_before["state_dir"]).resolve()

    # 1. Full timestamped backup
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = _REPO_ROOT / ".runtime" / "backups" / f"portal-live-sync-{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    to_backup = [
        portal_cfg_path,
        snap_db_path,
        model_db_path,
        bindings_path,
        access_path,
        he_node_path,
        he_bindings_path,
        he4_node_path,
        he4_worker_cfg_path,
    ]
    if jobs_dir.is_dir():
        to_backup.extend(sorted(p for p in jobs_dir.iterdir() if p.is_file() and p.suffix in (".sqlite3", ".json")))

    backup_records = []
    for src in to_backup:
        if not src.is_file():
            continue
        rel_safe = src.relative_to(_REPO_ROOT) if src.is_relative_to(_REPO_ROOT) else Path(src.name)
        dst = backup_dir / rel_safe
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        backup_records.append({"path": str(src), "backup_path": str(dst), "sha256": _sha256(dst), "bytes": dst.stat().st_size})
    (backup_dir / "backup-manifest.json").write_text(
        json.dumps({"created_at": datetime.now(timezone.utc).isoformat(), "files": backup_records}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # 2. Upgrade HE4 node.json (1.0.0 -> 1.1.0 + c3 build) and worker.json (+ c3 build)
    he4_node_updated = dict(he4_node_before)
    he4_node_updated["version"] = "he4-enterprise/1.1.0"
    he4_node_updated["builds"] = dict(he4_node_before["builds"], c3=str(build_c3_path))
    he4_node_path.write_bytes(canonical(he4_node_updated))

    he4_worker_before = json.loads(he4_worker_cfg_path.read_text(encoding="utf-8"))
    he4_worker_updated = dict(he4_worker_before)
    he4_worker_updated["builds"] = dict(he4_worker_before["builds"], c3=linux_path(build_c3_path))
    he4_worker_cfg_path.write_bytes(canonical(he4_worker_updated))

    # Temporary operator FileAuthorizer (never modifies live portal-access.demo.json!)
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp_dir = Path(tmp_str)
        dir_tok = "op-sync-director-" + "9" * 28
        acc_tok = "op-sync-accountant-" + "8" * 28
        auth_file = make_auth_policy_file(tmp_dir / "operator-auth.json", dir_tok, acc_tok)
        op_auth = FileAuthorizer(auth_file)
        dir_header = f"Bearer {dir_tok}"

        # Provision missing HE4 keys (specifically c3 for C001 & C002) using real DPAPI CryptoBridge
        HE4Settings(he4_node_updated)
        bridge = CryptoBridge(
            he4_node_updated["enterprise_root"],
            he4_node_updated["state_key_file"],
            distro=he4_node_updated["linux_distro"],
            python=he4_node_updated["linux_python"],
        )
        provisioned_profiles: dict[str, list[str]] = {"C001": [], "C002": []}
        existing_profiles: dict[str, list[str]] = {"C001": [], "C002": []}
        for company in ("C001", "C002"):
            scope_dir = op_auth.authorize_director(dir_header, company)
            for prof, bpath in sorted(he4_node_updated["builds"].items()):
                try:
                    bridge.public_context(scope_dir, bpath)
                    existing_profiles[company].append(prof)
                except HEUnavailable as exc:
                    if exc.code != "he4_key_not_provisioned":
                        raise
                    print(f"[{company}] Provisioning Concrete key vault for profile '{prof}'...", flush=True)
                    bridge.provision(scope_dir, bpath)
                    provisioned_profiles[company].append(prof)

        # Verify both HE1 and HE4 offline preflights pass
        he1_configuration(str(he_node_path), str(he_bindings_path), int(a2_cfg["he_worker"]["port"]))
        he4_pre = he4_preflight_check(str(he_node_path), str(he4_node_path), keys_only=True)
        assert he4_pre["status"] == "ready", he4_pre

        # 3. Open SnapshotStore & MethodStore, commit compatible 35-rule snapshots + fit current-contract models
        snapshots = SnapshotStore(snap_db_path)
        models = MethodStore(model_db_path)

        # Open JobStore + derived ReleaseStore / LabelStore / CaseQueueStore / RemediationStore matching review_server.py
        he_node_cfg = read_json(str(he_node_path))
        base_he = HEWorkbench(load_node(he_node_cfg, op_auth), str(he_bindings_path))
        four_wb = FourWorkbench(base_he.node, str(he_bindings_path), he4_node_updated)
        try:
            jstore: JobStore = four_wb.node.jobs.store
            rel_key = HKDF(algorithm=hashes.SHA256(), length=32, salt=b"agent2-pipeline-release-v1", info=b"enterprise-release-storage").derive(jstore.mac_key)
            lbl_key = HKDF(algorithm=hashes.SHA256(), length=32, salt=b"agent2-labels-v1", info=b"enterprise-verified-labels").derive(jstore.mac_key)

            release_store = ReleaseStore(jstore.path.with_name("pipeline-releases.sqlite3"), rel_key)
            label_store = LabelStore(jstore.path.with_name("verified-labels.sqlite3"), lbl_key)
            queue_store = CaseQueueStore(jstore.path.with_name("case-queue.sqlite3"))
            remediation_store = RemediationStore(jstore.path.with_name("remediation.sqlite3"))

            new_bindings_rows = []
            per_company_prep: dict[str, dict] = {}
            fc_now = feature_contract()

            for company, ml_method in COMPANY_METHODS.items():
                scope_dir = op_auth.authorize_director(dir_header, company)

                # Fit split (Jul 2 - Aug 24)
                fit_as_of = datetime(2026, 8, 24, 23, 59, 59, tzinfo=TZ)
                fit_raw, _ = _build_split_snapshot(company, f"SYNCFIT_{stamp}", datetime(2026, 7, 2, 10, 0, tzinfo=TZ), fit_as_of, [])
                fit_man = commit_snapshot(snapshots, scope_dir, fit_raw, f"sync-fit-{company}-{stamp}")

                def _fcfg(m: str) -> dict:
                    return dict(
                        fit_config(fit_man["snapshot_id"], m),
                        minimum_history=10,
                        history_end="2026-08-15T23:59:59+07:00",
                        reference_start="2026-08-16T00:00:00+07:00",
                        reference_end=fit_as_of.isoformat(),
                        evaluation_start="2026-08-25T00:00:00+07:00",
                    )

                rz_job = run_fit_job(snapshots, models, op_auth, dir_header, company, _fcfg("robust_z"), f"sync-rz-{company}-{stamp}")
                ml_job = run_fit_job(snapshots, models, op_auth, dir_header, company, _fcfg(ml_method), f"sync-{ml_method}-{company}-{stamp}")
                assert rz_job["job"]["status"] == "succeeded" and ml_job["job"]["status"] == "succeeded"

                comp_bind = {
                    "tenant_id": "demo",
                    "company_id": company,
                    "statistics_artifact_id": rz_job["job"]["artifact_id"],
                    "ml_artifacts": {ml_method: ml_job["job"]["artifact_id"]},
                }
                new_bindings_rows.append(comp_bind)
                comp_bind_tmp = tmp_dir / f"bind-{company}.json"
                comp_bind_tmp.write_bytes(canonical({"version": BINDINGS_VERSION, "bindings": [comp_bind]}))
                c_res = AnalysisResources(model_db=models.path, bindings_file=comp_bind_tmp)

                # History reference tail (Aug 25 - Aug 31)
                hist_as_of = datetime(2026, 8, 31, 23, 59, 59, tzinfo=TZ)
                href_specs = [{"id": f"{company}_SHREF_{i:02d}", "pattern": "clean", "day_offset": i % 6, "amount": 1_080_000 + i * 27_000} for i in range(1, 11)]
                href_raw, _ = _build_split_snapshot(company, f"SYNCHREF_{stamp}", datetime(2026, 8, 25, 10, 0, tzinfo=TZ), hist_as_of, href_specs)
                href_man = commit_snapshot(snapshots, scope_dir, href_raw, f"sync-href-{company}-{stamp}")
                href_ana = analyze_rule_snapshot(snapshots, scope_dir, href_man["snapshot_id"], hist_as_of.isoformat(), technical=True, resources=c_res)
                href_rows, _ = extract_split_rows("history_train", scope_dir, href_man, href_ana, raw_data=href_raw)

                ref_ml = build_reference_distribution(
                    ml_method,
                    [r["branches"][ml_method]["raw_score"] for r in href_rows],
                    company_id=company,
                    tenant_id="demo",
                    snapshot_id=href_man["snapshot_id"],
                    as_of=hist_as_of.isoformat(),
                    score_scale=f"{ml_method}_raw",
                )
                ref_rules = build_reference_distribution(
                    "rules_35",
                    [r["branches"]["rules_35"]["raw_score"] for r in href_rows],
                    company_id=company,
                    tenant_id="demo",
                    snapshot_id=href_man["snapshot_id"],
                    as_of=hist_as_of.isoformat(),
                    score_scale="rule_points",
                )
                refs_map = {r["reference_id"]: r for r in (ref_ml, ref_rules)}

                model_pins = {
                    "robust_z": {"company_id": company, "artifact_id": rz_job["job"]["artifact_id"], "artifact_sha256": digest(canonical(rz_job["manifest"]))},
                    ml_method: {"company_id": company, "artifact_id": ml_job["job"]["artifact_id"], "artifact_sha256": digest(canonical(ml_job["manifest"]))},
                }

                # Validation split (Sep 1 - Sep 25) & Calibration split (Sep 26 - Oct 8) & Held-out K1 (Oct 12 - Oct 25)
                val_start, val_end = datetime(2026, 9, 1, 0, 0, 0, tzinfo=TZ), datetime(2026, 9, 25, 23, 59, 59, tzinfo=TZ)
                cal_start, cal_end = datetime(2026, 9, 26, 0, 0, 0, tzinfo=TZ), datetime(2026, 10, 8, 23, 59, 59, tzinfo=TZ)
                ev1_start, ev1_end = datetime(2026, 10, 12, 0, 0, 0, tzinfo=TZ), datetime(2026, 10, 25, 23, 59, 59, tzinfo=TZ)

                val_specs, val_lbls = _val_cal_specs(company, "SVAL")
                cal_specs, cal_lbls = _val_cal_specs(company, "SCAL")
                ev1_specs, _ = _eval_k1_specs_and_review_profile(company)

                val_raw, _ = _build_split_snapshot(company, f"SYNCVAL_{stamp}", val_start, val_end, val_specs)
                cal_raw, _ = _build_split_snapshot(company, f"SYNCCAL_{stamp}", cal_start, cal_end, cal_specs)
                ev1_raw, _ = _build_split_snapshot(company, f"SYNCK1_{stamp}", ev1_start, ev1_end, ev1_specs)

                val_man = commit_snapshot(snapshots, scope_dir, val_raw, f"sync-val-{company}-{stamp}")
                cal_man = commit_snapshot(snapshots, scope_dir, cal_raw, f"sync-cal-{company}-{stamp}")
                ev1_man = commit_snapshot(snapshots, scope_dir, ev1_raw, f"sync-k1-{company}-{stamp}")

                # Top 4-candidate interactive demo snapshot (Nov 2 - Nov 5, committed LAST so it sits at top of dropdown!)
                demo_start, demo_end = datetime(2026, 11, 2, 9, 0, tzinfo=TZ), datetime(2026, 11, 5, 23, 59, 59, tzinfo=TZ)
                demo_raw, _ = _build_split_snapshot(company, f"SYNCLIVEDEMO_{stamp}", demo_start, demo_end, _live_demo_4_specs(company))
                demo_man = commit_snapshot(snapshots, scope_dir, demo_raw, f"sync-livedemo-{company}-{stamp}")

                manifests = {
                    "history_train": href_man,
                    "detector_validation": val_man,
                    "calibration_policy_validation": cal_man,
                    "sealed_future_test": ev1_man,
                }
                splits_cfg = {
                    "history_train": {
                        "snapshot_id": href_man["snapshot_id"],
                        "as_of": hist_as_of.isoformat(),
                        "start_at": "2026-07-01T00:00:00+07:00",
                        "end_at": hist_as_of.isoformat(),
                        "allowed_uses": ["fit_detectors", "fit_preprocess", "fit_reference_distribution"],
                        "episode_grouping": {"group_keys": ["simultaneous_group_id"], "episode_metadata_complete": False, "limitation_note": "Synthetic fit"},
                    },
                    "detector_validation": {
                        "snapshot_id": val_man["snapshot_id"],
                        "as_of": val_end.isoformat(),
                        "start_at": val_start.isoformat(),
                        "end_at": val_end.isoformat(),
                        "allowed_uses": ["compare_detectors", "select_combination"],
                        "episode_grouping": {"group_keys": ["simultaneous_group_id"], "episode_metadata_complete": False, "limitation_note": "Synthetic val"},
                    },
                    "calibration_policy_validation": {
                        "snapshot_id": cal_man["snapshot_id"],
                        "as_of": cal_end.isoformat(),
                        "start_at": cal_start.isoformat(),
                        "end_at": cal_end.isoformat(),
                        "allowed_uses": ["fit_calibrator", "evaluate_calibration_oos", "policy_sensitivity"],
                        "episode_grouping": {"group_keys": ["simultaneous_group_id"], "episode_metadata_complete": False, "limitation_note": "Synthetic cal"},
                    },
                    "sealed_future_test": {
                        "snapshot_id": ev1_man["snapshot_id"],
                        "as_of": ev1_end.isoformat(),
                        "start_at": ev1_start.isoformat(),
                        "end_at": ev1_end.isoformat(),
                        "allowed_uses": ["final_sealed_evaluation"],
                        "episode_grouping": {"group_keys": ["simultaneous_group_id"], "episode_metadata_complete": False, "limitation_note": "Synthetic K1 held-out"},
                    },
                }
                snap_list = [
                    {
                        "split": sn,
                        "snapshot_id": m["snapshot_id"],
                        "contract_version": RULE_SNAPSHOT_CONTRACT,
                        "as_of": splits_cfg[sn]["as_of"],
                        "snapshot_sha256": m["checksum"],
                        "data_checksum": m["data_checksum"],
                    }
                    for sn, m in manifests.items()
                ]

                split_bundles = {
                    "history_train": {
                        "rows": href_rows,
                        "groups": {},
                        "keys": {(r["record_id"], int(r["revision"])) for r in href_rows},
                    }
                }
                prov_list = []

                for sname, raw_b, man, lbl_dict in (
                    ("detector_validation", val_raw, val_man, val_lbls),
                    ("calibration_policy_validation", cal_raw, cal_man, cal_lbls),
                    ("sealed_future_test", ev1_raw, ev1_man, {}),
                ):
                    ana = analyze_rule_snapshot(snapshots, scope_dir, man["snapshot_id"], splits_cfg[sname]["as_of"], technical=True, resources=c_res)
                    s_rows, s_groups = extract_split_rows(sname, scope_dir, man, ana, raw_data=raw_b, model_artifacts=model_pins)
                    if sname == "calibration_policy_validation":
                        sorted_keys = sorted(lbl_dict)
                        pkts = []
                        for idx_b, st in enumerate((0, 4, 8), 1):
                            chunk = sorted_keys[st : st + 4]
                            spkt = source_packet(
                                snapshots,
                                scope_dir,
                                {
                                    "version": HE_ADAPTER_VERSION,
                                    "snapshot_id": man["snapshot_id"],
                                    "as_of": splits_cfg[sname]["as_of"],
                                    "training_start": splits_cfg[sname]["start_at"],
                                    "training_end": splits_cfg[sname]["end_at"],
                                    "rows": [{"record_id": k[0], "revision": k[1]} for k in chunk],
                                },
                            )
                            cr = label_store.create(scope_dir, spkt)
                            rnum = cr["revision"]
                            ev_map = {(c["record_id"], int(c["revision"])): [c["evidence"][0]["evidence_id"]] for c in spkt["cases"]}
                            for k in chunk:
                                sv = label_store.change(
                                    scope_dir,
                                    cr["packet_id"],
                                    "save",
                                    {
                                        "expected_revision": rnum,
                                        "request_id": f"sync-lbl-{company}-{stamp}-{idx_b}-{k[0]}",
                                        "label": {
                                            "record_id": k[0],
                                            "revision": k[1],
                                            "outcome": lbl_dict[k]["outcome"],
                                            "explanation": "Calibration ground truth label",
                                            "evidence_ids": ev_map[k],
                                            "documents_checked": True,
                                        },
                                    },
                                )
                                rnum = sv["revision"]
                            lk = label_store.change(
                                scope_dir,
                                cr["packet_id"],
                                "lock",
                                {"expected_revision": rnum, "request_id": f"sync-lock-packet-{company}-{stamp}-{idx_b}"},
                            )
                            pkts.append(label_store.export(scope_dir, cr["packet_id"], lk["revision"], lk["lock_sha256"]))
                            prov_list.append(
                                {
                                    "split": sname,
                                    "source_type": "label_store_packet",
                                    "packet_id": cr["packet_id"],
                                    "revision": lk["revision"],
                                    "lock_sha256": lk["lock_sha256"],
                                    "company_id": company,
                                    "labels_blinded_before_lock": False,
                                }
                            )
                        verif_dict = {"packets": pkts}
                    elif sname == "detector_validation":
                        prov_list.append(
                            {
                                "split": sname,
                                "source_type": "verified_fixture",
                                "packet_id": None,
                                "revision": None,
                                "lock_sha256": None,
                                "company_id": company,
                                "labels_blinded_before_lock": True,
                            }
                        )
                        verif_dict = {
                            "company_id": company,
                            "records": {k: {"outcome": v["outcome"], "company_id": company} for k, v in lbl_dict.items()},
                        }
                    else:
                        prov_list.append(
                            {
                                "split": sname,
                                "source_type": "verified_fixture",
                                "packet_id": None,
                                "revision": None,
                                "lock_sha256": None,
                                "company_id": company,
                                "labels_blinded_before_lock": True,
                            }
                        )
                        verif_dict = {"company_id": company, "records": {}}
                    split_bundles[sname] = {
                        "rows": s_rows,
                        "groups": s_groups,
                        "verified_labels": verif_dict,
                        "reviews": {"company_id": company, "reviews": {}},
                    }

                plan = {
                    "version": "evaluation-plan/1.0.0",
                    "study_id": f"live-sync-bundle-study-{company.lower()}-{stamp.lower()}",
                    "scope": {"tenant_id": "demo", "company_id": company},
                    "snapshots": snap_list,
                    "splits": splits_cfg,
                    "versions": {
                        "rule_engine_version": "agent2-rules-35/1.0.0",
                        "feature_contract_version": "rule-snapshot-point-in-time/1.0.0",
                        "preprocess_version": "frozen-feature-preprocess/1.0.0",
                        "random_seed": 20261116,
                        "model_bindings": [
                            {
                                "method_id": "rules_35",
                                "kind": "rules",
                                "artifact_id": "rules_35_v1",
                                "artifact_sha256": digest(b"rules_35"),
                                "model_version": "1.0.0",
                                "company_id": company,
                                "training_split": "history_train",
                                "training_mechanism": "deterministic_rules",
                            },
                            {
                                "method_id": ml_method,
                                "kind": "unsupervised",
                                "artifact_id": ml_job["job"]["artifact_id"],
                                "artifact_sha256": digest(canonical(ml_job["manifest"])),
                                "model_version": "1.0.0",
                                "company_id": company,
                                "training_split": "history_train",
                                "training_mechanism": "local_enterprise_fit",
                            },
                        ],
                        "reference_bindings": [
                            {
                                "method_id": r["method_id"],
                                "reference_id": r["reference_id"],
                                "reference_version": r["reference_version"],
                                "reference_sha256": r["reference_sha256"],
                                "company_id": company,
                                "fitted_split": "history_train",
                                "score_scale": r["score_scale"],
                            }
                            for r in (ref_ml, ref_rules)
                        ],
                    },
                    "labels": {
                        "target_contract": LABEL_TARGET,
                        "positive_label": "verified_fraud",
                        "negative_label": "verified_non_fraud",
                        "excluded_outcomes": ["confirmed_risk", "legitimate", "inconclusive", None],
                        "review_feedback_coercion_allowed": False,
                        "full_split_ground_truth": False,
                        "source_provenance": prov_list,
                    },
                    "candidates": [
                        {"arm_id": "rules_only", "kind": "rules_only", "branches": ["rules_35"], "weights": None, "uses_percentile_reference": False, "reference_ids": [], "he_is_training_mechanism_only": True, "complexity": 1},
                        {"arm_id": f"rules_plus_{ml_method}", "kind": "rules_plus_ml", "branches": ["rules_35", ml_method], "weights": None, "uses_percentile_reference": False, "reference_ids": [], "he_is_training_mechanism_only": True, "complexity": 2},
                    ],
                    "selection_policy": {
                        "locked_policy": {"policy_id": "rules_first_fill/1.0.0", "budget": 5, "tie_break": ["complexity_asc", "arm_id_asc"]},
                        "selection_objective": {"primary_metric": "verified_fraud_cases_selected", "secondary_metric": "resolved_fraud_precision", "min_incremental_gain": 0.0, "require_positive_marginal_value": True, "prefer_simpler_on_tie": True},
                        "policy_variants": [{"variant_id": "priority_top5_all_branches", "policy_kind": "priority_top_k", "budget": 5, "min_priority_threshold": None}],
                    },
                    "calibration_spec": {
                        "target_branch": ml_method,
                        "allowed_methods": ["platt_logistic", "isotonic_regression"],
                        "fit_split": "calibration_policy_validation",
                        "internal_eval_folds": 3,
                        "min_total_labels": 8,
                        "min_positive_labels": 3,
                        "min_negative_labels": 3,
                        "ece_bins": 4,
                        "block_on_insufficient_labels": True,
                    },
                    "fallback_specs": [
                        {"fallback_config_id": "fb_missing_unsup_rules_only_v1", "config_version": "1.0.0", "trigger_condition": "missing_unsupervised_model", "used_branches": ["rules_35"], "missing_or_ineligible_branches": [ml_method], "is_full_ensemble": False, "weight_policy": "explicit_fallback_subset", "weights": None},
                        {"fallback_config_id": "fb_incompatible_contract_v1", "config_version": "1.0.0", "trigger_condition": "incompatible_contract", "used_branches": [], "missing_or_ineligible_branches": ["rules_35", ml_method], "is_full_ensemble": False, "weight_policy": "unavailable", "weights": None},
                    ],
                    "metrics_and_criteria": {
                        "primary_metrics": ["confirmed_cases_found", "precision_resolved", "review_minutes", "availability_rate", "fallback_rate"],
                        "technical_gates": [
                            {"gate_id": "TG-COMPAT-01", "description": "Snapshot, feature contract, preprocess and pinned model checksums match", "required": True},
                            {"gate_id": "TG-NO-LEAK-01", "description": "No history_train or test leakage into split evaluation", "required": True},
                        ],
                        "quality_gates": deepcopy(list(DEFAULT_OPEN_QUALITY_GATES)),
                    },
                    "governance": {
                        "promotion_target": "candidate_shadow_only",
                        "production_approved": False,
                        "active_model_replaced": False,
                        "operational_queue_changed": False,
                        "execution_location": "enterprise_local_only",
                        "cloud_plaintext_sent": False,
                        "synthetic_data_disclosure": "Live demo staging validation package; synthetic snapshots only.",
                    },
                }

                pkg = make_package(
                    scope_dir,
                    model_selection={"version": BINDINGS_VERSION, **comp_bind},
                    contract=fc_now,
                    plan=plan,
                    snapshot_manifests=manifests,
                    model_artifacts=model_pins,
                    references=refs_map,
                    split_bundles=split_bundles,
                    case_policy=default_cq_policy(budget_limit=3, min_case_score=1.0, rule_weight=1, ml_weight=1),
                    ml_candidate_min_score=0.55,
                    fallback_order=["fb_missing_unsup_rules_only_v1", "fb_incompatible_contract_v1"],
                    label_packets=None,
                )
                per_company_prep[company] = {
                    "package": pkg,
                    "k1_man": ev1_man,
                    "k1_as_of": ev1_end.isoformat(),
                    "demo_man": demo_man,
                    "demo_as_of": demo_end.isoformat(),
                    "binding": comp_bind,
                }

            # 4. Write updated local-analysis-bindings.json (and dated copy)
            bindings_doc = {"version": BINDINGS_VERSION, "bindings": new_bindings_rows}
            bindings_path.parent.mkdir(parents=True, exist_ok=True)
            bindings_path.write_bytes(canonical(bindings_doc))
            dated_bindings_dir = snap_db_path.parent.parent / "activation_20261118"
            dated_bindings_dir.mkdir(parents=True, exist_ok=True)
            (dated_bindings_dir / "local-analysis-bindings.json").write_bytes(canonical(bindings_doc))

            # 5. Initialize ReleaseService with live AnalysisResources + BundleHE, register plans & activate bundles
            live_resources = AnalysisResources(model_db=models.path, bindings_file=bindings_path)
            release_svc = ReleaseService(release_store, snapshots, live_resources, queue_store)
            release_svc.workspace.remediation = remediation_store
            release_svc.he_executor = BundleHE(four_wb)

            company_summary = {}
            for company, info in per_company_prep.items():
                scope_dir = op_auth.authorize_director(dir_header, company)
                cur_rev = release_store.current(scope_dir, "staging")["revision"]

                reg = release_svc.register_plan(scope_dir, info["package"], f"sync-plan-{company}-{stamp}")

                # Bundle 1: Local Shadow (gives history for diff / rollback)
                b_local = release_svc.prepare(
                    scope_dir,
                    info["demo_man"]["snapshot_id"],
                    f"Staging Local Shadow ({company})",
                    f"sync-prep-local-{company}-{stamp}",
                    plan_id=reg["plan_id"],
                    execution_mode="enterprise_local_only",
                )
                g_local = release_svc.qualify(scope_dir, b_local["bundle_id"], "staging", key=f"sync-qual-local-{company}-{stamp}")
                assert g_local["technical_ready"], g_local
                a_local = release_svc.approve(scope_dir, b_local["bundle_id"], g_local["gate_id"], "staging", f"Staging local bundle sync {stamp}", key=f"sync-appr-local-{company}-{stamp}")
                sw_local = release_svc.switch(
                    scope_dir,
                    {
                        "bundle_id": b_local["bundle_id"],
                        "gate_id": g_local["gate_id"],
                        "approval_id": a_local["approval_id"],
                        "lane": "staging",
                        "expected_revision": cur_rev,
                        "reason": f"Activate staging local bundle {stamp}",
                        "action": "activate",
                    },
                    f"sync-sw-local-{company}-{stamp}",
                )

                # Bundle 2: Local + Cloud HE Shadow (active pointer -> enables BOTH Local and HE modes!)
                b_he = release_svc.prepare(
                    scope_dir,
                    info["demo_man"]["snapshot_id"],
                    f"Staging Local + Cloud HE ({company})",
                    f"sync-prep-he-{company}-{stamp}",
                    plan_id=reg["plan_id"],
                    execution_mode="cloud_ciphertext_only",
                )
                g_he = release_svc.qualify(scope_dir, b_he["bundle_id"], "staging", key=f"sync-qual-he-{company}-{stamp}")
                assert g_he["technical_ready"], g_he
                a_he = release_svc.approve(scope_dir, b_he["bundle_id"], g_he["gate_id"], "staging", f"Staging local+HE bundle sync {stamp}", key=f"sync-appr-he-{company}-{stamp}")
                sw_he = release_svc.switch(
                    scope_dir,
                    {
                        "bundle_id": b_he["bundle_id"],
                        "gate_id": g_he["gate_id"],
                        "approval_id": a_he["approval_id"],
                        "lane": "staging",
                        "expected_revision": sw_local["revision"],
                        "reason": f"Activate staging local+HE bundle {stamp}",
                        "action": "activate",
                    },
                    f"sync-sw-he-{company}-{stamp}",
                )

                # Execute one ready-to-browse shadow run on K1 (2026-W43), leaving top K_LIVE_DEMO (2026-W45) fresh!
                init_run_id = f"{company.lower()}-staging-ready-{stamp.lower()}"
                obs = release_svc.run(
                    scope_dir,
                    init_run_id,
                    "staging",
                    info["k1_man"]["snapshot_id"],
                    info["k1_as_of"],
                    execution_mode="enterprise_local_only",
                    require_case_profile=True,
                )
                ws_list = release_svc.workspace.list_runs(scope_dir)
                assert ws_list["can_run"] is True and "cloud_ciphertext_only" in ws_list["execution_modes"], ws_list

                company_summary[company] = {
                    "statistics_artifact_id": info["binding"]["statistics_artifact_id"],
                    "ml_artifacts": info["binding"]["ml_artifacts"],
                    "plan_id": reg["plan_id"],
                    "local_bundle_id": b_local["bundle_id"],
                    "active_he_bundle_id": b_he["bundle_id"],
                    "staging_revision": sw_he["revision"],
                    "top_demo_snapshot_id": info["demo_man"]["snapshot_id"],
                    "k1_snapshot_id": info["k1_man"]["snapshot_id"],
                    "initial_ready_run_id": init_run_id,
                    "initial_admitted_cases": obs["result"]["pipeline"]["queue"]["counts"]["queued_or_reserved"],
                    "execution_modes": ws_list["execution_modes"],
                    "he_provisioned_now": provisioned_profiles[company],
                    "he_previously_provisioned": existing_profiles[company],
                }
        finally:
            four_wb.node.jobs.close()

    summary = {
        "status": "pass",
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "backup_dir": str(backup_dir),
        "feature_contract_fingerprint": fc_now["fingerprint"],
        "he4_config_version": he4_node_updated["version"],
        "he4_builds": sorted(he4_node_updated["builds"]),
        "portal_access_unchanged": True,
        "companies": company_summary,
    }
    report_out = _AGENT2_ROOT / "reports" / "portal_live_runtime_sync_20261118.json"
    report_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--allow-running", action="store_true")
    args = p.parse_args()
    res = sync_live_runtime(allow_running=args.allow_running)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
