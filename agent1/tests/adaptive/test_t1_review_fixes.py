"""Fixed-claim trajectories, late label evidence, empirical prior and promotion proof."""
from copy import deepcopy
import json

import numpy as np
import pandas as pd
import pytest

from agent1.adaptive.cash_adapter import FIT_VERSION, fit_partial
from agent1.adaptive.compact_t1 import sha256
from agent1.adaptive.data import validate_dataset
from agent1.adaptive.t1_catalog import GlobalCatalog, LEGACY_CATALOG_VERSION
from agent1.adaptive.t1_data import landmarks
from agent1.adaptive.t1_update import train_update, valid_incumbent
from agent1.adaptive.training_report import report_data
from agent1_service.workspace import t1_lifecycle as life
from test_company_workspace import accounting_invoice
from test_cash_adapter import frame
from test_t1_periodic import catalog, invoice, seed_store, fake_fit, set_time


def data():
    return dict(invoices=[accounting_invoice(issue_date="2024-12-01", due_date="2024-12-31",
                                             known_at="2024-12-01")], payments=[], outflows=[],
                payment_coverage=[dict(complete=True, start_date="2024-12-01",
                                        end_date="2025-08-01", known_at="2025-04-02")])


def adjustment(original, iid, date, amount=-110, known=None):
    return dict(original, invoice_id=iid, invoice_no=iid, issue_date=date, known_at=known or date,
                adjustment_type="adjustment", adjusts_invoice_id="ORIGINAL",
                amount=amount, amount_net=amount//11*10, vat=amount//11)


def test_separate_credit_and_reversal_exclude_only_the_changed_claim():
    d = data()
    d["invoices"].extend([adjustment(d["invoices"][0], "CREDIT", "2025-01-10"),
                          adjustment(d["invoices"][0], "DEBIT", "2025-01-20", 110),
                          invoice(2, "2024-12-01")])
    validate_dataset(d)
    assert landmarks(d, "2025-01-01", "2025-04-02").invoice_id.tolist() == ["2"]


@pytest.mark.parametrize("kind", ["amount", "customer", "delete", "replace", "cancel"])
@pytest.mark.parametrize("day,eligible", [("2025-04-02", False), ("2025-04-03", True)])
def test_claim_window_ends_on_day_91_including_later_scoring(kind, day, eligible):
    d = data()
    original = d["invoices"][0]
    if kind in ("amount", "customer", "delete"):
        change = dict(original, known_at=day, record_version=2)
        if kind == "amount":
            change.update(amount=1210, amount_net=1100, vat=110)
        elif kind == "customer":
            change["customer_id"] = "OTHER"
        else:
            change = dict(invoice_id="ORIGINAL", known_at=day, _deleted=True)
        d["record_history"] = {"invoices": [original, change]}
        d["invoices"] = [] if kind == "delete" else [change]
    elif kind == "replace":
        d["invoices"].append(dict(original, invoice_id="REPLACE", invoice_no="REPLACE",
                                   adjustment_type="replacement", adjusts_invoice_id="ORIGINAL",
                                   issue_date=day, known_at=day))
    else:
        d["invoice_events"] = [dict(event_id="CANCEL", invoice_id="ORIGINAL", event_type="cancel",
                                    event_date=day, known_at=day)]
    result = landmarks(d, "2025-01-01", "2025-05-20")
    assert ("ORIGINAL" in result.invoice_id.tolist()) == eligible


def test_backdated_credit_and_reversal_known_after_day_91_still_invalidate_claim():
    d = data()
    d["invoices"].extend([adjustment(d["invoices"][0], "CREDIT", "2025-01-10", known="2025-05-01"),
                          adjustment(d["invoices"][0], "DEBIT", "2025-01-20", 110, "2025-05-02")])
    validate_dataset(d)
    assert not landmarks(d, "2025-01-01", "2025-04-02").empty
    assert landmarks(d, "2025-01-01", "2025-05-03").empty


def test_late_cash_is_received_on_its_economic_date_inside_the_fixed_window():
    d = data()
    d["payments"] = [dict(payment_id="LATE", invoice_id="ORIGINAL", amount=1100,
                           payment_date="2025-01-12", known_at="2025-05-01")]
    before = landmarks(d, "2025-01-01", "2025-04-02")
    after = landmarks(d, "2025-01-01", "2025-05-02")
    assert np.isinf(before.paid_days.iloc[0])
    assert after.paid_days.iloc[0] == 11
    assert after.cash_2.iloc[0] == 1
    assert after.followup_days.iloc[0] == 91


def test_confirmation_of_a_pre_origin_credit_does_not_change_the_claim():
    d = data()
    original = d["invoices"][0]
    credit = adjustment(original, "CREDIT", "2024-12-15")
    confirmation = dict(credit, known_at="2025-01-20", source_file="confirmed.xml")
    d["invoices"].append(confirmation)
    d["record_history"] = {"invoices": [original, credit, confirmation]}
    result = landmarks(d, "2025-01-01", "2025-05-02")
    assert result.claim_amount.tolist() == [990]


@pytest.mark.parametrize("change", ["superseded_parent", "active_credit_reversal"])
def test_pre_origin_replacement_has_its_own_fixed_principal(change):
    d = data()
    original = d["invoices"][0]
    replacement = dict(original, invoice_id="REPLACE", invoice_no="REPLACE",
                        adjustment_type="replacement", adjusts_invoice_id="ORIGINAL",
                        issue_date="2024-12-15", known_at="2024-12-15")
    d["invoices"].append(replacement)
    if change == "superseded_parent":
        revision = dict(original, amount=1210, amount_net=1100, vat=110,
                         known_at="2025-01-20", record_version=2)
        d["invoices"][0] = revision
        d["record_history"] = {"invoices": [original, replacement, revision]}
    else:
        d["invoices"].extend([dict(adjustment(original, "C", "2025-01-10"), adjusts_invoice_id="REPLACE"),
                              dict(adjustment(original, "D", "2025-01-20", 110), adjusts_invoice_id="REPLACE")])
    validate_dataset(d)
    result = landmarks(d, "2025-01-01", "2025-05-02")
    assert ("REPLACE" in result.invoice_id.tolist()) == (change == "superseded_parent")


@pytest.mark.parametrize("use_empty_prior", [False, True])
def test_first_partial_ratio_has_only_real_observed_mass(use_empty_prior):
    f = frame()
    f["cash_1"] = .01
    prior = fit_partial(pd.DataFrame(), "2020-01-01", prior=None) if use_empty_prior else None
    learned = fit_partial(f, "2025-01-08", prior=prior)
    assert learned.means[0] == pytest.approx(.01)
    assert learned.probability[0] == pytest.approx(1/31 if use_empty_prior else 1)
    assert learned.evidence["fit_version"] == FIT_VERSION
    assert learned.ratios[0].tolist() == [.01]
    assert all(learned.probability[k] == 0 for k in range(1, 6))


def test_prior_migration_keeps_incumbent_unchanged_until_an_audit_accepts(catalog):
    metadata = json.loads(catalog.path.read_text(encoding="utf-8"))
    parent = dict(metadata, version=LEGACY_CATALOG_VERSION)
    parent_file = catalog.path.parent / "parent_catalog.json"
    parent_file.write_text(json.dumps(parent), encoding="utf-8")
    legacy = GlobalCatalog(parent_file)
    metadata["compatible_parent"] = dict(file=parent_file.name, sha256=legacy.digest)
    catalog.path.write_text(json.dumps(metadata), encoding="utf-8")
    current = GlobalCatalog(catalog.path)
    incumbent = legacy.default_bundle("2025-02-01")
    before = life.encode(incumbent)
    assert valid_incumbent(incumbent, "2025-02-01", current) is incumbent
    result = train_update(dict(invoices=[invoice(0, "2025-01-01")], payments=[]),
                          "2025-02-01", incumbent=incumbent, catalog=current)
    assert result["promotion_status"] == "kept_incumbent"
    assert result["t1_version"] == incumbent["t1_version"]
    assert result["partial"].digest == incumbent["partial"].digest
    assert life.encode(incumbent) == before
    metadata["replay"]["sha256"] = "0"*64
    catalog.path.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ValueError, match="Migration"):
        GlobalCatalog(catalog.path)


def test_packaged_v3_keeps_frozen_t1_and_replay_and_changes_only_the_prior():
    current = GlobalCatalog()
    parent_spec = current.metadata["compatible_parent"]
    parent = json.loads(current.file(parent_spec["file"]).read_text(encoding="utf-8"))
    assert sha256(current.file(parent_spec["file"])) == parent_spec["sha256"]
    assert current.metadata["models"] == parent["models"]
    assert current.metadata["replay"] == parent["replay"]
    assert current.partial.evidence["fit_version"] == FIT_VERSION
    assert current.metadata["partial"]["sha256"] != parent["partial"]["sha256"]


def test_legacy_prior_remains_readable_but_cannot_seed_new_updates():
    current = GlobalCatalog()
    legacy = GlobalCatalog(current.path.parent.parent / "settlement_partial_catalog_v2_20261113/catalog.json")
    bundle = legacy.default_bundle("2025-12-31")
    assert bundle["partial"].digest == legacy.partial.digest
    assert valid_incumbent(bundle, "2025-12-31", current) is bundle
    with pytest.raises(ValueError, match="catalog partial v3"):
        train_update(dict(invoices=[invoice(0, "2025-01-01")], payments=[]),
                     "2025-12-31", catalog=legacy)


def test_promotion_proof_survives_new_candidates_metadata_reports_and_next_cycle(tmp_path, catalog, monkeypatch):
    store, d = seed_store(tmp_path, catalog)
    try:
        set_time(monkeypatch, "2025-01-01T12:00:00")
        life.run_cycle(store, "A", "2025-01-01", payments_complete=True, catalog=catalog, trainer=fake_fit)
        set_time(monkeypatch, "2025-04-02T12:00:00")
        decision = life.run_cycle(store, "A", "2025-04-02", payments_complete=True,
                                  catalog=catalog, trainer=fake_fit)
        audit = decision["promotion_audit"]
        assert audit["accepted"] and audit["challenger"]["score"] == 0
        assert decision["audit"] == audit
        assert decision["candidate_update_audit"] == {"accepted": False}
        version = store.one("A", "company_models", decision["model_id"])
        assert version["prospective_audit_id"] == audit["challenger_id"]
        assert version["promotion_audit"] == audit
        index = store.one("A", "company_t1_challenger_index", audit["challenger_id"])
        assert index["status"] == "accepted" and index["evaluation"]["challenger"]["score"] == 0
        assert "snapshot" not in index and "artifact_id" not in index
        legacy = life.decode(store.one("A", "company_weights", decision["model_id"]))
        legacy.pop("promotion_audit")
        legacy.pop("candidate_update_audit")
        legacy["audit"] = dict(accepted=False)
        store.put("A", "company_weights", [dict(id=decision["model_id"], **life.encode(legacy))])
        legacy_row = dict(version, audit=dict(accepted=False))
        for key in ("promotion_audit", "candidate_update_audit", "prospective_audit_id"):
            legacy_row.pop(key, None)
        store.put("A", "company_models", [legacy_row])
        repaired = life.with_promotion_evidence(store, "A", legacy_row)
        assert repaired["promotion_audit"] == audit
        assert repaired["audit"] == audit
        unrelated = dict(legacy_row, t1_version="unrelated-serving-bundle")
        assert life.with_promotion_evidence(store, "A", unrelated) is unrelated
        recovered, _ = life.load_active(store, "A", "2025-04-02", catalog=catalog)
        assert recovered["promotion_audit"] == audit
        # Reading does not rewrite the old artifact or metadata.
        assert store.one("A", "company_models", decision["model_id"]) == legacy_row
        set_time(monkeypatch, "2025-04-30T12:00:00")

        def kept(data, T, progress, *, incumbent, **kwargs):
            return dict(deepcopy(incumbent), audit=dict(accepted=False, status="insufficient_local_windows"),
                        promotion_status="kept_incumbent", proposal=None)

        next_run = life.run_cycle(store, "A", "2025-04-30", payments_complete=True,
                                  catalog=catalog, trainer=kept)
        bundle, _ = life.load_active(store, "A", "2025-04-30", catalog=catalog)
        assert next_run["promotion_audit"] == audit
        assert bundle["promotion_audit"] == audit
        report = report_data(bundle, d, "TEST")["training"]
        assert report["promotion_audit"] == audit
        assert report["candidate_update_audit"]["status"] == "insufficient_local_windows"
    finally:
        store.connection.close()


@pytest.mark.parametrize("width", [1500, 390])
def test_workspace_shows_promotion_audit_separately_from_next_candidate(
        tmp_path, catalog, monkeypatch, browser_runtime, client_proxy, width):
    from fastapi.testclient import TestClient
    from agent1_service.api import create_app
    runtime, chrome = browser_runtime
    monkeypatch.setenv("AGENT1_T1_GLOBAL_CATALOG", str(catalog.path))
    app = create_app(state_dir=tmp_path/"ui-state", key_dir=tmp_path/"ui-keys", token="review", firm_id="A")
    bundle = catalog.default_bundle("2025-04-02")
    bundle.update(update_asof="2025-04-02", asof="2025-03-01", t1_parameter_asof="2024-11-10")
    promotion = dict(accepted=True, kind="prospective", challenger=dict(score=.1234),
                     baseline=dict(score=.5678), rows=30)
    current_audit = dict(accepted=False, candidate=dict(score=9.9999), baseline=dict(score=8.8888), n=20)
    bundle.update(audit=current_audit, promotion_audit=promotion, candidate_update_audit=current_audit,
                  promotion_status="accepted_prospective_audit", prospective_audit_id="LOCKED")
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer review"
        store = app.state.store
        record = life.metadata(bundle, "ACTIVE", "2025-04-02T00:00:00Z")
        for key in ("promotion_audit", "candidate_update_audit", "prospective_audit_id"):
            record.pop(key, None)
        store.put_many("A", {"company_datasets": [dict(id="D", data=data())],
                              "company_dataset_active": [dict(id="active", version="D")],
                              "company_models": [record],
                              "company_weights": [dict(id="ACTIVE", **life.encode(bundle))],
                              "company_model_active": [dict(id="active", version="ACTIVE")],
                              "company_t1_update_runs": [dict(id="ACTIVE", prospective_audit_id="LOCKED")],
                              "company_t1_challengers": [dict(id="LOCKED", status="accepted",
                                  challenger_version=bundle["t1_version"], evaluated_asof="2025-04-02",
                                  evaluation=dict(status="scored", challenger=dict(score=.1234),
                                                  baseline=dict(score=.5678), rows=30))]})
        with runtime.sync_playwright() as p:
            browser = p.chromium.launch(executable_path=str(chrome), headless=True)
            try:
                page = browser.new_page(viewport=dict(width=width, height=960))
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.route("**/*", client_proxy(client))
                page.goto("http://testserver/workspace#training")
                page.locator("#versions-list .version").wait_for()
                page.locator(".version-evidence > summary").first.click()
                text = page.locator("#versions-list").inner_text()
                assert ".1234" in text and ".5678" in text
                assert "9.9999" not in text and "8.8888" not in text
                assert "Kết quả kiểm định dùng để chọn" in text
                assert "cập nhật dữ liệu đến 02-04-25" in page.locator("#versions-list h3").inner_text()
                assert "Ước tính thanh toán cập nhật: 10-11-24" in text
                assert "Ước tính trả từng phần: 01-01-20" in text
                assert "Phiên bản sẵn sàng: 01-03-25" in text
                assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
                page.screenshot(path=str(tmp_path / f"version-dates-{width}.png"), full_page=True)
                # The following kept cycle must show its own candidate check,
                # even while retaining the older promotion proof for provenance.
                record.update(promotion_status="kept_incumbent",
                              candidate_update_audit=dict(candidate=dict(score=.7777), n=25))
                store.put("A", "company_models", [record])
                page.reload()
                page.locator("#versions-list .version").wait_for()
                page.locator(".version-evidence > summary").first.click()
                text = page.locator("#versions-list").inner_text()
                assert ".7777" in text and ".1234" not in text
                assert "Kết quả kiểm tra ứng viên của chu kỳ này" in text
                assert not errors
            finally:
                browser.close()
