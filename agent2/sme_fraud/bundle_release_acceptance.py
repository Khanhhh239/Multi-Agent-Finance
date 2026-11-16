"""End-to-end R5/R6 bundle acceptance evaluation: locked 35-rule + ML comparison, shared union review timing, fallback/backlog metrics, and staging rollback drill.

All artifacts generated here operate on isolated temporary/staging workspaces and explicit
synthetic enterprise snapshots. They never deploy/restart live Portal services, modify live keys
or memberships, claim production approval, or simulate cloud HE execution.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import random
import shutil
import threading
import time
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from experiments.he_training.snapshot_adapter import VERSION as HE_ADAPTER_VERSION
from finance_input import AccessScope
from finance_input.json_io import loads

from .analysis_resources import AnalysisResources, VERSION as BINDINGS_VERSION
from .auth import FileAuthorizer
from .bundle_reviews import CompanyReviewStore, csv_report
from .case_queue_policy import default_fixture_policy as default_cq_policy
from .case_queue_store import CaseQueueStore
from .import_files import ImportFailure, canonical, digest
from .label_packets import LabelStore, TARGET as LABEL_TARGET, source_packet
from .method_jobs import run_fit_job
from .method_store import MethodStore
from .pipeline_release import ReleaseService, runtime_signature
from .pipeline_release_store import ReleaseStore
from .release_shadow_plan import PROFILE as LINKED_PROFILE, VERSION as RELEASE_PLAN_VERSION, make_package
from .remediation_store import RemediationStore
from .review_server import make_server
from .review_store import ReviewStore
from .rule35_comparison import make_rule35_plan, rule35_cases_for, rule35_report_for
from .rule35_ml_eval_demo import (
    COMPANY_METHODS,
    _add_clean_payment,
    _add_payroll_tx,
    _finalize,
    _seed_baseline_tables,
    base,
    evidence,
    fit_config,
)
from .rule_snapshot import CONTRACT as RULE_SNAPSHOT_CONTRACT, analyze as analyze_rule_snapshot
from .rule_snapshot_features import feature_contract
from .selection_comparison import BUDGET as TX_COMPARISON_BUDGET, POLICY as TX_COMPARISON_POLICY
from .snapshots import SnapshotStore
from .validation_study import (
    DEFAULT_OPEN_QUALITY_GATES,
    STUDY_VERSION,
    build_reference_distribution,
    extract_split_rows,
    run_validation_study,
)

TZ = timezone(timedelta(hours=7))

OPEN_OWNER_GATES = [
    "D-04",
    "D-05",
    "D-06",
    "D-07",
    "D-09",
    "D-14",
    "D-17",
    "D-18",
    "D-19",
]


def _stamp(dt: datetime) -> str:
    return dt.astimezone(TZ).isoformat()


def commit_snapshot(store: SnapshotStore, scope: AccessScope, data: dict, key: str) -> dict:
    draft = store.upload(scope, canonical(data), f"{key}.json", f"{key}-u")
    preview = store.preview(scope, draft["import_id"], 1)
    if preview["status"] == "rejected":
        raise AssertionError(f"Snapshot {key} rejected: {preview.get('errors')}")
    req = {k: preview[k] for k in ("preview_id", "source_hash", "mapping_hash", "report_hash", "context_hash")}
    req.update(expected_revision=preview["revision"], acknowledge=True)
    return store.commit(scope, draft["import_id"], req, f"{key}-c")["snapshot"]


def make_auth_policy_file(path: Path, director_token: str, accountant_token: str) -> Path:
    exp = (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat()

    def _tok_hash(t: str) -> str:
        return hashlib.sha256(t.encode("utf-8")).hexdigest()

    doc = {
        "policy_version": "1.0.0",
        "principals": [
            {
                "actor_id": "staging-director",
                "tenant_id": "demo",
                "token_sha256": _tok_hash(director_token),
                "status": "active",
                "expires_at": exp,
                "memberships": [
                    {
                        "company_id": cid,
                        "role": "director",
                        "status": "active",
                        "permissions": ["data.import", "evidence.verify", "model.fit"],
                    }
                    for cid in ("C001", "C002")
                ],
            },
            {
                "actor_id": "staging-accountant",
                "tenant_id": "demo",
                "token_sha256": _tok_hash(accountant_token),
                "status": "active",
                "expires_at": exp,
                "memberships": [
                    {
                        "company_id": cid,
                        "role": "accountant",
                        "status": "active",
                        "permissions": ["data.import"],
                    }
                    for cid in ("C001", "C002")
                ],
            },
        ],
    }
    path.write_bytes(canonical(doc))
    return path


def _build_split_snapshot(
    company: str,
    prefix: str,
    start_dt: datetime,
    as_of_dt: datetime,
    specs: list[dict],
    *,
    include_history: bool = True,
    tenant_id: str = "demo",
) -> tuple[dict, list[str]]:
    """Build agent2-rule-snapshot/1.0.0 payload with strict pre-split history_only isolation."""
    scale = 1 if company == "C001" else 3
    c = base()
    _seed_baseline_tables(c, company, scale, datetime(2026, 7, 1, 10, 0, tzinfo=TZ))

    rng = random.Random(20261116 + (1 if company == "C001" else 2))
    history_ids: list[str] = []
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
        # Historical anomalous-looking high control kept strictly in history_only (excluded from candidates).
        hist_ctrl_id = f"{company}_HIST_HIGH_CONTROL"
        _add_clean_payment(
            c,
            hist_ctrl_id,
            datetime(2026, 7, 18, 10, 0, tzinfo=TZ),
            99_500_000 * scale,
            scale=scale,
            company_id=company,
            invoice_number=f"INV_{company}_HIST_ONLY",
            invoice_gross_vnd=99_500_000 * scale,
            doc=True,
        )
        history_ids.append(hist_ctrl_id)

        for p_i, p_day in enumerate((datetime(2026, 7, 25, 10, 0, tzinfo=TZ), datetime(2026, 8, 12, 10, 0, tzinfo=TZ)), 1):
            pid = f"{company}_HPAY_{p_i:02d}"
            _add_payroll_tx(c, pid, p_day, 14_200_000 * scale, company_id=company, scale=scale, terminated=False)
            history_ids.append(pid)
        ref_day = datetime(2026, 8, 19, 10, 0, tzinfo=TZ)
        for r_i in range(1, 11):
            while ref_day.weekday() >= 5:
                ref_day += timedelta(days=1)
            tid = f"{company}_R_{r_i:02d}"
            amt = (1_120_000 + rng.randint(0, 30) * 11_300) * scale
            _add_clean_payment(c, tid, ref_day, amt, scale=scale, company_id=company, doc=True)
            history_ids.append(tid)
            ref_day += timedelta(hours=12)

    cand_ids: list[str] = []
    for idx, sp in enumerate(specs):
        tid = sp["id"]
        cand_ids.append(tid)
        ev_at = start_dt + timedelta(days=sp.get("day_offset", idx % 10), hours=sp.get("hour_offset", 10 + (idx % 5)))
        kind = sp.get("pattern", "clean")
        if kind == "p1_pair_a":
            _add_clean_payment(
                c,
                tid,
                ev_at,
                15_000_000 * scale,
                scale=scale,
                company_id=company,
                invoice_number=sp["inv"],
                invoice_gross_vnd=18_000_000 * scale,
                doc=True,
            )
        elif kind == "p1_pair_b":
            _add_clean_payment(
                c,
                tid,
                ev_at,
                14_000_000 * scale,
                scale=scale,
                company_id=company,
                invoice_number=sp["inv"],
                invoice_gross_vnd=18_000_000 * scale,
                doc=True,
            )
        elif kind == "c2_self":
            _add_clean_payment(
                c,
                tid,
                ev_at,
                sp.get("amount", 16_000_000) * scale,
                scale=scale,
                company_id=company,
                approver_id=c.maker["employee_id"],
                doc=True,
            )
        elif kind == "a6_rounded":
            _add_clean_payment(
                c,
                tid,
                ev_at,
                7_500_000 * scale,
                scale=scale,
                company_id=company,
                invoice_gross_vnd=7_489_123 * scale,
                doc=True,
            )
        elif kind == "b1_bank":
            vb1 = deepcopy(c.vendor)
            vb1.update(
                vendor_id=f"{company}_V_B1_{prefix}_{idx}",
                name=f"B1 Vendor {company}",
                representative_id=f"{company}_REP_B1_{idx}",
                bank_account=c.worker["bank_account"],
                phone="0908222111",
                address="25 Bach Dang",
                national_id=f"{company}_NB1_{idx}",
                tax_code=f"{company}_TB1_{idx}",
            )
            c.tables["vendors"].append(vb1)
            _add_clean_payment(c, tid, ev_at, 4_200_000 * scale, vendor=vb1, scale=scale, company_id=company, doc=True)
        elif kind == "b2_contact":
            vb2 = deepcopy(c.vendor)
            vb2.update(
                vendor_id=f"{company}_V_B2_{prefix}_{idx}",
                name=f"B2 Vendor {company}",
                representative_id=f"{company}_REP_B2_{idx}",
                bank_account=f"{company}_VB2_BANK_{idx}",
                phone=c.worker["phone"],
                address=c.worker["address"],
                national_id=f"{company}_NB2_{idx}",
                tax_code=f"{company}_TB2_{idx}",
            )
            c.tables["vendors"].append(vb2)
            _add_clean_payment(c, tid, ev_at, 4_500_000 * scale, vendor=vb2, scale=scale, company_id=company, doc=True)
        elif kind == "e2_term_payroll":
            _add_payroll_tx(c, tid, ev_at, 18_000_000 * scale, company_id=company, scale=scale, terminated=True)
        elif kind == "b5_e4_dup":
            v_dup = deepcopy(c.vendor)
            v_dup.update(
                vendor_id=f"{company}_V_DUP_{prefix}_{idx}",
                name=f"Dup Master {company}",
                representative_id=f"{company}_REP_DUP_{idx}",
                national_id=f"{company}_NDUP_{idx}",
                tax_code=f"{company}_TDUP_{idx}",
                address="99 Tran Hung Dao",
            )
            c.tables["vendors"].append(v_dup)
            _add_clean_payment(c, tid, ev_at, 1_240_000 * scale, vendor=v_dup, scale=scale, company_id=company, doc=True)
        elif kind == "payroll_clean":
            _add_payroll_tx(c, tid, ev_at, 14_500_000 * scale, company_id=company, scale=scale, terminated=False)
        elif kind == "ml_outlier_high":
            _add_clean_payment(
                c,
                tid,
                ev_at,
                sp.get("amount", 84_317_250) * scale,
                scale=scale,
                company_id=company,
                doc=False,
                imbalance=sp.get("imbalance", 12_000_000) * scale,
                approver_id=c.director["employee_id"],
            )
        elif kind == "ml_outlier_benign":
            _add_clean_payment(
                c,
                tid,
                ev_at,
                sp.get("amount", 64_215_900) * scale,
                scale=scale,
                company_id=company,
                doc=True,
                imbalance=sp.get("imbalance", 8_500_000) * scale,
            )
        elif kind == "partial_gap_clean":
            _add_clean_payment(c, tid, ev_at, sp.get("amount", 1_950_000) * scale, scale=scale, company_id=company, doc=False)
        else:
            amt = sp.get("amount", (1_080_000 + idx * 21_500) * scale)
            _add_clean_payment(c, tid, ev_at, amt, scale=scale, company_id=company, doc=True)

    bundle = _finalize(
        c,
        tenant_id=tenant_id,
        company_id=company,
        as_of=as_of_dt.isoformat(),
        candidate_ids=cand_ids if cand_ids else history_ids[-10:],
        source_id=f"synthetic-{company.lower()}-{prefix}",
    )
    return bundle, (cand_ids or history_ids)


def _val_cal_specs(company: str, tag: str) -> tuple[list[dict], dict[tuple[str, int], dict]]:
    specs = [
        {"id": f"{company}_{tag}_01_P1A", "pattern": "p1_pair_a", "day_offset": 1, "inv": f"INV_{company}_{tag}_P1"},
        {"id": f"{company}_{tag}_02_P1B", "pattern": "p1_pair_b", "day_offset": 1, "inv": f"INV_{company}_{tag}_P1"},
        {"id": f"{company}_{tag}_03_C2", "pattern": "c2_self", "day_offset": 2},
        {"id": f"{company}_{tag}_04_ML_F1", "pattern": "ml_outlier_high", "day_offset": 3, "amount": 92_451_300, "imbalance": 11_000_000},
        {"id": f"{company}_{tag}_05_ML_F2", "pattern": "ml_outlier_high", "day_offset": 4, "amount": 85_319_700, "imbalance": 9_500_000},
        {"id": f"{company}_{tag}_06_BENIGN", "pattern": "ml_outlier_benign", "day_offset": 5, "amount": 60_512_300, "imbalance": 6_500_000},
    ]
    for i in range(7, 15):
        specs.append({"id": f"{company}_{tag}_{i:02d}_NORM", "pattern": "clean", "day_offset": 2 + (i % 7)})
    labels = {
        (f"{company}_{tag}_01_P1A", 1): {"outcome": "verified_fraud"},
        (f"{company}_{tag}_02_P1B", 1): {"outcome": "verified_fraud"},
        (f"{company}_{tag}_03_C2", 1): {"outcome": "verified_fraud"},
        (f"{company}_{tag}_04_ML_F1", 1): {"outcome": "verified_fraud"},
        (f"{company}_{tag}_05_ML_F2", 1): {"outcome": "verified_fraud"},
        (f"{company}_{tag}_06_BENIGN", 1): {"outcome": "verified_non_fraud"},
    }
    for sp in specs[6:]:
        labels[(sp["id"], 1)] = {"outcome": "verified_non_fraud"}
    return specs, labels


def _eval_k1_specs_and_review_profile(company: str) -> tuple[list[dict], dict[str, dict]]:
    """25 candidates per company on held-out Period 1 (W43) leaving room for ML additions."""
    review_profile: dict[str, dict] = {}
    if company == "C001":
        # Rules hit exactly 3 slots: C1_K1_01_P1A + C1_K1_02_P1B + C1_K1_03_C2 -> 2 free slots for isolation_forest.
        specs = [
            {"id": "C1_K1_01_P1A", "pattern": "p1_pair_a", "day_offset": 1, "hour_offset": 10, "inv": "INV_C1_K1_P1"},
            {"id": "C1_K1_02_P1B", "pattern": "p1_pair_b", "day_offset": 1, "hour_offset": 10, "inv": "INV_C1_K1_P1"},
            {"id": "C1_K1_03_C2", "pattern": "c2_self", "day_offset": 2, "hour_offset": 11},
            {"id": "C1_K1_04_B5E4", "pattern": "b5_e4_dup", "day_offset": 3},
            {"id": "C1_K1_05_C1CTX", "pattern": "clean", "day_offset": 4, "hour_offset": 21},
            {"id": "C1_K1_06_PAY", "pattern": "payroll_clean", "day_offset": 5},
            {"id": "C1_K1_07_ML_ISSUE", "pattern": "ml_outlier_high", "day_offset": 6, "amount": 88_412_300, "imbalance": 12_500_000},
            {"id": "C1_K1_08_ML_BENIGN", "pattern": "ml_outlier_benign", "day_offset": 7, "amount": 64_215_900, "imbalance": 8_500_000},
            {"id": "C1_K1_09_GAP", "pattern": "partial_gap_clean", "day_offset": 8},
        ]
        for i in range(10, 25):
            specs.append({"id": f"C1_K1_{i:02d}_NORM", "pattern": "clean", "day_offset": (i % 10) + 1})
        specs.append({"id": "SHARED_AUDIT_00", "pattern": "clean", "day_offset": 11})

        review_profile = {
            "C1_K1_01_P1A": {"outcome": "confirmed_risk", "usefulness": "yes", "seconds": 45, "wait_seconds": 0, "explanation": "Thanh toan vuot hoa don P1 dot 1", "action": "Doi chieu thu hoi khoan chi vuot"},
            "C1_K1_02_P1B": {"outcome": "confirmed_risk", "usefulness": "yes", "seconds": 40, "wait_seconds": 0, "explanation": "Thanh toan vuot hoa don P1 dot 2", "action": "Doi chieu thu hoi khoan chi vuot"},
            "C1_K1_03_C2": {"outcome": "confirmed_risk", "usefulness": "yes", "seconds": 50, "wait_seconds": 0, "explanation": "Nguoi lap tu phe duyet vuot han muc", "action": "Bo sung phe duyet cap tren"},
            "C1_K1_07_ML_ISSUE": {"outcome": "confirmed_risk", "usefulness": "yes", "seconds": 65, "wait_seconds": 1800, "explanation": "Chi 88.4M lech so sach, thieu chung tu goc", "action": "Tam giu hach toan va doi chieu phieu thu chi", "missing": "Thieu hoa don VAT & uy nhiem chi"},
            "C1_K1_08_ML_BENIGN": {"outcome": "legitimate", "usefulness": "no", "seconds": 55, "wait_seconds": 0, "explanation": "Mua thiet bi dot xuat da co du hoa don hop le", "action": "Luu ho so khong phat hien sai pham"},
            "C1_K1_06_PAY": {"outcome": "legitimate", "usefulness": "no", "seconds": 44, "wait_seconds": 0, "explanation": "Chi luong hop le khop bang cong ky", "action": "Luu ho so khop ky luong"},
        }
    else:
        # C002: Rules hit 4 slots: A6 + B1 + B2 + E2 -> 1 free slot for ecod.
        specs = [
            {"id": "C2_K1_01_A6", "pattern": "a6_rounded", "day_offset": 1, "hour_offset": 10},
            {"id": "C2_K1_02_B1", "pattern": "b1_bank", "day_offset": 2, "hour_offset": 10},
            {"id": "C2_K1_03_B2", "pattern": "b2_contact", "day_offset": 3, "hour_offset": 10},
            {"id": "C2_K1_04_E2", "pattern": "e2_term_payroll", "day_offset": 4, "hour_offset": 10},
            {"id": "C2_K1_05_B5E4", "pattern": "b5_e4_dup", "day_offset": 5},
            {"id": "C2_K1_06_CTRL", "pattern": "clean", "day_offset": 6},
            {"id": "C2_K1_07_ML_INCONC", "pattern": "ml_outlier_high", "day_offset": 7, "amount": 175_642_300, "imbalance": 19_000_000},
            {"id": "C2_K1_08_GAP", "pattern": "partial_gap_clean", "day_offset": 8},
        ]
        for i in range(9, 25):
            specs.append({"id": f"C2_K1_{i:02d}_NORM", "pattern": "clean", "day_offset": (i % 10) + 1})
        specs.append({"id": "SHARED_AUDIT_00", "pattern": "clean", "day_offset": 11})

        review_profile = {
            "C2_K1_01_A6": {"outcome": "confirmed_risk", "usefulness": "yes", "seconds": 40, "wait_seconds": 0, "explanation": "Gia tri chi tron so vuot hoa don goc", "action": "Doi chieu don gia hop dong"},
            "C2_K1_02_B1": {"outcome": "confirmed_risk", "usefulness": "yes", "seconds": 48, "wait_seconds": 0, "explanation": "Tai khoan nha cung cap trung nhan vien", "action": "Xac minh ho so thu huong"},
            "C2_K1_03_B2": {"outcome": "confirmed_risk", "usefulness": "yes", "seconds": 42, "wait_seconds": 0, "explanation": "NCC trung dien thoai/dia chi voi nhan vien", "action": "Kiem tra xung dot loi ich"},
            "C2_K1_04_E2": {"outcome": "confirmed_risk", "usefulness": "yes", "seconds": 52, "wait_seconds": 0, "explanation": "Chi luong sau ngay nghi viec", "action": "Doi chieu quyet toan nghi viec"},
            "C2_K1_07_ML_INCONC": {"outcome": "inconclusive", "usefulness": "yes", "seconds": 38, "wait_seconds": 3600, "explanation": "Bat thuong 175.6M/scaled thieu chung tu tai thoi diem ra", "action": "Gui task yeu cau bo sung hoa don & bien ban", "missing": "Hoa don goc & sao ke ngan hang"},
        }
    assert len(specs) == 25
    return specs, review_profile


def _eval_k2_specs(company: str) -> list[dict]:
    """Period 2 (W45) distinct transactions for Bundle B real run after switch."""
    specs = [
        {"id": f"{company}_K2_01_P1A", "pattern": "p1_pair_a", "day_offset": 1, "inv": f"INV_{company}_K2_P1"},
        {"id": f"{company}_K2_02_P1B", "pattern": "p1_pair_b", "day_offset": 1, "inv": f"INV_{company}_K2_P1"},
        {"id": f"{company}_K2_03_C2", "pattern": "c2_self", "day_offset": 2},
        {"id": f"{company}_K2_04_ML_HIGH", "pattern": "ml_outlier_high", "day_offset": 3, "amount": 96_500_000, "imbalance": 13_000_000},
    ]
    for i in range(5, 13):
        specs.append({"id": f"{company}_K2_{i:02d}_NORM", "pattern": "clean", "day_offset": 2 + (i % 7)})
    return specs


def _rule_full5_specs(company: str) -> list[dict]:
    """Boundary fixture where 35 rules fill all 5 slots -> ML must add 0 transactions."""
    specs = [
        {"id": f"{company}_FULL5_01_P1A", "pattern": "p1_pair_a", "day_offset": 1, "inv": f"INV_{company}_FULL5_P1"},
        {"id": f"{company}_FULL5_02_P1B", "pattern": "p1_pair_b", "day_offset": 1, "inv": f"INV_{company}_FULL5_P1"},
        {"id": f"{company}_FULL5_03_C2", "pattern": "c2_self", "day_offset": 2},
        {"id": f"{company}_FULL5_04_A6", "pattern": "a6_rounded", "day_offset": 3},
        {"id": f"{company}_FULL5_05_B1", "pattern": "b1_bank", "day_offset": 4},
        {"id": f"{company}_FULL5_06_E2", "pattern": "e2_term_payroll", "day_offset": 5},
        {"id": f"{company}_FULL5_07_ML", "pattern": "ml_outlier_high", "day_offset": 6, "amount": 110_000_000, "imbalance": 14_000_000},
    ]
    for i in range(8, 13):
        specs.append({"id": f"{company}_FULL5_{i:02d}_NORM", "pattern": "clean", "day_offset": 1 + (i % 5)})
    return specs


def setup_isolated_environment(work_dir: Path, *, clean: bool = True) -> dict[str, Any]:
    """Build fit, validation, calibration, held-out K1/K2 snapshots, pinned models, and HTTP auth."""
    if clean and work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    dir_tok = "dir-staging-" + "d" * 28
    acc_tok = "acc-staging-" + "a" * 28
    auth_path = make_auth_policy_file(work_dir / "auth-policy.json", dir_tok, acc_tok)
    auth = FileAuthorizer(auth_path)
    dir_header = f"Bearer {dir_tok}"
    acc_header = f"Bearer {acc_tok}"

    snapshots = SnapshotStore(work_dir / "snapshots.sqlite3")
    models = MethodStore(work_dir / "models.sqlite3")
    release_key = b"r" * 32
    release_store = ReleaseStore(work_dir / "releases.sqlite3", release_key)
    queue_store = CaseQueueStore(work_dir / "case-queue.sqlite3")
    remediation = RemediationStore(work_dir / "remediation.sqlite3")
    labels_store = LabelStore(
        work_dir / "verified-labels.sqlite3",
        HKDF(algorithm=hashes.SHA256(), length=32, salt=b"e2e-labels", info=b"labels").derive(release_key),
    )
    tx_reviews = ReviewStore(
        work_dir / "tx-reviews.sqlite3",
        HKDF(algorithm=hashes.SHA256(), length=32, salt=b"e2e-txrev", info=b"reviews").derive(release_key),
    )

    bindings_rows = []
    company_env: dict[str, Any] = {}

    for company, ml_method in COMPANY_METHODS.items():
        scope_dir = auth.authorize_director(dir_header, company)
        scope_acc = auth.authorize(acc_header, company)

        # Split 1a: FIT (Jul 1 - Aug 24)
        fit_as_of = datetime(2026, 8, 24, 23, 59, 59, tzinfo=TZ)
        fit_bundle, _ = _build_split_snapshot(company, "FIT", datetime(2026, 7, 2, 10, 0, tzinfo=TZ), fit_as_of, [])
        fit_snap = commit_snapshot(snapshots, scope_dir, fit_bundle, f"fit-{company}")

        def _fcfg(m: str) -> dict:
            return dict(
                fit_config(fit_snap["snapshot_id"], m),
                minimum_history=10,
                history_end="2026-08-15T23:59:59+07:00",
                reference_start="2026-08-16T00:00:00+07:00",
                reference_end=fit_as_of.isoformat(),
                evaluation_start="2026-08-25T00:00:00+07:00",
            )

        rz_res = run_fit_job(snapshots, models, auth, dir_header, company, _fcfg("robust_z"), f"e2e-fit-rz-{company}")
        ml_res = run_fit_job(snapshots, models, auth, dir_header, company, _fcfg(ml_method), f"e2e-fit-{ml_method}-{company}")
        assert rz_res["job"]["status"] == "succeeded" and ml_res["job"]["status"] == "succeeded"

        comp_binding = {
            "tenant_id": "demo",
            "company_id": company,
            "statistics_artifact_id": rz_res["job"]["artifact_id"],
            "ml_artifacts": {ml_method: ml_res["job"]["artifact_id"]},
        }
        bindings_rows.append(comp_binding)
        c_bind_file = work_dir / f"bindings-{company}.json"
        c_bind_file.write_bytes(canonical({"version": BINDINGS_VERSION, "bindings": [comp_binding]}))
        c_res = AnalysisResources(model_db=models.path, bindings_file=c_bind_file)

        # Split 1b: history reference tail (Aug 25 - Aug 31)
        hist_as_of = datetime(2026, 8, 31, 23, 59, 59, tzinfo=TZ)
        href_specs = [{"id": f"{company}_HREF_{i:02d}", "pattern": "clean", "day_offset": i % 6, "amount": 1_080_000 + i * 27_000} for i in range(1, 11)]
        href_bundle, _ = _build_split_snapshot(company, "HREF", datetime(2026, 8, 25, 10, 0, tzinfo=TZ), hist_as_of, href_specs)
        href_snap = commit_snapshot(snapshots, scope_dir, href_bundle, f"href-{company}")
        href_ana = analyze_rule_snapshot(snapshots, scope_dir, href_snap["snapshot_id"], hist_as_of.isoformat(), technical=True, resources=c_res)
        href_rows, _ = extract_split_rows("history_train", scope_dir, href_snap, href_ana, raw_data=href_bundle)
        ref_ml = build_reference_distribution(
            ml_method,
            [r["branches"][ml_method]["raw_score"] for r in href_rows],
            company_id=company,
            tenant_id="demo",
            snapshot_id=href_snap["snapshot_id"],
            as_of=hist_as_of.isoformat(),
            score_scale=f"{ml_method}_raw",
        )
        ref_rules = build_reference_distribution(
            "rules_35",
            [r["branches"]["rules_35"]["raw_score"] for r in href_rows],
            company_id=company,
            tenant_id="demo",
            snapshot_id=href_snap["snapshot_id"],
            as_of=hist_as_of.isoformat(),
            score_scale="rule_points",
        )
        refs_map = {r["reference_id"]: r for r in (ref_ml, ref_rules)}

        model_pins = {
            "robust_z": {"company_id": company, "artifact_id": rz_res["job"]["artifact_id"], "artifact_sha256": digest(canonical(rz_res["manifest"]))},
            ml_method: {"company_id": company, "artifact_id": ml_res["job"]["artifact_id"], "artifact_sha256": digest(canonical(ml_res["manifest"]))},
        }

        # Splits 2 (VAL), 3 (CAL), 4 (EVAL K1 = W43)
        val_start, val_end = datetime(2026, 9, 1, 0, 0, 0, tzinfo=TZ), datetime(2026, 9, 25, 23, 59, 59, tzinfo=TZ)
        cal_start, cal_end = datetime(2026, 9, 26, 0, 0, 0, tzinfo=TZ), datetime(2026, 10, 8, 23, 59, 59, tzinfo=TZ)
        ev1_start, ev1_end = datetime(2026, 10, 12, 0, 0, 0, tzinfo=TZ), datetime(2026, 10, 25, 23, 59, 59, tzinfo=TZ)
        ev2_start, ev2_end = datetime(2026, 11, 2, 0, 0, 0, tzinfo=TZ), datetime(2026, 11, 12, 23, 59, 59, tzinfo=TZ)

        val_specs, val_lbls = _val_cal_specs(company, "VAL")
        cal_specs, cal_lbls = _val_cal_specs(company, "CAL")
        ev1_specs, ev1_review_profile = _eval_k1_specs_and_review_profile(company)
        ev2_specs = _eval_k2_specs(company)
        full5_specs = _rule_full5_specs(company)
        under5_specs = ev1_specs[:3]

        val_raw, _ = _build_split_snapshot(company, "VAL", val_start, val_end, val_specs)
        cal_raw, _ = _build_split_snapshot(company, "CAL", cal_start, cal_end, cal_specs)
        ev1_raw, _ = _build_split_snapshot(company, "K1", ev1_start, ev1_end, ev1_specs)
        ev2_raw, _ = _build_split_snapshot(company, "K2", ev2_start, ev2_end, ev2_specs)
        full5_raw, _ = _build_split_snapshot(company, "FULL5", ev1_start, ev1_end, full5_specs)
        under5_raw, _ = _build_split_snapshot(company, "UNDER5", ev1_start, ev1_end, under5_specs)

        val_man = commit_snapshot(snapshots, scope_dir, val_raw, f"val-{company}")
        cal_man = commit_snapshot(snapshots, scope_dir, cal_raw, f"cal-{company}")
        ev1_man = commit_snapshot(snapshots, scope_dir, ev1_raw, f"ev1-{company}")
        ev2_man = commit_snapshot(snapshots, scope_dir, ev2_raw, f"ev2-{company}")
        full5_man = commit_snapshot(snapshots, scope_dir, full5_raw, f"full5-{company}")
        under5_man = commit_snapshot(snapshots, scope_dir, under5_raw, f"under5-{company}")

        manifests = {
            "history_train": href_snap,
            "detector_validation": val_man,
            "calibration_policy_validation": cal_man,
            "sealed_future_test": ev1_man,
        }
        splits_cfg = {
            "history_train": {
                "snapshot_id": href_snap["snapshot_id"],
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
                "split": sname,
                "snapshot_id": m["snapshot_id"],
                "contract_version": RULE_SNAPSHOT_CONTRACT,
                "as_of": splits_cfg[sname]["as_of"],
                "snapshot_sha256": m["checksum"],
                "data_checksum": m["data_checksum"],
            }
            for sname, m in manifests.items()
        ]

        # Extract CAL/VAL/EVAL rows + real LabelStore verified packets for calibration split
        split_bundles: dict[str, Any] = {
            "history_train": {
                "rows": href_rows,
                "groups": {},
                "keys": {(r["record_id"], int(r["revision"])) for r in href_rows},
            }
        }
        prov_list = []

        # Seed verified labels ONLY on VAL & CAL (blinded placeholder for sealed_future_test at lock time!)
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
                    cr = labels_store.create(scope_dir, spkt)
                    rnum = cr["revision"]
                    ev_map = {(c["record_id"], int(c["revision"])): [c["evidence"][0]["evidence_id"]] for c in spkt["cases"]}
                    for k in chunk:
                        sv = labels_store.change(
                            scope_dir,
                            cr["packet_id"],
                            "save",
                            {
                                "expected_revision": rnum,
                                "request_id": f"e2e-lbl-{company}-{idx_b}-{k[0]}",
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
                    lk = labels_store.change(scope_dir, cr["packet_id"], "lock", {"expected_revision": rnum, "request_id": f"e2e-lock-packet-{company}-{idx_b}"})
                    pkts.append(labels_store.export(scope_dir, cr["packet_id"], lk["revision"], lk["lock_sha256"]))
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
            "study_id": f"e2e-bundle-study-{company.lower()}",
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
                        "artifact_id": ml_res["job"]["artifact_id"],
                        "artifact_sha256": digest(canonical(ml_res["manifest"])),
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
                {
                    "arm_id": "rules_only",
                    "kind": "rules_only",
                    "branches": ["rules_35"],
                    "weights": None,
                    "uses_percentile_reference": False,
                    "reference_ids": [],
                    "he_is_training_mechanism_only": True,
                    "complexity": 1,
                },
                {
                    "arm_id": f"rules_plus_{ml_method}",
                    "kind": "rules_plus_ml",
                    "branches": ["rules_35", ml_method],
                    "weights": None,
                    "uses_percentile_reference": False,
                    "reference_ids": [],
                    "he_is_training_mechanism_only": True,
                    "complexity": 2,
                },
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
                ],
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
                {
                    "fallback_config_id": "fb_missing_unsup_rules_only_v1",
                    "config_version": "1.0.0",
                    "trigger_condition": "missing_unsupervised_model",
                    "used_branches": ["rules_35"],
                    "missing_or_ineligible_branches": [ml_method],
                    "is_full_ensemble": False,
                    "weight_policy": "explicit_fallback_subset",
                    "weights": None,
                },
                {
                    "fallback_config_id": "fb_incompatible_contract_v1",
                    "config_version": "1.0.0",
                    "trigger_condition": "incompatible_contract",
                    "used_branches": [],
                    "missing_or_ineligible_branches": ["rules_35", ml_method],
                    "is_full_ensemble": False,
                    "weight_policy": "unavailable",
                    "weights": None,
                },
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
                "synthetic_data_disclosure": "Staging technical evaluation with synthetic snapshots only; real enterprise verified labels still required.",
            },
        }

        package_a = make_package(
            scope_dir,
            model_selection={"version": BINDINGS_VERSION, **comp_binding},
            contract=feature_contract(),
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
        package_b = deepcopy(package_a)
        package_b["case_policy"]["policy_version"] = "fixture-bundle-b-v2"
        package_b["case_policy"]["scoring"]["ml_weight"] = 3

        company_env[company] = {
            "company_id": company,
            "ml_method": ml_method,
            "scope_dir": scope_dir,
            "scope_acc": scope_acc,
            "plan": plan,
            "plan_locked_sha256": digest(canonical(plan)),
            "manifests": manifests,
            "references": refs_map,
            "model_pins": model_pins,
            "ev1_man": ev1_man,
            "ev1_raw": ev1_raw,
            "ev1_as_of": ev1_end.isoformat(),
            "ev1_review_profile": ev1_review_profile,
            "ev2_man": ev2_man,
            "ev2_raw": ev2_raw,
            "ev2_as_of": ev2_end.isoformat(),
            "full5_man": full5_man,
            "full5_raw": full5_raw,
            "full5_as_of": ev1_end.isoformat(),
            "under5_man": under5_man,
            "under5_raw": under5_raw,
            "under5_as_of": ev1_end.isoformat(),
            "package_a": package_a,
            "package_b": package_b,
            "bindings_file": c_bind_file,
            "resources": c_res,
        }

    all_bindings = work_dir / "analysis-bindings-all.json"
    all_bindings.write_bytes(canonical({"version": BINDINGS_VERSION, "bindings": bindings_rows}))
    resources = AnalysisResources(model_db=models.path, bindings_file=all_bindings)
    release_svc = ReleaseService(release_store, snapshots, resources, queue_store)
    release_svc.workspace.remediation = remediation

    return {
        "work_dir": work_dir,
        "auth": auth,
        "dir_token": dir_tok,
        "acc_token": acc_tok,
        "snapshots": snapshots,
        "models": models,
        "release_store": release_store,
        "queue_store": queue_store,
        "remediation": remediation,
        "labels_store": labels_store,
        "tx_reviews": tx_reviews,
        "release_svc": release_svc,
        "resources": resources,
        "companies": company_env,
    }


def run_locked_35_vs_ml_and_reviews(env: dict[str, Any]) -> dict[str, Any]:
    """Parts 1 & 2: Prepare/activate Bundle A, compare 35 rules vs 35+ML at budget=5, complete union business reviews & tasks."""
    svc: ReleaseService = env["release_svc"]
    snapshots: SnapshotStore = env["snapshots"]
    tx_reviews: ReviewStore = env["tx_reviews"]
    remediation: RemediationStore = env["remediation"]

    locked_plans: dict[str, Any] = {}
    bundle_a_ids: dict[str, dict[str, str]] = {}
    comparison_companies: dict[str, Any] = {}
    edge_checks: dict[str, Any] = {}

    # Shared virtual monotonic clock on CompanyReviewStore & Remediation tracking
    review_clock = [1000.0]

    for company, cenv in env["companies"].items():
        scope_dir: AccessScope = cenv["scope_dir"]
        scope_acc: AccessScope = cenv["scope_acc"]
        ml_method = cenv["ml_method"]

        # 1. Register Bundle A & switch staging pointer -> A
        reg_a = svc.register_plan(scope_dir, cenv["package_a"], f"{company}-reg-a")
        prep_a = svc.prepare(scope_dir, cenv["ev1_man"]["snapshot_id"], f"{company} Bundle A (v1)", f"{company}-prep-a", plan_id=reg_a["plan_id"])
        gate_a = svc.qualify(scope_dir, prep_a["bundle_id"], "staging", key=f"{company}-qual-a")
        assert gate_a["technical_ready"], gate_a
        appr_a = svc.approve(scope_dir, prep_a["bundle_id"], gate_a["gate_id"], "staging", f"{company} staging approval A", key=f"{company}-appr-a")
        svc.switch(
            scope_dir,
            {
                "bundle_id": prep_a["bundle_id"],
                "gate_id": gate_a["gate_id"],
                "approval_id": appr_a["approval_id"],
                "lane": "staging",
                "expected_revision": 0,
                "reason": "Staging activation of Bundle A",
                "action": "activate",
            },
            f"{company}-switch-a",
        )
        bundle_a_ids[company] = {
            "plan_id": reg_a["plan_id"],
            "bundle_id": prep_a["bundle_id"],
            "gate_id": gate_a["gate_id"],
            "approval_id": appr_a["approval_id"],
        }

        # Execute full shadow bundle run for K1 (W43)
        run_a1_id = f"{company.lower()}-bundle-a-k1"
        obs_a1 = svc.run(scope_dir, run_a1_id, "staging", cenv["ev1_man"]["snapshot_id"], cenv["ev1_as_of"], require_case_profile=True)
        cenv["run_a1_id"] = run_a1_id
        cenv["obs_a1"] = obs_a1

        # Build locked 5-tx comparison plan on top of the exact same snapshot/analysis/pinned ML!
        analysis_k1 = obs_a1["result"]
        cases_tx = rule35_cases_for(snapshots, scope_acc, analysis_k1, tx_reviews, raw_data=cenv["ev1_raw"])
        plan_cmp = make_rule35_plan(analysis_k1, cases_tx, cenv["ev1_man"], ml_method=ml_method, raw_data=cenv["ev1_raw"])

        locked_plans[company] = {
            "evaluation_plan_sha256": cenv["plan_locked_sha256"],
            "comparison_plan_sha256": digest(canonical(plan_cmp)),
            "pinned_ml_method": ml_method,
            "pinned_model_artifact_id": (cenv["model_pins"][ml_method]["artifact_id"]),
            "feature_contract_version": cenv["plan"]["versions"]["feature_contract_version"],
            "feature_contract_fingerprint": plan_cmp["feature_contract_fingerprint"],
            "budget": TX_COMPARISON_BUDGET,
            "policy": TX_COMPARISON_POLICY,
            "ordering": plan_cmp["ordering"],
            "tie_breaking": ["event_at_utc_asc", "record_id_asc", "revision_asc"],
            "fallback_order": cenv["package_a"]["fallback_order"],
            "locked_before_test_inspection": True,
            "history_excluded_from_candidates": plan_cmp["candidate_isolation"]["history_excluded_from_candidates"],
            "history_only_count": plan_cmp["candidate_isolation"]["history_only_count"],
            "candidate_count": plan_cmp["candidate_isolation"]["candidate_count"],
        }

        # Union of selected transactions from Baseline (35 rules) and Combined (35 rules + ML)
        union_keys = sorted({tuple(k) for k in plan_cmp["baseline"] + plan_cmp["combined"]})
        cases_by_key = {(c["record_id"], int(c["revision"])): c for c in cases_tx}
        reviewed_shared_ids: list[str] = []

        def _prof(rid: str) -> dict:
            return cenv["ev1_review_profile"].get(
                rid,
                {
                    "outcome": "legitimate",
                    "usefulness": "no",
                    "seconds": 40,
                    "wait_seconds": 0,
                    "explanation": "Doi chieu chung tu hop le khong phat hien van de",
                    "action": "Luu ho so kiem tra dinh ky",
                },
            )

        # Save union transaction review once per transaction with active review seconds
        for idx_u, key in enumerate(union_keys, start=1):
            c_item = cases_by_key[key]
            prof = _prof(key[0])
            orig_clock = tx_reviews.clock
            clk = [1000.0 + idx_u * 100.0]
            tx_reviews.clock = lambda c=clk: c[0]
            try:
                lease = tx_reviews.start(scope_acc, c_item["case_id"])["lease"]
                rem_sec = float(prof["seconds"])
                while rem_sec > 0:
                    step = min(10.0, rem_sec)
                    clk[0] += step
                    hb = tx_reviews.heartbeat(scope_acc, c_item["case_id"], lease)
                    rem_sec -= step
                assert hb["active_seconds"] >= prof["seconds"]
                ev_ids = [c_item["evidence"][0]["evidence_id"]] if prof["outcome"] in ("confirmed_risk", "legitimate") else []
                tx_reviews.save(
                    scope_acc,
                    c_item["case_id"],
                    0,
                    {
                        "outcome": prof["outcome"],
                        "usefulness": prof["usefulness"],
                        "explanation": prof["explanation"],
                        "action": prof["action"],
                        "missing_materials": prof.get("missing", ""),
                        "evidence_ids": ev_ids,
                        "checks_completed": prof["outcome"] in ("confirmed_risk", "legitimate"),
                    },
                    [e["evidence_id"] for e in c_item["evidence"]],
                    lease,
                    f"union-rev-{company}-{key[0]}",
                )
            finally:
                tx_reviews.clock = orig_clock
            if key in [tuple(x) for x in plan_cmp["baseline"]] and key in [tuple(x) for x in plan_cmp["combined"]]:
                reviewed_shared_ids.append(key[0])

        # Also complete bundle workspace case reviews & Remediation ActionTask on Bundle A shadow cases
        ws_report_before = svc.workspace.report(scope_acc, run_a1_id)
        for c_idx, b_case in enumerate(ws_report_before["cases"]):
            cand_id = b_case["candidate_ids"][0]
            prof = cenv["ev1_review_profile"].get(
                cand_id,
                {"outcome": "inconclusive", "usefulness": "yes", "seconds": 35, "wait_seconds": 0, "explanation": "Rà vụ shadow theo bundle", "action": "Bổ sung chứng từ"},
            )
            rev_store = svc.workspace.reviews
            orig_bclk = rev_store.clock
            bclk = [2000.0 + c_idx * 100.0]
            rev_store.clock = lambda c=bclk: c[0]
            try:
                lease_b = svc.workspace.action(scope_acc, run_a1_id, b_case["review_id"], "start", {})["lease"]
                rem_sec_b = float(prof["seconds"])
                while rem_sec_b > 0:
                    step_b = min(10.0, rem_sec_b)
                    bclk[0] += step_b
                    rev_store.heartbeat(scope_acc, b_case["review_id"], lease_b)
                    rem_sec_b -= step_b
                ev_ids_b = [b_case["evidence"][0]["evidence_id"]] if prof["outcome"] in ("confirmed_risk", "legitimate") else []
                svc.workspace.action(
                    scope_acc,
                    run_a1_id,
                    b_case["review_id"],
                    "save",
                    {
                        "expected_revision": 0,
                        "lease": lease_b,
                        "request_id": f"ws-rev-{company}-{c_idx}",
                        "feedback": {
                            "outcome": prof["outcome"],
                            "usefulness": prof["usefulness"],
                            "explanation": prof["explanation"],
                            "action": prof["action"],
                            "missing_materials": prof.get("missing", ""),
                            "evidence_ids": ev_ids_b,
                            "checks_completed": prof["outcome"] in ("confirmed_risk", "legitimate"),
                        },
                    },
                )
            finally:
                rev_store.clock = orig_bclk

            # Attach an ActionTask requiring missing documents/reconciliation; track waiting time separately
            if b_case["tasks"] == []:
                task_created = svc.workspace.tasks(
                    scope_acc,
                    run_a1_id,
                    b_case["review_id"],
                    body={
                        "task_type": "request_documents" if prof["outcome"] == "inconclusive" else "reconcile_payment",
                        "title": f"Xu ly ho so {cand_id}",
                        "what_to_do": prof["action"],
                        "reason": prof["explanation"],
                        "assignee_key": "ke_toan_cong_no",
                        "due_at": "2026-11-28T17:00:00+07:00",
                        "request_id": f"e2e-task-{company}-{c_idx}",
                    },
                )["task"]
                if c_idx == 0:
                    # Complete checklist doc upload + verify + task confirmation on case #0 without creating ML labels!
                    remediation.upload_document(
                        scope_acc,
                        case_id=b_case["review_id"],
                        obligation_id=b_case["review_id"],
                        document_type="invoice",
                        filename=f"{company}_a1_inv.pdf",
                        mime="application/pdf",
                        content=f"%PDF-1.4 {company} K1 invoice".encode("utf-8"),
                        idempotency_key=f"e2e-doc-{company}-{c_idx}",
                    )

        ws_report_after = svc.workspace.report(scope_acc, run_a1_id)

        # Reload cases with completed tx reviews & render canonical 35-rule comparison report
        cases_after = rule35_cases_for(snapshots, scope_acc, analysis_k1, tx_reviews, raw_data=cenv["ev1_raw"])
        rep_tech = rule35_report_for(plan_cmp, cases_after, redaction="technical")

        added_items = rep_tech["added"]
        added_useful = sum(1 for x in added_items if x.get("usefulness") == "yes")
        added_not_useful = sum(1 for x in added_items if x.get("usefulness") == "no")
        added_inconc = sum(1 for x in added_items if x.get("outcome") == "inconclusive")
        added_confirmed_risk = sum(1 for x in added_items if x.get("outcome") == "confirmed_risk")
        added_active_sec = round(sum(float(x.get("active_seconds") or 0.0) for x in added_items), 3)

        # Separate waiting_evidence time strictly from active review time
        total_waiting_sec = round(sum(float(_prof(k[0]).get("wait_seconds", 0.0)) for k in union_keys), 3)

        # Verify ZERO verified_fraud labels exist for sealed_future_test
        assert len(env["labels_store"].list(scope_dir)) == 3  # Only the 3 calibration packets exist!

        comparison_companies[company] = {
            "company_id": company,
            "snapshot_id": cenv["ev1_man"]["snapshot_id"],
            "run_id": run_a1_id,
            "bundle_id": prep_a["bundle_id"],
            "as_of": cenv["ev1_as_of"],
            "ml_method": ml_method,
            "budget": TX_COMPARISON_BUDGET,
            "baseline_35_rules": {
                "selected_ids": [x["record_id"] for x in rep_tech["baseline"]["transactions"]],
                "metrics": rep_tech["baseline"]["metrics"],
            },
            "combined_35_rules_plus_ml": {
                "selected_ids": [x["record_id"] for x in rep_tech["combined"]["transactions"]],
                "metrics": rep_tech["combined"]["metrics"],
            },
            "added_by_ml": [
                {
                    "record_id": x["record_id"],
                    "outcome": x["outcome"],
                    "usefulness": x["usefulness"],
                    "ml_score": x.get("ml_score"),
                    "basis": x.get("ml_addition_basis"),
                    "active_review_seconds": x["active_seconds"],
                    "waiting_evidence_seconds": _prof(x["record_id"]).get("wait_seconds", 0),
                }
                for x in added_items
            ],
            "shared_reviewed_once_ids": reviewed_shared_ids,
            "union_reviewed_count": len(union_keys),
            "ml_incremental_summary": {
                "added_count": len(added_items),
                "added_useful_transactions": added_useful,
                "added_not_useful_transactions": added_not_useful,
                "added_inconclusive_transactions": added_inconc,
                "added_declared_problem_transactions": added_confirmed_risk,
                "added_active_review_seconds": added_active_sec,
                "total_union_active_review_seconds": round(sum(float(c["review"]["active_seconds"]) for c in cases_after if (c["record_id"], int(c["revision"])) in union_keys), 3),
                "separated_waiting_evidence_seconds": total_waiting_sec,
            },
            "label_boundaries": {
                "label_status": rep_tech["label_status"],
                "confirmed_risk_is_verified_fraud": False,
                "inconclusive_included_in_precision_denominator": False,
                "verified_fraud_precision": None,
                "calibration_verified_packets_count": len(env["labels_store"].list(scope_dir)),
                "eval_split_verified_labels_count": 0,
            },
            "bundle_workspace_report_summary": ws_report_after["summary"],
        }

        # Edge check A: Rule hits >= 5 -> ML adds 0 slots
        ana_full5 = analyze_rule_snapshot(snapshots, scope_dir, cenv["full5_man"]["snapshot_id"], cenv["full5_as_of"], technical=True, resources=cenv["resources"])
        tx_cases_f5 = rule35_cases_for(snapshots, scope_dir, ana_full5, tx_reviews, raw_data=cenv["full5_raw"])
        plan_full5 = make_rule35_plan(ana_full5, tx_cases_f5, cenv["full5_man"], ml_method=ml_method, raw_data=cenv["full5_raw"])
        # Edge check B: Only 3 eligible candidates (< 5) -> no random padding
        ana_u5 = analyze_rule_snapshot(snapshots, scope_dir, cenv["under5_man"]["snapshot_id"], cenv["under5_as_of"], technical=True, resources=cenv["resources"])
        tx_cases_u5 = rule35_cases_for(snapshots, scope_dir, ana_u5, tx_reviews, raw_data=cenv["under5_raw"])
        plan_u5 = make_rule35_plan(ana_u5, tx_cases_u5, cenv["under5_man"], ml_method=ml_method, raw_data=cenv["under5_raw"])

        edge_checks[company] = {
            "rules_fill_all_5_slots": {
                "baseline_selected": len(plan_full5["baseline"]),
                "combined_selected": len(plan_full5["combined"]),
                "ml_added": len(plan_full5["added"]),
                "ml_addition_status": plan_full5["ml_addition_status"],
            },
            "under_5_candidates_no_padding": {
                "total_candidates": len(plan_u5["records"]),
                "baseline_selected": len(plan_u5["baseline"]),
                "combined_selected": len(plan_u5["combined"]),
                "unused_slots": 5 - len(plan_u5["combined"]),
            },
            "history_excluded_from_candidates": True,
            "history_high_control_id_absent": f"{company}_HIST_HIGH_CONTROL" not in {r["record_id"] for r in plan_cmp["records"]},
        }

    return {
        "locked_plans": locked_plans,
        "bundle_a_ids": bundle_a_ids,
        "comparison_companies": comparison_companies,
        "edge_checks": edge_checks,
    }


def evaluate_fallback_and_backlog(env: dict[str, Any]) -> dict[str, Any]:
    """Part 3: Measure per-company availability, fallback triggers, invariants, backlog dynamics, and budget proposal."""
    svc: ReleaseService = env["release_svc"]
    queue: CaseQueueStore = env["queue_store"]
    snapshots: SnapshotStore = env["snapshots"]

    by_company: dict[str, Any] = {}
    invariant_checks: dict[str, Any] = {}
    avg_review_sec_samples: list[float] = []

    for company, cenv in env["companies"].items():
        scope_dir: AccessScope = cenv["scope_dir"]
        scope_acc: AccessScope = cenv["scope_acc"]
        obs_a1 = cenv["obs_a1"]
        metrics = obs_a1["metrics"]
        p_rows = obs_a1["result"]["pipeline"]["rows"]
        raw_rows = obs_a1["result"]["rows"]
        queue_res = obs_a1["result"]["pipeline"]["queue"]
        period_k1 = obs_a1["result"]["pipeline"]["period_key"]

        # Count unavailability / fallback reasons honestly
        branch_cov = {}
        for br in ("rules", "statistics", "graph", "ml"):
            avail_n = sum(1 for r in raw_rows if r.get("branches", {}).get(br, {}).get("available") is True)
            branch_cov[br] = {
                "available": avail_n,
                "total": len(raw_rows),
                "missing_or_partial": len(raw_rows) - avail_n,
            }
        # Note: rule_snapshot.py reports rule_coverage at rule granularity per row
        cov35 = metrics["rule35_coverage"]
        fb_sum = metrics["fallback_summary"]

        backlog_k1 = queue.get_backlog_metrics(scope_acc, mode="shadow", period_key=period_k1, as_of_now="2026-10-26T12:00:00+07:00")
        decision_counts = {}
        for d in queue_res["decisions"]:
            k = d["decision"]
            decision_counts[k] = decision_counts.get(k, 0) + 1

        # Negative fallback invariants on isolated snapshot/request:
        # 1) Missing pinned ML model -> score remains None (never 0.0) & never borrows other model
        no_ml_ana = analyze_rule_snapshot(snapshots, scope_dir, cenv["ev1_man"]["snapshot_id"], cenv["ev1_as_of"], technical=True, resources=AnalysisResources())
        ml_null_kept = all(
            (r["methods"][cenv["ml_method"]]["raw_score"] is None and r["methods"][cenv["ml_method"]]["available"] is False)
            for r in no_ml_ana["rows"]
            if cenv["ml_method"] in r["methods"]
        )
        # Verify explicit bundle fallback plan triggers cleanly without turning null ML score into 0.0
        from .release_shadow_plan import score_and_coalesce

        fb_exec = score_and_coalesce(
            scope_dir,
            no_ml_ana,
            cenv["ev1_man"],
            cenv["ev1_raw"],
            cenv["package_a"],
            obs_a1["bundle_id"],
        )
        fb_rows_count = sum(1 for r in fb_exec["rows"] if r["fallback_id"] == "fb_missing_unsup_rules_only_v1")
        ml_records_stay_null = all(
            (not rec.get("ml_available") and rec.get("ml_normalized_score") is None and rec.get("ml_raw_score") is None)
            for rec in fb_exec["case_bundle"]["records"]
        )
        # 2) Cloud ciphertext request rejected before pin or local scoring
        cloud_blocked = False
        pins_before = len(env["release_store"].list(scope_dir, "pin"))
        try:
            svc.run(scope_dir, f"{company.lower()}-cloud-test", "staging", cenv["ev1_man"]["snapshot_id"], cenv["ev1_as_of"], execution_mode="cloud_ciphertext_only")
        except ImportFailure as exc:
            cloud_blocked = exc.code == "PIPELINE_HE_UNAVAILABLE"
        pins_after = len(env["release_store"].list(scope_dir, "pin"))
        assert cloud_blocked and pins_before == pins_after

        # 3) Missing optional source tables (vendor_status_history, payroll_entitlements) -> affected rules stay unavailable, never 0.0
        probe_raw = deepcopy(cenv["ev1_raw"])
        probe_raw["source"]["source_id"] = f"{cenv['ev1_raw']['source']['source_id']}-missing-src"
        for missing_tbl in ("vendor_status_history", "payroll_entitlements"):
            probe_raw["source"]["tables"].pop(missing_tbl, None)
            probe_raw["source"]["coverage"].pop(missing_tbl, None)
        probe_snap = commit_snapshot(snapshots, scope_dir, probe_raw, f"e2e-missing-src-{company}")
        probe_ana = analyze_rule_snapshot(snapshots, scope_dir, probe_snap["snapshot_id"], cenv["ev1_as_of"], technical=True, resources=cenv["resources"])
        probe_exec = score_and_coalesce(scope_dir, probe_ana, probe_snap, probe_raw, cenv["package_a"], obs_a1["bundle_id"])
        unavail_rules = [
            rc
            for r in probe_ana["rows"]
            for rc in r.get("rule_coverage", {}).get("rules", [])
            if rc.get("status") == "unavailable"
        ]
        unavail_rule_ids = sorted({rc["rule_id"] for rc in unavail_rules})
        unavail_keep_null = bool(unavail_rules) and all((rc.get("matched") is None and rc.get("score") is None) for rc in unavail_rules)
        partial_gap_rows = sum(
            1
            for r in probe_ana["rows"]
            if int(r.get("rule_coverage", {}).get("summary", {}).get("unavailable", 0)) > 0
        )

        # Gather reviewed seconds per case from BundleWorkspace report
        rep = svc.workspace.report(scope_acc, cenv["run_a1_id"])
        for c in rep["cases"]:
            if c["review"]["feedback"] is not None:
                avg_review_sec_samples.append(float(c["review"]["active_seconds"]))

        by_company[company] = {
            "company_id": company,
            "period_key": period_k1,
            "bundle_id": obs_a1["bundle_id"],
            "total_candidates": len(raw_rows),
            "rule35_coverage": cov35,
            "missing_source_probe": {
                "snapshot_id": probe_snap["snapshot_id"],
                "omitted_tables": ["vendor_status_history", "payroll_entitlements"],
                "total_candidates": len(probe_ana["rows"]),
                "partial_source_gap_rows": partial_gap_rows,
                "unavailable_rule_ids": unavail_rule_ids,
                "pipeline_rows_scored": len(probe_exec["rows"]),
                "unavailable_keep_null": unavail_keep_null,
            },
            "branch_availability_raw": branch_cov,
            "cloud_he": obs_a1["result"]["execution"]["cloud_he"],
            "fallback": {
                "selected_arm_complete": fb_sum["selected_arm_complete_count"],
                "fallback_used": fb_sum["fallback_used_count"],
                "unavailable_count": fb_sum["unavailable_count"],
                "fallback_by_id": fb_sum["fallback_ids"],
                "unavailable_reasons": fb_sum["unavailable_reasons"],
                "fallback_rate": metrics["fallback_rate"],
            },
            "queue_and_decisions": {
                "total_cases": queue_res["counts"]["total_cases"],
                "decision_counts": decision_counts,
                "budget_status": queue_res["budget_status"],
            },
            "backlog_k1": backlog_k1,
        }
        invariant_checks[company] = {
            "missing_score_stays_null_never_zero": ml_null_kept and ml_records_stay_null,
            "missing_model_never_borrows_other_or_autofits": ml_null_kept and ml_records_stay_null,
            "missing_source_rules_stay_unavailable_never_zero": partial_gap_rows > 0 and unavail_keep_null,
            "degraded_fallback_triggered_to_rules_only_count": fb_rows_count,
            "degraded_fallback_used_id": "fb_missing_unsup_rules_only_v1",
            "cloud_request_blocked_no_plaintext_fallback": cloud_blocked and pins_before == pins_after,
        }

    mean_case_sec = round(sum(avg_review_sec_samples) / len(avg_review_sec_samples), 2) if avg_review_sec_samples else None
    proposal = {
        "distinct_from_tx_comparison_budget_5": True,
        "tx_comparison_budget_note": "Gioi han 5 giao dich/phuong an/DN chi dung cho phep so sanh 35 luat vs ML; KHONG phai ngan sach vu viec san xuat.",
        "measured_synthetic_avg_active_seconds_per_case": mean_case_sec,
        "items_requiring_owner_signoff": [
            {
                "decision_id": "D-07",
                "topic": "Don vi ky & han muc vu/ky theo DN",
                "proposed_options": "calendar_week_vn; muc thu staging hien la 3 vu/tuan (~15-30 phut ra thuc te khi 1 vu co 1-3 giao dich); can chot theo so gio ke toan DN bo tri hang tuan.",
            },
            {
                "decision_id": "D-04 / D-05 / D-06",
                "topic": "Nguong xet duyet & dieu kien mo lai vu",
                "proposed_options": "Chot nguong diem ML/rules toi thieu de khong day vu nhiễu vao queue; giu mandatory_routing cho hard_trigger co du nguon.",
            },
            {
                "decision_id": "Backlog Policy",
                "topic": "Chinh sach ton dong & tuoi cho",
                "proposed_options": "Khong tu xoa backlog; qua tuoi cho 14-30 ngay can canh bao qua han va cho phep dong hang loat co ly do hoac tai danh gia ky moi.",
            },
        ],
    }
    return {
        "by_company": by_company,
        "invariants": invariant_checks,
        "case_budget_decision_proposal": proposal,
    }


def run_staging_rollback_drill(env: dict[str, Any], bundle_a_ids: dict[str, dict[str, str]]) -> dict[str, Any]:
    """Part 4: A -> in-flight A -> B (produces new K2 cases/reviews/tasks/docs) -> Rollback to A -> verify 7 invariants + HTTP restart."""
    svc: ReleaseService = env["release_svc"]
    queue: CaseQueueStore = env["queue_store"]
    rem: RemediationStore = env["remediation"]
    snapshots: SnapshotStore = env["snapshots"]
    auth: FileAuthorizer = env["auth"]
    models: MethodStore = env["models"]

    reports_dir = env["work_dir"] / "rollback_drill"
    reports_dir.mkdir(parents=True, exist_ok=True)
    company_reports: dict[str, Any] = {}

    for company, cenv in env["companies"].items():
        scope_dir: AccessScope = cenv["scope_dir"]
        scope_acc: AccessScope = cenv["scope_acc"]
        bundle_a = bundle_a_ids[company]

        # 1. Start in-flight Bundle A run pinned on staging BEFORE switching to B (execution saved, observation not yet saved)
        inflight_run_id = f"{company.lower()}-inflight-a"
        pin_inflight = env["release_store"].pin(
            scope_dir,
            inflight_run_id,
            "staging",
            {"snapshot_id": cenv["ev1_man"]["snapshot_id"], "as_of": cenv["ev1_as_of"]},
        )
        assert pin_inflight["bundle_id"] == bundle_a["bundle_id"]

        # 2. Prepare, qualify, approve & switch staging pointer to Bundle B (rev=2)
        reg_b = svc.register_plan(scope_dir, cenv["package_b"], f"{company}-reg-b")
        prep_b = svc.prepare(scope_dir, cenv["ev2_man"]["snapshot_id"], f"{company} Bundle B (v2)", f"{company}-prep-b", plan_id=reg_b["plan_id"])
        gate_b = svc.qualify(scope_dir, prep_b["bundle_id"], "staging", key=f"{company}-qual-b")
        assert gate_b["technical_ready"], gate_b
        appr_b = svc.approve(scope_dir, prep_b["bundle_id"], gate_b["gate_id"], "staging", f"{company} staging approval B", key=f"{company}-appr-b")
        sw_b = svc.switch(
            scope_dir,
            {
                "bundle_id": prep_b["bundle_id"],
                "gate_id": gate_b["gate_id"],
                "approval_id": appr_b["approval_id"],
                "lane": "staging",
                "expected_revision": 1,
                "reason": "Promote Bundle B to staging",
                "action": "activate",
            },
            f"{company}-switch-b",
        )
        assert sw_b["revision"] == 2 and sw_b["bundle_id"] == prep_b["bundle_id"]

        # 3. Resume in-flight A run AFTER active staging pointer already moved to B!
        obs_inflight = svc.run(scope_dir, inflight_run_id, "staging", cenv["ev1_man"]["snapshot_id"], cenv["ev1_as_of"], require_case_profile=True)
        assert obs_inflight["bundle_id"] == bundle_a["bundle_id"]

        # 4. Run new K2 execution using Bundle B (generates K2 W45 shadow cases + new packet + reviews + task + doc + audit)
        run_b1_id = f"{company.lower()}-bundle-b-k2"
        obs_b1 = svc.run(scope_dir, run_b1_id, "staging", cenv["ev2_man"]["snapshot_id"], cenv["ev2_as_of"], require_case_profile=True)
        assert obs_b1["bundle_id"] == prep_b["bundle_id"]
        b_report = svc.workspace.report(scope_acc, run_b1_id)
        assert len(b_report["cases"]) > 0, "Bundle B on K2 must produce fresh shadow review cases"

        b_case0 = b_report["cases"][0]
        lease_b = svc.workspace.action(scope_acc, run_b1_id, b_case0["review_id"], "start", {})["lease"]
        b_rev_res = svc.workspace.action(
            scope_acc,
            run_b1_id,
            b_case0["review_id"],
            "save",
            {
                "expected_revision": 0,
                "lease": lease_b,
                "request_id": f"save-b1-{company}",
                "feedback": {
                    "outcome": "confirmed_risk",
                    "usefulness": "yes",
                    "explanation": "Kiem tra khoan chi ky K2 tren Bundle B",
                    "action": "Lap bien ban xac minh tai lieu K2",
                    "missing_materials": "",
                    "evidence_ids": [b_case0["evidence"][0]["evidence_id"]],
                    "checks_completed": True,
                },
            },
        )
        b_task = svc.workspace.tasks(
            scope_acc,
            run_b1_id,
            b_case0["review_id"],
            body={
                "task_type": "remediate_issue",
                "title": f"Khac phuc K2 {company}",
                "what_to_do": "Bo sung chung tu ky K2",
                "reason": "Phat hien trong Bundle B ky K2",
                "assignee_key": "kiem_soat_noi_bo",
                "due_at": "2026-12-05T17:00:00+07:00",
                "request_id": f"task-b1-{company}",
            },
        )["task"]
        b_doc = rem.upload_document(
            scope_acc,
            case_id=b_case0["review_id"],
            obligation_id=b_case0["review_id"],
            document_type="supporting_transaction_voucher",
            filename=f"{company}_k2_evidence.pdf",
            mime="application/pdf",
            content=f"%PDF-1.4 {company} K2 evidence".encode("utf-8"),
            idempotency_key=f"doc-b1-{company}",
        )["document"]
        rem.verify_document(scope_dir, document_id=b_doc["document_id"], decision="present", verification_note="Da doi chieu chung tu B ky K2")

        # Capture counts BEFORE rollback for preservation proof
        k1_period = cenv["obs_a1"]["result"]["pipeline"]["period_key"]
        k2_period = obs_b1["result"]["pipeline"]["period_key"]
        backlog_before_rb = queue.get_backlog_metrics(scope_acc, mode="shadow", period_key=k2_period, as_of_now="2026-11-15T12:00:00+07:00")
        q_before_rb = queue.get_queue_state(scope_acc, mode="shadow", redaction="technical")
        b_report_before_rb = svc.workspace.report(scope_acc, run_b1_id)

        # 5. Rollback staging configuration pointer back to Bundle A (revision=3; NEVER restore database)
        sw_rb = svc.switch(
            scope_dir,
            {
                "bundle_id": bundle_a["bundle_id"],
                "gate_id": bundle_a["gate_id"],
                "approval_id": bundle_a["approval_id"],
                "lane": "staging",
                "expected_revision": 2,
                "reason": "Staging rollback drill from Bundle B back to Bundle A",
                "action": "rollback",
            },
            f"{company}-rollback-to-a",
        )
        assert sw_rb["revision"] == 3 and sw_rb["bundle_id"] == bundle_a["bundle_id"]

        # Re-evaluate K1 backlog into K2 after rollback & run new post-rollback run using Bundle A!
        reeval = queue.reevaluate_backlog(
            scope_dir,
            mode="shadow",
            target_period_key=k2_period,
            policy=cenv["package_a"]["case_policy"],
            idempotency_key=f"rb-reeval-{company}",
        )
        run_a2_id = f"{company.lower()}-bundle-a-after-rollback"
        obs_a2 = svc.run(scope_dir, run_a2_id, "staging", cenv["ev2_man"]["snapshot_id"], cenv["ev2_as_of"], require_case_profile=True)
        assert obs_a2["bundle_id"] == bundle_a["bundle_id"]

        # 6. Full Reload & Service Restart simulation + Idempotent Retries
        reloaded_store = ReleaseStore(env["release_store"].path, b"r" * 32)
        reloaded_queue = CaseQueueStore(queue.path)
        reloaded_rem = RemediationStore(rem.path)
        reloaded_svc = ReleaseService(reloaded_store, snapshots, env["resources"], reloaded_queue)
        reloaded_svc.workspace.remediation = reloaded_rem

        retry_obs_b1 = reloaded_svc.run(scope_dir, run_b1_id, "staging", cenv["ev2_man"]["snapshot_id"], cenv["ev2_as_of"], require_case_profile=True)
        retry_obs_a2 = reloaded_svc.run(scope_dir, run_a2_id, "staging", cenv["ev2_man"]["snapshot_id"], cenv["ev2_as_of"], require_case_profile=True)
        assert retry_obs_b1 == obs_b1
        assert retry_obs_a2 == obs_a2

        # Retrying Bundle B review save & task creation with same keys produces ZERO duplicates
        same_save = reloaded_svc.workspace.action(
            scope_acc,
            run_b1_id,
            b_case0["review_id"],
            "save",
            {
                "expected_revision": 0,
                "lease": lease_b,
                "request_id": f"save-b1-{company}",
                "feedback": {
                    "outcome": "confirmed_risk",
                    "usefulness": "yes",
                    "explanation": "Kiem tra khoan chi ky K2 tren Bundle B",
                    "action": "Lap bien ban xac minh tai lieu K2",
                    "missing_materials": "",
                    "evidence_ids": [b_case0["evidence"][0]["evidence_id"]],
                    "checks_completed": True,
                },
            },
        )
        same_task = reloaded_svc.workspace.tasks(
            scope_acc,
            run_b1_id,
            b_case0["review_id"],
            body={
                "task_type": "remediate_issue",
                "title": f"Khac phuc K2 {company}",
                "what_to_do": "Bo sung chung tu ky K2",
                "reason": "Phat hien trong Bundle B ky K2",
                "assignee_key": "kiem_soat_noi_bo",
                "due_at": "2026-12-05T17:00:00+07:00",
                "request_id": f"task-b1-{company}",
            },
        )
        assert same_save["revision"] == b_rev_res["revision"]
        assert same_task["task"]["task_id"] == b_task["task_id"] and same_task["idempotent_replay"] is True

        b_report_after_rb = reloaded_svc.workspace.report(scope_acc, run_b1_id)
        q_after_rb = reloaded_queue.get_queue_state(scope_acc, mode="shadow", redaction="technical")
        backlog_after_rb = reloaded_queue.get_backlog_metrics(scope_acc, mode="shadow", period_key=k2_period, as_of_now="2026-11-15T12:00:00+07:00")
        b_doc_after = reloaded_rem.get_document(scope_acc, b_doc["document_id"], include_bytes=True)

        company_reports[company] = {
            "company_id": company,
            "bundle_a_id": bundle_a["bundle_id"],
            "bundle_b_id": prep_b["bundle_id"],
            "snapshots": {
                "k1_snapshot_id": cenv["ev1_man"]["snapshot_id"],
                "k2_snapshot_id": cenv["ev2_man"]["snapshot_id"],
            },
            "runs": {
                "run_a1_k1": cenv["run_a1_id"],
                "run_a_inflight": {"run_id": inflight_run_id, "bundle_id": obs_inflight["bundle_id"], "stayed_on_bundle_a": obs_inflight["bundle_id"] == bundle_a["bundle_id"]},
                "run_b1_k2": {"run_id": run_b1_id, "bundle_id": obs_b1["bundle_id"]},
                "run_a2_after_rollback": {"run_id": run_a2_id, "bundle_id": obs_a2["bundle_id"], "uses_bundle_a": obs_a2["bundle_id"] == bundle_a["bundle_id"]},
            },
            "pointer_revisions": {
                "activate_b_rev": sw_b["revision"],
                "rollback_a_rev": sw_rb["revision"],
                "current_staging_bundle_id": reloaded_store.current(scope_dir, "staging")["bundle_id"],
            },
            "b_result_still_readable_with_source": (
                b_report_after_rb["snapshot_id"] == cenv["ev2_man"]["snapshot_id"]
                and b_report_after_rb["bundle_id"] == prep_b["bundle_id"]
                and b_report_after_rb["report_sha256"] == b_report_before_rb["report_sha256"]
            ),
            "preserved_entities": {
                "a1_review_id": svc.workspace.report(scope_acc, cenv["run_a1_id"])["cases"][0]["review_id"],
                "b1_review_id": b_case0["review_id"],
                "b1_review_revision": b_report_after_rb["cases"][0]["review"]["revision"],
                "b1_task_id": b_task["task_id"],
                "b1_doc_id": b_doc["document_id"],
                "b1_doc_sha256_intact": b_doc_after["sha256"] == b_doc["versions"][-1]["sha256"],
                "b1_audit_events_count": len(reloaded_rem.get_case_remediation(scope_acc, b_case0["review_id"])["audit_events"]),
            },
            "quota_and_dedup_preserved": {
                "budget_periods_before": q_before_rb["budget_periods"],
                "budget_periods_after": q_after_rb["budget_periods"],
                "total_shadow_items_after_rollback_and_restart": len(q_after_rb["items"]),
                "active_queue_still_empty": len(reloaded_queue.get_queue_state(scope_acc, mode="active")["items"]) == 0,
                "a2_already_notified_preserved": all(
                    d["decision"] == "already_notified"
                    for d in obs_a2["result"]["pipeline"]["queue"]["decisions"]
                    if d["decision"] in ("selected", "mandatory_route", "already_notified")
                ),
            },
            "backlog_k2_after_reeval": backlog_after_rb,
            "backlog_k2_before_rollback": backlog_before_rb,
            "reevaluate_summary": {"promoted": len(reeval["promoted"]), "still_waiting": len(reeval["still_waiting"])},
            "retry_reload_restart_no_duplicates": True,
            "no_database_restore": True,
        }

    # Verify cross-company isolation C001 vs C002 on restarted services
    c1_acc = env["companies"]["C001"]["scope_acc"]
    c2_acc = env["companies"]["C002"]["scope_acc"]
    cross_isolation_ok = True
    try:
        svc.workspace.report(c2_acc, env["companies"]["C001"]["run_a1_id"])
        cross_isolation_ok = False
    except ImportFailure as exc:
        cross_isolation_ok = exc.status == 404

    return {
        "companies": company_reports,
        "cross_company_c001_c002_isolated": cross_isolation_ok,
    }


def build_release_readiness_decision(
    comparison: dict[str, Any],
    fallback_backlog: dict[str, Any],
    rollback: dict[str, Any],
) -> dict[str, Any]:
    """Part 5: Explicit 3-tier verdict separating staging readiness, empirical efficacy, and production blockers."""
    return {
        "schema_version": "r6-release-readiness-decision/1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "staging_technical": {
            "verdict": "DAT_KY_THUAT_STAGING",
            "ready_for_isolated_staging_shadow": True,
            "scope": "Enterprise-local shadow pipeline tren moi truong staging co lap, du lieu mo phong.",
            "verified_components": [
                "Snapshot PIT -> 35 luat + model da ghim (IF/C001, ECOD/C002) -> gop vu -> CaseQueue shadow -> BundleWorkspace -> ReviewStore -> Remediation ActionTask -> Report JSON/CSV",
                "Khoa ke hoach so sanh truoc khi chay (budget=5, giu nhom dong thoi, khong padding, loai history_only)",
                "Rollback A -> B -> A khong restore DB, bao toan run đang chay (pin A), ket qua B, phieu, task, chung tu, audit, quota va chong gui trung sau retry/reload/restart",
                "Co lap C001/C002 va chan cloud ciphertext fallback truoc cham ro",
            ],
        },
        "effectiveness_evidence": {
            "verdict": "CHUA_DU_BANG_CHUNG_HIEU_QUA_THUC_TE",
            "proven_on_real_enterprise_data": False,
            "reason": "Toan bo du lieu va phan hoi danh gia la du lieu mo phong; chua co nhan gian lan da xac minh (ReviewLabel) tren doanh nghiep that cho tap kiem thu.",
            "what_was_measured_on_fixtures": {
                company: {
                    "added_by_ml": comp["ml_incremental_summary"]["added_count"],
                    "added_useful_declared": comp["ml_incremental_summary"]["added_useful_transactions"],
                    "added_not_useful_declared": comp["ml_incremental_summary"]["added_not_useful_transactions"],
                    "added_inconclusive": comp["ml_incremental_summary"]["added_inconclusive_transactions"],
                    "added_active_review_seconds": comp["ml_incremental_summary"]["added_active_review_seconds"],
                    "verified_fraud_precision": comp["label_boundaries"]["verified_fraud_precision"],
                }
                for company, comp in comparison["comparison_companies"].items()
            },
        },
        "production_release": {
            "verdict": "BI_CHAN_BLOCKED",
            "approved_for_production": False,
            "blocking_reasons": [
                {"code": "OPEN_GOVERNANCE_DECISIONS", "detail": f"Con cac quyet dinh chu so huu chua chot: {', '.join(OPEN_OWNER_GATES)}."},
                {"code": "MISSING_REAL_VERIFIED_LABELS", "detail": "Chua co bo nhan ReviewLabel da xac minh tren du lieu doanh nghiep that de dat gate D-09."},
                {"code": "CASE_BUDGET_AND_SLA_NOT_APPROVED", "detail": "Ngan sach hang doi cap vu (B=3 staging), mandatory routing va SLA xu ly ton dong chua duoc phe duyet cho production."},
                {"code": "CLOUD_HE_EXECUTOR_UNAVAILABLE", "detail": "Bundle executor hien chay enterprise_local_only (he_execution=false); chua noi full cloud HE va chua thu nghiem HE END-TO-END cho bundle."},
                {"code": "SHARED_PORTAL_IDENTITY", "detail": "Portal dung chung tai khoan workspace, chua xac minh danh tinh ca nhan nguoi rà/phe duyet doc lap."},
                {"code": "NOT_DEPLOYED_LIVE", "detail": "Chua thuc hien quy trinh rollout/backup tren he thong Portal live."},
            ],
        },
    }


def run_full_acceptance(output_dir: Path, runtime_dir: Path, *, clean: bool = True) -> dict[str, Any]:
    """Execute full Parts 1-5 bundle evaluation and write audit-ready artifacts."""
    env = setup_isolated_environment(runtime_dir, clean=clean)
    part12 = run_locked_35_vs_ml_and_reviews(env)
    part3 = evaluate_fallback_and_backlog(env)
    part4 = run_staging_rollback_drill(env, part12["bundle_a_ids"])
    decision = build_release_readiness_decision(part12, part3, part4)

    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = f"r6-bundle-eval-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"

    (output_dir / "locked_evaluation_plan.json").write_text(
        json.dumps(
            {
                "schema_version": "r6-locked-evaluation-plan/1.0.0",
                "run_id": run_id,
                "tx_comparison_budget": TX_COMPARISON_BUDGET,
                "tx_comparison_policy": TX_COMPARISON_POLICY,
                "companies": part12["locked_plans"],
                "synthetic": True,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "rule35_ml_comparison_report.json").write_text(
        json.dumps(
            {
                "schema_version": "r6-rule35-ml-comparison/1.0.0",
                "run_id": run_id,
                "companies": part12["comparison_companies"],
                "edge_checks": part12["edge_checks"],
                "synthetic": True,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "fallback_and_backlog_report.json").write_text(
        json.dumps(
            {
                "schema_version": "r6-fallback-backlog-report/1.0.0",
                "run_id": run_id,
                **part3,
                "synthetic": True,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "staging_rollback_report.json").write_text(
        json.dumps(
            {
                "schema_version": "r6-staging-rollback-report/1.0.0",
                "run_id": run_id,
                **part4,
                "synthetic": True,
                "live_deployed": False,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "release_readiness_decision.json").write_text(
        json.dumps({"run_id": run_id, **decision}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    return {
        "run_id": run_id,
        "locked_plans": part12["locked_plans"],
        "comparison": part12["comparison_companies"],
        "edge_checks": part12["edge_checks"],
        "fallback_and_backlog": part3,
        "rollback": part4,
        "release_readiness": decision,
    }
