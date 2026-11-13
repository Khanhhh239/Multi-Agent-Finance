"""Dated accounting parity, real continuation and T6 budget contracts."""
from copy import deepcopy

import numpy as np
import pandas as pd
import pytest
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from agent1.adaptive.compact_t1 import Ledger, workspace_context
from agent1.adaptive.landmark_features import FEATURES, LandmarkHazard, prepare_features
from agent1.adaptive.ledger_bridge import ledger_context, workspace_data
from agent1.adaptive.landmark_adaptation import continue_neural
from experiments.t1_compact.historical_workspace import forecast, Method
from agent1.adaptive.data import observed, as_of
from agent1_service.workspace.api import Prediction
from agent1_service.ingest.invoices import _date
from experiments.t1_compact.aligned_data import calendar_settlements,correct_labels


def dated_ledger():
    invoices = pd.DataFrame([dict(invoice_id=f"I{i}", customer_id=f"C{i%3}", amount=100000,
        issue_date="2024-01-01", due_date="2024-02-01", known_at="2024-01-01", written_off_at=pd.NaT)
        for i in range(8)])
    payments = pd.DataFrame([
        dict(invoice_id="I0", date="2024-02-01", known_at="2024-03-01", amount=40000),
        dict(invoice_id="I0", date="2024-02-10", known_at="2024-02-11", amount=40000),
        dict(invoice_id="I1", date="2024-02-01", known_at="2024-02-02", amount=100000),
    ])
    credits = pd.DataFrame([dict(invoice_id="I0", date="2024-02-20", known_at="2024-02-21", amount=20000)])
    return Ledger(invoices, payments, credits)


def test_cash_paid_target_uses_actual_cash_order_and_excludes_noncash_closure():
    inv=pd.DataFrame([dict(invoice_id="A",customer_id="C",amount=100000,
        issue_date="2024-01-01",due_date="2024-02-01",known_at="2024-01-01")])
    pay=pd.DataFrame([dict(invoice_id="A",date="2024-02-01",known_at="2024-03-01",amount=40000),
                      dict(invoice_id="A",date="2024-02-10",known_at="2024-02-11",amount=60000)])
    ledger=Ledger(inv,pay)
    assert calendar_settlements(ledger,"2024-03-02")["A"]==pd.Timestamp("2024-02-10")
    assert calendar_settlements(ledger,"2024-02-20").empty
    rows=pd.DataFrame(dict(invoice_id=["A"],origin=[pd.Timestamp("2024-01-15")]))
    assert correct_labels(rows,ledger,"2024-03-02").paid_days.iloc[0]==26
    assert calendar_settlements(dated_ledger(),"2024-04-01").get("I0") is None


@pytest.mark.parametrize("cutoff", ["2024-01-01", "2024-02-02", "2024-02-21", "2024-03-01", "2024-04-01"])
def test_vector_adapter_matches_canonical_features_even_after_noncash_closure(cutoff):
    ledger = dated_ledger()
    canonical = workspace_context(workspace_data(ledger), cutoff).set_index("invoice_id").sort_index()
    fast = ledger_context(ledger, cutoff).set_index("invoice_id").sort_index()
    for column in ["amount", "received", "remaining_amount", "receipt_count", "received_28d"]:
        np.testing.assert_array_equal(canonical[column], fast[column])
    for column in ["known_at", "settled", "settled_known_at", "last_receipt", "written_off_at"]:
        pd.testing.assert_series_equal(canonical[column].astype("datetime64[ns]"), fast[column].astype("datetime64[ns]"), check_names=False)
    targets = canonical[canonical.remaining_amount > .01].reset_index()
    fast_targets = fast.loc[targets.invoice_id].reset_index()
    np.testing.assert_array_equal(prepare_features(targets, canonical.reset_index(), cutoff),
                                  prepare_features(fast_targets, fast.reset_index(), cutoff))


def test_neural_continuation_changes_weights_without_mutating_global_or_scaler():
    rng = np.random.default_rng(3)
    x = rng.normal(size=(150, 19))
    y = (x[:, 0]>0).astype(int)
    estimator = make_pipeline(StandardScaler(), MLPClassifier(hidden_layer_sizes=(4,), max_iter=80,
        random_state=5, tol=.01, n_iter_no_change=3))
    estimator.fit(x, y)
    model = LandmarkHazard(estimator, "neural")
    before = deepcopy(estimator.steps[-1][1].coefs_)
    adapted = continue_neural(model, x[:100], 1-y[:100], np.ones(100),
                              (x[100:], y[100:], np.ones(50)), epochs=5)
    np.testing.assert_array_equal(adapted.booster[0].mean_, estimator[0].mean_)
    assert any(not np.array_equal(a, b) for a, b in zip(adapted.booster[-1].coefs_, before))
    for a, b in zip(estimator[-1].coefs_, before):
        np.testing.assert_array_equal(a, b)
    assert adapted.booster[-1]._optimizer.learning_rate_init == .0001


def test_local_neural_control_handles_one_class_without_inventing_paid_class():
    from experiments.t1_compact.compare_adaptation import fit_scratch
    from agent1.adaptive.landmark_features import LandmarkRule
    frame=pd.DataFrame(np.ones((70,18)),columns=FEATURES)
    frame["world"],frame["firm"],frame["origin"]="W","F",pd.Timestamp("2024-01-01")
    frame["invoice_id"]=[str(i) for i in range(70)]
    frame["paid_days"]=np.inf
    model,messages=fit_scratch(None,frame,400)
    assert isinstance(model,LandmarkRule) and messages
    np.testing.assert_allclose(model.distribution_from_features(frame[list(FEATURES)]).sum(1),1.,atol=1e-12)


def portfolio():
    return dict(invoices=[dict(invoice_id=f"I{i}", customer_id=f"C{i%4}", amount=100000+i*1000,
                issue_date="2024-01-01", due_date="2024-03-01", known_at="2024-01-01") for i in range(45)],
                payments=[], actions=[], outflows=[])


@pytest.mark.parametrize("policy", ["amount", "amount_at_risk"])
def test_compute_budgets_preserve_all_invoices_queue_and_analytic_cash(policy):
    data = portfolio()
    method = Method("customer").fit(observed(data, "2024-02-01"), "2024-02-01")
    bundle = dict(model=method, anchor=method, weight=1., asof="2024-02-01", collection_policy=policy)
    a = forecast(data, "2024-02-01", 0, bundle, simulation_paths=400, shap_limit=0)
    b = forecast(data, "2024-02-01", 0, bundle, simulation_paths=1000, shap_limit=10)
    assert a["open_invoices"] == b["open_invoices"] == 45
    assert len(a["collections"]) == len(b["collections"]) == 30
    assert [r["invoice_id"] for r in a["collections"]] == [r["invoice_id"] for r in b["collections"]]
    for x, y in zip(a["weeks"], b["weeks"]):
        assert (x["cash_in"],x["cash_out"],x["balance"]) == (y["cash_in"],y["cash_out"],y["balance"])
    assert sum(r["payment_explanation"]["status"]=="available" for r in b["collections"]) == 10
    assert all(r["payment_explanation"]["status"]=="deferred" for r in a["collections"])
    if policy == "amount_at_risk":
        assert all(r["ranking_explanation"]["probability_explanation"]["status"]=="deferred" for r in b["collections"][10:])


def test_budget_validation_and_daily_intraday_asof():
    assert Prediction(cutoff="2024-01-01", opening_balance=0).simulation_paths == 1000
    with pytest.raises(ValueError):
        Prediction(cutoff="2024-01-01", opening_balance=0, simulation_paths=True)
    for kwargs in [dict(simulation_paths=0), dict(shap_limit=31), dict(simulation_seed=-1)]:
        with pytest.raises(ValueError):
            forecast(portfolio(), "2024-02-01", 0, **kwargs)
    assert _date(None) is None
    history = dict(invoices=[dict(invoice_id="A", known_at="2024-01-01", known_at_time="2024-01-01T10:00:00+07:00")])
    data = dict(invoices=[], record_history=history)
    assert len(as_of(data,"2024-01-01")["invoices"]) == 1
    assert not as_of(data,"2024-01-01T09:00:00+07:00")["invoices"]


def test_research_loader_requires_acceptance_and_intact_evidence(tmp_path):
    import json
    from agent1.adaptive.compact_t1 import load_research_t1_bundle
    (tmp_path / "release.json").write_text(json.dumps(dict(research_integration_accepted=False)), encoding="utf-8")
    with pytest.raises(ValueError, match="chưa đạt"):
        load_research_t1_bundle(tmp_path, "2026-01-01")
    (tmp_path / "release.json").write_text(json.dumps(dict(research_integration_accepted=True,
        required_hashes={"audit.json": "wrong"})), encoding="utf-8")
    (tmp_path / "audit.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="thay đổi"):
        load_research_t1_bundle(tmp_path, "2026-01-01")


def test_research_t1_preserves_other_company_learners_and_serves_full_cash(tmp_path):
    import json
    from agent1.adaptive.compact_t1 import sha256
    from agent1.adaptive.landmark_features import LandmarkRule, LandmarkEnsemble
    from agent1.adaptive.compact_t1 import load_research_t1_bundle
    model = LandmarkEnsemble([LandmarkRule("survival",np.full((5,13),.1))],[1.])
    model.save(tmp_path/"artifact",dict(available_asof="2024-01-01",data_fingerprint="data",source_sha256="code"))
    release = dict(research_integration_accepted=True, artifact_directory="artifact",
        feature_context_contract="workspace-accounting-landmark18-v1",
        required_hashes={"artifact/metadata.json":sha256(tmp_path/"artifact/metadata.json")})
    (tmp_path/"release.json").write_text(json.dumps(release),encoding="utf-8")
    bundle = load_research_t1_bundle(tmp_path,"2024-02-01",dict(operating={"kept":True},collection_policy="amount"))
    assert bundle["operating"] == {"kept":True}
    plan = forecast(portfolio(),"2024-02-01",0,bundle,shap_limit=0)
    assert plan["open_invoices"] == 45
    assert plan["t1_provenance"]["source"] == "research_global_refit"
    assert plan["weeks"][0]["cash_in"] > 0
    with pytest.raises(ValueError,match="after"):
        load_research_t1_bundle(tmp_path,"2023-12-01")


def test_api_catalog_replaces_removed_research_allowlist_and_keeps_budget(tmp_path,monkeypatch):
    import json
    from fastapi.testclient import TestClient
    from agent1_service.api import create_app
    from agent1.adaptive.data import fingerprint
    from agent1.adaptive.compact_t1 import sha256
    from agent1.adaptive.landmark_features import LandmarkRule,LandmarkEnsemble
    directory=tmp_path/"research"
    model=LandmarkEnsemble([LandmarkRule("survival",np.full((5,13),.1))],[1.])
    model.save(directory/"artifact",dict(available_asof="2024-01-01",data_fingerprint="data",source_sha256="code"))
    (directory/"release.json").write_text(json.dumps(dict(research_integration_accepted=True,
        artifact_directory="artifact",feature_context_contract="workspace-accounting-landmark18-v1",
        required_hashes={"artifact/metadata.json":sha256(directory/"artifact/metadata.json")})),encoding="utf-8")
    monkeypatch.setenv("AGENT1_T1_RESEARCH_RUN",str(directory))
    monkeypatch.setenv("AGENT1_T1_RESEARCH_FIRMS","TEST")
    app=create_app(state_dir=tmp_path/"state",key_dir=tmp_path/"keys",token="local-test",firm_id="TEST")
    data=portfolio()
    with TestClient(app) as client:
        client.headers["Authorization"]="Bearer local-test"
        digest=fingerprint(data)
        app.state.store.put("TEST","company_datasets",[{"id":digest,"data":data}])
        app.state.store.put("TEST","company_dataset_active",[{"id":"active","version":digest}])
        response=client.post("/v1/predict",json=dict(cutoff="2024-08-01",opening_balance=0,
            payments_complete=True,simulation_paths=1000,shap_limit=2))
        assert response.status_code==200,response.text
        plan=response.json()
        assert plan["model_version"].startswith("global:")
        assert plan["compute_budget"]["simulation_paths"]==1000
        assert len(plan["collections"])==30
        assert plan["collections"][0]["payment_explanation"]["feature_schema"]=="t1-landmark-18-v2"
        assert plan["collections"][2]["payment_explanation"]["status"]=="deferred"
        monkeypatch.setenv("AGENT1_T1_RESEARCH_FIRMS","OTHER")
        response=client.post("/v1/predict",json=dict(cutoff="2024-08-01",opening_balance=0,payments_complete=True,shap_limit=0))
        assert response.status_code==200,response.text
        assert response.json()["t1_provenance"]["source"] == "global_catalog"
        assert response.json()["model_version"] == plan["model_version"]
