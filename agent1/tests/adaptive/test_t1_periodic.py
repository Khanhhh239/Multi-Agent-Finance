"""Production global/local T1: real continuation, causal labels and delayed promotion."""

import json
import pickle
from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest
from agent1.adaptive.compact_t1 import sha256
from agent1.adaptive.landmark_features import (
    FEATURES,
    SCHEMA,
    LandmarkEnsemble,
    LandmarkHazard,
    LandmarkRule,
)
from agent1.adaptive.cash_adapter import LABEL_CONTRACT, fit_partial
from agent1.adaptive.t1_catalog import CATALOG_VERSION, GlobalCatalog
from agent1.adaptive.t1_data import (
    landmarks,
    risk_rows,
    score_audit_snapshot,
    snapshot_for_audit,
)
from agent1.adaptive.t1_update import UpdatePolicy, train_update
from agent1_service.store import Store
from agent1_service.workspace import t1_lifecycle as life
from cryptography.fernet import Fernet
from lightgbm import LGBMClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier


@pytest.fixture
def catalog(tmp_path):
    rng = np.random.default_rng(123)
    x = rng.normal(size=(300, 19))
    x[:, -1] = rng.integers(1, 14, len(x))
    y = (rng.random(len(x)) < 0.18).astype(int)
    neural = make_pipeline(
        StandardScaler(),
        MLPClassifier(
            hidden_layer_sizes=(5,), batch_size=64, max_iter=4, random_state=7
        ),
    )
    neural.fit(x, y)
    lgb = LGBMClassifier(
        n_estimators=5, num_leaves=5, min_child_samples=5, verbosity=-1, n_jobs=1
    ).fit(x, y)
    xgb = XGBClassifier(n_estimators=5, max_depth=2, n_jobs=1).fit(x, y)
    models = {
        "neural": LandmarkHazard(neural, "neural"),
        "lightgbm": LandmarkHazard(lgb, "lightgbm"),
        "xgboost": LandmarkHazard(xgb, "xgboost"),
    }
    models["default"] = LandmarkEnsemble(
        [models["neural"], LandmarkRule("customer", np.full((5, 13), 0.06))],
        [0.75, 0.25],
    )
    root = tmp_path / "globals"
    specs = {}
    for name, model in models.items():
        model.save(root / name, {"available_asof": "2020-01-01", "label_contract": LABEL_CONTRACT})
        specs[name] = {
            "directory": name,
            "metadata_sha256": sha256(root / name / "metadata.json"),
            "available_asof": "2020-01-01",
        }
    np.savez_compressed(root / "replay.npz", x=x, y=y, weights=np.ones(len(y)))
    prior = fit_partial(pd.DataFrame(), "2020-01-01", prior=None)
    (root / "partial.json").write_text(json.dumps(prior.record()), encoding="utf-8")
    meta = {
        "label_contract": LABEL_CONTRACT,
        "partial": {"file": "partial.json", "sha256": sha256(root / "partial.json"), "available_asof": "2020-01-01"},
        "version": CATALOG_VERSION,
        "feature_schema": SCHEMA,
        "features": list(FEATURES),
        "synthetic": True,
        "models": specs,
        "replay": {
            "file": "replay.npz",
            "sha256": sha256(root / "replay.npz"),
            "available_asof": "2020-01-01",
        },
    }
    path = root / "catalog.json"
    path.write_text(json.dumps(meta), encoding="utf-8")
    return GlobalCatalog(path)


def invoice(i, issued, amount=1000000):
    day = pd.Timestamp(issued)
    return {
        "invoice_id": str(i),
        "customer_id": f"C{int(i) % 12}",
        "issue_date": str(day.date()),
        "due_date": str((day + pd.Timedelta(days=30)).date()),
        "known_at": str(day.date()),
        "amount": amount,
    }


def history():
    data = {"invoices": [], "payments": [], "outflows": [], "actions": [], "payment_coverage": [{"complete": True, "start_date": "2022-01-01", "end_date": end, "known_at": end} for end in ("2025-06-04", "2025-10-01", "2025-12-31")]}
    for j, day in enumerate(pd.date_range("2022-01-01", "2025-12-01", freq="7D")):
        for n in range(5):
            i = j * 5 + n
            row = invoice(i, day, 1000000 + (i % 5) * 100000)
            data["invoices"].append(row)
            if i % 5:
                paid = str((day + pd.Timedelta(days=35 + (i % 4) * 7)).date())
                data["payments"].append(
                    {
                        "payment_id": "P" + str(i),
                        "invoice_id": str(i),
                        "payment_date": paid,
                        "known_at": paid,
                        "amount": row["amount"],
                    }
                )
    return data


def test_censored_weeks_never_become_future_negatives():
    frame = pd.DataFrame(np.zeros((2, 18)), columns=FEATURES)
    frame["invoice_id"] = ["1", "2"]
    frame["origin"] = pd.Timestamp("2025-01-01")
    frame["label_end"] = pd.Timestamp("2025-01-11")
    frame["paid_days"] = [np.inf, 9.0]
    frame["followup_days"] = 10
    (x, y, _), receipt = risk_rows(frame)
    assert sorted(zip(x[:, -1], y)) == [(1.0, 0), (1.0, 0)]
    assert receipt["censored_snapshots"] == 2


def test_cash_date_and_knowledge_date_do_not_leak():
    origin = pd.Timestamp("2025-01-01")
    data = {
        "invoices": [invoice(i, "2024-12-01", 100) for i in range(4)],
        "payments": [
            {
                "payment_id": "A",
                "invoice_id": "0",
                "amount": 40,
                "payment_date": "2025-01-03",
                "known_at": "2025-01-20",
            },
            {
                "payment_id": "B",
                "invoice_id": "0",
                "amount": 60,
                "payment_date": "2025-01-10",
                "known_at": "2025-01-11",
            },
            {
                "payment_id": "L",
                "invoice_id": "1",
                "amount": 20,
                "payment_date": "2024-12-30",
                "known_at": "2025-01-02",
            },
            {
                "payment_id": "F",
                "invoice_id": "2",
                "amount": 100,
                "payment_date": "2025-01-04",
                "known_at": "2026-01-01",
            },
        ],
    }
    data["payment_coverage"] = [{"complete": True, "start_date": "2024-01-01", "end_date": "2025-04-02", "known_at": "2025-04-02"}]
    frame = landmarks(data, origin, origin + pd.Timedelta(days=91)).set_index(
        "invoice_id"
    )
    assert "1" not in frame.index
    assert frame.loc["0", "paid_days"] == 9
    assert frame.loc["0", "cash_1"] == pytest.approx(0.4)
    assert frame.loc["0", "cash_2"] == pytest.approx(0.6)
    assert np.isinf(frame.loc["2", "paid_days"])
    modified = deepcopy(data)
    modified["payments"][-1]["amount"] = 9999
    pd.testing.assert_frame_equal(
        frame,
        landmarks(modified, origin, origin + pd.Timedelta(days=91)).set_index(
            "invoice_id"
        ),
    )


def test_claim_revision_is_not_a_cash_label():
    old = invoice(0, "2024-12-01", 100)
    changed = dict(old, amount=80, known_at="2025-02-01")
    data = {
        "invoices": [changed],
        "payments": [],
        "record_history": {"invoices": [old, changed]},
    }
    assert landmarks(data, "2025-01-01", "2025-04-02").empty


def test_three_real_families_share_sample_refit_recent_data_and_keep_globals(catalog):
    data = history()
    before = {k: pickle.dumps(m) for k, m in catalog.models.items()}
    policy = UpdatePolicy(
        lookback_days=365,
        stride_days=56,
        minimum_fit_snapshots=20,
        minimum_fit_invoices=10,
        minimum_validation_snapshots=10,
        minimum_audit_snapshots=10,
        alphas=(0.0, 1.0),
    )
    result = train_update(
        data,
        "2025-12-31",
        catalog=catalog,
        policy=policy,
        grids={
            "neural": ((0.0001, 1),),
            "lightgbm": ((0.02, 2),),
            "xgboost": ((0.02, 2),),
        },
    )
    traces = [t for t in result["training_trace"] if t["stage"] == "selection"]
    assert {t["family"] for t in traces} == {"neural", "lightgbm", "xgboost"}
    assert len({t["sample_sha256"] for t in traces}) == 1
    assert {r["partial_sha256"] for r in result["selection"]} == {result["partial_selection"]["sha256"]}
    assert all(
        "pool" not in r["method"]
        and r["family"] in (None, "neural", "lightgbm", "xgboost")
        for r in result["selection"]
    )
    assert result["audit"]["comparator"] == "incumbent"
    assert result["audit"]["baseline_partial_sha256"] == catalog.partial.digest
    if not result["audit"]["accepted"]:
        assert result["proposal"] is None
        assert "final_data" not in result
        assert all(t["stage"] == "selection" for t in result["training_trace"])
    assert result["windows"]["audit_origin"] == "2025-10-01"
    if "final_data" in result:
        assert result["final_data"]["latest_origin"] == "2025-12-24"
        assert result["final_data"]["censored_snapshots"] > 0
    for k, m in catalog.models.items():
        assert pickle.dumps(m) == before[k]


def test_new_incumbent_is_never_scored_on_older_audit(catalog):
    data = history()
    incumbent = catalog.default_bundle("2025-12-31")
    incumbent["asof"] = "2025-12-01"
    result = train_update(
        data,
        "2025-12-31",
        catalog=catalog,
        incumbent=incumbent,
        policy=UpdatePolicy(
            lookback_days=180,
            stride_days=90,
            minimum_fit_snapshots=5,
            minimum_fit_invoices=5,
            minimum_validation_snapshots=5,
            minimum_audit_snapshots=5,
            alphas=(0.0,),
        ),
        grids={n: ((0.01, 1),) for n in ("neural", "lightgbm", "xgboost")},
    )
    assert not result["audit"]["incumbent_available_at_origin"]
    assert not result["audit"]["accepted"]
    assert result["audit"]["candidate"] is None
    assert result["audit"]["baseline"] is None
    assert result["t1_version"] == incumbent["t1_version"]
    assert result["proposal"]["prospective_eligible"]
    assert not result["proposal"]["historical_audit_passed"]


class FixedModel:
    feature_schema = SCHEMA
    feature_names = FEATURES

    def __init__(self, week):
        self.week = week

    def distribution_from_features(self, x, ages=None, horizon=13):
        p = np.zeros((len(x), horizon + 1))
        p[:, min(self.week, horizon)] = 1.0
        return p


def seed_store(tmp_path, catalog):
    store = Store(tmp_path / "tenant.db", Fernet.generate_key())
    data = {
        "invoices": [invoice(i, "2024-12-01") for i in range(30)],
        "payments": [],
        "outflows": [],
    }
    store.put_many(
        "A",
        {
            "company_datasets": [{"id": "data", "data": data}],
            "company_dataset_active": [{"id": "active", "version": "data"}],
        },
    )
    base = catalog.default_bundle("2025-01-01")
    base.update(
        model=FixedModel(0),
        anchor=FixedModel(0),
        t1_version="incumbent",
        asof="2024-12-01",
    )
    store.put_many(
        "A",
        {
            "company_weights": [dict(id="base", **life.encode(base))],
            "company_models": [life.metadata(base, "base", "2024-12-01T00:00:00")],
            "company_model_active": [{"id": "active", "version": "base"}],
        },
    )
    return store, data


def fake_fit(data, T, progress, *, incumbent, catalog, policy):
    result = deepcopy(incumbent)
    result.update(
        asof=str(T.date()),
        policy={k: v for k, v in policy.__dict__.items()},
        promotion_status="pending_prospective_audit",
        audit={"accepted": False},
        windows={},
        train_n=30,
        validation_n=30,
        proposal={
            "partial": incumbent["partial"],
            "model": FixedModel(13),
            "version": "challenger",
            "asof": str(T.date()),
            "method": "neural_local",
            "historical_audit_passed": True,
        },
    )
    return result


def set_time(monkeypatch, when):
    monkeypatch.setattr(
        life,
        "now",
        lambda: datetime.fromisoformat(when).replace(
            tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")
        ),
    )


def test_periodic_cycle_waits_then_promotes_only_scored_frozen_challenger(
    tmp_path, catalog, monkeypatch
):
    store, _ = seed_store(tmp_path, catalog)
    try:
        set_time(monkeypatch, "2025-01-01T12:00:00")
        first = life.run_cycle(
            store,
            "A",
            "2025-01-01",
            payments_complete=True,
            catalog=catalog,
            trainer=fake_fit,
        )
        assert first["serving_version"] == "incumbent"
        assert first["next_due"] == "2025-01-29"
        assert len(store.get("A", "company_t1_challengers")) == 1
        set_time(monkeypatch, "2025-01-02T12:00:00")
        assert (
            life.run_cycle(
                store,
                "A",
                "2025-01-02",
                payments_complete=True,
                catalog=catalog,
                trainer=fake_fit,
            )["status"]
            == "not_due"
        )
        set_time(monkeypatch, "2025-01-29T12:00:00")
        second = life.run_cycle(
            store,
            "A",
            "2025-01-29",
            payments_complete=True,
            catalog=catalog,
            trainer=fake_fit,
        )
        assert second["serving_version"] == "incumbent"
        set_time(monkeypatch, "2025-04-02T12:00:00")
        final = life.run_cycle(
            store,
            "A",
            "2025-04-02",
            payments_complete=True,
            catalog=catalog,
            trainer=fake_fit,
            policy=UpdatePolicy(minimum_cash_gain=2.0, minimum_audit_snapshots=1000),
        )
        assert final["serving_version"] == "challenger"
        assert final["status"] == "accepted_prospective_audit"
        accepted = [
            r
            for r in store.get("A", "company_t1_challengers")
            if r["status"] == "accepted"
        ]
        assert (
            len(accepted) == 1 and accepted[0]["evaluation"]["challenger"]["score"] == 0
        )
        assert not store.get("B", "company_models")
        loaded, _ = life.load_active(store, "A", "2025-04-02", catalog=catalog)
        assert loaded["model"].week == 13
        assert loaded["t1_parameter_asof"] == "2025-01-01"
        assert loaded["asof"] == "2025-04-02"
        assert loaded["serving_manifest"]["ready_on"] == "2025-04-02"
        assert loaded["serving_manifest"]["t1_version"] == "challenger"
        assert loaded["serving_manifest"]["partial_version"] == loaded["partial"].digest
        assert loaded["t1_provenance"]["local_adaptation"]
    finally:
        store.connection.close()


def test_retroactive_snapshot_cannot_promote():
    data = {"invoices": [invoice(i, "2024-12-01") for i in range(30)], "payments": []}
    snap = snapshot_for_audit(
        data,
        "2025-01-01",
        {"model": FixedModel(0), "partial": fit_partial(pd.DataFrame(), "2020-01-01", prior=None)},
        {"model": FixedModel(13), "partial": fit_partial(pd.DataFrame(), "2020-01-01", prior=None)},
        "a",
        "b",
        "2025-01-02T00:00:00",
    )
    assert (
        score_audit_snapshot(snap, data, "2025-04-02")["status"]
        == "retrospective_snapshot_not_for_promotion"
    )


def test_catalog_hash_and_tenant_artifact_integrity(catalog):
    record = life.encode(catalog.default_bundle("2025-01-01"))
    record["artifact_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="Artifact"):
        life.decode(record)
    meta = json.loads(catalog.path.read_text())
    meta["models"]["neural"]["metadata_sha256"] = "0" * 64
    catalog.path.write_text(json.dumps(meta))
    with pytest.raises(ValueError, match="Hash"):
        GlobalCatalog(catalog.path)


def test_catalog_rejects_unverified_target_and_changed_partial_prior(catalog):
    original = catalog.path.read_text(encoding="utf-8")
    meta = json.loads(original)
    meta["label_contract"] = "pre-cash-calendar"
    catalog.path.write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(ValueError, match="Contract nhãn"):
        GlobalCatalog(catalog.path)
    catalog.path.write_text(original, encoding="utf-8")
    (catalog.path.parent / "partial.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Hash prior partial"):
        GlobalCatalog(catalog.path)


def test_concurrent_activation_does_not_get_overwritten(tmp_path, catalog, monkeypatch):
    store, _ = seed_store(tmp_path, catalog)
    set_time(monkeypatch, "2025-01-01T12:00:00")

    def mutate(*args, **kwargs):
        store.put("A", "company_model_active", [{"id": "active", "version": "other"}])
        return fake_fit(*args, **kwargs)

    try:
        with pytest.raises(ValueError, match="đã đổi"):
            life.run_cycle(
                store,
                "A",
                "2025-01-01",
                payments_complete=True,
                catalog=catalog,
                trainer=mutate,
            )
        assert store.one("A", "company_model_active", "active")["version"] == "other"
        assert not store.get("A", "company_t1_update_state")
        assert len(store.get("A", "company_models")) == 1
    finally:
        store.connection.close()


@pytest.mark.parametrize(
    "changes",
    [
        {"half_life_days": float("nan")},
        {"ibs_ratio": float("inf")},
        {"alphas": (float("nan"),)},
        {"validation_offsets_days": (120,)},
        {"validation_offsets_days": (182, 182)},
        {"interval_days": 0},
        {"lookback_days": 731},
    ],
)
def test_invalid_update_policy_is_rejected(changes):
    with pytest.raises(ValueError):
        UpdatePolicy(**changes)


def test_cold_history_returns_global_and_does_not_hash_future_rows(catalog):
    data = {"invoices": [invoice(0, "2025-01-01")], "payments": []}
    first = train_update(data, "2025-02-01", catalog=catalog)
    second = train_update(
        dict(data, invoices=data["invoices"] + [invoice(1, "2026-01-01")]),
        "2025-02-01",
        catalog=catalog,
    )
    assert first["promotion_status"] == "kept_incumbent"
    assert first["train_n"] == 0
    assert first["dataset_hash"] == second["dataset_hash"]
    assert first["t1_version"] == second["t1_version"]
    assert first["serving_manifest"] == second["serving_manifest"]
    assert first["serving_manifest"]["ready_on"] == "2020-01-01"
    assert first["serving_manifest"]["partial_version"] == catalog.partial.digest


def test_new_receipt_reforecasts_remaining_debt_without_retraining(tmp_path, catalog, monkeypatch):
    from agent1_service.api import create_app
    from fastapi.testclient import TestClient
    from agent1.adaptive import t1_update

    monkeypatch.setenv("AGENT1_T1_GLOBAL_CATALOG", str(catalog.path))
    def forbidden(*args, **kwargs):
        pytest.fail("A payment/forecast must not train T1")
    monkeypatch.setattr(t1_update, "train_update", forbidden)
    monkeypatch.setattr(life, "train_update", forbidden)
    app = create_app(state_dir=tmp_path/"api", key_dir=tmp_path/"keys", token="receipt-test", firm_id="A")
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer receipt-test"
        store = app.state.store
        data = dict(invoices=[invoice(0, "2024-12-01", 100)], payments=[], outflows=[])
        def publish(identifier):
            store.put_many("A", {"company_datasets": [dict(id=identifier, data=deepcopy(data))],
                                  "company_dataset_active": [dict(id="active", version=identifier)]})
        publish("before")
        request = dict(cutoff="2025-01-01", opening_balance=0, payments_complete=True, shap_limit=0)
        before = client.post("/v1/predict", json=request)
        assert before.status_code == 200, before.text
        data["payments"] = [dict(payment_id="new", invoice_id="0", amount=40,
                                 payment_date="2025-01-01", known_at="2025-01-01")]
        publish("after")
        after = client.post("/v1/predict", json=request)
        assert after.status_code == 200, after.text
        assert before.json()["outstanding"] == 100 and after.json()["outstanding"] == 60
        assert before.json()["model_version"] == after.json()["model_version"]
        assert not store.get("A", "company_t1_update_runs")


def test_api_cycle_uses_same_registry_and_ignores_removed_local_artifact(
    tmp_path, catalog, monkeypatch
):
    import time

    from agent1.adaptive import methods
    from agent1.adaptive.data import fingerprint
    from agent1_service.api import create_app
    from fastapi.testclient import TestClient

    assert not any(
        hasattr(methods, name)
        for name in ("Method", "DistributionEnsemble", "CATALOG", "train_legacy")
    )
    monkeypatch.setenv("AGENT1_T1_GLOBAL_CATALOG", str(catalog.path))
    set_time(monkeypatch, "2025-01-01T12:00:00")
    app = create_app(
        state_dir=tmp_path / "api",
        key_dir=tmp_path / "keys",
        token="periodic-test",
        firm_id="A",
    )
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer periodic-test"
        store = app.state.store
        data = {
            "invoices": [invoice(i, "2024-12-01") for i in range(30)],
            "payments": [],
            "outflows": [],
        }
        digest = fingerprint(data)
        store.put_many(
            "A",
            {
                "company_datasets": [{"id": digest, "data": data}],
                "company_dataset_active": [{"id": "active", "version": digest}],
                "company_models": [
                    {
                        "id": "old",
                        "artifact_id": "old",
                        "algorithm_version": "company-bag-v3",
                        "dataset_hash": digest,
                        "created_at": "2024-12-01",
                    }
                ],
                "company_weights": [{"id": "old", "artifact": "not even a pickle"}],
                "company_model_active": [{"id": "active", "version": "old"}],
            },
        )
        assert client.get("/v1/workspace").json()["versions"] == []
        assert client.post("/v1/models/old/activate").status_code == 422
        response = client.post(
            "/v1/predict",
            json={
                "cutoff": "2025-01-01",
                "opening_balance": 0,
                "payments_complete": True,
                "shap_limit": 0,
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["model_version"].startswith("global:")
        assert (
            client.post("/v1/t1/updates", json={"asof": "2025-01-01"}).status_code
            == 422
        )
        response = client.post(
            "/v1/t1/updates", json={"asof": "2025-01-01", "payments_complete": True}
        )
        assert response.status_code == 202, response.text
        end = time.monotonic() + 30
        while time.monotonic() < end:
            state = client.get("/v1/workspace").json()
            if state["jobs"][0]["status"] in ("completed", "failed"):
                break
            time.sleep(0.02)
        assert state["jobs"][0]["status"] == "completed", state["jobs"]
        assert state["active_version"] == state["versions"][0]["id"]
        assert state["versions"][0]["algorithm_version"] == "t1-partial-bundle-v2"
        status = client.get("/v1/t1/updates")
        assert (
            status.status_code == 200
            and status.json()["state"]["next_due"] == "2025-01-29"
        )
        assert '"snapshot":' not in status.text and '"artifact":' not in status.text
        saved = client.post(
            "/v1/predict",
            json={
                "cutoff": "2025-01-01",
                "opening_balance": 0,
                "payments_complete": True,
                "shap_limit": 1,
            },
        ).json()
        assert (
            saved["collections"][0]["payment_explanation"]["model_version"]
            == saved["model_version"]
        )
        assert client.get("/v1/forecasts/" + saved["id"]).json() == saved
