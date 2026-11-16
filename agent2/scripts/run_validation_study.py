"""Run end-to-end multi-period validation, verified calibration, and fallback acceptance for C001 & C002."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import random
import secrets
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
for extra in (ROOT, ROOT / "tests", ROOT / "tests_he", Path(__file__).resolve().parent, REPO / "shared" / "finance_input" / "src", REPO):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from experiments.he_training.batch_enterprise import BatchEnterprise
from experiments.he_training.protocol import atomic, sha, strict_json, verify
from experiments.he_training.snapshot_adapter import VERSION as HE_ADAPTER_VERSION
from sme_fraud.analysis_resources import AnalysisResources, VERSION as BINDINGS_VERSION
from sme_fraud.auth import FileAuthorizer
from sme_fraud.batch_training_api import BatchTrainingManager, _summarize_plan
from sme_fraud.import_files import canonical, digest
from sme_fraud.label_packets import LabelStore, TARGET as LABEL_TARGET, source_packet
from sme_fraud.method_jobs import run_fit_job
from sme_fraud.method_store import MethodStore
from sme_fraud.review_store import ReviewStore
from sme_fraud.rule35_comparison import rule35_cases_for
from sme_fraud.rule35_ml_eval_demo import (
    _add_clean_payment,
    _add_payroll_tx,
    _finalize,
    _seed_baseline_tables,
    base,
    fit_config,
)
from sme_fraud.rule_snapshot import CONTRACT, analyze as analyze_rule_snapshot
from sme_fraud.snapshots import SnapshotStore
from sme_fraud.validation_study import (
    DEFAULT_OPEN_QUALITY_GATES,
    ValidationStudyError,
    apply_calibrator,
    build_reference_distribution,
    extract_split_rows,
    fit_and_evaluate_calibration,
    lock_evaluation_plan,
    parse_verified_labels,
    run_validation_study,
)

TZ = timezone(timedelta(hours=7))
SOURCE_HE_ACCEPTANCE_DIR = REPO / ".runtime" / "he-training-batches-20261115" / "portal-he-acceptance-v1"
DEFAULT_BUILD_DIR = REPO / ".runtime" / "he-training-20261115" / "build-v3"
DEFAULT_RUNTIME_DIR = REPO / ".runtime" / "validation-calibration-acceptance-v1"
DEFAULT_JSON_REPORT = ROOT / "reports" / "validation_study_acceptance.json"
DEFAULT_MD_REPORT = ROOT / "docs" / "VALIDATION_CALIBRATION_FALLBACK.md"
TENANT = "training-demo"


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic(path, json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))


def _write_policy(path: Path, token: str) -> None:
    exp = (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat()
    policy = {
        "policy_version": "1.0.0",
        "principals": [
            {
                "actor_id": "validation-director",
                "tenant_id": TENANT,
                "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
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
            }
        ],
    }
    path.write_bytes(canonical(policy))


def _commit(store: SnapshotStore, scope, data: dict, key: str) -> dict:
    draft = store.upload(scope, canonical(data), f"{key}.json", key + "-u")
    p = store.preview(scope, draft["import_id"], 1)
    if p["status"] == "rejected":
        raise AssertionError(p["errors"])
    req = {k: p[k] for k in ("preview_id", "source_hash", "mapping_hash", "report_hash", "context_hash")}
    req.update(expected_revision=p["revision"], acknowledge=True)
    return store.commit(scope, draft["import_id"], req, key + "-c")["snapshot"]


def _build_period_snapshot(
    company: str,
    prefix: str,
    start_dt: datetime,
    as_of_dt: datetime,
    specs: list[dict],
) -> dict:
    scale = 1 if company == "C001" else 3
    c = base()
    _seed_baseline_tables(c, company, scale, datetime(2026, 7, 1, 10, 0, tzinfo=TZ))

    rng = random.Random(100 if company == "C001" else 200)
    history_ids = []
    day = datetime(2026, 7, 2, 10, 0, tzinfo=TZ)
    idx = 0
    while idx < 32:
        if day.weekday() < 5:
            idx += 1
            tid = f"{company}_HIST_{idx:02d}"
            amt = (1_050_000 + rng.randint(0, 35) * 14_300) * scale
            _add_clean_payment(c, tid, day, amt, scale=scale, company_id=company, doc=True)
            history_ids.append(tid)
        day += timedelta(days=1)

    for p_i, p_day in enumerate((datetime(2026, 7, 25, 10, 0, tzinfo=TZ), datetime(2026, 8, 12, 10, 0, tzinfo=TZ)), 1):
        pid = f"{company}_HPAY_{p_i:02d}"
        _add_payroll_tx(c, pid, p_day, 14_200_000 * scale, company_id=company, scale=scale, terminated=False)
        history_ids.append(pid)

    ref_day = datetime(2026, 8, 17, 10, 0, tzinfo=TZ)
    for r_i in range(1, 13):
        while ref_day.weekday() >= 5:
            ref_day += timedelta(days=1)
        tid = f"{company}_HREF_{r_i:02d}"
        amt = (1_120_000 + rng.randint(0, 30) * 11_300) * scale
        _add_clean_payment(c, tid, ref_day, amt, scale=scale, company_id=company, doc=True)
        history_ids.append(tid)
        ref_day += timedelta(hours=12)

    cand_ids = []
    for i, sp in enumerate(specs):
        tid = sp["id"]
        cand_ids.append(tid)
        ev_at = start_dt + timedelta(days=sp.get("day_offset", i % 18), hours=sp.get("hour_offset", 10 + (i % 5)))
        kind = sp.get("pattern", "clean")
        if kind == "p1_a":
            _add_clean_payment(c, tid, ev_at, 15_000_000 * scale, scale=scale, company_id=company,
                               invoice_number=sp.get("inv", f"INV_{prefix}_P1"), invoice_gross_vnd=18_000_000 * scale)
        elif kind == "p1_b":
            _add_clean_payment(c, tid, ev_at, 14_000_000 * scale, scale=scale, company_id=company,
                               invoice_number=sp.get("inv", f"INV_{prefix}_P1"), invoice_gross_vnd=18_000_000 * scale)
        elif kind == "c2_self":
            _add_clean_payment(c, tid, ev_at, 16_000_000 * scale, scale=scale, company_id=company,
                               approver_id=c.maker["employee_id"])
        elif kind == "b1_bank":
            vb1 = deepcopy(c.vendor)
            vb1.update(
                vendor_id=f"{company}_{tid}_VB1", name="Worker Linked Vendor", representative_id=f"{tid}_REP",
                bank_account=c.worker["bank_account"], phone="0908111222", address="12 Le Loi, HCMC",
                national_id=f"{tid}_NAT", tax_code=f"{tid}_TAX",
            )
            c.tables["vendors"].append(vb1)
            _add_clean_payment(c, tid, ev_at, 4_200_000 * scale, vendor=vb1, scale=scale, company_id=company)
        elif kind == "ml_high":
            _add_clean_payment(
                c, tid, ev_at, sp.get("amount", 84_317_250) * scale, scale=scale, company_id=company,
                doc=False, imbalance=11_000_000 * scale,
                approver_id=c.maker["employee_id"] if sp.get("same_approver") else c.director["employee_id"],
            )
        elif kind == "sup_pattern":
            # exact round-million + creator_equals_approver under maker limit -> fires supervised HE model cleanly
            _add_clean_payment(
                c, tid, ev_at, sp.get("amount", 2_000_000), scale=scale, company_id=company,
                approver_id=c.maker["employee_id"], doc=True,
            )
        else:
            amt = sp.get("amount", (1_090_000 + i * 27_300) * scale)
            _add_clean_payment(
                c, tid, ev_at, amt, scale=scale, company_id=company,
                approver_id=c.maker["employee_id"] if sp.get("same_approver") else c.director["employee_id"],
            )
        if sp.get("episode_id"):
            c.rows[-1]["episode_id"] = sp["episode_id"]

    return _finalize(
        c,
        tenant_id=TENANT,
        company_id=company,
        as_of=as_of_dt.isoformat(),
        candidate_ids=cand_ids,
        source_id=f"synthetic-{company.lower()}-{prefix.lower()}",
    )


def _split_specs(company: str, split: str) -> tuple[list[dict], dict[tuple[str, int], dict]]:
    pref = f"{company}_{split[:3].upper()}"
    specs = [
        {"id": f"{pref}_01_P1A", "pattern": "p1_a", "day_offset": 1, "inv": f"INV_{pref}_P1"},
        {"id": f"{pref}_02_P1B", "pattern": "p1_b", "day_offset": 1, "inv": f"INV_{pref}_P1"},
        {"id": f"{pref}_03_C2", "pattern": "c2_self", "day_offset": 3},
        {"id": f"{pref}_04_ML_F1", "pattern": "ml_high", "day_offset": 5, "amount": 92_451_300, "same_approver": False},
        {"id": f"{pref}_05_ML_F2", "pattern": "ml_high", "day_offset": 6, "amount": 85_319_700, "same_approver": False},
        {"id": f"{pref}_06_BENIGN_OUT", "pattern": "ml_high", "day_offset": 7, "amount": 58_111_700, "same_approver": False},
        {"id": f"{pref}_07_SUP_F1", "pattern": "sup_pattern", "day_offset": 8, "amount": 2_000_000},
        {"id": f"{pref}_08_SUP_F2", "pattern": "sup_pattern", "day_offset": 9, "amount": 3_000_000},
        {"id": f"{pref}_09_SUP_FP", "pattern": "sup_pattern", "day_offset": 10, "amount": 1_000_000},
    ]
    if company == "C002":
        specs[2] = {"id": f"{pref}_03_B1", "pattern": "b1_bank", "day_offset": 3}

    for i in range(10, 16):
        specs.append({"id": f"{pref}_{i:02d}_NORM", "pattern": "clean", "day_offset": 11 + (i % 7)})
    if split == "sealed_future_test":
        specs.append({"id": "SHARED_AUDIT_00", "pattern": "clean", "day_offset": 18})

    labels = {
        (specs[0]["id"], 1): {"outcome": "verified_fraud"},
        (specs[1]["id"], 1): {"outcome": "verified_fraud"},
        (specs[2]["id"], 1): {"outcome": "verified_fraud"},
        (specs[3]["id"], 1): {"outcome": "verified_fraud"},
        (specs[4]["id"], 1): {"outcome": "verified_fraud"},
        (specs[5]["id"], 1): {"outcome": "verified_non_fraud"},
        (specs[6]["id"], 1): {"outcome": "verified_fraud"},
        (specs[7]["id"], 1): {"outcome": "verified_fraud"},
        (specs[8]["id"], 1): {"outcome": "verified_non_fraud"},
    }
    for j, sp in enumerate(specs[9:]):
        if split == "sealed_future_test" and j >= len(specs[9:]) - 2:
            labels[(sp["id"], 1)] = {"outcome": "inconclusive" if j % 2 == 0 else None}
        else:
            labels[(sp["id"], 1)] = {"outcome": "verified_non_fraud"}
    return specs, labels


def _seed_he_manager(runtime_dir: Path, source_he_dir: Path, build_dir: Path, snapshots: SnapshotStore, labels: LabelStore) -> BatchTrainingManager:
    if not source_he_dir.exists() or not build_dir.exists():
        raise RuntimeError(f"Missing real Concrete HE artifacts at {source_he_dir} or {build_dir}")
    shutil.copytree(
        source_he_dir / "enterprise",
        runtime_dir / "enterprise",
        ignore=shutil.ignore_patterns("context.sealed", "evaluation.keys"),
    )
    enterprise_root = runtime_dir / "enterprise"

    def make_node(session_dir: Path, scope, company: str, recheck):
        node = BatchEnterprise(session_dir, build_dir, scope, recheck=recheck)
        return node, "http://127.0.0.1:0", "0" * 64

    manager = BatchTrainingManager(
        runtime_dir / "batch-training.sqlite3",
        secrets.token_bytes(32),
        snapshot_store=snapshots,
        label_store=labels,
        enterprise_root=enterprise_root,
        build=build_dir,
        worker_url="http://127.0.0.1:0",
        worker_verify_key="0" * 64,
        node_factory=make_node,
    )

    from sme_fraud.auth import AccessScope
    for cid in ("C001", "C002"):
        sc = AccessScope(TENANT, frozenset({cid}), "validation-director", frozenset({"data.import", "evidence.verify", "model.fit"}))
        sess_parent = enterprise_root / "_sessions" / f"{TENANT}_{cid}"
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
        with manager._tx(sc, None, "model.fit") as conn:
            manager._append(
                conn, TENANT, cid,
                dict(
                    version="portal-batch-training/0.1.0",
                    tenant_id=TENANT, company_id=cid, revision=1, run_id=run_id, phase="shadow_approved",
                    request=prov["request"], plan_sha256=prov["plan_sha256"], plan_summary=_summarize_plan(prov),
                    packets=[], locks=[], evaluation_locks=[], epochs=2, dataset_id=source["dataset_id"],
                    job_id=candidate["job_id"], consent_sha256=candidate["consent_sha256"],
                    worker_job=dict(job_id=candidate["job_id"], status="completed", completed_updates=4, total_updates=4),
                    candidate=dict(candidate, candidate_sha256=sha(canonical(candidate)), approved_for_shadow=True),
                    evaluation=evaluation, evaluation_sha256=sha(canonical(evaluation)),
                    approval=approval_body, shadow=None, last_error=None,
                    created_at="2026-11-15T10:05:00Z", updated_at="2026-11-15T10:15:00Z",
                    updated_by="validation-director",
                ),
            )
    return manager


def run_acceptance(
    *,
    runtime_dir: Path = DEFAULT_RUNTIME_DIR,
    source_he_dir: Path = SOURCE_HE_ACCEPTANCE_DIR,
    build_dir: Path = DEFAULT_BUILD_DIR,
    json_report: Path = DEFAULT_JSON_REPORT,
    md_report: Path = DEFAULT_MD_REPORT,
) -> dict:
    if runtime_dir.exists():
        shutil.rmtree(runtime_dir)
    runtime_dir.mkdir(parents=True, exist_ok=True)

    token = secrets.token_urlsafe(24)
    header = "Bearer " + token
    policy_path = runtime_dir / "policy.json"
    _write_policy(policy_path, token)
    auth = FileAuthorizer(policy_path)
    snapshots = SnapshotStore(runtime_dir / "snapshots.sqlite3")
    models = MethodStore(runtime_dir / "models.sqlite3")
    labels_store = LabelStore(runtime_dir / "labels.sqlite3", secrets.token_bytes(32))
    reviews = ReviewStore(runtime_dir / "reviews.sqlite3", secrets.token_bytes(32))
    manager = _seed_he_manager(runtime_dir, source_he_dir, build_dir, snapshots, labels_store)

    reports_by_company = {}
    acceptance_checks = {}

    for company in ("C001", "C002"):
        scope = auth.authorize(header, company)
        recheck = lambda: auth.authorize(header, company)
        approved_model = manager.status(scope)["approved_models"][0]
        he_run_id = approved_model.get("model_run_id") or approved_model.get("run_id") or approved_model["job_id"]

        # 1a. History fit snapshot (Jul 1 - Aug 24)
        fit_as_of = datetime(2026, 8, 24, 23, 59, 59, tzinfo=TZ)
        fit_src = _build_period_snapshot(company, "FIT", datetime(2026, 7, 2, 10, 0, tzinfo=TZ), fit_as_of,
                                         [{"id": f"{company}_FIT_SEED", "pattern": "clean", "day_offset": 1}])
        fit_snap = _commit(snapshots, scope, fit_src, f"fit-{company}")

        def _fcfg(m: str) -> dict:
            return dict(
                fit_config(fit_snap["snapshot_id"], m),
                minimum_history=10,
                history_end="2026-08-15T23:59:59+07:00",
                reference_start="2026-08-16T00:00:00+07:00",
                reference_end=fit_as_of.isoformat(),
                evaluation_start="2026-08-25T00:00:00+07:00",
            )

        rz = run_fit_job(snapshots, models, auth, header, company, _fcfg("robust_z"), f"fit-rz-{company}")
        if_job = run_fit_job(snapshots, models, auth, header, company, _fcfg("isolation_forest"), f"fit-if-{company}")
        ecod_job = run_fit_job(snapshots, models, auth, header, company, _fcfg("ecod"), f"fit-ecod-{company}")

        bindings_file = runtime_dir / f"analysis-bindings-{company}.json"
        bindings_file.write_bytes(canonical({
            "version": BINDINGS_VERSION,
            "bindings": [{
                "tenant_id": TENANT,
                "company_id": company,
                "statistics_artifact_id": rz["job"]["artifact_id"],
                "ml_artifacts": {
                    "isolation_forest": if_job["job"]["artifact_id"],
                    "ecod": ecod_job["job"]["artifact_id"],
                },
            }],
        }))
        resources = AnalysisResources(model_db=runtime_dir / "models.sqlite3", bindings_file=bindings_file)

        # 1b. History reference tail (Aug 25 - Aug 31) to freeze historical reference distributions incl. real HE shadow
        hist_as_of = datetime(2026, 8, 31, 23, 59, 59, tzinfo=TZ)
        href_specs = [
            {"id": f"{company}_HTAIL_{i:02d}", "pattern": "sup_pattern" if i in (2, 7) else "clean",
             "day_offset": i % 6, "amount": 2_000_000 if i in (2, 7) else (1_100_000 + i * 33_000)}
            for i in range(1, 11)
        ]
        href_src = _build_period_snapshot(company, "HREF", datetime(2026, 8, 25, 10, 0, tzinfo=TZ), hist_as_of, href_specs)
        href_snap = _commit(snapshots, scope, href_src, f"href-{company}")
        href_ana = analyze_rule_snapshot(snapshots, scope, href_snap["snapshot_id"], hist_as_of.isoformat(), technical=True, recheck=recheck, resources=resources)
        href_sh_res = manager.create_shadow_run(
            scope, {"model_run_id": he_run_id, "snapshot_id": href_snap["snapshot_id"], "as_of": hist_as_of.isoformat()},
            f"sh-href-{company}", recheck,
        )
        href_shadow = href_sh_res["shadow_run"]
        sup_artifact_id = href_shadow["model"].get("job_id") or href_shadow["model"].get("model_id") or he_run_id
        sup_artifact_sha = href_shadow["model"]["approval_sha256"]

        model_pins = {
            "robust_z": {"company_id": company, "artifact_id": rz["job"]["artifact_id"], "artifact_sha256": digest(canonical(rz["manifest"]))},
            "isolation_forest": {"company_id": company, "artifact_id": if_job["job"]["artifact_id"], "artifact_sha256": digest(canonical(if_job["manifest"]))},
            "ecod": {"company_id": company, "artifact_id": ecod_job["job"]["artifact_id"], "artifact_sha256": digest(canonical(ecod_job["manifest"]))},
            "supervised_shadow": {"company_id": company, "artifact_id": sup_artifact_id, "artifact_sha256": sup_artifact_sha},
        }
        href_rows, _ = extract_split_rows("history_train", scope, href_snap, href_ana, shadow=href_shadow, raw_data=href_src, model_artifacts=model_pins)

        ref_ecod = build_reference_distribution("ecod", [r["branches"]["ecod"]["raw_score"] for r in href_rows],
                                                company_id=company, tenant_id=TENANT, snapshot_id=href_snap["snapshot_id"],
                                                as_of=hist_as_of.isoformat(), score_scale="ecod_tail_sum")
        ref_if = build_reference_distribution("isolation_forest", [r["branches"]["isolation_forest"]["raw_score"] for r in href_rows],
                                              company_id=company, tenant_id=TENANT, snapshot_id=href_snap["snapshot_id"],
                                              as_of=hist_as_of.isoformat(), score_scale="if_anomaly_raw")
        ref_sup = build_reference_distribution("supervised_shadow", [r["branches"]["supervised_shadow"]["raw_score"] for r in href_rows],
                                               company_id=company, tenant_id=TENANT, snapshot_id=href_snap["snapshot_id"],
                                               as_of=hist_as_of.isoformat(), score_scale="uncalibrated_he_prob")
        ref_artifacts = {r["reference_id"]: r for r in (ref_ecod, ref_if, ref_sup)}

        # 2. Validation, Calibration, and Sealed Future Test splits (Sept, Oct, Nov 2026)
        split_defs = [
            ("detector_validation", datetime(2026, 9, 1, 0, 0, 0, tzinfo=TZ), datetime(2026, 9, 30, 23, 59, 59, tzinfo=TZ)),
            ("calibration_policy_validation", datetime(2026, 10, 1, 0, 0, 0, tzinfo=TZ), datetime(2026, 10, 31, 23, 59, 59, tzinfo=TZ)),
            ("sealed_future_test", datetime(2026, 11, 1, 0, 0, 0, tzinfo=TZ), datetime(2026, 11, 30, 23, 59, 59, tzinfo=TZ)),
        ]
        manifests = {"history_train": href_snap}
        bundles = {"history_train": {"rows": href_rows, "groups": {}, "keys": {(r["record_id"], int(r["revision"])) for r in href_rows}}}
        label_packets_meta = {}
        splits_cfg = {
            "history_train": {
                "snapshot_id": href_snap["snapshot_id"], "as_of": hist_as_of.isoformat(),
                "start_at": "2026-07-01T00:00:00+07:00", "end_at": hist_as_of.isoformat(),
                "allowed_uses": ["fit_detectors", "fit_preprocess", "fit_reference_distribution"],
                "episode_grouping": {"group_keys": ["simultaneous_group_id", "episode_id"], "episode_metadata_complete": False,
                                     "limitation_note": "Synthetic baseline uses simultaneous payment groups without external ERP case table."},
            }
        }
        snap_list = [{
            "split": "history_train", "snapshot_id": href_snap["snapshot_id"], "contract_version": CONTRACT,
            "as_of": hist_as_of.isoformat(), "snapshot_sha256": href_snap["checksum"], "data_checksum": href_snap["data_checksum"],
        }]
        prov_list = []

        for sname, s_start, s_end in split_defs:
            specs, lbls = _split_specs(company, sname)
            raw_b = _build_period_snapshot(company, sname, s_start, s_end, specs)
            man = _commit(snapshots, scope, raw_b, f"{sname}-{company}")
            ana = analyze_rule_snapshot(snapshots, scope, man["snapshot_id"], s_end.isoformat(), technical=True, recheck=recheck, resources=resources)
            shd = manager.create_shadow_run(
                scope, {"model_run_id": he_run_id, "snapshot_id": man["snapshot_id"], "as_of": s_end.isoformat()},
                f"sh-{sname}-{company}", recheck,
            )["shadow_run"]
            s_rows, s_groups = extract_split_rows(sname, scope, man, ana, shadow=shd, raw_data=raw_b, model_artifacts=model_pins)
            manifests[sname] = man
            splits_cfg[sname] = {
                "snapshot_id": man["snapshot_id"], "as_of": s_end.isoformat(),
                "start_at": s_start.isoformat(), "end_at": s_end.isoformat(),
                "allowed_uses": (["compare_detectors", "select_combination"] if sname == "detector_validation"
                                 else ["fit_calibrator", "evaluate_calibration_oos", "policy_sensitivity"] if sname == "calibration_policy_validation"
                                 else ["final_sealed_evaluation"]),
                "episode_grouping": {"group_keys": ["simultaneous_group_id", "episode_id"], "episode_metadata_complete": False,
                                     "limitation_note": f"{sname}: synthetic payment batch without external ERP case-link table."},
            }
            snap_list.append({
                "split": sname, "snapshot_id": man["snapshot_id"], "contract_version": CONTRACT,
                "as_of": s_end.isoformat(), "snapshot_sha256": man["checksum"], "data_checksum": man["data_checksum"],
            })

            # Populate separate ReviewStore entries (benign outlier stays confirmed_risk, NOT verified_fraud!)
            reviews_map = {}
            cases = {(c["record_id"], int(c["revision"])): c for c in rule35_cases_for(snapshots, scope, ana, reviews, recheck=recheck, raw_data=raw_b)}
            benign_id = next(sp["id"] for sp in specs if "BENIGN_OUT" in sp["id"])
            for k in sorted(cases)[:7]:
                case = cases[k]
                lease = reviews.start(scope, case["case_id"])["lease"]
                out = "confirmed_risk" if (k[0] == benign_id or lbls.get(k, {}).get("outcome") == "verified_fraud") else "legitimate"
                reviews.save(
                    scope, case["case_id"], 0,
                    {"outcome": out, "usefulness": "yes", "explanation": "Manual document check.", "action": "Hold/escalate.",
                     "missing_materials": "", "evidence_ids": [case["evidence"][0]["evidence_id"]], "checks_completed": True},
                    [e["evidence_id"] for e in case["evidence"]], lease, f"rev-{company}-{sname}-{k[0]}",
                )
                reviews_map[k] = reviews.get(scope, case["case_id"])

            if sname == "calibration_policy_validation":
                sorted_keys = [k for k in sorted(lbls) if lbls[k]["outcome"] in ("verified_fraud", "verified_non_fraud")]
                exported_packets = []
                for b_idx in range(3):
                    chunk = sorted_keys[b_idx * 4:(b_idx + 1) * 4]
                    if len(chunk) < 4:
                        break
                    src_pkt = source_packet(snapshots, scope, {
                        "version": HE_ADAPTER_VERSION, "snapshot_id": man["snapshot_id"], "as_of": s_end.isoformat(),
                        "training_start": s_start.isoformat(), "training_end": s_end.isoformat(),
                        "rows": [{"record_id": r[0], "revision": r[1]} for r in chunk],
                    }, recheck)
                    created = labels_store.create(scope, src_pkt, recheck)
                    rev_num = created["revision"]
                    ev_map = {(c["record_id"], int(c["revision"])): [c["evidence"][0]["evidence_id"]] for c in src_pkt["cases"]}
                    for r_key in chunk:
                        saved = labels_store.change(scope, created["packet_id"], "save", {
                            "expected_revision": rev_num, "request_id": f"save-req-{company}-{b_idx}-{r_key[0]}",
                            "label": {"record_id": r_key[0], "revision": r_key[1], "outcome": lbls[r_key]["outcome"],
                                      "explanation": "Verified calibration label from audit.", "evidence_ids": ev_map[r_key], "documents_checked": True},
                        }, recheck)
                        rev_num = saved["revision"]
                    locked_pkt = labels_store.change(scope, created["packet_id"], "lock",
                                                     {"expected_revision": rev_num, "request_id": f"lock-req-{company}-batch-{b_idx}"}, recheck)
                    exp_pkt = labels_store.export(scope, created["packet_id"], locked_pkt["revision"], locked_pkt["lock_sha256"], recheck)
                    exported_packets.append(exp_pkt)
                    label_packets_meta[created["packet_id"]] = {
                        "packet_id": created["packet_id"], "revision": locked_pkt["revision"],
                        "lock_sha256": locked_pkt["lock_sha256"], "company_id": company,
                    }
                    prov_list.append({
                        "split": sname, "source_type": "label_store_packet", "packet_id": created["packet_id"],
                        "revision": locked_pkt["revision"], "lock_sha256": locked_pkt["lock_sha256"],
                        "company_id": company, "labels_blinded_before_lock": False,
                    })
                verified_dict = {"packets": exported_packets}
            else:
                prov_list.append({
                    "split": sname, "source_type": "verified_fixture", "packet_id": None, "revision": None,
                    "lock_sha256": None, "company_id": company, "labels_blinded_before_lock": True,
                })
                verified_dict = {"company_id": company, "records": {k: {"outcome": v["outcome"], "company_id": company} for k, v in lbls.items()}}

            bundles[sname] = {"rows": s_rows, "groups": s_groups, "verified_labels": verified_dict, "reviews": {"company_id": company, "reviews": reviews_map}}

        plan = {
            "version": "evaluation-plan/1.0.0",
            "study_id": f"val-study-{company.lower()}-20261116",
            "scope": {"tenant_id": TENANT, "company_id": company},
            "snapshots": snap_list,
            "splits": splits_cfg,
            "versions": {
                "rule_engine_version": "agent2-rules-35/1.0.0",
                "feature_contract_version": "rule-snapshot-point-in-time/1.0.0",
                "preprocess_version": "frozen-feature-preprocess/1.0.0",
                "random_seed": 42,
                "model_bindings": [
                    {"method_id": "rules_35", "kind": "rules", "artifact_id": "rules_35_v1", "artifact_sha256": digest(b"rules_35"),
                     "model_version": "1.0.0", "company_id": company, "training_split": "history_train", "training_mechanism": "deterministic_rules"},
                    {"method_id": "isolation_forest", "kind": "unsupervised", "artifact_id": if_job["job"]["artifact_id"],
                     "artifact_sha256": model_pins["isolation_forest"]["artifact_sha256"], "model_version": "1.0.0",
                     "company_id": company, "training_split": "history_train", "training_mechanism": "local_enterprise_fit"},
                    {"method_id": "ecod", "kind": "unsupervised", "artifact_id": ecod_job["job"]["artifact_id"],
                     "artifact_sha256": model_pins["ecod"]["artifact_sha256"], "model_version": "1.0.0",
                     "company_id": company, "training_split": "history_train", "training_mechanism": "local_enterprise_fit"},
                    {"method_id": "supervised_shadow", "kind": "supervised_shadow", "artifact_id": sup_artifact_id,
                     "artifact_sha256": sup_artifact_sha, "model_version": "1.0.0",
                     "company_id": company, "training_split": "history_train", "training_mechanism": "concrete_fhe"},
                ],
                "reference_bindings": [
                    {"method_id": ref["method_id"], "reference_id": ref["reference_id"], "reference_version": ref["reference_version"],
                     "reference_sha256": ref["reference_sha256"], "company_id": company, "fitted_split": "history_train", "score_scale": ref["score_scale"]}
                    for ref in (ref_ecod, ref_if, ref_sup)
                ],
            },
            "labels": {
                "target_contract": LABEL_TARGET, "positive_label": "verified_fraud", "negative_label": "verified_non_fraud",
                "excluded_outcomes": ["confirmed_risk", "legitimate", "inconclusive", None],
                "review_feedback_coercion_allowed": False, "full_split_ground_truth": False, "source_provenance": prov_list,
            },
            "candidates": [
                {"arm_id": "rules_only", "kind": "rules_only", "branches": ["rules_35"], "weights": None,
                 "uses_percentile_reference": False, "reference_ids": [], "he_is_training_mechanism_only": True, "complexity": 1},
                {"arm_id": "ecod_standalone", "kind": "individual_detector", "branches": ["ecod"], "weights": None,
                 "uses_percentile_reference": False, "reference_ids": [], "he_is_training_mechanism_only": True, "complexity": 1},
                {"arm_id": "if_standalone", "kind": "individual_detector", "branches": ["isolation_forest"], "weights": None,
                 "uses_percentile_reference": False, "reference_ids": [], "he_is_training_mechanism_only": True, "complexity": 1},
                {"arm_id": "supervised_shadow_standalone", "kind": "individual_detector", "branches": ["supervised_shadow"], "weights": None,
                 "uses_percentile_reference": False, "reference_ids": [], "he_is_training_mechanism_only": True, "complexity": 1},
                {"arm_id": "rules_plus_ecod", "kind": "rules_plus_ml", "branches": ["rules_35", "ecod"], "weights": None,
                 "uses_percentile_reference": False, "reference_ids": [], "he_is_training_mechanism_only": True, "complexity": 2},
                {"arm_id": "rules_plus_isolation_forest", "kind": "rules_plus_ml", "branches": ["rules_35", "isolation_forest"], "weights": None,
                 "uses_percentile_reference": False, "reference_ids": [], "he_is_training_mechanism_only": True, "complexity": 2},
                {"arm_id": "rules_plus_supervised_shadow", "kind": "rules_plus_ml", "branches": ["rules_35", "supervised_shadow"], "weights": None,
                 "uses_percentile_reference": False, "reference_ids": [], "he_is_training_mechanism_only": True, "complexity": 2},
                {"arm_id": "rules_plus_ens_ecod_sup", "kind": "rules_plus_percentile_ensemble",
                 "branches": ["rules_35", "ecod", "supervised_shadow"], "weights": {"ecod": 0.5, "supervised_shadow": 0.5},
                 "uses_percentile_reference": True, "reference_ids": [ref_ecod["reference_id"], ref_sup["reference_id"]],
                 "he_is_training_mechanism_only": True, "complexity": 3},
            ],
            "selection_policy": {
                "locked_policy": {"policy_id": "rules_first_fill/1.0.0", "budget": 5, "tie_break": ["complexity_asc", "arm_id_asc"]},
                "selection_objective": {"primary_metric": "verified_fraud_cases_selected", "secondary_metric": "resolved_fraud_precision",
                                        "min_incremental_gain": 0.0, "require_positive_marginal_value": True, "prefer_simpler_on_tie": True},
                "policy_variants": [
                    {"variant_id": "priority_top5_no_rules_priority", "policy_kind": "priority_top_k", "budget": 5, "min_priority_threshold": None},
                    {"variant_id": "rules_first_thresh_0.55", "policy_kind": "threshold_gated_rules_first", "budget": 5, "min_priority_threshold": 0.55},
                ],
            },
            "calibration_spec": {
                "target_branch": "supervised_shadow", "allowed_methods": ["platt_logistic", "isotonic_regression"],
                "fit_split": "calibration_policy_validation", "internal_eval_folds": 3, "min_total_labels": 8,
                "min_positive_labels": 3, "min_negative_labels": 3, "ece_bins": 4, "block_on_insufficient_labels": True,
            },
            "fallback_specs": [
                {"fallback_config_id": "fb_missing_sup_v1", "config_version": "1.0.0", "trigger_condition": "missing_supervised_model",
                 "used_branches": ["rules_35", "ecod"], "missing_or_ineligible_branches": ["supervised_shadow"], "is_full_ensemble": False,
                 "weight_policy": "explicit_fallback_subset", "weights": None},
                {"fallback_config_id": "fb_missing_unsup_v1", "config_version": "1.0.0", "trigger_condition": "missing_unsupervised_model",
                 "used_branches": ["rules_35", "supervised_shadow"], "missing_or_ineligible_branches": ["ecod", "isolation_forest", "robust_z"],
                 "is_full_ensemble": False, "weight_policy": "explicit_fallback_subset", "weights": None},
                {"fallback_config_id": "fb_incompatible_contract_v1", "config_version": "1.0.0", "trigger_condition": "incompatible_contract",
                 "used_branches": ["rules_35"], "missing_or_ineligible_branches": ["ecod", "isolation_forest", "supervised_shadow"],
                 "is_full_ensemble": False, "weight_policy": "explicit_fallback_subset", "weights": None},
                {"fallback_config_id": "fb_missing_feature_v1", "config_version": "1.0.0", "trigger_condition": "missing_feature_or_post_cutoff",
                 "used_branches": ["rules_35", "ecod"], "missing_or_ineligible_branches": ["supervised_shadow"],
                 "is_full_ensemble": False, "weight_policy": "explicit_fallback_subset", "weights": None},
                {"fallback_config_id": "fb_missing_ref_v1", "config_version": "1.0.0", "trigger_condition": "missing_reference_distribution",
                 "used_branches": ["rules_35", "supervised_shadow"], "missing_or_ineligible_branches": ["ecod"],
                 "is_full_ensemble": False, "weight_policy": "explicit_fallback_subset", "weights": None},
                {"fallback_config_id": "fb_partial_rule_gap_v1", "config_version": "1.0.0", "trigger_condition": "partial_rule_source_gap",
                 "used_branches": ["rules_35", "ecod"], "missing_or_ineligible_branches": ["rule_E2_partial"],
                 "is_full_ensemble": False, "weight_policy": "explicit_fallback_subset", "weights": None},
                {"fallback_config_id": "fb_all_unavailable_v1", "config_version": "1.0.0", "trigger_condition": "all_branches_unavailable",
                 "used_branches": [], "missing_or_ineligible_branches": ["rules_35", "ecod", "isolation_forest", "supervised_shadow"],
                 "is_full_ensemble": False, "weight_policy": "unavailable", "weights": None},
            ],
            "metrics_and_criteria": {
                "primary_metrics": ["resolved_precision", "additional_useful_verified_cases_over_rules", "brier_score", "log_loss"],
                "technical_gates": [
                    {"gate_id": "TG-01", "description": "EvaluationPlan & selection locked before touching sealed_future_test labels.", "required": True},
                    {"gate_id": "TG-02", "description": "No raw score mixing without frozen historical reference distributions.", "required": True},
                    {"gate_id": "TG-03", "description": "Missing source/model emits null unavailable rather than 0 or implicit fit.", "required": True},
                ],
                "quality_gates": [dict(g) for g in DEFAULT_OPEN_QUALITY_GATES],
            },
            "governance": {
                "promotion_target": "candidate_shadow_only", "production_approved": False, "active_model_replaced": False,
                "operational_queue_changed": False, "execution_location": "enterprise_local_only", "cloud_plaintext_sent": False,
                "synthetic_data_disclosure": "Du lieu synthetic da ky dung de kiem chung quy trinh ky thuat tai enterprise; khong thay bang chung hieu qua tren doanh nghiep that.",
            },
        }

        report_a = run_validation_study(
            plan, snapshot_manifests=manifests, model_artifacts=model_pins,
            reference_artifacts=ref_artifacts, split_bundles=bundles, label_packets=label_packets_meta,
        )
        report_b = run_validation_study(
            plan, snapshot_manifests=manifests, model_artifacts=model_pins,
            reference_artifacts=ref_artifacts, split_bundles=bundles, label_packets=label_packets_meta,
        )
        reports_by_company[company] = {
            "report": report_a,
            "deterministic_rerun_match": report_a["study_result_sha256"] == report_b["study_result_sha256"],
        }

    # Global mandatory cross-checks
    c1_r = reports_by_company["C001"]["report"]
    c2_r = reports_by_company["C002"]["report"]
    acceptance_checks["deterministic_reproducible_c001_c002"] = (
        reports_by_company["C001"]["deterministic_rerun_match"] and reports_by_company["C002"]["deterministic_rerun_match"]
    )
    acceptance_checks["recall_pr_auc_gated_under_incomplete_gt"] = all(
        a["verified_label_metrics"]["recall_at_budget"] is None and a["verified_label_metrics"]["pr_auc"] is None
        for r in (c1_r, c2_r) for a in r["sealed_future_test"]["arm_results"]
    )
    acceptance_checks["governance_shadow_only_no_prod_approval"] = all(
        (not r["governance"]["production_approved"]
         and not r["governance"]["active_model_replaced"]
         and not r["governance"]["operational_queue_changed"]
         and r["governance"]["execution_location"] == "enterprise_local_only"
         and not r["governance"]["cloud_plaintext_sent"]
         and all(not g["approved_for_production"] for g in r["open_quality_gates"]))
        for r in (c1_r, c2_r)
    )

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "report_version": "validation-study-acceptance/1.0.0",
        "real_concrete_he_models_used": True,
        "enterprise_local_execution_only": True,
        "cloud_plaintext_sent": False,
        "acceptance_checks": acceptance_checks,
        "companies": {cid: reports_by_company[cid]["report"] for cid in ("C001", "C002")},
    }
    _write_json(json_report, payload)
    _write_markdown_report(md_report, payload)
    return payload


def _write_markdown_report(path: Path, payload: dict) -> None:
    lines = [
        "# Validation, Calibration, and Fallback Plan — Agent2",
        "",
        "## 1. Architecture & Contracts",
        "- **Schema & Lock:** `agent2/sme_fraud/evaluation_plan.schema.json` (`evaluation-plan/1.0.0`, validated via `StrictValidator` + SHA-256 checksum pinning).",
        "- **Core Pipeline:** `agent2/sme_fraud/validation_study.py` (`agent2-validation-study/1.0.0`) enforcing 4 chronological splits (`history_train` -> `detector_validation` -> `calibration_policy_validation` -> `sealed_future_test`), structural test-label blinding (`pre_test_lock_sha256`), frozen historical reference percentiles (`historical-reference-dist/1.0.0`), verified-only calibration (`verified-calibrator/1.0.0`), and explicit degraded fallbacks (`explicit-fallback-plan/1.0.0`).",
        "- **Enterprise CLI Runner:** `agent2/scripts/run_validation_study.py` executing strictly locally at enterprise node (no cloud plaintext upload, active model & operational queue untouched).",
        "- **Verification Suite:** `agent2/tests_he/test_validation_study.py` covering test-label blinding, plan pin mismatch detection, missing source/model null/unavailable semantics, calibration blocking on insufficient/non-verified labels, `C001`/`C002` + episode isolation, and deterministic rerun reproducibility.",
        "",
        "## 2. Governance & Scope Disclosures",
        f"- **Generated (UTC):** `{payload['generated_at_utc']}`",
        f"- **Real HE Models Used:** `{payload['real_concrete_he_models_used']}` (enterprise-decrypted signed `Concrete FHE` models from `C001` & `C002`, no cloud plaintext sent).",
        "- **Promotion Status:** `candidate_shadow_only` (`production_approved = false`, `active_model_replaced = false`, `operational_queue_changed = false`).",
        "- **Synthetic Limit:** Du lieu synthetic da ky dung de kiem chung quy trinh validation/calibration/fallback; khong thay the bang chung hieu qua tren du lieu doanh nghiep that.",
        "- **Open Decision Gates (`Agent2_Spec_v2_1/99_decision_log.md`):** `D-03`, `D-04`, `D-06`, `D-07`, `D-09` remain explicitly `OPEN_BLOCKING` / `PROPOSED_DEFAULT_EXPERIMENTAL_ONLY` (`approved_for_production = false`).",
        "",
        "## 3. Automated Acceptance Gates",
    ]
    for k, v in payload["acceptance_checks"].items():
        lines.append(f"- `{k}`: **{v}**")

    for idx, cid in enumerate(("C001", "C002"), 1):
        rep = payload["companies"][cid]
        sel = rep["detector_validation"]
        cal = rep["calibration_validation"]["calibrator"]
        cal_test = rep["calibration_validation"]["sealed_future_test_calibration"]
        costs = rep["execution_costs"]
        lines.extend([
            "",
            f"## 4.{idx} Enterprise `{cid}` Results",
            f"- **Plan Lock:** `{rep['plan_lock']['plan_id']}` (`plan_sha256={rep['plan_lock']['plan_sha256'][:16]}...`, `pre_test_lock_sha256={rep['plan_lock']['pre_test_lock_sha256'][:16]}...`)",
            f"- **Selected Candidate (locked from `detector_validation`):** `{sel['selected_arm_id']}` (`selection_sha256={sel['selection_sha256'][:16]}...`)",
            f"- **Episode Limitations:** {'; '.join(rep['episode_limitations']) or 'None'}",
            f"- **Calibrator (`calibration_policy_validation`):** status=`{cal['status']}`, method=`{cal['method']}`, verified pos/neg=`{cal['counts']['verified_fraud']}/{cal['counts']['verified_non_fraud']}`, excluded `confirmed_risk` reviews=`{cal['counts']['review_confirmed_risk_excluded']}`",
            f"- **Execution Costs:** val=`{costs['detector_validation']['runtime_ms']}ms` / `{costs['detector_validation']['peak_memory_kb']}KB`, cal=`{costs['calibration_validation']['runtime_ms']}ms`, sealed_test=`{costs['sealed_test_evaluation']['runtime_ms']}ms`, fallback=`{costs['fallback_validation']['runtime_ms']}ms`",
        ])
        if cal_test.get("sealed_test_metrics"):
            cm = cal_test["sealed_test_metrics"]
            lines.append(f"- **Sealed Test Calibration Metrics:** `brier={cm['brier_score']}`, `log_loss={cm['log_loss']}`, `ece={cm['ece']}` (uncalibrated: brier=`{cm['uncalibrated_brier_score']}`, log_loss=`{cm['uncalibrated_log_loss']}`)")
            lines.extend([
                "",
                "### Calibration Reliability Bins (Sealed Future Test)",
                "| Bin | Range | Count | Mean Predicted Prob | Observed Fraud Rate | Abs Gap |",
                "|---:|---|---:|---:|---:|---:|",
            ])
            for b in cm["reliability_bins"]:
                mp = f"{b['mean_predicted_prob']:.4f}" if b["mean_predicted_prob"] is not None else "n/a"
                ob = f"{b['observed_fraud_rate']:.4f}" if b["observed_fraud_rate"] is not None else "n/a"
                gp = f"{b['abs_gap']:.4f}" if b["abs_gap"] is not None else "n/a"
                lines.append(f"| {b['bin']} | [{b['lower']:.2f}, {b['upper']:.2f}] | {b['count']} | {mp} | {ob} | {gp} |")

        lines.extend([
            "",
            "### Sealed Future Test Comparison (`rules_first_fill/1.0.0`, budget=5)",
            "| Arm ID | Kind | Available | Selected | VF Added Over Rules | Resolved Denom | Unresolved (Rate) | Precision | Review Effort (s) | Recall / PR-AUC |",
            "|---|---|---:|---:|---:|---:|---|---:|---|---|",
        ])
        for a in rep["sealed_future_test"]["arm_results"]:
            vm = a["verified_label_metrics"]
            pr = vm["resolved_precision"]
            pr_str = f"{pr['value']:.3f} ({pr['numerator']}/{pr['denominator']})" if pr["value"] is not None else "null"
            unr_rate = f"{vm['unresolved_rate']:.2f}" if vm["unresolved_rate"] is not None else "n/a"
            eff = a["review_feedback_separate"]["review_effort_seconds"]
            eff_str = f"{eff['total_active_seconds']}" if eff["recorded"] else "null (unrecorded)"
            lines.append(
                f"| `{a['arm_id']}` | `{a['kind']}` | {a['availability']['available_rows']}/{a['availability']['total_rows']} | "
                f"{a['selected_count']} | {a['additional_useful_verified_cases_over_rules']} cases | {vm['resolved_count']} | "
                f"{vm['unresolved_count']} ({unr_rate}) | {pr_str} | {eff_str} | null ({vm['recall_pr_auc_scope']}) |"
            )

        cc = rep["sealed_future_test"]["common_coverage_subset"]
        lines.append(f"\n- **Common Coverage Subset:** `{cc['row_count']}/{cc['total_rows']}` rows simultaneously available across all candidate arms.")
        for pv in rep["sealed_future_test"]["policy_sensitivity"]:
            sel_pv = next((x for x in pv["arms"] if x["arm_id"] == sel["selected_arm_id"]), None)
            if sel_pv:
                d = sel_pv["delta_vs_locked_policy"]
                lines.append(f"- **Policy Variant `{pv['variant_id']}` (isolated delta on `{sel['selected_arm_id']}`):** `vf_selected_delta={d['vf_selected_delta']}`, `precision_delta={d['precision_delta']}`")

        lines.extend([
            "",
            "### Fallback Plan Validation Matrix",
            "| Fallback ID | Trigger | Is Full Ensemble | Used Branches | Missing Branches | Avail Rate | Null On Unavail |",
            "|---|---|---:|---|---|---:|---:|",
        ])
        for fb in rep["fallback_validation"]["scenarios"]:
            lines.append(
                f"| `{fb['fallback_config_id']}` | `{fb['trigger_condition']}` | {fb['is_full_ensemble']} | "
                f"`{', '.join(fb['used_branches']) or 'none'}` | `{', '.join(fb['missing_or_ineligible_branches'])}` | "
                f"{fb['coverage']['availability_rate']:.2f} | {fb['effectiveness']['null_score_when_unavailable']} |"
            )

    path.parent.mkdir(parents=True, exist_ok=True)
    atomic(path, ("\n".join(lines) + "\n").encode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Agent2 validation, calibration, and fallback acceptance study.")
    parser.add_argument("--runtime-dir", type=Path, default=DEFAULT_RUNTIME_DIR)
    parser.add_argument("--he-source-dir", type=Path, default=SOURCE_HE_ACCEPTANCE_DIR)
    parser.add_argument("--he-build-dir", type=Path, default=DEFAULT_BUILD_DIR)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON_REPORT)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_MD_REPORT)
    args = parser.parse_args()
    out = run_acceptance(
        runtime_dir=args.runtime_dir,
        source_he_dir=args.he_source_dir,
        build_dir=args.he_build_dir,
        json_report=args.output_json,
        md_report=args.output_md,
    )
    print(json.dumps({
        "status": "ok",
        "checks": out["acceptance_checks"],
        "c001_selected": out["companies"]["C001"]["detector_validation"]["selected_arm_id"],
        "c002_selected": out["companies"]["C002"]["detector_validation"]["selected_arm_id"],
        "json_report": str(args.output_json),
        "md_report": str(args.output_md),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
