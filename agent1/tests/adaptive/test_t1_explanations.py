"""Faithfulness checks, not evidence of real-world predictive quality."""

import base64
import pickle
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np
import pandas as pd
import pytest
from agent1.adaptive.data import fingerprint, observed
from agent1.adaptive.explanations import explain_collections, shapley_values
from agent1.adaptive.methods import (
    CATALOG,
    DistributionEnsemble,
    Method,
    forecast,
)
from agent1_service.api import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def data():
    book = {"invoices": [], "payments": [], "outflows": []}
    for i in range(100):
        day = date(2025, 1, 1) + timedelta(days=i)
        amount = 100_000 * (i % 7 + 1)
        book["invoices"].append(
            {
                "invoice_id": f"I{i:03}",
                "customer_id": f"C{i % 5}",
                "amount": amount,
                "issue_date": str(day),
                "known_at": str(day),
                "due_date": str(day + timedelta(days=14 + i % 3 * 7)),
                "currency": "VND",
            }
        )
        if i < 75 and i % 4:
            paid = day + timedelta(days=7 + i % 5 * 7)
            book["payments"].append(
                {
                    "payment_id": f"P{i}",
                    "invoice_id": f"I{i:03}",
                    "amount": amount,
                    "payment_date": str(paid),
                    "known_at": str(paid),
                }
            )
    return book


def test_exact_shapley_recovers_linear_effects_and_splits_interaction():
    masks = np.arange(8)
    x = (masks[:, None] & (1 << np.arange(3))) != 0
    linear = 0.2 + x @ np.array([0.1, -0.05, 0.3])
    interaction = 0.2 + 0.4 * (x[:, 0] & x[:, 1])
    actual = shapley_values(np.array([linear, interaction]), 3)
    np.testing.assert_allclose(actual, [[0.1, -0.05, 0.3], [0.2, 0.2, 0]], atol=1e-15)


def assert_business_reviews(row):
    for factor in row["payment_explanation"]["factors"]:
        assert "comparison" not in factor
        review = factor["business_review"]
        assert review["feature"] == factor["feature"]
        assert review["value"] == factor["value"]
        if factor["feature"] in ("term_days", "customer_history_count"):
            assert review["status"] == "context_only"
        if review["status"] == "eligible":
            assert factor["stability"]["status"] == "stable"
            assert abs(factor["contribution_pp"]) >= 1


@pytest.mark.parametrize("name", [r[0] for r in CATALOG if r[0] != "blend"])
def test_every_t1_method_explains_the_final_blended_probability(
    data, name, monkeypatch
):
    monkeypatch.setenv("AGENT1_NEURAL_MAX_ITER", "2")
    clock = pd.Timestamp("2025-05-01")
    frame = observed(data, clock)
    opened = frame[frame.remaining_amount > 0.01].copy()
    model = Method(name).fit(frame, clock)
    anchor = Method("customer").fit(frame, clock)
    ages = (clock - opened.issue_date).dt.days.to_numpy()
    probability = 0.35 * model.distribution(opened, ages)[:, :4].sum(1)
    probability += 0.65 * anchor.distribution(opened, ages)[:, :4].sum(1)
    expected_baseline = probability.mean()
    rows = [
        {
            "invoice_id": str(r.invoice_id),
            "customer_id": str(r.customer_id),
            "payment_probability_4w": float(probability[i]),
        }
        for i, r in enumerate(opened.iloc[:3].itertuples())
    ]
    explain_collections(rows, opened, [(0.35, model), (0.65, anchor)], clock)
    for row in rows:
        e = row["payment_explanation"]
        assert e["status"] == "available" and e["horizon_weeks"] == 4
        assert e["probability"] == row["payment_probability_4w"]
        assert e["baseline_probability"] == pytest.approx(expected_baseline, abs=1e-10)
        assert e["baseline_probability"] + sum(
            f["contribution"] for f in e["factors"]
        ) == pytest.approx(e["probability"], abs=1e-10)
        assert e["additivity_error"] < 1e-10
        assert (
            e["units"] == "probability"
            and e["contribution_units"] == "percentage_points"
        )
        assert len(e["factors"]) == 6 and e["reference"]["count"] == len(opened)
        assert e["reference"]["selection"] == "census"
        assert e["stability"]["checked"] and e["stability"]["sample_count"] == 3
        assert all("stability" in f for f in e["factors"])
        amount = next(f for f in e["factors"] if f["feature"] == "amount")
        assert amount["value"] == int(
            opened.set_index("invoice_id").loc[row["invoice_id"], "amount"]
        )
        assert [m["weight"] for m in e["members"]] == [0.35, 0.65]
        assert_business_reviews(row)


def test_nested_pool_and_customer_specific_scenario_keep_four_week_target(data):
    clock = pd.Timestamp("2025-05-01")
    frame = observed(data, clock)
    logistic = Method("logistic").fit(frame, clock)
    survival = Method("survival").fit(frame, clock)
    anchor = Method("customer").fit(frame, clock)
    pool = DistributionEnsemble([logistic, DistributionEnsemble([survival, anchor])])
    bundle = {"model": pool, "anchor": anchor, "weight": 0.6, "asof": "2025-05-01"}
    short = forecast(
        data,
        str(clock.date()),
        0,
        bundle,
        delay_days=14,
        delay_customer="C1",
        horizon_weeks=1,
    )
    long = forecast(
        data,
        str(clock.date()),
        0,
        bundle,
        delay_days=14,
        delay_customer="C1",
        horizon_weeks=26,
    )
    assert short["collections"] == long["collections"]
    assert len(short["weeks"]) == 1 and len(long["weeks"]) == 26
    for row in short["collections"]:
        e = row["payment_explanation"]
        assert e["scenario_shift_weeks"] == (2 if row["customer_id"] == "C1" else 0)
        assert e["probability"] == pytest.approx(
            e["reconstructed_probability"], abs=1e-10
        )
        assert len(e["members"]) == 4
        assert_business_reviews(row)
    # A four-week shift makes settlement within four weeks impossible for affected invoices.
    delayed = forecast(data, str(clock.date()), 0, bundle, delay_days=28)
    for row in delayed["collections"]:
        e = row["payment_explanation"]
        assert e["probability"] == 0 and e["baseline_probability"] == 0
        assert all(f["contribution"] == 0 for f in e["factors"])


def test_reference_is_deterministic_and_ignores_future_data(data):
    first = forecast(data, "2025-05-01", 0)
    reordered = deepcopy(data)
    reordered["invoices"].reverse()
    reordered["payments"].reverse()
    second = forecast(reordered, "2025-05-01", 0)
    a = {r["invoice_id"]: r["payment_explanation"] for r in first["collections"]}
    b = {r["invoice_id"]: r["payment_explanation"] for r in second["collections"]}
    assert a == b
    future = deepcopy(data)
    future["payments"].append(
        {
            "payment_id": "FUTURE",
            "invoice_id": "I099",
            "amount": 200_000,
            "payment_date": "2025-06-01",
            "known_at": "2025-06-01",
        }
    )
    assert forecast(future, "2025-05-01", 0) == first


def test_single_invoice_and_empty_cohort_are_honest(data):
    data["invoices"] = data["invoices"][-1:]
    data["payments"] = []
    plan = forecast(data, "2025-05-01", 0)
    e = plan["collections"][0]["payment_explanation"]
    assert e["reference"]["count"] == 1
    assert all(abs(f["contribution"]) < 1e-12 for f in e["factors"])
    assert "một hóa đơn" in e["limitations"][-1]
    data["payments"] = [
        {
            "payment_id": "SETTLED",
            "invoice_id": "I099",
            "amount": 200_000,
            "payment_date": "2025-04-30",
            "known_at": "2025-04-30",
        }
    ]
    assert forecast(data, "2025-05-01", 0)["collections"] == []


def test_saved_explanation_keeps_model_and_data_provenance(tmp_path, data):
    app = create_app(
        state_dir=tmp_path / "data",
        key_dir=tmp_path / "keys",
        token="test-explain",
        firm_id="TEST",
    )
    with TestClient(app) as client:
        store = app.state.store
        digest = fingerprint(data)
        store.put("TEST", "company_datasets", [{"id": digest, "data": data}])
        store.put(
            "TEST", "company_dataset_active", [{"id": "active", "version": digest}]
        )
        clock = pd.Timestamp("2025-05-01")
        frame = observed(data, clock)
        model = Method("logistic").fit(frame, clock)
        anchor = Method("customer").fit(frame, clock)
        bundle = {
            "asof": "2025-05-01",
            "weight": 0.5,
            "model": model,
            "anchor": anchor,
            "collection_policy": "amount_at_risk",
        }
        store.put(
            "TEST",
            "company_weights",
            [{"id": "W1", "artifact": base64.b64encode(pickle.dumps(bundle)).decode()}],
        )
        store.put(
            "TEST",
            "company_models",
            [{"id": "MODEL1", "artifact_id": "W1", "dataset_hash": digest}],
        )
        store.put(
            "TEST", "company_model_active", [{"id": "active", "version": "MODEL1"}]
        )
        headers = {"Authorization": "Bearer test-explain"}
        result = client.post(
            "/v1/predict",
            headers=headers,
            json={
                "cutoff": "2025-05-01",
                "opening_balance": 0,
                "payments_complete": True,
            },
        )
        assert result.status_code == 200, result.text
        plan = result.json()
        assert plan["explanation_references"]
        for row in plan["collections"]:
            for explanation in (
                row["payment_explanation"],
                row["ranking_explanation"]["probability_explanation"],
            ):
                snapshot = plan["explanation_references"][
                    explanation["reference"]["hash"]
                ]
                assert snapshot["cutoff"] == "2025-05-01"
                assert len(snapshot["sample_sets"]) == 4
                assert snapshot["selection"] == "census"
                for member in snapshot["prepared_inputs"]:
                    assert len(member["values"]) == len(snapshot["invoice_ids"])
                assert all(
                    sum(s["weights"]) == pytest.approx(1)
                    for s in snapshot["sample_sets"]
                )
        assert all(
            r["payment_explanation"]["model_version"] == "MODEL1"
            and r["payment_explanation"]["dataset_hash"] == digest
            for r in plan["collections"]
        )
        assert plan["collection_ranking"]["model_version"] == "MODEL1"
        assert plan["collection_ranking"]["dataset_hash"] == digest
        for row in plan["collections"]:
            ranking = row["ranking_explanation"]
            assert ranking["displayed_model_version"] == "MODEL1"
            assert ranking["probability_source"]["model_version"] is None
            assert ranking["probability_source"]["dataset_hash"] == digest
            assert ranking["probability_explanation"]["model_version"] is None
            assert ranking["probability_explanation"]["dataset_hash"] == digest
        store.put(
            "TEST", "company_model_active", [{"id": "active", "version": "OTHER"}]
        )
        store.put(
            "TEST", "company_dataset_active", [{"id": "active", "version": "NEW-DATA"}]
        )
        assert client.get("/v1/forecasts/" + plan["id"], headers=headers).json() == plan
        assert client.get("/v1/forecasts/" + plan["id"]).status_code == 401


def test_browser_opens_saved_explanation_on_desktop_and_mobile(tmp_path, data):
    playwright = pytest.importorskip("playwright.sync_api")
    chrome = Path("C:/Program Files/Google/Chrome/Application/chrome.exe")
    if not chrome.exists():
        pytest.skip("Chrome is not installed")
    app = create_app(
        state_dir=tmp_path / "data",
        key_dir=tmp_path / "keys",
        token="browser-test-only",
        firm_id="TEST",
    )
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer browser-test-only"
        digest = fingerprint(data)
        app.state.store.put("TEST", "company_datasets", [{"id": digest, "data": data}])
        app.state.store.put(
            "TEST", "company_dataset_active", [{"id": "active", "version": digest}]
        )
        response = client.post(
            "/v1/predict",
            json={
                "cutoff": "2025-05-01",
                "opening_balance": 0,
                "payments_complete": True,
            },
        )
        assert response.status_code == 200, response.text
        plan = response.json()
        selected = next(
            i
            for i, row in enumerate(plan["collections"])
            if row["payment_explanation"]["plausibility"]["status"] == "no_warning"
            and any(
                f["business_review"]["status"] == "eligible"
                for f in row["payment_explanation"]["factors"]
            )
        )
        # Persist hostile text as data to exercise the real browser renderer.
        next(
            f
            for f in plan["collections"][selected]["payment_explanation"]["factors"]
            if f["business_review"]["status"] == "eligible"
        )["label"] = "<img src=x onerror=alert(1)>"
        for factor in plan["collections"][selected]["payment_explanation"]["factors"]:
            if factor["stability"]["status"] != "stable":
                factor["label"] = "Yếu tố phải loại " + factor["feature"]
        app.state.store.put("TEST", "company_predictions", [plan])
        output = (
            Path(__file__).resolve().parents[2]
            / "outputs/ui_checks/business_evidence_review"
        )
        output.mkdir(parents=True, exist_ok=True)

        def proxy(route):
            request = route.request
            url = urlsplit(request.url)
            result = client.request(
                request.method,
                url.path + ("?" + url.query if url.query else ""),
                content=request.post_data_buffer,
                headers={
                    "Content-Type": request.headers.get(
                        "content-type", "application/json"
                    )
                },
            )
            route.fulfill(
                status=result.status_code,
                body=result.content,
                headers={
                    k: v
                    for k, v in result.headers.items()
                    if k not in ("content-length", "content-encoding")
                },
            )

        with playwright.sync_playwright() as p:
            browser = p.chromium.launch(executable_path=str(chrome), headless=True)
            try:
                page = browser.new_page(viewport={"width": 1500, "height": 960})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.route("**/*", proxy)
                page.goto("http://testserver/workspace#forecast")
                playwright.expect(page.locator("#connection-state")).to_contain_text(
                    "Đã kết nối"
                )
                page.locator(".history-menu > summary").click()
                page.locator("#saved-plans").click()
                page.locator("#plans-list button").first.click()
                playwright.expect(page.locator("#forecast-period")).to_contain_text(
                    "13 tuần"
                )
                button = page.locator(
                    f'#collections-table button[aria-controls="payment-explanation-{selected}"]'
                )
                button.click()
                dialog = page.locator(f"#payment-explanation-{selected}")
                panel = dialog.locator(".t1-explanation")
                playwright.expect(panel).to_be_visible()
                assert panel.locator("details").count() == 0
                assert "Mức tham chiếu" not in panel.inner_text()
                assert "Phân rã SHAP" not in panel.inner_text()
                assert "Yếu tố phải loại" not in panel.inner_text()
                assert "Ảnh hưởng chưa ổn định" not in panel.inner_text()
                assert 0 < panel.locator(".t1-drivers tbody tr").count() <= 3
                assert panel.locator(".t1-comparison").count() == 0
                assert "Đối chiếu giả định" not in panel.inner_text()
                assert "Chiều ảnh hưởng trong dự báo" in panel.inner_text()
                assert panel.locator(".t1-business-evidence").count() > 0
                assert "<img src=x onerror=alert(1)>" in panel.inner_text()
                assert panel.locator("img").count() == 0
                for width in (1500, 390):
                    page.set_viewport_size({"width": width, "height": 960})
                    page.wait_for_function(
                        "() => document.documentElement.scrollWidth <= innerWidth",
                        timeout=3000,
                    )
                    dialog.screenshot(path=str(output / f"explanation_{width}.png"))
                    overflow = page.evaluate("""() => [...document.querySelectorAll('body *')]
                        .map(e => ({tag:e.tagName, id:e.id, cls:e.className, right:e.getBoundingClientRect().right,
                                    width:e.getBoundingClientRect().width}))
                        .filter(e => e.right > innerWidth + 1 && e.width > 0).slice(0, 15)""")
                    assert page.evaluate(
                        "document.documentElement.scrollWidth <= innerWidth"
                    ), overflow
                    assert panel.bounding_box()["width"] <= width
                page.get_by_role("button", name="Đóng giải thích", exact=True).click()
                playwright.expect(dialog).to_be_hidden()
                button.click()
                page.keyboard.press("Escape")
                playwright.expect(dialog).to_be_hidden()
                playwright.expect(button).to_have_attribute("aria-expanded", "false")
                # The actual first invoice has unsupported hybrids: show no reasons.
                page.locator(
                    '#collections-table button[aria-controls="payment-explanation-0"]'
                ).click()
                empty = page.locator("#payment-explanation-0 .t1-explanation")
                playwright.expect(empty).to_contain_text("Chưa đủ cơ sở")
                assert empty.locator("table, details").count() == 0
                assert not errors, errors
            finally:
                browser.close()
