"""Ranking explanations must reproduce policy scores, not invent action effects."""

import base64
import pickle
from copy import deepcopy
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np
import pandas as pd
import pytest
from agent1.adaptive.collection_explanations import rank_with_explanations
from agent1.adaptive.data import fingerprint, observed
from agent1.adaptive.methods import Method, forecast
from agent1_service.api import create_app
from agent1_service.workspace.forecast_export import workbook_bytes
from fastapi.testclient import TestClient
from openpyxl import load_workbook


@pytest.fixture
def rows():
    return [
        {
            "invoice_id": i,
            "customer_id": i,
            "outstanding": amount,
            "triage_probability_4w": p,
            "payment_probability_4w": 0.5,
            "overdue_days": 2,
            "disputed": False,
            "promised_date": None,
            "promise_reliability": None,
        }
        for i, amount, p in [("A", 100, 0.9), ("C", 100, 0.4), ("B", 60, 0.1)]
    ]


@pytest.mark.parametrize(
    ("policy", "expected", "scores"),
    [
        ("amount", ["A", "C", "B"], [100, 100, 60]),
        ("risk", ["B", "C", "A"], [0.9, 0.6, 0.1]),
        ("amount_at_risk", ["C", "B", "A"], [60, 54, 10]),
    ],
)
def test_each_policy_reports_its_actual_score_and_comparison(
    rows, policy, expected, scores
):
    ranked, meta = rank_with_explanations(
        rows, policy=policy, cutoff="2026-11-11", has_serving_model=True
    )
    assert [r["invoice_id"] for r in ranked] == expected
    np.testing.assert_allclose([r["priority_score"] for r in ranked], scores)
    assert meta["policy"] == policy and meta["eligible_count"] == 3
    for i, row in enumerate(ranked):
        e = row["ranking_explanation"]
        assert e["rank"] == row["collection_rank"] == i + 1
        assert e["score"] == row["priority_score"]
        assert e["probability_source"]["used_in_score"] == (policy != "amount")
        assert (
            e["next"]["invoice_id"] == expected[i + 1] if i < 2 else e["next"] is None
        )
    if policy == "amount":
        assert ranked[0]["ranking_explanation"]["next"]["tied"]
        assert ranked[0]["ranking_explanation"]["tie_break"] == {
            "rule": "snapshot_order",
            "group_size": 2,
            "position": 1,
        }


def test_disputes_promises_and_overdue_flags_do_not_invent_score_adjustments(rows):
    plain, _ = rank_with_explanations(
        deepcopy(rows), policy="amount_at_risk", cutoff="2026-11-11"
    )
    rows[0].update(
        disputed=True,
        promised_date="2026-11-10",
        promise_reliability=0.2,
        overdue_days=100,
    )
    rows[1].update(promised_date="2026-11-11")
    rows[2].update(promised_date="2026-11-12")
    flagged, _ = rank_with_explanations(
        rows, policy="amount_at_risk", cutoff="2026-11-11"
    )
    assert [(r["invoice_id"], r["priority_score"]) for r in plain] == [
        (r["invoice_id"], r["priority_score"]) for r in flagged
    ]
    factors = {
        r["invoice_id"]: {f["feature"]: f for f in r["ranking_explanation"]["factors"]}
        for r in flagged
    }
    assert factors["A"]["promised_date"]["state"] == "overdue"
    assert factors["C"]["promised_date"]["state"] == "due_today"
    assert factors["B"]["promised_date"]["state"] == "upcoming"
    assert factors["A"]["promised_date"]["reliability"] == 0.2
    assert factors["A"]["disputed"]["value"] is True
    assert all(
        not f["affects_score"]
        for fs in factors.values()
        for key, f in fs.items()
        if key in ("promised_date", "disputed", "overdue_days")
    )


def test_ties_keep_snapshot_order_and_compare_to_candidate_beyond_display_limit(rows):
    candidates = [dict(rows[0], invoice_id=f"Z{100 - i}") for i in range(32)]
    ranked, meta = rank_with_explanations(
        candidates, policy="amount", cutoff="2026-11-11"
    )
    assert [r["invoice_id"] for r in ranked] == [
        r["invoice_id"] for r in candidates[:30]
    ]
    assert meta["eligible_count"] == 32 and meta["displayed_count"] == 30
    last = ranked[-1]["ranking_explanation"]
    assert last["next"]["invoice_id"] == candidates[30]["invoice_id"]
    assert last["tie_break"]["group_size"] == 32 and last["tie_break"]["position"] == 30
    assert last["next"]["tied"] and last["next"]["score_difference"] == 0


@pytest.mark.parametrize("policy", ["amount", "amount_at_risk", "risk"])
def test_large_vnd_preserves_one_dong_order_true_ties_and_fractional_scores(
    rows, policy
):
    small, large = 9007199254741008, 9007199254741009
    candidates = [
        dict(rows[0], invoice_id=iid, outstanding=amount, triage_probability_4w=0.5)
        for iid, amount in [("SMALL", small), ("LARGE", large), ("TIE", large)]
    ]
    ranked, _ = rank_with_explanations(candidates, policy=policy, cutoff="2026-11-11")
    if policy == "risk":
        assert [r["invoice_id"] for r in ranked] == ["SMALL", "LARGE", "TIE"]
        assert ranked[0]["ranking_explanation"]["tie_break"]["group_size"] == 3
        return
    assert [r["invoice_id"] for r in ranked] == ["LARGE", "TIE", "SMALL"]
    first, second = [r["ranking_explanation"] for r in ranked[:2]]
    assert first["next"]["tied"]
    assert first["tie_break"]["group_size"] == 2
    assert second["tie_break"]["position"] == 2
    assert not second["next"]["tied"]
    assert Decimal(str(second["next"]["score_difference"])) == (
        Decimal(1) if policy == "amount" else Decimal("0.5")
    )
    multiplier = Decimal(1) if policy == "amount" else Decimal("0.5")
    assert Decimal(str(ranked[0]["priority_score"])) == large * multiplier
    assert Decimal(str(ranked[-1]["priority_score"])) == small * multiplier
    assert ranked[0]["outstanding"] == str(large)
    assert ranked[0]["ranking_explanation"]["factors"][0]["value"] == str(large)
    sheet = load_workbook(
        BytesIO(
            workbook_bytes(
                {"cutoff": "2026-11-11", "weeks": [], "collections": ranked}, "TEST"
            )
        )
    )["Khoản cần chú ý"]
    columns = {cell.value: cell.column for cell in sheet[1]}
    assert Decimal(sheet.cell(2, columns["Điểm ưu tiên"]).value) == large * multiplier
    assert sheet.cell(2, columns["Điểm ưu tiên"]).data_type == "s"


def test_weighted_score_keeps_differences_smaller_than_one_dong(rows):
    candidates = [
        dict(rows[0], invoice_id=iid, outstanding=amount, triage_probability_4w=0.99999)
        for iid, amount in [("SMALL", 9007199254741008), ("LARGE", 9007199254741009)]
    ]
    ranked, _ = rank_with_explanations(
        candidates, policy="amount_at_risk", cutoff="2026-11-11"
    )
    assert [r["invoice_id"] for r in ranked] == ["LARGE", "SMALL"]
    peer = ranked[0]["ranking_explanation"]["next"]
    assert not peer["tied"] and peer["score_difference"] == "0.00001"
    assert ranked[0]["priority_score"] == "90071992547.41009"


def test_policy_selection_fallback_and_missing_audit_are_not_called_validated(rows):
    _, meta = rank_with_explanations(
        deepcopy(rows), policy="unknown", cutoff="2026-11-11", has_serving_model=True
    )
    assert (
        meta["policy"] == "amount"
        and meta["selection"]["status"] == "unknown_policy_fallback"
    )
    _, meta = rank_with_explanations(
        deepcopy(rows), policy="amount", cutoff="2026-11-11", has_serving_model=True
    )
    assert meta["selection"]["status"] == "saved_without_audit"
    for evaluation, expected in [
        ({"status": "insufficient_history"}, "insufficient_history"),
        ({"status": "evaluated", "accepted": False}, "evaluated"),
    ]:
        _, meta = rank_with_explanations(
            deepcopy(rows),
            policy="amount",
            cutoff="2026-11-11",
            has_serving_model=True,
            evaluation=evaluation,
        )
        assert meta["selection"]["status"] == expected


@pytest.fixture
def book():
    inv = []
    for iid, customer, amount, issued, due in [
        ("H1", "X", 50, "2026-01-01", "2026-01-08"),
        ("H2", "Y", 50, "2026-01-01", "2026-01-08"),
        ("A", "X", 100, "2026-02-01", "2026-02-08"),
        ("B", "Y", 300, "2026-02-07", "2026-02-28"),
        ("C", "Z", 300, "2026-02-07", "2026-02-28"),
    ]:
        inv.append(
            {
                "invoice_id": iid,
                "customer_id": customer,
                "amount": amount,
                "issue_date": issued,
                "due_date": due,
                "known_at": issued,
                "currency": "VND",
            }
        )
    return {
        "invoices": inv,
        "payments": [
            {
                "payment_id": "P1",
                "invoice_id": "H1",
                "amount": 50,
                "payment_date": "2026-01-15",
                "known_at": "2026-01-15",
            },
            {
                "payment_id": "P2",
                "invoice_id": "H2",
                "amount": 50,
                "payment_date": "2026-01-29",
                "known_at": "2026-01-29",
            },
        ],
        "outflows": [],
    }


def bundle_for(book, policy):
    clock = pd.Timestamp("2026-02-10")
    frame = observed(book, clock)
    return {
        "asof": str(clock.date()),
        "model": Method("due").fit(frame, clock),
        "anchor": Method("customer").fit(frame, clock),
        "weight": 1.0,
        "collection_policy": policy,
    }


def test_ranking_shap_explains_the_separate_baseline_without_forecast_shift(book):
    bundle = bundle_for(book, "amount_at_risk")
    base = forecast(book, "2026-02-10", 0, bundle)
    delayed = forecast(book, "2026-02-10", 0, bundle, delay_days=28)
    assert [(r["invoice_id"], r["priority_score"]) for r in base["collections"]] == [
        (r["invoice_id"], r["priority_score"]) for r in delayed["collections"]
    ]
    assert any(
        r["payment_probability_4w"] != r["triage_probability_4w"]
        for r in base["collections"]
    )
    for row in delayed["collections"]:
        e = row["ranking_explanation"]
        assert e["probability_source"]["differs_from_displayed"]
        assert not e["probability_source"]["scenario_shift_applied"]
        assert row["payment_probability_4w"] == 0
        shap = e["probability_explanation"]
        assert (
            shap["target"] == "triage_probability_4w"
            and shap["scenario_shift_weeks"] == 0
        )
        assert shap["model_version"] is None and shap["model_asof"] == "2026-02-10"
        assert shap["probability"] == row["triage_probability_4w"]
        assert shap["baseline_probability"] + sum(
            f["contribution"] for f in shap["factors"]
        ) == pytest.approx(row["triage_probability_4w"], abs=1e-10)


def test_rules_filter_asof_actions_and_release_contact_at_seven_days(book):
    for iid, amount in [("W", 400), ("CONTACT", 500), ("SKIP", 600), ("OLD", 700)]:
        book["invoices"].append(
            dict(book["invoices"][-1], invoice_id=iid, amount=amount)
        )
    book["actions"] = [
        {
            "event_id": "W",
            "invoice_id": "W",
            "date": "2026-02-09",
            "known_at": "2026-02-09",
            "kind": "write_off",
        },
        {
            "event_id": "CONTACT",
            "invoice_id": "CONTACT",
            "date": "2026-02-09",
            "known_at": "2026-02-09",
            "kind": "contact",
        },
        {
            "event_id": "SKIP",
            "invoice_id": "SKIP",
            "date": "2026-02-04",
            "known_at": "2026-02-04",
            "kind": "skip",
        },
        {
            "event_id": "OLD",
            "invoice_id": "OLD",
            "date": "2026-02-03",
            "known_at": "2026-02-03",
            "kind": "contact",
        },
        {
            "event_id": "LATE",
            "invoice_id": "OLD",
            "date": "2026-02-09",
            "known_at": "2026-02-11",
            "kind": "contact",
        },
        {
            "event_id": "DISPUTE",
            "invoice_id": "A",
            "date": "2026-02-09",
            "known_at": "2026-02-09",
            "kind": "dispute",
        },
        {
            "event_id": "PROMISE",
            "invoice_id": "B",
            "date": "2026-02-09",
            "known_at": "2026-02-09",
            "kind": "promise",
            "promise_date": "2026-02-10",
        },
    ]
    plan = forecast(book, "2026-02-10", 0)
    assert [r["invoice_id"] for r in plan["collections"]] == ["OLD", "B", "C", "A"]
    assert plan["collection_ranking"]["eligibility"] == {
        "open_before_rules": 7,
        "writeoff_excluded": 1,
        "recent_contact_or_skip_excluded": 2,
        "cooldown_days": 7,
    }
    assert plan["collection_ranking"]["eligible_count"] == 4
    a = next(r for r in plan["collections"] if r["invoice_id"] == "A")
    assert a["disputed"] and a["priority_score"] == 100
    later = forecast(book, "2026-02-11", 0)
    assert "OLD" not in {r["invoice_id"] for r in later["collections"]}


def test_default_amount_policy_does_not_attach_probability_shap_to_the_score(book):
    plan = forecast(book, "2026-02-10", 0)
    assert plan["collection_ranking"]["selection"]["status"] == "default"
    assert not plan["collection_ranking"]["uses_probability"]
    assert all(
        "probability_explanation" not in r["ranking_explanation"]
        for r in plan["collections"]
    )


def test_export_keeps_ranking_scores_sources_and_probability_units(book):
    plan = forecast(book, "2026-02-10", 0, bundle_for(book, "risk"))
    wb = load_workbook(BytesIO(workbook_bytes(plan, "TEST")))
    sheet = wb["Khoản cần chú ý"]
    columns = {c.value: c.column for c in sheet[1]}
    assert sheet.cell(2, columns["Thứ tự ưu tiên"]).value == 1
    score = sheet.cell(2, columns["Điểm ưu tiên"])
    assert (
        score.value == plan["collections"][0]["priority_score"]
        and score.number_format == "0.0%"
    )
    assert (
        sheet.cell(2, columns["Nguồn ước lượng xếp hạng"]).value
        == "Lịch sử khách hàng tại ngày dự báo"
    )
    assert sheet.cell(2, columns["Đơn vị điểm"]).value == "Xác suất"
    legacy = deepcopy(plan)
    legacy.pop("collection_ranking")
    for row in legacy["collections"]:
        row.pop("ranking_explanation")
    assert workbook_bytes(legacy, "TEST")


def test_browser_ranking_uses_saved_policy_and_separate_shap_on_both_screen_sizes(
    tmp_path, book
):
    playwright = pytest.importorskip("playwright.sync_api")
    chrome = Path("C:/Program Files/Google/Chrome/Application/chrome.exe")
    if not chrome.exists():
        pytest.skip("Chrome is not installed")
    book["actions"] = [
        {
            "event_id": "D",
            "invoice_id": "B",
            "date": "2026-02-09",
            "known_at": "2026-02-09",
            "kind": "dispute",
        },
        {
            "event_id": "P",
            "invoice_id": "B",
            "date": "2026-02-09",
            "known_at": "2026-02-09",
            "kind": "promise",
            "promise_date": "2026-02-10",
        },
    ]
    app = create_app(
        state_dir=tmp_path / "data",
        key_dir=tmp_path / "keys",
        token="ranking-browser-test",
        firm_id="TEST",
    )
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer ranking-browser-test"
        store, digest = app.state.store, fingerprint(book)
        store.put("TEST", "company_datasets", [{"id": digest, "data": book}])
        store.put(
            "TEST", "company_dataset_active", [{"id": "active", "version": digest}]
        )
        bundle = bundle_for(book, "amount_at_risk")
        store.put(
            "TEST",
            "company_weights",
            [
                {
                    "id": "WEIGHTS",
                    "artifact": base64.b64encode(pickle.dumps(bundle)).decode(),
                }
            ],
        )
        # UI fixture metadata only; these audit numbers are not model-quality evidence.
        store.put(
            "TEST",
            "company_models",
            [
                {
                    "id": "RANK-MODEL",
                    "artifact_id": "WEIGHTS",
                    "created_at": "2026-02-10T00:00:00Z",
                    "asof": "2026-02-10",
                    "dataset_hash": digest,
                    "audit": {
                        "candidate_brier4": 0.1,
                        "baseline_brier4": 0.2,
                        "n": 20,
                        "accepted": True,
                        "improvement_ci_low": 0,
                        "improvement_ci_high": 0,
                        "ci_reliable": False,
                    },
                    "train_n": 5,
                    "validation_n": 3,
                }
            ],
        )
        store.put(
            "TEST", "company_model_active", [{"id": "active", "version": "RANK-MODEL"}]
        )
        response = client.post(
            "/v1/predict",
            json={
                "cutoff": "2026-02-10",
                "opening_balance": 0,
                "payments_complete": True,
            },
        )
        assert response.status_code == 200, response.text
        plan = response.json()
        assert plan["collections"][0]["invoice_id"] == "B"
        assert (
            plan["collections"][0]["ranking_explanation"]["probability_explanation"][
                "target"
            ]
            == "triage_probability_4w"
        )
        output = (
            Path(__file__).resolve().parents[2] / "outputs/ui_checks/collection_ranking"
        )
        output.mkdir(parents=True, exist_ok=True)

        def proxy(route):
            req, url = route.request, urlsplit(route.request.url)
            response = client.request(
                req.method,
                url.path + ("?" + url.query if url.query else ""),
                content=req.post_data_buffer,
                headers={
                    "Content-Type": req.headers.get("content-type", "application/json")
                },
            )
            route.fulfill(
                status=response.status_code,
                body=response.content,
                headers={
                    k: v
                    for k, v in response.headers.items()
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
                playwright.expect(page.locator("#collection-policy")).to_contain_text(
                    "Dư nợ × nguy cơ"
                )
                button = page.locator(
                    '#collections-table button[aria-controls="ranking-explanation-0"]'
                )
                button.click()
                dialog = page.locator("#ranking-explanation-0")
                playwright.expect(dialog).to_contain_text("RANK-MODEL")
                playwright.expect(dialog).to_contain_text("Cùng điểm với hóa đơn C")
                playwright.expect(dialog).to_contain_text("khác nguồn")
                playwright.expect(dialog).to_contain_text("không đổi điểm")
                dialog.locator(".ranking-explanation > details > summary").click()
                shap = dialog.locator("details .t1-explanation")
                playwright.expect(shap).to_contain_text("Chưa đủ cơ sở")
                assert "RANK-MODEL" not in shap.inner_text()
                assert shap.locator("table, details").count() == 0
                assert "SHAP" not in shap.inner_text()
                for width in (1500, 390):
                    page.set_viewport_size({"width": width, "height": 960})
                    page.wait_for_function(
                        "() => document.documentElement.scrollWidth <= innerWidth"
                    )
                    dialog.evaluate("e => e.scrollTop = 0")
                    dialog.screenshot(path=str(output / f"ranking_{width}.png"))
                    assert dialog.bounding_box()["width"] <= width
                page.keyboard.press("Escape")
                playwright.expect(dialog).to_be_hidden()
                assert not errors, errors
            finally:
                browser.close()


def import_precision_invoices(client):
    source = (
        "invoice_id,customer_id,issue_date,due_date,known_at,amount,currency\n"
        "SMALL,C1,2026-01-01,2026-02-17,2026-01-01,9007199254741008,VND\n"
        "LARGE,C2,2026-01-01,2026-02-17,2026-01-01,9007199254741009,VND\n"
    )
    response = client.post(
        "/v1/imports/preview",
        files={"file": ("precision.csv", source.encode())},
        data={
            "kind": "invoices",
            "date_format": "%Y-%m-%d",
            "number_format": "plain",
            "known_at": "2026-01-01",
        },
    )
    assert response.status_code == 200 and response.json()["can_commit"], response.text
    result = client.post("/v1/imports/" + response.json()["id"] + "/commit")
    assert result.status_code == 200, result.text


def test_large_vnd_roundtrips_from_csv_through_api_saved_plan_and_excel(tmp_path):
    app = create_app(
        state_dir=tmp_path / "data",
        key_dir=tmp_path / "keys",
        token="precision-test",
        firm_id="TEST",
    )
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer precision-test"
        import_precision_invoices(client)
        source = (
            "statement_id,account,start_date,end_date,opening_balance,closing_balance,known_at\n"
            "S,Q,2026-01-01,2026-01-31,0,0,2026-01-31\n"
        )
        statement = client.post(
            "/v1/imports/preview",
            files={"file": ("statement.csv", source.encode())},
            data={
                "kind": "statements",
                "date_format": "%Y-%m-%d",
                "number_format": "plain",
                "known_at": "2026-01-31",
            },
        )
        assert statement.status_code == 200 and statement.json()["can_commit"], (
            statement.text
        )
        committed = client.post("/v1/imports/" + statement.json()["id"] + "/commit")
        assert committed.status_code == 200, committed.text
        response = client.post(
            "/v1/predict",
            json={
                "cutoff": "2026-02-10",
                "opening_balance": 0,
                "payments_complete": True,
            },
        )
        assert response.status_code == 200, response.text
        plan = response.json()
        assert [r["invoice_id"] for r in plan["collections"]] == ["LARGE", "SMALL"]
        large = plan["collections"][0]
        assert large["outstanding"] == large["priority_score"] == "9007199254741009"
        assert large["ranking_explanation"]["next"]["score_difference"] == 1
        assert not large["ranking_explanation"]["next"]["tied"]
        assert large["ranking_explanation"]["protocol"] == "collection-ranking-v2"
        factor = next(
            f
            for f in large["payment_explanation"]["factors"]
            if f["feature"] == "amount"
        )
        assert factor["value"] == "9007199254741009"
        assert client.get("/v1/forecasts/" + plan["id"]).json() == plan
        response = client.get("/v1/forecasts/" + plan["id"] + "/xlsx")
        assert response.status_code == 200
        sheet = load_workbook(BytesIO(response.content))["Khoản cần chú ý"]
        columns = {cell.value: cell.column for cell in sheet[1]}
        for heading in ("Còn phải thu (VND)", "Điểm ưu tiên"):
            cell = sheet.cell(2, columns[heading])
            assert cell.value == "9007199254741009" and cell.data_type == "s"
            assert sheet.cell(3, columns[heading]).value == "9007199254741008"
        actuals = client.get(
            "/v1/forecasts/" + plan["id"] + "/actuals",
            params={"asof": "2026-03-10", "payments_complete": "true"},
        )
        assert actuals.status_code == 200, actuals.text
        assert (
            actuals.json()["collections_curve"][0]["reviewed_vnd"] == 18014398509482017
        )


def test_browser_exact_priority_and_deferred_queue_on_both_screen_sizes(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    chrome = Path("C:/Program Files/Google/Chrome/Application/chrome.exe")
    if not chrome.exists():
        pytest.skip("Chrome is not installed")
    app = create_app(
        state_dir=tmp_path / "data",
        key_dir=tmp_path / "keys",
        token="precision-browser-test",
        firm_id="TEST",
    )
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer precision-browser-test"
        import_precision_invoices(client)
        response = client.post(
            "/v1/predict",
            json={
                "cutoff": "2026-02-10",
                "opening_balance": 0,
                "payments_complete": True,
            },
        )
        assert response.status_code == 200, response.text
        precise = response.json()
        deferred_book = {
            "invoices": [
                {
                    "invoice_id": f"I{i}",
                    "customer_id": f"C{i}",
                    "amount": 100,
                    "issue_date": "2026-01-01",
                    "due_date": "2026-02-17",
                    "known_at": "2026-01-01",
                }
                for i in range(3)
            ],
            "payments": [],
            "outflows": [],
            "actions": [
                {
                    "event_id": f"E{i}",
                    "invoice_id": f"I{i}",
                    "kind": "contact",
                    "date": "2026-02-09",
                    "known_at": "2026-02-09",
                }
                for i in range(3)
            ],
        }
        digest = fingerprint(deferred_book)
        app.state.store.put(
            "TEST", "company_datasets", [{"id": digest, "data": deferred_book}]
        )
        app.state.store.put(
            "TEST", "company_dataset_active", [{"id": "active", "version": digest}]
        )
        response = client.post(
            "/v1/predict",
            json={
                "cutoff": "2026-02-10",
                "opening_balance": 0,
                "payments_complete": True,
            },
        )
        assert response.status_code == 200, response.text
        deferred = response.json()
        assert deferred["open_invoices"] == 3 and deferred["outstanding"] == 300
        assert not deferred["collections"]
        output = (
            Path(__file__).resolve().parents[2]
            / "outputs/ui_checks/collection_precision"
        )
        output.mkdir(parents=True, exist_ok=True)

        def proxy(route):
            req, url = route.request, urlsplit(route.request.url)
            response = client.request(
                req.method,
                url.path + ("?" + url.query if url.query else ""),
                content=req.post_data_buffer,
                headers={
                    "Content-Type": req.headers.get("content-type", "application/json")
                },
            )
            route.fulfill(
                status=response.status_code,
                body=response.content,
                headers={
                    k: v
                    for k, v in response.headers.items()
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

                def open_plan(identifier):
                    page.locator(".history-menu > summary").click()
                    page.locator("#saved-plans").click()
                    page.locator("#plans-list button").nth(
                        0 if identifier == deferred["id"] else 1
                    ).click()

                for width in (1500, 390):
                    page.set_viewport_size({"width": width, "height": 960})
                    open_plan(precise["id"])
                    first = page.locator("#collections-table tbody tr").first
                    playwright.expect(first).to_contain_text("LARGE")
                    playwright.expect(first).to_contain_text(
                        "9.007.199.254.741.009 VND"
                    )
                    first.locator(
                        'button[aria-controls="ranking-explanation-0"]'
                    ).click()
                    dialog = page.locator("#ranking-explanation-0")
                    playwright.expect(dialog).to_contain_text(
                        "9.007.199.254.741.009 VND"
                    )
                    playwright.expect(dialog).to_contain_text(
                        "9.007.199.254.741.008 VND"
                    )
                    assert "Cùng điểm" not in dialog.inner_text()
                    page.wait_for_function(
                        "() => document.documentElement.scrollWidth <= innerWidth"
                    )
                    dialog.screenshot(path=str(output / f"priority_{width}.png"))
                    page.keyboard.press("Escape")
                    first.locator(
                        'button[aria-controls="payment-explanation-0"]'
                    ).click()
                    shap = page.locator("#payment-explanation-0")
                    # Two invoices cannot support stability checks; neutral
                    # amount attribution must not be presented as a reason.
                    playwright.expect(shap).to_contain_text("Chưa đủ cơ sở")
                    assert shap.locator("table, details").count() == 0
                    page.keyboard.press("Escape")
                    open_plan(deferred["id"])
                    queue = page.locator("#collections-table")
                    playwright.expect(queue).to_contain_text("Còn 3 hóa đơn đang mở")
                    playwright.expect(queue).to_contain_text("3 khoản đang tạm hoãn")
                    assert "Không có công nợ còn mở" not in queue.inner_text()
                    page.wait_for_function(
                        "() => document.documentElement.scrollWidth <= innerWidth"
                    )
                    queue.screenshot(path=str(output / f"deferred_{width}.png"))
                assert not errors, errors
            finally:
                browser.close()
