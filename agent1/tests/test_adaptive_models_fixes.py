"""Comprehensive unit and regression tests for Agent 1 AI/Math & Lifecycle fixes.

Covers:
1. 210-day `payment_coverage` onboarding deadlock resolution via honest
   `reconciled_through` confirmation (`known_at = confirmation_date`), actual
   `payment_date` preservation for late-reconciled payments (no false-unpaid
   trap), historical `ACCOUNTING` row projection without feature lookahead,
   missing period/cohort Vietnamese diagnostics, and challenger-vs-active audit.
2. `parse_rows` 1,000x VND comma-thousands (`"500,000"`) guard under `vi-VN`
   and proper parsing under `en-US`.
3. `PartialModel` Empirical Bayes conditional ratio shrinkage (`prior_mass * prior_p`
   instead of raw `prior_mass`), `overdue()` true due-date conditioning without
   asymmetric clipping bias, and bounded `[0, 1]` survival hazards.
4. Operating cashflow short-history (`8-52` weeks) Jackknife+ / rolling calibration
   with non-degenerate `P10 / P50 / P90` bands, plus exact log-normal Jensen
   inequality correction `E[y] = scale * expm1(mu + 0.5 * sigma^2)`.
5. `G0` (`CompactRule` / `LandmarkRule`) smooth due-date transition without 1-day
   cliff, `>13w` geometric tail conservation, `shared_customer_risk` spawned
   Gaussian copula streams without RNG cloning, realistic SME `train_risk` (6-12m)
   & `calibrate_bands` (`>= 4` matured monthly origins), `models/t10.py` balance
   tuple unpacking, and `models/t8_promise.py` future leak prevention.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta
import json
from zoneinfo import ZoneInfo

from cryptography.fernet import Fernet
from lightgbm import LGBMClassifier
import numpy as np
import pandas as pd
import pytest
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from agent1.adaptive.cash_adapter import (
    LABEL_CONTRACT,
    PartialModel,
    expected_cash,
    expected_cash_components,
    fit_partial,
    iter_cash_paths,
    overdue,
)
from agent1.adaptive.cash_history import calibrate_bands
from agent1.adaptive.compact_t1 import sha256
from agent1.adaptive.data import parse_rows, suggested_mapping, validate_dataset
from agent1.adaptive.landmark_features import (
    FEATURES,
    SCHEMA,
    LandmarkEnsemble,
    LandmarkHazard,
    LandmarkRule,
)
from agent1.adaptive.methods import forecast
from agent1.adaptive.operating import fit_candidate, predict_candidate, select_operating
from agent1.adaptive.payment_coverage import (
    attest_reconciled_books,
    check_reconciled_completeness,
    followup_days,
)
from agent1.adaptive.risk import train_risk
from agent1.adaptive.t1_catalog import CATALOG_VERSION, GlobalCatalog
from agent1.adaptive.t1_data import landmarks
from agent1.adaptive.t1_update import UpdatePolicy, train_update
from agent1.models.t8_promise import PromiseReliability
from agent1.models.t10 import scenario_library
from agent1_service.store import Store
from agent1_service.workspace import t1_lifecycle as life


@pytest.fixture
def fast_catalog(tmp_path):
    """Lightweight deterministic GlobalCatalog for onboarding & adaptation tests."""
    rng = np.random.default_rng(2026)
    x = rng.normal(size=(320, 19))
    x[:, -1] = rng.integers(1, 14, len(x))
    y = (rng.random(len(x)) < 0.16).astype(int)
    neural = make_pipeline(
        StandardScaler(),
        MLPClassifier(hidden_layer_sizes=(6,), batch_size=64, max_iter=6, random_state=7),
    ).fit(x, y)
    lgb = LGBMClassifier(
        n_estimators=6, num_leaves=5, min_child_samples=5, verbosity=-1, n_jobs=1
    ).fit(x, y)
    xgb = XGBClassifier(n_estimators=6, max_depth=2, n_jobs=1).fit(x, y)
    models = {
        "neural": LandmarkHazard(neural, "neural"),
        "lightgbm": LandmarkHazard(lgb, "lightgbm"),
        "xgboost": LandmarkHazard(xgb, "xgboost"),
    }
    models["default"] = LandmarkEnsemble(
        [models["neural"], LandmarkRule("customer", np.full((5, 13), 0.05))],
        [0.75, 0.25],
    )
    root = tmp_path / "catalog"
    specs = {}
    for name, model in models.items():
        model.save(
            root / name,
            {"available_asof": "2023-01-01", "label_contract": LABEL_CONTRACT},
        )
        specs[name] = {
            "directory": name,
            "metadata_sha256": sha256(root / name / "metadata.json"),
            "available_asof": "2023-01-01",
        }
    np.savez_compressed(root / "replay.npz", x=x, y=y, weights=np.ones(len(y)))
    prior = fit_partial(pd.DataFrame(), "2023-01-01", prior=None)
    (root / "partial.json").write_text(json.dumps(prior.record()), encoding="utf-8")
    meta = {
        "label_contract": LABEL_CONTRACT,
        "partial": {
            "file": "partial.json",
            "sha256": sha256(root / "partial.json"),
            "available_asof": "2023-01-01",
        },
        "version": CATALOG_VERSION,
        "feature_schema": SCHEMA,
        "features": list(FEATURES),
        "synthetic": True,
        "models": specs,
        "replay": {
            "file": "replay.npz",
            "sha256": sha256(root / "replay.npz"),
            "available_asof": "2023-01-01",
        },
    }
    path = root / "catalog.json"
    path.write_text(json.dumps(meta), encoding="utf-8")
    return GlobalCatalog(path)


# ==============================================================================
# 1. 210-Day Onboarding Deadlock, Honest `reconciled_through`, & False-Unpaid Guard
# ==============================================================================


def _build_onboarding_sme_book(onboarding_day: str = "2026-11-01"):
    """Simulate an SME uploading 14 months of reconciled accounting books on Day 1.

    Invoices & payments carry `known_at = onboarding_day` (as produced when
    uploading historical XML/accounting exports and reconciling bank statements
    on Day 1), while preserving true `issue_date` and `payment_date`.
    """
    invoices, payments = [], []
    for idx, day in enumerate(pd.date_range("2025-08-01", "2026-10-15", freq="7D")):
        for slot in range(6):
            iid = f"HD-{idx:03d}-{slot}"
            amount_net = 10_000_000 + (slot * 2_000_000)
            vat = amount_net // 10
            amount = amount_net + vat
            invoices.append(
                dict(
                    invoice_id=iid,
                    customer_id=f"KH{slot % 4}",
                    seller_mst="0101234567",
                    buyer_mst=f"030765432{slot}",
                    symbol="1C25TAA",
                    invoice_no=f"{idx * 6 + slot + 1:07d}",
                    issue_date=str(day.date()),
                    due_date=str((day + pd.Timedelta(days=21)).date()),
                    amount_net=amount_net,
                    vat=vat,
                    amount=amount,
                    currency="VND",
                    record_version=1,
                    known_at=onboarding_day,
                )
            )
            # Settle in 14..28 days so ~15-18 invoices are open at every landmark
            paid_day = day + pd.Timedelta(days=14 + (slot % 3) * 7)
            if paid_day <= pd.Timestamp("2026-10-25"):
                payments.append(
                    dict(
                        payment_id=f"TT-{idx:03d}-{slot}",
                        invoice_id=iid,
                        payment_date=str(paid_day.date()),
                        amount=amount,
                        known_at=onboarding_day,
                    )
                )
    return dict(invoices=invoices, payments=payments, outflows=[], actions=[])


def test_onboarding_day1_breaks_210d_deadlock_and_preserves_honest_known_at(
    tmp_path, fast_catalog, monkeypatch
):
    onboarding_day = "2026-11-01"
    reconciled_through = "2026-10-25"
    monkeypatch.setattr(
        life,
        "now",
        lambda: datetime(2026, 11, 1, 10, 30, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")),
    )
    store = Store(tmp_path / "sme.db", Fernet.generate_key())
    try:
        book = _build_onboarding_sme_book(onboarding_day)
        store.put_many(
            "SME1",
            {
                "company_datasets": [dict(id="V1", data=book)],
                "company_dataset_active": [dict(id="active", version="V1")],
            },
        )
        policy = UpdatePolicy(
            lookback_days=450,
            stride_days=28,
            minimum_fit_snapshots=15,
            minimum_fit_invoices=10,
            minimum_validation_snapshots=8,
            minimum_audit_snapshots=8,
            alphas=(0.0, 0.5, 1.0),
        )
        # Confirm historical reconciled books up to 2026-10-25 on 2026-11-01
        confirmation = life.confirm_reconciled_books(
            store, "SME1", reconciled_through, policy=policy, strict=True
        )
        assert confirmation["ok"] is True
        assert confirmation["recorded"] is True
        # Honest auditability: known_at is today (2026-11-01), NEVER backdated!
        assert confirmation["coverage"]["known_at"] == onboarding_day
        assert confirmation["coverage"]["reconciled_through"] == reconciled_through
        assert all(r["known_at"] == onboarding_day for r in book["invoices"])
        assert all(r["known_at"] == onboarding_day for r in book["payments"])

        decision = life.run_cycle(
            store,
            "SME1",
            onboarding_day,
            payments_complete=True,
            reconciled_through=reconciled_through,
            policy=policy,
            catalog=fast_catalog,
        )
        saved_meta = store.one("SME1", "company_models", decision["model_id"])
        # Previously: train_n == 0 and validation_n == 0 for 210 calendar days!
        assert saved_meta["train_n"] >= 15
        assert saved_meta["validation_n"] >= 16
        assert saved_meta["audit"]["status"] == "scored"
        assert saved_meta["audit"]["n"] >= 8
        assert saved_meta["windows"]["audit_label_through"] == reconciled_through
        assert saved_meta["asof"] in ("2023-01-01", onboarding_day)
    finally:
        store.connection.close()


def test_april_payment_reconciled_in_may_keeps_april_payment_date_no_false_unpaid():
    """April cash reconciled in May must score on its April payment_date and never look ahead."""
    data = {
        "invoices": [
            dict(
                invoice_id="INV_APR",
                customer_id="KH_A",
                issue_date="2025-03-15",
                due_date="2025-04-14",
                amount=50_000_000,
                known_at="2025-03-15",
            ),
            dict(
                invoice_id="INV_LATE_POSTED_PRE_ORIGIN",
                customer_id="KH_A",
                issue_date="2025-03-01",
                due_date="2025-03-25",
                amount=30_000_000,
                known_at="2025-03-01",
            ),
        ],
        "payments": [
            # Paid April 10, bank statement reconciled May 8
            dict(
                payment_id="PAY_APR",
                invoice_id="INV_APR",
                payment_date="2025-04-10",
                amount=50_000_000,
                known_at="2025-05-08",
            ),
            # Paid March 28 (<= origin April 1), posted April 12 -> pre-origin guard
            dict(
                payment_id="PAY_MAR_LATE",
                invoice_id="INV_LATE_POSTED_PRE_ORIGIN",
                payment_date="2025-03-28",
                amount=30_000_000,
                known_at="2025-04-12",
                book_posted_at="2025-04-12",
            ),
        ],
        "payment_coverage": [
            attest_reconciled_books(
                {"invoices": [dict(issue_date="2025-03-01", known_at="2025-11-21")]},
                reconciled_through="2025-11-01",
                confirmation_date="2025-11-21",
            )
        ],
    }
    # Fit cutoff validation_origin = 2025-04-25 (< May 8 reconciliation date!),
    # while training happens at T = 2025-11-21.
    cohort = landmarks(
        data,
        origin="2025-04-01",
        label_end="2025-04-25",
        knowledge_end="2025-11-21",
    ).set_index("invoice_id")

    assert "INV_APR" in cohort.index
    # Pre-origin late-posted cash is guarded against feature/label corruption
    assert "INV_LATE_POSTED_PRE_ORIGIN" not in cohort.index
    # Features at t0 = 2025-04-01 have ZERO lookahead into the April 10 payment
    assert cohort.loc["INV_APR", "received_fraction"] == 0.0
    # Outcome uses true April 10 payment_date (9 days after April 1 = week 2), NOT inf!
    assert cohort.loc["INV_APR", "paid_days"] == 9.0
    assert cohort.loc["INV_APR", "cash_2"] == pytest.approx(1.0)
    assert cohort.loc["INV_APR", "followup_days"] == 24


def test_reconciled_completeness_diagnostics_detect_missing_months_statements_and_cohorts():
    data = {
        "invoices": [
            dict(
                invoice_id="I1",
                customer_id="C1",
                issue_date="2026-01-10",
                due_date="2026-02-10",
                amount=10_000_000,
                known_at="2026-06-01",
            ),
            dict(
                invoice_id="I2",
                customer_id="C2",
                issue_date="2026-04-15",
                due_date="2026-05-15",
                amount=15_000_000,
                known_at="2026-06-01",
            ),
        ],
        "payments": [],
        "statements": [
            dict(
                statement_id="S1",
                account="TK_VND",
                start_date="2026-01-01",
                end_date="2026-01-31",
                opening_balance=0,
                closing_balance=0,
                known_at="2026-06-01",
            ),
            dict(
                statement_id="S2",
                account="TK_VND",
                start_date="2026-04-01",
                end_date="2026-04-30",
                opening_balance=0,
                closing_balance=0,
                known_at="2026-06-01",
            ),
        ],
    }
    report = check_reconciled_completeness(
        data,
        "2026-05-31",
        confirmation_date="2026-06-01",
        periods=["2026-01", "2026-04", "2026-05"],
    )
    assert report["ok"] is False
    # Explicitly lists missing confirmed months 2026-02, 2026-03 and statement gaps
    assert "2026-02" in report["missing_periods"]
    assert "2026-03" in report["missing_periods"]
    assert any("TK_VND:2026-02-01..2026-03-31" in p for p in report["missing_periods"])
    assert any(c["cohort"] == "historical_span_days" for c in report["missing_cohorts"])
    assert any("2026-02" in m for m in report["messages_vi"])


def test_parse_rows_vi_vn_rejects_comma_thousands_1000x_trap_and_en_us_parses():
    raw = pd.DataFrame(
        [
            {
                "Mã hóa đơn": "HD_500K",
                "Mã khách hàng": "KH01",
                "Ngày lập": "01/03/2026",
                "Hạn thanh toán": "31/03/2026",
                "Số tiền": "500,000",
            }
        ]
    )
    mapping = suggested_mapping(raw.columns, "invoices")
    # Under vi-VN, "500,000" MUST NOT silently become 500 VND!
    rows, errors, _ = parse_rows(raw, "invoices", mapping, number_format="vi-VN")
    assert not rows and len(errors) == 1
    assert "1.000 lần" in errors[0]["message"]

    # Under en-US, "500,000" parses cleanly to exact 500,000 VND
    rows_en, errors_en, _ = parse_rows(raw, "invoices", mapping, number_format="en-US")
    assert not errors_en and rows_en[0]["amount"] == 500_000

    # Standard vi-VN "500.000" and "1.500.000,00" continue to parse to exact VND
    raw.loc[0, "Số tiền"] = "500.000"
    rows_vi, errors_vi, _ = parse_rows(raw, "invoices", mapping, number_format="vi-VN")
    assert not errors_vi and rows_vi[0]["amount"] == 500_000


# ==============================================================================
# 2. PartialModel Empirical Bayes Prior Ratio & Overdue Conditioning
# ==============================================================================


def test_partial_model_prior_ratio_weights_by_prior_p_not_raw_strength():
    # Global prior has low partial incidence prior_p = 0.02, high synthetic ratio 0.95
    prior = PartialModel(
        np.full(6, 0.02),
        tuple(np.array([0.95]) for _ in range(6)),
        tuple(np.ones(1) for _ in range(6)),
        "2024-01-01",
        {"label_contract": LABEL_CONTRACT},
    )
    # Local SME has 50 open weeks, 4 of which have 25% partial payments
    f = pd.DataFrame(np.zeros((50, len(FEATURES))), columns=FEATURES)
    f["invoice_id"] = [f"INV_{i}" for i in range(50)]
    f["customer_id"] = "C"
    f["origin"] = pd.Timestamp("2025-01-01")
    f["label_end"] = pd.Timestamp("2025-01-08")
    f["followup_days"] = 7
    f["paid_days"] = np.inf
    for w in range(1, 14):
        f[f"cash_{w}"] = 0.0
    f.loc[:3, "cash_1"] = 0.25

    learned = fit_partial(f, "2025-01-08", prior=prior, strength=30.0)
    # Posterior incidence: (4 + 30 * 0.02) / (50 + 30) = 4.6 / 80 = 0.0575
    assert learned.probability[0] == pytest.approx((4.0 + 30.0 * 0.02) / (50.0 + 30.0))
    # Posterior conditional ratio mean: (4 * 0.25 + (30 * 0.02) * 0.95) / (4 + 0.6)
    expected_ratio_mean = (4.0 * 0.25 + 0.6 * 0.95) / (4.0 + 0.6)
    assert learned.means[0] == pytest.approx(expected_ratio_mean)
    # Before fix, ratio mean was (4*0.25 + 30*0.95)/34 = 0.8676 (> 0.80)!
    assert learned.means[0] < 0.40


def test_overdue_conditioning_long_term_contract_and_bounded_hazards():
    # 400-day contract issued 2025-01-01, due 2026-02-05; cutoff 2026-01-15 is NOT overdue (-21d)
    opened = pd.DataFrame(
        [
            dict(
                invoice_id="RETENTION_1",
                customer_id="C1",
                issue_date=pd.Timestamp("2025-01-01"),
                due_date=pd.Timestamp("2026-02-05"),
                received=0.0,
            ),
            dict(
                invoice_id="OVERDUE_120D",
                customer_id="C2",
                issue_date=pd.Timestamp("2025-08-01"),
                due_date=pd.Timestamp("2025-09-17"),
                received=10.0,
            ),
        ]
    )
    opened.attrs["cutoff"] = "2026-01-15"
    late = overdue(opened)
    assert late[0] == -21.0  # Previously +14.0 due to mismatched 730/365 clipping!
    assert late[1] == 120.0

    # Near-degenerate deterministic tail distribution stays strictly in [0, 1]
    p = np.zeros((2, 14))
    p[0, 3] = 1.0
    p[1, 0] = 0.4
    p[1, 13] = 0.6
    part = PartialModel(
        np.full(6, 0.3),
        tuple(np.array([0.4]) for _ in range(6)),
        tuple(np.ones(1) for _ in range(6)),
        "2025-01-01",
        {"label_contract": LABEL_CONTRACT},
    )
    comp = expected_cash_components(p, opened, part)
    assert ((comp["hazard"] >= 0.0) & (comp["hazard"] <= 1.0)).all()
    assert (comp["cash"] >= 0.0).all()
    np.testing.assert_allclose(comp["cash"].sum(axis=1), 1.0, atol=1e-12)


# ==============================================================================
# 3. Operating Cashflow Short-History Calibration & Log-Normal Jensen Bias
# ==============================================================================


def test_short_sme_operating_history_20_weeks_calibrated_non_degenerate_bands():
    rng = np.random.default_rng(99)
    start = date(2026, 1, 5)
    bank, statements = [], []
    balance = 50_000_000
    # 20 weeks of SME reconciled bank history (12 <= n_weeks < 52)
    for i in range(20):
        w_start = start + timedelta(weeks=i)
        w_end = w_start + timedelta(days=6)
        sale = int(80_000_000 + 15_000_000 * np.sin(i * np.pi / 2) + rng.normal(0, 8_000_000))
        cost = int(55_000_000 + 8_000_000 * np.cos(i * np.pi / 2) + rng.normal(0, 5_000_000))
        bank.append(
            dict(
                bank_id=f"IN_{i}",
                account="TK1",
                date=str(w_end),
                known_at=str(w_end),
                amount=sale,
                direction="in",
                component="cash_sale",
            )
        )
        bank.append(
            dict(
                bank_id=f"OUT_{i}",
                account="TK1",
                date=str(w_end),
                known_at=str(w_end),
                amount=cost,
                direction="out",
                component="variable_cost",
            )
        )
        next_bal = balance + sale - cost
        statements.append(
            dict(
                statement_id=f"ST_{i}",
                account="TK1",
                start_date=str(w_start),
                end_date=str(w_end),
                opening_balance=balance,
                closing_balance=next_bal,
                known_at=str(w_end),
            )
        )
        balance = next_bal

    cutoff = str(w_end)
    data = dict(
        invoices=[
            dict(
                invoice_id="CLOSED_SEED",
                customer_id="C0",
                issue_date=str(start),
                due_date=str(start),
                known_at=str(start),
                amount=1_000_000,
            )
        ],
        payments=[
            dict(
                payment_id="PAY_SEED",
                invoice_id="CLOSED_SEED",
                payment_date=str(start),
                known_at=str(start),
                amount=1_000_000,
            )
        ],
        outflows=[],
        bank=bank,
        statements=statements,
    )
    validate_dataset(data)

    operating = select_operating(data, cutoff, include_new_credit=False)
    assert operating is not None
    assert operating["adaptive_short"] is True
    assert len(operating["residuals"]) >= 32  # Not collapsed to 3 discrete trajectories!

    bundle = GlobalCatalog().default_bundle(cutoff)
    bundle["operating"] = operating
    plan = forecast(
        data,
        cutoff,
        balance=balance,
        bundle=bundle,
        include_operating=True,
        shap_limit=0,
        simulation_paths=2000,
    )
    assert plan["operating_included"] is True
    for w in plan["weeks"]:
        assert w["low"] < w["median_balance"] < w["high"]


def test_lognormal_jensen_inequality_unbiased_expectation():
    rng = np.random.default_rng(77)
    mu_true, sigma_true = 1.15, 0.55
    scale_ref = 10_000_000.0
    # Generate log1p(Y / scale_ref) ~ N(mu_true, sigma_true^2)
    z = rng.normal(mu_true, sigma_true, size=(400, 2))
    y = np.maximum(0.0, np.expm1(z) * scale_ref)
    empirical_mean = y.mean(axis=0)
    naive_median_biased = (
        np.expm1(np.log1p(y / y.mean(axis=0)).mean(axis=0)) * y.mean(axis=0)
    )

    ln_model = fit_candidate("lognormal", y)
    ln_pred = predict_candidate("lognormal", ln_model, y)
    assert ln_pred.shape == (13, 2)
    # Close to true E[Y], strictly above Jensen-underpredicted median expm1(mu)
    np.testing.assert_allclose(ln_pred[0], empirical_mean, rtol=0.06)
    assert (ln_pred[0] > naive_median_biased * 1.08).all()


def test_gru_jensen_inequality_when_torch_installed():
    pytest.importorskip("torch")
    rng = np.random.default_rng(77)
    z = rng.normal(1.15, 0.55, size=(240, 2))
    y = np.maximum(0.0, np.expm1(z) * 10_000_000.0)
    naive_median_biased = (
        np.expm1(np.log1p(y / y.mean(axis=0)).mean(axis=0)) * y.mean(axis=0)
    )
    gru_model = fit_candidate("gaussian_gru", y)
    gru_pred = predict_candidate("gaussian_gru", gru_model, y)
    assert gru_pred.shape == (13, 2)
    assert (gru_pred[0] > naive_median_biased * 1.05).all()


# ==============================================================================
# 4. G0 Cliff, >13w Tail, Copula RNG Spawn, SME Risk/Calibration, t10 & t8
# ==============================================================================


def test_g0_compact_rule_smooth_across_due_date_and_post_13w_tail_conservation():
    rule = LandmarkRule("customer", np.full((5, 13), 0.05))
    # Vary age_days from 25 to 35 around term_days=30, delay=0 (remaining +5..-5 days)
    ages = np.arange(25.0, 36.0)
    x = np.zeros((len(ages), len(FEATURES)))
    x[:, 1] = 30.0  # term_days
    x[:, 2] = ages  # age_days
    x[:, 8] = 0.0  # customer_delay_180d
    p4w = rule.distribution_from_features(x)[:, :4].sum(axis=1)
    max_daily_step = float(np.max(np.abs(np.diff(p4w))))
    # Smooth transition across due date (< 0.06 per day vs old ~0.95 rule cliff / ~0.24 G0 cliff!)
    assert max_daily_step < 0.06

    # Check >13w tail extrapolation conserves probability mass = 1.0
    p52_extrap = rule.distribution_from_features(x[:2], horizon=52, tail_extrapolation=True)
    assert p52_extrap.shape == (2, 53)
    np.testing.assert_allclose(p52_extrap.sum(axis=1), 1.0, atol=1e-12)
    assert (p52_extrap[:, 13:52] > 0).all()
    assert (np.diff(p52_extrap[:, 13:52], axis=1) <= 0).all()


def test_shared_customer_risk_spawns_correlated_streams_without_rng_cloning():
    frame = pd.DataFrame(
        dict(
            invoice_id=["INV_1", "INV_2", "INV_OTHER"],
            customer_id=["CUST_SAME", "CUST_SAME", "CUST_OTHER"],
            age_days=[15.0, 15.0, 15.0],
            term_days=[30.0, 30.0, 30.0],
            received_fraction=[0.0, 0.0, 0.0],
        )
    )
    p = np.zeros((3, 14))
    p[:, 0] = 0.5
    p[:, -1] = 0.5
    part = PartialModel(
        np.full(6, 0.25),
        tuple(np.array([0.3, 0.7]) for _ in range(6)),
        tuple(np.array([0.5, 0.5]) for _ in range(6)),
        "2025-01-01",
        {"label_contract": LABEL_CONTRACT},
    )
    paths = list(
        iter_cash_paths(
            p,
            frame,
            part,
            [100.0, 100.0, 100.0],
            np.random.default_rng(42),
            4000,
            shared_customer="copula",
        )
    )
    r0, r1, r2 = paths[0].receipts[:, 0], paths[1].receipts[:, 0], paths[2].receipts[:, 0]
    # NOT cloned identical trajectories!
    assert not np.array_equal(r0, r1)
    corr_same = float(np.corrcoef(r0, r1)[0, 1])
    corr_diff = float(np.corrcoef(r0, r2)[0, 1])
    assert 0.35 < corr_same < 0.95
    assert abs(corr_diff) < 0.08
    # Marginal expectation remains exact
    analytic = expected_cash(p[:1], frame.iloc[:1], part)[0, 0] * 100.0
    assert r0.mean() == pytest.approx(analytic, abs=1.5)


def test_sme_train_risk_9_months_and_calibrate_bands_4_monthly_origins():
    # 1. 9-month SME dataset (36 invoices issued 2025-01..2025-05, evaluated 2025-11-15)
    invoices, actions = [], []
    for i, day in enumerate(pd.date_range("2025-01-01", "2025-05-10", freq="3D")):
        invoices.append(
            dict(
                invoice_id=f"SME_INV_{i}",
                customer_id=f"C{i % 6}",
                amount=5_000_000 + (i % 5) * 3_000_000,
                issue_date=str(day.date()),
                due_date=str((day + pd.Timedelta(days=30)).date()),
                known_at=str(day.date()),
            )
        )
        if i % 6 == 0:
            wo_day = str((day + pd.Timedelta(days=120)).date())
            actions.append(
                dict(
                    event_id=f"WO_{i}",
                    invoice_id=f"SME_INV_{i}",
                    kind="write_off",
                    date=wo_day,
                    known_at=wo_day,
                )
            )
    sme_data = dict(invoices=invoices, payments=[], actions=actions)
    risk_bundle = train_risk(sme_data, "2025-11-15")
    assert risk_bundle["status"] == "evaluated"
    assert risk_bundle["horizon_days"] == 180

    # Future write-off after cutoff never leaks
    leaked = deepcopy(sme_data)
    leaked["actions"].append(
        dict(
            event_id="WO_FUT",
            invoice_id="SME_INV_1",
            kind="write_off",
            date="2025-04-01",
            known_at="2026-01-10",
        )
    )
    assert train_risk(leaked, "2025-11-15")["audit_brier"] == risk_bundle["audit_brier"]

    # 2. calibrate_bands activates with 4 matured monthly 13-week forecasts (~7 months)
    cal_data = dict(
        invoices=[],
        payments=[],
        bank=[],
        outflows=[],
        statements=[
            dict(
                statement_id="ST_ALL",
                account="Q",
                start_date="2026-01-01",
                end_date="2026-08-01",
                known_at="2026-08-01",
                opening_balance=100.0,
                closing_balance=100.0,
            )
        ],
    )

    def make_13w_plan(cutoff_str: str):
        base_d = pd.Timestamp(cutoff_str)
        return dict(
            cutoff=cutoff_str,
            created_at=cutoff_str + "T10:00:00+07:00",
            accounts=["Q"],
            model_version="v1",
            band_protocol="settlement-partial-paths-v4",
            opening_balance=100.0,
            cash_floor=0.0,
            assumptions=[],
            alerts=[],
            weeks=[
                dict(
                    week=w,
                    date=str((base_d + pd.Timedelta(weeks=w)).date()),
                    balance=80.0,
                    low=70.0,
                    high=90.0,
                    cash_in=0.0,
                    cash_out=0.0,
                )
                for w in range(1, 14)
            ],
        )

    past_4_months = [
        make_13w_plan(d)
        for d in ("2026-01-15", "2026-02-15", "2026-03-15", "2026-04-15")
    ]
    current_plan = make_13w_plan("2026-08-01")
    calibrate_bands(current_plan, past_4_months, cal_data)
    assert current_plan["calibration_origins"] == 4
    assert current_plan["band_status"] == "calibrated_out_of_sample"
    # Actual balance is 100 vs raw [70, 90] -> excess error is 10 -> calibrated [60, 100]
    assert current_plan["weeks"][0]["low"] == pytest.approx(60.0)
    assert current_plan["weeks"][0]["high"] == pytest.approx(100.0)


def test_t10_scenario_library_uses_balance_not_net_flow_and_t8_promise_blocks_future_leak():
    # 1. models/t10.py: B0 = 500, weekly outflow = 20 -> net = -20 < 0, but balance >= 420 > 0!
    inv = pd.DataFrame({"invoice_id": ["i1"], "customer_id": ["c1"], "amount_open": [100.0]})
    p = np.zeros((1, 13))
    p[0, 5] = 1.0
    sim_args = dict(
        open_df=inv,
        P=p,
        B0=500.0,
        known_out=np.r_[np.full(4, 20.0), np.zeros(9)],
        rev_q=None,
        kernel=np.zeros(17),
        capex_rate=0.0,
        capex_sizes=[],
        n=100,
        seed=7,
    )
    scenarios = scenario_library(sim_args).set_index("scenario")
    # Previously unpacked `_, bal = simulate(**args)` -> minimum_balance = -20, runway_weeks = 0!
    for sc_name, row in scenarios.iterrows():
        assert row["minimum_balance"] >= 420.0, sc_name
        assert row["runway_weeks"] == 13, sc_name
        assert bool(row["censored_at_13w"]) is True, sc_name

    # 2. models/t8_promise.py: future actual_paid_date > T and known_at > T must never leak
    promises_full = pd.DataFrame(
        dict(
            customer_id=["C1", "C1", "C1"],
            firm_id=["F1", "F1", "F1"],
            made_date=pd.to_datetime(["2025-01-01", "2025-01-05", "2025-01-10"]),
            promised_date=pd.to_datetime(["2025-01-05", "2025-01-10", "2025-01-15"]),
            kept=[True, False, True],
            actual_paid_date=pd.to_datetime(["2025-01-06", "2025-06-20", "2025-01-16"]),
            known_at=pd.to_datetime(["2025-01-01", "2025-01-05", "2025-03-01"]),
        )
    )
    # Censor what is genuinely observable at T = 2025-02-01:
    # - row 1's future payment on 2025-06-20 is NaT at 2025-02-01
    # - row 2's promise has known_at = 2025-03-01 > 2025-02-01
    promises_censored = promises_full.iloc[:2].copy()
    promises_censored.loc[1, "actual_paid_date"] = pd.NaT

    query = pd.DataFrame({"customer_id": ["C1"], "firm_id": ["F1"]})
    out_full = PromiseReliability().fit(promises_full, "2025-02-01").predict(query)
    out_cens = PromiseReliability().fit(promises_censored, "2025-02-01").predict(query)
    pd.testing.assert_frame_equal(out_full, out_cens)
    assert out_full["delay"].iloc[0] == pytest.approx(1.0)  # Only Jan 6 - Jan 5 = +1d!


class RareJumboModel:
    def distribution(self, frame, ages, horizon=13):
        p = np.zeros((len(frame), horizon + 1))
        p[:, 0] = 0.05  # <10% chance of settling in week 1 -> P90 receipt = 0!
        p[:, -1] = 0.95
        return p


def test_skewed_jumbo_invoice_surfaces_median_p50_guidance_when_mean_exceeds_p90():
    data = dict(
        invoices=[
            dict(
                invoice_id="JUMBO_1B",
                customer_id="KH_BIG",
                amount=1_000_000_000,
                issue_date="2026-01-01",
                due_date="2026-01-31",
                known_at="2026-01-01",
            )
        ],
        payments=[],
        outflows=[
            dict(
                expense_id="PAYROLL",
                amount=20_000_000,
                date="2026-02-03",
                known_at="2026-02-01",
                category="payroll",
            )
        ],
    )
    part = fit_partial(pd.DataFrame(), "2025-01-01", prior=None)
    bundle = dict(
        model=RareJumboModel(),
        anchor=RareJumboModel(),
        weight=1.0,
        partial=part,
        asof="2026-01-01",
    )
    plan = forecast(data, "2026-02-01", balance=0.0, bundle=bundle, shap_limit=0, simulation_paths=2000)
    w1 = plan["weeks"][0]
    # Expected balance is +30M (+50M - 20M), while P10 = P50 = P90 = -20M!
    assert w1["expected_balance"] == pytest.approx(30_000_000.0)
    assert w1["median_balance"] == pytest.approx(-20_000_000.0)
    assert w1["expected_balance"] > w1["high"]
    # Explicit CFO warning in assumptions advising to steer by median_balance (P50) & [P10, P90]
    assert any("median_balance / P50" in a for a in plan["assumptions"])
    # Shortfall alert fires despite positive expected_balance because >25% of paths fall below 0
    assert any(a["week"] == 1 for a in plan["alerts"])

