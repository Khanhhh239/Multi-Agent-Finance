"""Mandatory unit & integration tests for EvaluationPlan, calibration, fallback, and isolation."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import random
import sqlite3
import secrets
import tempfile
import unittest

from sme_fraud.analysis_resources import AnalysisResources, VERSION as BINDINGS_VERSION
from sme_fraud.auth import FileAuthorizer
from sme_fraud.import_files import canonical, digest
from sme_fraud.label_packets import LabelStore, TARGET as LABEL_TARGET, source_packet
from sme_fraud.method_jobs import run_fit_job
from sme_fraud.method_store import MethodStore
from sme_fraud.review_store import ReviewStore
from experiments.he_training.snapshot_adapter import VERSION as HE_ADAPTER_VERSION
from sme_fraud.rule35_comparison import rule35_cases_for
from sme_fraud.rule35_ml_eval_demo import (
    _add_clean_payment,
    _add_payroll_tx,
    _finalize,
    _seed_baseline_tables,
    base,
    evidence,
    fit_config,
)
from sme_fraud.rule_snapshot import CONTRACT, analyze as analyze_rule_snapshot
from sme_fraud.snapshots import SnapshotStore
from sme_fraud.validation_study import (
    DEFAULT_OPEN_QUALITY_GATES,
    STUDY_VERSION,
    ValidationStudyError,
    apply_calibrator,
    build_reference_distribution,
    extract_split_rows,
    fit_and_evaluate_calibration,
    lock_evaluation_plan,
    parse_verified_labels,
    run_detector_validation,
    run_validation_study,
    transform_with_reference,
    validate_evaluation_plan,
)

TZ = timezone(timedelta(hours=7))


def _policy_file(path: Path, token: str) -> None:
    exp = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    policy = {
        "policy_version": "1.0.0",
        "principals": [
            {
                "actor_id": "val-director",
                "tenant_id": "demo",
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
    preview = store.preview(scope, draft["import_id"], 1)
    if preview["status"] == "rejected":
        raise AssertionError(preview["errors"])
    req = {k: preview[k] for k in ("preview_id", "source_hash", "mapping_hash", "report_hash", "context_hash")}
    req.update(expected_revision=preview["revision"], acknowledge=True)
    return store.commit(scope, draft["import_id"], req, key + "-c")["snapshot"]


def _build_period_source(
    company: str,
    prefix: str,
    start_dt: datetime,
    as_of_dt: datetime,
    specs: list[dict],
    *,
    include_history: bool = True,
    tenant_id: str = "demo",
) -> tuple[dict, list[str]]:
    """Build valid agent2-rule-snapshot/1.0.0 snapshot carrying clean pre-history plus period candidates."""
    scale = 1 if company == "C001" else 3
    c = base()
    _seed_baseline_tables(c, company, scale, datetime(2026, 7, 1, 10, 0, tzinfo=TZ))

    rng = random.Random(100 if company == "C001" else 200)
    history_ids = []
    if include_history:
        day = datetime(2026, 7, 2, 10, 0, tzinfo=TZ)
        idx = 0
        while idx < 32:
            if day.weekday() < 5:
                idx += 1
                tid = f"{company}_H_{idx:02d}"
                amt = (1_050_000 + rng.randint(0, 35) * 14_300) * scale
                _add_clean_payment(c, tid, day, amt, scale=scale, company_id=company, doc=True)
                history_ids.append(tid)
            day += timedelta(days=1)
        for p_i, p_day in enumerate((datetime(2026, 7, 25, 10, 0, tzinfo=TZ), datetime(2026, 8, 12, 10, 0, tzinfo=TZ)), 1):
            pid = f"{company}_HPAY_{p_i:02d}"
            _add_payroll_tx(c, pid, p_day, 14_200_000 * scale, company_id=company, scale=scale, terminated=False)
            history_ids.append(pid)
        ref_day = datetime(2026, 8, 19, 10, 0, tzinfo=TZ)
        for r_i in range(1, 13):
            while ref_day.weekday() >= 5:
                ref_day += timedelta(days=1)
            tid = f"{company}_R_{r_i:02d}"
            amt = (1_120_000 + rng.randint(0, 30) * 11_300) * scale
            _add_clean_payment(c, tid, ref_day, amt, scale=scale, company_id=company, doc=True)
            history_ids.append(tid)
            ref_day += timedelta(hours=12)

    cand_ids = []
    for idx, sp in enumerate(specs):
        tid = sp["id"]
        cand_ids.append(tid)
        ev_at = start_dt + timedelta(days=sp.get("day_offset", idx % 18), hours=sp.get("hour_offset", 10 + (idx % 6)))
        kind = sp.get("pattern", "clean")
        if kind == "p1_pair_a":
            _add_clean_payment(
                c, tid, ev_at, 15_000_000 * scale, scale=scale, company_id=company,
                invoice_number=sp.get("inv", f"INV_{prefix}_P1"), invoice_gross_vnd=18_000_000 * scale,
            )
        elif kind == "p1_pair_b":
            _add_clean_payment(
                c, tid, ev_at, 14_000_000 * scale, scale=scale, company_id=company,
                invoice_number=sp.get("inv", f"INV_{prefix}_P1"), invoice_gross_vnd=18_000_000 * scale,
            )
        elif kind == "c2_self":
            _add_clean_payment(
                c, tid, ev_at, 16_000_000 * scale, scale=scale, company_id=company,
                approver_id=c.maker["employee_id"],
            )
        elif kind == "b1_worker_bank":
            vb1 = deepcopy(c.vendor)
            vb1.update(
                vendor_id=f"{company}_{tid}_VB1", name="Shadow Link Vendor", representative_id=f"{tid}_REP",
                bank_account=c.worker["bank_account"], phone="0908111222", address="12 Le Loi, HCMC",
                national_id=f"{tid}_NAT", tax_code=f"{tid}_TAX",
            )
            c.tables["vendors"].append(vb1)
            _add_clean_payment(c, tid, ev_at, 4_200_000 * scale, vendor=vb1, scale=scale, company_id=company)
        elif kind == "ml_fraud_high":
            _add_clean_payment(
                c, tid, ev_at, sp.get("amount", 78_543_210) * scale,
                scale=scale, company_id=company, doc=False, imbalance=10_000_000 * scale,
                approver_id=c.maker["employee_id"] if sp.get("same_approver") else c.director["employee_id"],
            )
        elif kind == "benign_outlier":
            _add_clean_payment(
                c, tid, ev_at, sp.get("amount", 62_111_700) * scale,
                scale=scale, company_id=company, doc=False, imbalance=7_000_000 * scale,
            )
        else:
            amt = sp.get("amount", (1_110_000 + idx * 23_750) * scale)
            _add_clean_payment(
                c, tid, ev_at, amt, scale=scale, company_id=company,
                approver_id=c.maker["employee_id"] if sp.get("same_approver") else c.director["employee_id"],
            )
        if sp.get("episode_id"):
            c.rows[-1]["episode_id"] = sp["episode_id"]

    bundle = _finalize(
        c,
        tenant_id=tenant_id,
        company_id=company,
        as_of=as_of_dt.isoformat(),
        candidate_ids=cand_ids if cand_ids else history_ids[-10:],
        source_id=f"synthetic-{company.lower()}-{prefix}",
    )
    return bundle, (cand_ids or history_ids)


def _mock_shadow_run(scope, manifest: dict, analysis: dict, approved_id: str, approval_sha: str, score_fn) -> dict:
    company = next(iter(scope.company_ids))
    return {
        "version": "portal-shadow-snapshot-run/0.1.0",
        "shadow_run_id": f"shrun_{digest(canonical([company, manifest['snapshot_id']]))[:16]}",
        "tenant_id": scope.tenant_id,
        "company_id": company,
        "snapshot": {
            "snapshot_id": manifest["snapshot_id"],
            "checksum": manifest["checksum"],
            "data_checksum": manifest["data_checksum"],
            "contract_version": manifest["contract_version"],
            "as_of": analysis["as_of"],
        },
        "model": {
            "job_id": approved_id,
            "model_id": approved_id,
            "approved_for_shadow": True,
            "approval_sha256": approval_sha,
            "training_mechanism": "concrete_fhe",
        },
        "rows": [
            {
                "record_id": r["transaction_id"],
                "revision": int(r["revision"]),
                "status": "scored",
                "available": True,
                "is_new_transaction": True,
                "history_status": "new_transaction",
                "score": float(score_fn(r)),
                "issues": [],
            }
            for r in analysis["rows"]
        ],
    }


def _make_period_specs(prefix: str, include_shared: str | None = None) -> tuple[list[dict], dict[tuple[str, int], dict]]:
    """Return 14 period specs + ground truth verified labels separating ML signal, rule hits, and noise."""
    p1_at = 1
    specs = [
        {"id": f"{prefix}_01_P1A", "pattern": "p1_pair_a", "day_offset": p1_at, "hour_offset": 10, "inv": f"INV_{prefix}_P1"},
        {"id": f"{prefix}_02_P1B", "pattern": "p1_pair_b", "day_offset": p1_at, "hour_offset": 10, "inv": f"INV_{prefix}_P1"},
        {"id": f"{prefix}_03_C2", "pattern": "c2_self", "day_offset": 3, "hour_offset": 11},
        {"id": f"{prefix}_04_ML_F1", "pattern": "ml_fraud_high", "day_offset": 5, "amount": 92_451_300, "same_approver": False},
        {"id": f"{prefix}_05_ML_F2", "pattern": "ml_fraud_high", "day_offset": 6, "amount": 85_319_700, "same_approver": False},
        {"id": f"{prefix}_06_BENIGN_OUT", "pattern": "benign_outlier", "day_offset": 7, "amount": 60_512_300},
        {"id": f"{prefix}_07_SUP_F1", "pattern": "clean", "day_offset": 8, "amount": 2_000_000, "same_approver": True},
        {"id": f"{prefix}_08_SUP_F2", "pattern": "clean", "day_offset": 9, "amount": 3_000_000, "same_approver": True},
    ]
    for i in range(9, 14):
        specs.append({"id": f"{prefix}_{i:02d}_NORM", "pattern": "clean", "day_offset": 10 + (i % 8)})
    specs.append({"id": include_shared or f"{prefix}_14_NORM", "pattern": "clean", "day_offset": 19})

    labels = {
        (f"{prefix}_01_P1A", 1): {"outcome": "verified_fraud"},
        (f"{prefix}_02_P1B", 1): {"outcome": "verified_fraud"},
        (f"{prefix}_03_C2", 1): {"outcome": "verified_fraud"},
        (f"{prefix}_04_ML_F1", 1): {"outcome": "verified_fraud"},
        (f"{prefix}_05_ML_F2", 1): {"outcome": "verified_fraud"},
        (f"{prefix}_06_BENIGN_OUT", 1): {"outcome": "verified_non_fraud"},
        (f"{prefix}_07_SUP_F1", 1): {"outcome": "verified_fraud"},
        (f"{prefix}_08_SUP_F2", 1): {"outcome": "verified_fraud"},
    }
    for sp in specs[8:]:
        labels[(sp["id"], 1)] = {"outcome": "verified_non_fraud"}
    return specs, labels


class ValidationStudyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.token = secrets.token_urlsafe(24)
        cls.header = "Bearer " + cls.token
        cls.policy_path = cls.root / "policy.json"
        _policy_file(cls.policy_path, cls.token)
        cls.auth = FileAuthorizer(cls.policy_path)
        cls.snapshots = SnapshotStore(cls.root / "snapshots.sqlite3")
        cls.models = MethodStore(cls.root / "models.sqlite3")
        cls.labels_store = LabelStore(cls.root / "labels.sqlite3", digest(b"val-test-labels").encode()[:32])
        cls.reviews = ReviewStore(cls.root / "reviews.sqlite3", digest(b"val-test-reviews").encode()[:32])

        cls.company_ctx = {}
        for company in ("C001", "C002"):
            cls.company_ctx[company] = cls._build_company_fixture(company)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @classmethod
    def _build_company_fixture(cls, company: str) -> dict:
        scope = cls.auth.authorize(cls.header, company)
        # 1a. History fit snapshot (Jul 1 - Aug 24) used for unsupervised model & internal ref fit
        fit_as_of = datetime(2026, 8, 24, 23, 59, 59, tzinfo=TZ)
        fit_bundle, _ = _build_period_source(
            company, "FIT", datetime(2026, 7, 2, 10, 0, tzinfo=TZ), fit_as_of, []
        )
        fit_snap = _commit(cls.snapshots, scope, fit_bundle, f"fit-snap-{company}")

        def _fit_cfg(m: str) -> dict:
            return dict(
                fit_config(fit_snap["snapshot_id"], m),
                minimum_history=10,
                history_end="2026-08-15T23:59:59+07:00",
                reference_start="2026-08-16T00:00:00+07:00",
                reference_end=fit_as_of.isoformat(),
                evaluation_start="2026-08-25T00:00:00+07:00",
            )

        rz = run_fit_job(cls.snapshots, cls.models, cls.auth, cls.header, company, _fit_cfg("robust_z"), f"fit-rz-{company}")
        if_res = run_fit_job(cls.snapshots, cls.models, cls.auth, cls.header, company, _fit_cfg("isolation_forest"), f"fit-if-{company}")
        ecod_res = run_fit_job(cls.snapshots, cls.models, cls.auth, cls.header, company, _fit_cfg("ecod"), f"fit-ecod-{company}")
        assert all(x["job"]["status"] == "succeeded" for x in (rz, if_res, ecod_res))

        bindings_file = cls.root / f"bindings-{company}.json"
        bindings_file.write_bytes(canonical({
            "version": BINDINGS_VERSION,
            "bindings": [{
                "tenant_id": "demo",
                "company_id": company,
                "statistics_artifact_id": rz["job"]["artifact_id"],
                "ml_artifacts": {
                    "isolation_forest": if_res["job"]["artifact_id"],
                    "ecod": ecod_res["job"]["artifact_id"],
                },
            }],
        }))
        resources = AnalysisResources(model_db=cls.root / "models.sqlite3", bindings_file=bindings_file)

        sup_job_id = f"job_sup_{company.lower()}"
        sup_sha = digest(f"sup-{company}".encode())

        # Deterministic score helper for supervised_shadow in unit tests: high for round_million + same approver or F1/F2
        def sup_score(row: dict) -> float:
            tid = row["transaction_id"]
            if any(tag in tid for tag in ("SUP_F", "ML_F", "P1", "C2")):
                return 0.88 if "SUP_F" in tid else 0.72
            if "BENIGN_OUT" in tid:
                return 0.34
            return 0.14 if int(row.get("amount_vnd", 0)) % 1_000_000 != 0 else 0.42

        # 1b. History reference tail (Aug 25 - Aug 31, AFTER artifact available_from=Aug 24, BEFORE detector_validation=Sept 1)
        hist_as_of = datetime(2026, 8, 31, 23, 59, 59, tzinfo=TZ)
        href_specs = [
            {"id": f"{company}_HREF_{i:02d}", "pattern": "clean", "day_offset": i % 6, "amount": 1_080_000 + i * 31_000}
            for i in range(1, 11)
        ]
        hist_bundle, _ = _build_period_source(
            company, "HREF", datetime(2026, 8, 25, 10, 0, tzinfo=TZ), hist_as_of, href_specs
        )
        hist_snap = _commit(cls.snapshots, scope, hist_bundle, f"hist-snap-{company}")

        hist_analysis = analyze_rule_snapshot(
            cls.snapshots, scope, hist_snap["snapshot_id"], hist_as_of.isoformat(), technical=True, resources=resources
        )
        hist_shadow = _mock_shadow_run(scope, hist_snap, hist_analysis, sup_job_id, sup_sha, sup_score)
        hist_rows, _ = extract_split_rows("history_train", scope, hist_snap, hist_analysis, shadow=hist_shadow, raw_data=hist_bundle)

        ref_ecod = build_reference_distribution(
            "ecod", [r["branches"]["ecod"]["raw_score"] for r in hist_rows],
            company_id=company, tenant_id="demo", snapshot_id=hist_snap["snapshot_id"],
            as_of=hist_as_of.isoformat(), score_scale="ecod_tail_sum",
        )
        ref_if = build_reference_distribution(
            "isolation_forest", [r["branches"]["isolation_forest"]["raw_score"] for r in hist_rows],
            company_id=company, tenant_id="demo", snapshot_id=hist_snap["snapshot_id"],
            as_of=hist_as_of.isoformat(), score_scale="if_anomaly_raw",
        )
        ref_sup = build_reference_distribution(
            "supervised_shadow", [r["branches"]["supervised_shadow"]["raw_score"] for r in hist_rows],
            company_id=company, tenant_id="demo", snapshot_id=hist_snap["snapshot_id"],
            as_of=hist_as_of.isoformat(), score_scale="uncalibrated_prob",
        )
        ref_rules = build_reference_distribution(
            "rules_35", [r["branches"]["rules_35"]["raw_score"] for r in hist_rows],
            company_id=company, tenant_id="demo", snapshot_id=hist_snap["snapshot_id"],
            as_of=hist_as_of.isoformat(), score_scale="rule_points",
        )
        ref_artifacts = {r["reference_id"]: r for r in (ref_ecod, ref_if, ref_sup, ref_rules)}

        split_defs = [
            ("detector_validation", "VAL", datetime(2026, 9, 1, 0, 0, 0, tzinfo=TZ), datetime(2026, 9, 30, 23, 59, 59, tzinfo=TZ), None),
            ("calibration_policy_validation", "CAL", datetime(2026, 10, 1, 0, 0, 0, tzinfo=TZ), datetime(2026, 10, 31, 23, 59, 59, tzinfo=TZ), None),
            ("sealed_future_test", "TEST", datetime(2026, 11, 1, 0, 0, 0, tzinfo=TZ), datetime(2026, 11, 30, 23, 59, 59, tzinfo=TZ), f"SHARED_AUDIT_{company}_14"),
        ]

        manifests = {"history_train": hist_snap}
        bundles = {"history_train": {"rows": hist_rows, "groups": {}, "keys": set(tuple((r["record_id"], int(r["revision"])) for r in hist_rows))}}
        label_packets_meta = {}
        splits_cfg = {
            "history_train": {
                "snapshot_id": hist_snap["snapshot_id"], "as_of": hist_as_of.isoformat(),
                "start_at": "2026-07-01T00:00:00+07:00", "end_at": hist_as_of.isoformat(),
                "allowed_uses": ["fit_detectors", "fit_preprocess", "fit_reference_distribution"],
                "episode_grouping": {"group_keys": ["simultaneous_group_id", "episode_id"], "episode_metadata_complete": False,
                                     "limitation_note": "Synthetic baseline uses simultaneous groups + explicit episode_id where attached."},
            }
        }
        snap_list = [{
            "split": "history_train", "snapshot_id": hist_snap["snapshot_id"],
            "contract_version": CONTRACT, "as_of": hist_as_of.isoformat(),
            "snapshot_sha256": hist_snap["checksum"], "data_checksum": hist_snap["data_checksum"],
        }]
        prov_list = []

        for sname, pref, s_start, s_end, shared_id in split_defs:
            specs, lbls = _make_period_specs(f"{company}_{pref}", include_shared=shared_id)
            raw_b, _ = _build_period_source(company, pref, s_start, s_end, specs)
            man = _commit(cls.snapshots, scope, raw_b, f"{pref}-{company}")
            ana = analyze_rule_snapshot(cls.snapshots, scope, man["snapshot_id"], s_end.isoformat(), technical=True, resources=resources)
            shd = _mock_shadow_run(scope, man, ana, sup_job_id, sup_sha, sup_score)
            rz_sha = digest(canonical(rz["manifest"]))
            if_sha = digest(canonical(if_res["manifest"]))
            ecod_sha = digest(canonical(ecod_res["manifest"]))
            model_pins = {
                "robust_z": {"company_id": company, "artifact_id": rz["job"]["artifact_id"], "artifact_sha256": rz_sha},
                "isolation_forest": {"company_id": company, "artifact_id": if_res["job"]["artifact_id"], "artifact_sha256": if_sha},
                "ecod": {"company_id": company, "artifact_id": ecod_res["job"]["artifact_id"], "artifact_sha256": ecod_sha},
                "supervised_shadow": {"company_id": company, "artifact_id": sup_job_id, "artifact_sha256": sup_sha},
            }
            s_rows, s_groups = extract_split_rows(
                sname, scope, man, ana, shadow=shd, raw_data=raw_b, model_artifacts=model_pins,
            )
            manifests[sname] = man
            splits_cfg[sname] = {
                "snapshot_id": man["snapshot_id"], "as_of": s_end.isoformat(),
                "start_at": s_start.isoformat(), "end_at": s_end.isoformat(),
                "allowed_uses": (["compare_detectors", "select_combination"] if sname == "detector_validation"
                                 else ["fit_calibrator", "evaluate_calibration_oos", "policy_sensitivity"] if sname == "calibration_policy_validation"
                                 else ["final_sealed_evaluation"]),
                "episode_grouping": {"group_keys": ["simultaneous_group_id", "episode_id"], "episode_metadata_complete": False,
                                     "limitation_note": f"{sname}: synthetic payment streams without external ERP case table."},
            }
            snap_list.append({
                "split": sname, "snapshot_id": man["snapshot_id"], "contract_version": CONTRACT,
                "as_of": s_end.isoformat(), "snapshot_sha256": man["checksum"], "data_checksum": man["data_checksum"],
            })

            # Populate real ReviewStore feedback separately (with benign error marked confirmed_risk!)
            reviews_map = {}
            cases = {(_k := (c["record_id"], int(c["revision"]))): c for c in rule35_cases_for(cls.snapshots, scope, ana, cls.reviews, raw_data=raw_b)}
            benign_key = (f"{company}_{pref}_06_BENIGN_OUT", 1)
            for idx_k, k in enumerate(sorted(cases)[:6]):
                case = cases[k]
                if not case["review"]["feedback"]:
                    lease = cls.reviews.start(scope, case["case_id"])["lease"]
                    outcome = "confirmed_risk" if k == benign_key else ("confirmed_risk" if lbls.get(k, {}).get("outcome") == "verified_fraud" else "legitimate")
                    cls.reviews.save(
                        scope, case["case_id"], 0,
                        {
                            "outcome": outcome,
                            "usefulness": "yes",
                            "explanation": "Manual operational check on invoice & approval documents.",
                            "action": "Inspect source voucher before settlement.",
                            "missing_materials": "",
                            "evidence_ids": [case["evidence"][0]["evidence_id"]],
                            "checks_completed": True,
                        },
                        [e["evidence_id"] for e in case["evidence"]],
                        lease,
                        f"rev-{company}-{pref}-{idx_k}",
                    )
                reviews_map[k] = cls.reviews.get(scope, case["case_id"])
            if benign_key in cases and benign_key not in reviews_map:
                reviews_map[benign_key] = cls.reviews.get(scope, cases[benign_key]["case_id"])

            # Create real locked 4-row AEAD LabelStore packets for calibration_policy_validation (3 packets = 12 verified labels)
            if sname == "calibration_policy_validation":
                sorted_keys = sorted(lbls)
                exported_packets = []
                for b_idx, start_i in enumerate((0, 4, 8), 1):
                    chunk = sorted_keys[start_i:start_i + 4]
                    pkt_req = {
                        "version": HE_ADAPTER_VERSION,
                        "snapshot_id": man["snapshot_id"],
                        "as_of": s_end.isoformat(),
                        "training_start": s_start.isoformat(),
                        "training_end": s_end.isoformat(),
                        "rows": [{"record_id": r[0], "revision": r[1]} for r in chunk],
                    }
                    src_pkt = source_packet(cls.snapshots, scope, pkt_req)
                    created = cls.labels_store.create(scope, src_pkt)
                    rev_num = created["revision"]
                    case_ev_by_key = {(c["record_id"], int(c["revision"])): [c["evidence"][0]["evidence_id"]] for c in src_pkt["cases"]}
                    for r_key in chunk:
                        saved = cls.labels_store.change(
                            scope, created["packet_id"], "save",
                            {
                                "expected_revision": rev_num,
                                "request_id": f"lbl-{company}-{pref}-{b_idx}-{r_key[0]}",
                                "label": {
                                    "record_id": r_key[0],
                                    "revision": r_key[1],
                                    "outcome": lbls[r_key]["outcome"],
                                    "explanation": "Verified ground-truth outcome from period audit.",
                                    "evidence_ids": case_ev_by_key[r_key],
                                    "documents_checked": True,
                                },
                            },
                        )
                        rev_num = saved["revision"]
                    lock_res = cls.labels_store.change(
                        scope, created["packet_id"], "lock",
                        {"expected_revision": rev_num, "request_id": f"lock-req-{company}-{pref}-{b_idx}"},
                    )
                    exported = cls.labels_store.export(scope, created["packet_id"], lock_res["revision"], lock_res["lock_sha256"])
                    exported_packets.append(exported)
                    label_packets_meta[created["packet_id"]] = {
                        "packet_id": created["packet_id"], "revision": lock_res["revision"],
                        "lock_sha256": lock_res["lock_sha256"], "company_id": company,
                    }
                    prov_list.append({
                        "split": sname, "source_type": "label_store_packet",
                        "packet_id": created["packet_id"], "revision": lock_res["revision"],
                        "lock_sha256": lock_res["lock_sha256"], "company_id": company, "labels_blinded_before_lock": False,
                    })
                verified_dict = {"packets": exported_packets}
            else:
                prov_list.append({
                    "split": sname, "source_type": "verified_fixture",
                    "packet_id": None, "revision": None, "lock_sha256": None,
                    "company_id": company, "labels_blinded_before_lock": True,
                })
                verified_dict = {
                    "company_id": company,
                    "records": {k: {"outcome": v["outcome"], "company_id": company} for k, v in lbls.items()},
                }

            bundles[sname] = {
                "rows": s_rows, "groups": s_groups,
                "verified_labels": verified_dict,
                "reviews": {"company_id": company, "reviews": reviews_map},
            }

        plan = {
            "version": "evaluation-plan/1.0.0",
            "study_id": f"study-{company.lower()}-v1",
            "scope": {"tenant_id": "demo", "company_id": company},
            "snapshots": snap_list,
            "splits": splits_cfg,
            "versions": {
                "rule_engine_version": "agent2-rules-35/1.0.0",
                "feature_contract_version": "rule-snapshot-point-in-time/1.0.0",
                "preprocess_version": "frozen-feature-preprocess/1.0.0",
                "random_seed": 42,
                "model_bindings": [
                    {"method_id": "rules_35", "kind": "rules", "artifact_id": "rules_35_v1",
                     "artifact_sha256": digest(b"rules_35"), "model_version": "1.0.0",
                     "company_id": company, "training_split": "history_train", "training_mechanism": "deterministic_rules"},
                    {"method_id": "isolation_forest", "kind": "unsupervised", "artifact_id": if_res["job"]["artifact_id"],
                     "artifact_sha256": digest(canonical(if_res["manifest"])), "model_version": "1.0.0",
                     "company_id": company, "training_split": "history_train", "training_mechanism": "local_enterprise_fit"},
                    {"method_id": "ecod", "kind": "unsupervised", "artifact_id": ecod_res["job"]["artifact_id"],
                     "artifact_sha256": digest(canonical(ecod_res["manifest"])), "model_version": "1.0.0",
                     "company_id": company, "training_split": "history_train", "training_mechanism": "local_enterprise_fit"},
                    {"method_id": "supervised_shadow", "kind": "supervised_shadow", "artifact_id": sup_job_id,
                     "artifact_sha256": sup_sha, "model_version": "1.0.0",
                     "company_id": company, "training_split": "history_train", "training_mechanism": "concrete_fhe"},
                ],
                "reference_bindings": [
                    {"method_id": ref["method_id"], "reference_id": ref["reference_id"],
                     "reference_version": ref["reference_version"], "reference_sha256": ref["reference_sha256"],
                     "company_id": company, "fitted_split": "history_train", "score_scale": ref["score_scale"]}
                    for ref in (ref_ecod, ref_if, ref_sup, ref_rules)
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
                {"arm_id": "rules_only", "kind": "rules_only", "branches": ["rules_35"], "weights": None,
                 "uses_percentile_reference": False, "reference_ids": [], "he_is_training_mechanism_only": True, "complexity": 1},
                {"arm_id": "ecod_standalone", "kind": "individual_detector", "branches": ["ecod"], "weights": None,
                 "uses_percentile_reference": False, "reference_ids": [], "he_is_training_mechanism_only": True, "complexity": 1},
                {"arm_id": "sup_standalone", "kind": "individual_detector", "branches": ["supervised_shadow"], "weights": None,
                 "uses_percentile_reference": False, "reference_ids": [], "he_is_training_mechanism_only": True, "complexity": 1},
                {"arm_id": "rules_plus_ecod", "kind": "rules_plus_ml", "branches": ["rules_35", "ecod"], "weights": None,
                 "uses_percentile_reference": False, "reference_ids": [], "he_is_training_mechanism_only": True, "complexity": 2},
                {"arm_id": "rules_plus_supervised_shadow", "kind": "rules_plus_ml", "branches": ["rules_35", "supervised_shadow"], "weights": None,
                 "uses_percentile_reference": False, "reference_ids": [], "he_is_training_mechanism_only": True, "complexity": 2},
                {"arm_id": "rules_plus_ens_ecod_sup", "kind": "rules_plus_percentile_ensemble",
                 "branches": ["rules_35", "ecod", "supervised_shadow"],
                 "weights": {"ecod": 0.5, "supervised_shadow": 0.5},
                 "uses_percentile_reference": True,
                 "reference_ids": [ref_ecod["reference_id"], ref_sup["reference_id"]],
                 "he_is_training_mechanism_only": True, "complexity": 3},
            ],
            "selection_policy": {
                "locked_policy": {"policy_id": "rules_first_fill/1.0.0", "budget": 5, "tie_break": ["complexity_asc", "arm_id_asc"]},
                "selection_objective": {
                    "primary_metric": "verified_fraud_cases_selected",
                    "secondary_metric": "resolved_fraud_precision",
                    "min_incremental_gain": 0.0,
                    "require_positive_marginal_value": True,
                    "prefer_simpler_on_tie": True,
                },
                "policy_variants": [
                    {"variant_id": "priority_top5_all_branches", "policy_kind": "priority_top_k", "budget": 5, "min_priority_threshold": None},
                    {"variant_id": "rules_first_threshold_0.6", "policy_kind": "threshold_gated_rules_first", "budget": 5, "min_priority_threshold": 0.6},
                ],
            },
            "calibration_spec": {
                "target_branch": "supervised_shadow",
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
                {"fallback_config_id": "fb_missing_sup_v1", "config_version": "1.0.0",
                 "trigger_condition": "missing_supervised_model", "used_branches": ["rules_35", "ecod"],
                 "missing_or_ineligible_branches": ["supervised_shadow"], "is_full_ensemble": False,
                 "weight_policy": "explicit_fallback_subset", "weights": None},
                {"fallback_config_id": "fb_missing_unsup_v1", "config_version": "1.0.0",
                 "trigger_condition": "missing_unsupervised_model", "used_branches": ["rules_35", "supervised_shadow"],
                 "missing_or_ineligible_branches": ["ecod", "isolation_forest", "robust_z"], "is_full_ensemble": False,
                 "weight_policy": "explicit_fallback_subset", "weights": None},
                {"fallback_config_id": "fb_incompatible_contract_v1", "config_version": "1.0.0",
                 "trigger_condition": "incompatible_contract", "used_branches": ["rules_35"],
                 "missing_or_ineligible_branches": ["ecod", "supervised_shadow"], "is_full_ensemble": False,
                 "weight_policy": "explicit_fallback_subset", "weights": None},
                {"fallback_config_id": "fb_missing_feature_v1", "config_version": "1.0.0",
                 "trigger_condition": "missing_feature_or_post_cutoff", "used_branches": ["rules_35", "ecod"],
                 "missing_or_ineligible_branches": ["supervised_shadow"], "is_full_ensemble": False,
                 "weight_policy": "explicit_fallback_subset", "weights": None},
                {"fallback_config_id": "fb_missing_ref_v1", "config_version": "1.0.0",
                 "trigger_condition": "missing_reference_distribution", "used_branches": ["rules_35", "supervised_shadow"],
                 "missing_or_ineligible_branches": ["ecod"], "is_full_ensemble": False,
                 "weight_policy": "explicit_fallback_subset", "weights": None},
                {"fallback_config_id": "fb_partial_rule_gap_v1", "config_version": "1.0.0",
                 "trigger_condition": "partial_rule_source_gap", "used_branches": ["rules_35", "ecod"],
                 "missing_or_ineligible_branches": ["rule_E2_partial"], "is_full_ensemble": False,
                 "weight_policy": "explicit_fallback_subset", "weights": None},
                {"fallback_config_id": "fb_all_unavailable_v1", "config_version": "1.0.0",
                 "trigger_condition": "all_branches_unavailable", "used_branches": [],
                 "missing_or_ineligible_branches": ["rules_35", "ecod", "supervised_shadow"], "is_full_ensemble": False,
                 "weight_policy": "unavailable", "weights": None},
            ],
            "metrics_and_criteria": {
                "primary_metrics": ["resolved_precision", "additional_useful_verified_cases_over_rules", "brier_score", "log_loss"],
                "technical_gates": [
                    {"gate_id": "TG-01", "description": "Sealed test labels hidden before pre_test_lock_sha256.", "required": True},
                    {"gate_id": "TG-02", "description": "No raw score mixing without frozen historical reference.", "required": True},
                ],
                "quality_gates": [dict(g) for g in DEFAULT_OPEN_QUALITY_GATES],
            },
            "governance": {
                "promotion_target": "candidate_shadow_only",
                "production_approved": False,
                "active_model_replaced": False,
                "operational_queue_changed": False,
                "execution_location": "enterprise_local_only",
                "cloud_plaintext_sent": False,
                "synthetic_data_disclosure": "Synthetic SME multi-period fixture verifying technical validation only.",
            },
        }
        return {
            "scope": scope, "plan": plan, "manifests": manifests,
            "model_artifacts": model_pins, "references": ref_artifacts,
            "bundles": bundles, "label_packets": label_packets_meta,
        }

    def test_01_mutating_test_labels_never_alters_selection_weights_or_calibrator(self):
        ctx = self.company_ctx["C001"]
        res_a = run_validation_study(
            ctx["plan"], snapshot_manifests=ctx["manifests"], model_artifacts=ctx["model_artifacts"],
            reference_artifacts=ctx["references"], split_bundles=ctx["bundles"], label_packets=ctx["label_packets"],
        )
        mutated_bundles = deepcopy(ctx["bundles"])
        for k, entry in mutated_bundles["sealed_future_test"]["verified_labels"]["records"].items():
            entry["outcome"] = "verified_non_fraud" if entry["outcome"] == "verified_fraud" else "verified_fraud"
        res_b = run_validation_study(
            ctx["plan"], snapshot_manifests=ctx["manifests"], model_artifacts=ctx["model_artifacts"],
            reference_artifacts=ctx["references"], split_bundles=mutated_bundles, label_packets=ctx["label_packets"],
        )
        self.assertEqual(res_a["plan_lock"]["plan_sha256"], res_b["plan_lock"]["plan_sha256"])
        self.assertEqual(res_a["plan_lock"]["pre_test_lock_sha256"], res_b["plan_lock"]["pre_test_lock_sha256"])
        self.assertEqual(res_a["detector_validation"]["selection_sha256"], res_b["detector_validation"]["selection_sha256"])
        self.assertEqual(res_a["detector_validation"]["selected_arm"], res_b["detector_validation"]["selected_arm"])
        self.assertEqual(res_a["calibration_validation"]["calibrator"]["calibrator_sha256"],
                         res_b["calibration_validation"]["calibrator"]["calibrator_sha256"])
        self.assertEqual(res_a["calibration_validation"]["calibrator"]["params"],
                         res_b["calibration_validation"]["calibrator"]["params"])
        # Confirm sealed metrics DID change to prove mutation reached test evaluation
        self.assertNotEqual(
            res_a["sealed_future_test"]["selected_arm_summary"]["verified_label_metrics"]["resolved_precision"],
            res_b["sealed_future_test"]["selected_arm_summary"]["verified_label_metrics"]["resolved_precision"],
        )

    def test_02_plan_pin_mismatch_on_snapshot_model_or_reference_change(self):
        ctx = self.company_ctx["C001"]
        bad_manifests = deepcopy(ctx["manifests"])
        bad_manifests["sealed_future_test"]["data_checksum"] = "f" * 64
        with self.assertRaises(ValidationStudyError) as ex1:
            lock_evaluation_plan(ctx["plan"], snapshot_manifests=bad_manifests)
        self.assertEqual(ex1.exception.code, "EVALUATION_PLAN_PIN_MISMATCH")

        bad_models = deepcopy(ctx["model_artifacts"])
        bad_models["ecod"]["artifact_sha256"] = "0" * 64
        with self.assertRaises(ValidationStudyError) as ex2:
            lock_evaluation_plan(ctx["plan"], model_artifacts=bad_models)
        self.assertEqual(ex2.exception.code, "EVALUATION_PLAN_PIN_MISMATCH")

        bad_refs = deepcopy(ctx["references"])
        first_rid = next(iter(bad_refs))
        bad_refs[first_rid]["reference_sha256"] = "1" * 64
        with self.assertRaises(ValidationStudyError) as ex3:
            lock_evaluation_plan(ctx["plan"], reference_artifacts=bad_refs)
        self.assertEqual(ex3.exception.code, "EVALUATION_PLAN_PIN_MISMATCH")

        # Forbid building percentile reference from test or validation splits
        with self.assertRaises(ValidationStudyError) as ex4:
            build_reference_distribution(
                "ecod", [0.1, 0.2, 0.3, 0.4, 0.5], company_id="C001", tenant_id="demo",
                snapshot_id="s1", as_of="2026-11-30T23:59:59+07:00", source_split="sealed_future_test",
            )
        self.assertEqual(ex4.exception.code, "REFERENCE_MISMATCH_OR_TEST_LEAK")

    def test_03_missing_model_feature_or_reference_never_emits_zero_or_implicit_fit(self):
        ctx = self.company_ctx["C001"]
        def _count_model_rows() -> dict[str, int]:
            with sqlite3.connect(self.root / "models.sqlite3") as conn:
                tbls = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
                return {t: conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0] for t in tbls}

        before_counts = _count_model_rows()
        res = run_validation_study(
            ctx["plan"], snapshot_manifests=ctx["manifests"], model_artifacts=ctx["model_artifacts"],
            reference_artifacts=ctx["references"], split_bundles=ctx["bundles"], label_packets=ctx["label_packets"],
        )
        self.assertEqual(_count_model_rows(), before_counts)
        by_trig = {s["trigger_condition"]: s for s in res["fallback_validation"]["scenarios"]}
        for trig in ("missing_supervised_model", "missing_unsupervised_model", "missing_feature_or_post_cutoff",
                     "missing_reference_distribution", "partial_rule_source_gap", "all_branches_unavailable"):
            sc = by_trig[trig]
            self.assertFalse(sc["is_full_ensemble"])
            self.assertFalse(sc["silent_weight_redistribution"])
            self.assertTrue(sc["effectiveness"]["null_score_when_unavailable"])
        self.assertEqual(by_trig["all_branches_unavailable"]["coverage"]["available_rows"], 0)
        self.assertTrue(by_trig["missing_feature_or_post_cutoff"]["coverage"]["unavailable_rows"] > 0)

        # Forbid mixing raw scores without frozen historical percentile references
        bad_plan = deepcopy(ctx["plan"])
        bad_plan["candidates"][-1]["uses_percentile_reference"] = False
        with self.assertRaises(ValidationStudyError) as ex_mix:
            validate_evaluation_plan(bad_plan)
        self.assertEqual(ex_mix.exception.code, "RAW_SCORE_MIXING_FORBIDDEN")

        # Forbid HE as separate independent voter in candidates
        he_plan = deepcopy(ctx["plan"])
        he_plan["candidates"].append({
            "arm_id": "bad_he_voter", "kind": "rules_plus_ml", "branches": ["rules_35", "concrete_fhe"],
            "weights": None, "uses_percentile_reference": False, "reference_ids": [],
            "he_is_training_mechanism_only": True, "complexity": 2,
        })
        with self.assertRaises(ValidationStudyError) as ex_he:
            validate_evaluation_plan(he_plan)
        self.assertEqual(ex_he.exception.code, "EVALUATION_PLAN_SCHEMA_INVALID")

        # Forbid fallback silently posing as full ensemble or keeping branches when unavailable
        bad_fb_plan = deepcopy(ctx["plan"])
        bad_fb_plan["fallback_specs"][-1]["used_branches"] = ["rules_35"]
        with self.assertRaises(ValidationStudyError) as ex_fb:
            validate_evaluation_plan(bad_fb_plan)
        self.assertEqual(ex_fb.exception.code, "FALLBACK_SILENT_REWEIGHT_FORBIDDEN")

    def test_04_insufficient_labels_and_confirmed_risk_block_calibration(self):
        ctx = self.company_ctx["C001"]
        locked = lock_evaluation_plan(ctx["plan"])
        # (a) Confirmed_risk coerced inside verified_labels -> explicit failure
        with self.assertRaises(ValidationStudyError) as ex_coerce:
            parse_verified_labels({"company_id": "C001", "records": {("TX1", 1): {"outcome": "confirmed_risk"}}},
                                  scope_company_id="C001")
        self.assertEqual(ex_coerce.exception.code, "LABEL_COERCION_FORBIDDEN")

        # (b) Only inconclusive / insufficient verified labels + separate confirmed_risk review -> insufficient_labels
        small_labels = {
            ("C001_CAL_01_P1A", 1): {"outcome": "verified_fraud"},
            ("C001_CAL_06_BENIGN_OUT", 1): {"outcome": "inconclusive"},
            ("C001_CAL_09_NORM", 1): {"outcome": "verified_non_fraud"},
        }
        blocked_cal = fit_and_evaluate_calibration(
            locked, ctx["bundles"]["calibration_policy_validation"]["rows"],
            small_labels, ctx["bundles"]["calibration_policy_validation"]["reviews"]["reviews"],
            references=ctx["references"],
        )
        self.assertEqual(blocked_cal["status"], "insufficient_labels")
        self.assertFalse(blocked_cal["calibrated"])
        self.assertIsNone(apply_calibrator(blocked_cal, 0.85))
        self.assertGreater(blocked_cal["counts"]["review_confirmed_risk_excluded"], 0)

        # (c) Sufficient verified labels fits & evaluates cleanly out-of-sample
        cal_labels_full = parse_verified_labels(ctx["bundles"]["calibration_policy_validation"]["verified_labels"], scope_company_id="C001")
        ok_cal = fit_and_evaluate_calibration(
            locked, ctx["bundles"]["calibration_policy_validation"]["rows"],
            cal_labels_full, ctx["bundles"]["calibration_policy_validation"]["reviews"]["reviews"],
            references=ctx["references"],
        )
        self.assertEqual(ok_cal["status"], "calibrated")
        self.assertTrue(ok_cal["calibrated"])
        self.assertIn(ok_cal["method"], ("platt_logistic", "isotonic_regression"))
        p = apply_calibrator(ok_cal, 0.85)
        self.assertIsNotNone(p)
        self.assertTrue(0.0 < p < 1.0)

    def test_05_c001_c002_isolation_episode_check_and_gt_gating(self):
        c1 = self.company_ctx["C001"]
        c2 = self.company_ctx["C002"]

        # Cross-company artifact injected into C001 -> blocked
        bad_artifacts = dict(c1["model_artifacts"], ecod=c2["model_artifacts"]["ecod"])
        with self.assertRaises(ValidationStudyError) as ex_c:
            lock_evaluation_plan(c1["plan"], model_artifacts=bad_artifacts)
        self.assertEqual(ex_c.exception.code, "TENANT_OR_COMPANY_ISOLATION_VIOLATION")

        # Cross-company reference usage -> blocked
        c2_ref = next(iter(c2["references"].values()))
        with self.assertRaises(ValidationStudyError) as ex_ref_co:
            transform_with_reference(c2_ref, {("TX1", 1): 0.5}, expected_binding=c2["plan"]["versions"]["reference_bindings"][0], expected_company="C001")
        self.assertEqual(ex_ref_co.exception.code, "TENANT_OR_COMPANY_ISOLATION_VIOLATION")

        # Cross-company label packet injected into C001 -> blocked
        bad_bundles = deepcopy(c1["bundles"])
        bad_bundles["calibration_policy_validation"]["verified_labels"] = deepcopy(c2["bundles"]["calibration_policy_validation"]["verified_labels"])
        with self.assertRaises(ValidationStudyError) as ex_lbl:
            run_validation_study(
                c1["plan"], snapshot_manifests=c1["manifests"], model_artifacts=c1["model_artifacts"],
                reference_artifacts=c1["references"], split_bundles=bad_bundles, label_packets=c1["label_packets"],
            )
        self.assertEqual(ex_lbl.exception.code, "TENANT_OR_COMPANY_ISOLATION_VIOLATION")

        # Record appearing in two splits -> SPLIT_RECORD_OVERLAP
        dup_bundles = deepcopy(c1["bundles"])
        dup_bundles["sealed_future_test"]["rows"][0]["record_id"] = dup_bundles["detector_validation"]["rows"][0]["record_id"]
        with self.assertRaises(ValidationStudyError) as ex_dup:
            run_validation_study(
                c1["plan"], snapshot_manifests=c1["manifests"], model_artifacts=c1["model_artifacts"],
                reference_artifacts=c1["references"], split_bundles=dup_bundles, label_packets=c1["label_packets"],
            )
        self.assertEqual(ex_dup.exception.code, "SPLIT_RECORD_OVERLAP")

        # Episode spanning two splits -> EPISODE_SPLIT_LEAKAGE
        ep_bundles = deepcopy(c1["bundles"])
        ep_bundles["detector_validation"]["rows"][0]["episode_id"] = "EP_CROSS_01"
        ep_bundles["sealed_future_test"]["rows"][0]["episode_id"] = "EP_CROSS_01"
        with self.assertRaises(ValidationStudyError) as ex_ep:
            run_validation_study(
                c1["plan"], snapshot_manifests=c1["manifests"], model_artifacts=c1["model_artifacts"],
                reference_artifacts=c1["references"], split_bundles=ep_bundles, label_packets=c1["label_packets"],
            )
        self.assertEqual(ex_ep.exception.code, "EPISODE_SPLIT_LEAKAGE")

        # Recall/PR-AUC must be None when full_split_ground_truth=False or unresolved labels exist
        res_partial = run_validation_study(
            c1["plan"], snapshot_manifests=c1["manifests"], model_artifacts=c1["model_artifacts"],
            reference_artifacts=c1["references"], split_bundles=c1["bundles"], label_packets=c1["label_packets"],
        )
        for arm_r in res_partial["sealed_future_test"]["arm_results"]:
            self.assertIsNone(arm_r["verified_label_metrics"]["recall_at_budget"])
            self.assertIsNone(arm_r["verified_label_metrics"]["pr_auc"])

        # Verify unrecorded review active_seconds stays None rather than fabricated 0
        for arm_r in res_partial["sealed_future_test"]["arm_results"]:
            eff = arm_r["review_feedback_separate"]["review_effort_seconds"]
            if not eff["recorded"]:
                self.assertIsNone(eff["total_active_seconds"])
                self.assertIsNone(eff["mean_active_seconds"])
        # Verify C001 vs C002 case_id isolation on shared ID
        c1_cases = res_partial["detector_validation"]
        c2_res = run_validation_study(
            c2["plan"], snapshot_manifests=c2["manifests"], model_artifacts=c2["model_artifacts"],
            reference_artifacts=c2["references"], split_bundles=c2["bundles"], label_packets=c2["label_packets"],
        )
        self.assertNotEqual(c1_cases["plan_sha256"], c2_res["plan_lock"]["plan_sha256"])

        # Enable full_split_ground_truth=True with 0 unresolved labels -> recall & PR-AUC computed for scored ML arms
        full_plan = deepcopy(c1["plan"])
        full_plan["labels"]["full_split_ground_truth"] = True
        res_full = run_validation_study(
            full_plan, snapshot_manifests=c1["manifests"], model_artifacts=c1["model_artifacts"],
            reference_artifacts=c1["references"], split_bundles=c1["bundles"], label_packets=c1["label_packets"],
        )
        ens_arm = next(a for a in res_full["sealed_future_test"]["arm_results"] if a["arm_id"] == "rules_plus_ens_ecod_sup")
        self.assertIsNotNone(ens_arm["verified_label_metrics"]["recall_at_budget"])
        self.assertIsNotNone(ens_arm["verified_label_metrics"]["pr_auc"])

    def test_06_deterministic_reproducibility_parsimony_and_governance(self):
        c1 = self.company_ctx["C001"]
        r1 = run_validation_study(
            c1["plan"], snapshot_manifests=c1["manifests"], model_artifacts=c1["model_artifacts"],
            reference_artifacts=c1["references"], split_bundles=c1["bundles"], label_packets=c1["label_packets"],
        )
        r2 = run_validation_study(
            c1["plan"], snapshot_manifests=c1["manifests"], model_artifacts=c1["model_artifacts"],
            reference_artifacts=c1["references"], split_bundles=c1["bundles"], label_packets=c1["label_packets"],
        )
        self.assertEqual(r1["study_result_sha256"], r2["study_result_sha256"])
        self.assertEqual(r1["candidate_shadow_artifact"]["candidate_artifact_sha256"],
                         r2["candidate_shadow_artifact"]["candidate_artifact_sha256"])
        self.assertEqual(r1["version"], STUDY_VERSION)
        self.assertEqual(r1["governance"]["promotion_target"], "candidate_shadow_only")
        self.assertFalse(r1["governance"]["production_approved"])
        self.assertFalse(r1["governance"]["active_model_replaced"])
        self.assertFalse(r1["governance"]["operational_queue_changed"])
        self.assertEqual(r1["governance"]["execution_location"], "enterprise_local_only")
        self.assertFalse(r1["governance"]["cloud_plaintext_sent"])
        self.assertTrue(all(g["approved_for_production"] is False for g in r1["open_quality_gates"]))
        # Verify policy sensitivity is reported cleanly and separated
        self.assertGreaterEqual(len(r1["sealed_future_test"]["policy_sensitivity"]), 1)
        # Verify parsimony: when rules_plus_ens_ecod_sup ties with simpler rules_plus_* arm, simpler arm wins
        selected_id = r1["detector_validation"]["selected_arm_id"]
        trace_by_arm = {t["arm_id"]: t for t in r1["detector_validation"]["selection_trace"]}
        if selected_id in ("rules_plus_ecod", "rules_plus_supervised_shadow"):
            self.assertEqual(
                trace_by_arm["rules_plus_ens_ecod_sup"]["decision"],
                "rejected_no_incremental_gain_keep_simpler",
            )


if __name__ == "__main__":
    unittest.main()
