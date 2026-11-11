"""Synthetic fixtures verify mechanics only; never production method selection evidence."""

import time
import io
import hashlib
import json
from datetime import date, timedelta
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from agent1.adaptive.data import (
    parse_rows,
    suggested_mapping,
    observed,
    validate_dataset,
    fingerprint,
    account_scope,
)
from agent1.adaptive.methods import Method, features, forecast, train
from agent1_service.api import create_app
from agent1.synth.einvoice import invoice_to_xml
from agent1.synth.names import make_mst


def company_data(days=210):
    data = dict(invoices=[], payments=[], outflows=[])
    start = date(2025, 1, 1)
    for day in range(days):
        issued = start + timedelta(days=day)
        for k in range(2):
            iid = f"INV-{day}-{k}"
            amount = float(100000 * (1 + day % 9))
            data["invoices"].append(
                dict(
                    invoice_id=iid,
                    customer_id=f"C{day % 19}",
                    issue_date=str(issued),
                    due_date=str(issued + timedelta(days=21)),
                    known_at=str(issued),
                    amount=amount,
                    currency="VND",
                )
            )
            if (day + k) % 5:
                paid = issued + timedelta(days=14 + (day % 4) * 7)
                data["payments"].append(
                    dict(
                        payment_id="PAY-" + iid,
                        invoice_id=iid,
                        payment_date=str(paid),
                        known_at=str(paid),
                        amount=amount,
                    )
                )
    data["outflows"] = [
        dict(
            expense_id="EXP1",
            date="2025-08-07",
            known_at="2025-07-01",
            amount=1500000.0,
            category="rent",
        )
    ]
    return data


@pytest.fixture
def client(tmp_path):
    app = create_app(
        state_dir=tmp_path / "data",
        key_dir=tmp_path / "keys",
        token="company-test-token",
        firm_id="SME",
    )
    with TestClient(app) as c:
        c.headers["Authorization"] = "Bearer company-test-token"
        yield c


def upload(client, kind, rows):
    file = pd.DataFrame(rows).to_csv(index=False).encode("utf-8-sig")
    response = client.post(
        "/v1/imports/preview",
        files={"file": ("data.csv", file, "text/csv")},
        data={"kind": kind, "date_format": "%Y-%m-%d", "number_format": "plain"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def import_all(client, data):
    for kind, rows in data.items():
        preview = upload(client, kind, rows)
        assert preview["can_commit"], preview
        assert (
            client.post("/v1/imports/" + preview["id"] + "/commit").status_code == 200
        )


def accounting_invoice(invoice_id="ORIGINAL", **changes):
    rng = np.random.default_rng(9)
    row = dict(
        invoice_id=invoice_id,
        customer_id="BUYER",
        seller_mst=make_mst(rng),
        buyer_mst=make_mst(rng),
        symbol="1C26TAA",
        invoice_no=invoice_id,
        issue_date="2026-01-01",
        due_date="2026-02-01",
        known_at="2026-01-01",
        amount_net=1000,
        vat=100,
        amount=1100,
        currency="VND",
        record_version=1,
    )
    return dict(row, **changes)


def active_data(client):
    store = client.app.state.store
    pointer = store.one("SME", "company_dataset_active", "active")
    return store.one("SME", "company_datasets", pointer["version"])["data"]


def test_accounting_lifecycle_preserves_asof_and_allocations(client):
    original = accounting_invoice()
    import_all(
        client,
        {
            "invoices": [original],
            "payments": [
                dict(
                    payment_id="P",
                    invoice_id="ORIGINAL",
                    payment_date="2026-01-05",
                    known_at="2026-01-05",
                    amount=500,
                )
            ],
        },
    )
    replacement = accounting_invoice(
        "REPLACEMENT",
        issue_date="2026-01-10",
        known_at="2026-01-20",
        adjustment_type="replacement",
        adjusts_invoice_id="ORIGINAL",
    )
    import_all(client, {"invoices": [replacement]})
    delta = accounting_invoice(
        "DELTA",
        issue_date="2026-01-21",
        known_at="2026-01-25",
        amount_net=-500,
        vat=-50,
        amount=-550,
        adjustment_type="adjustment",
        adjusts_invoice_id="REPLACEMENT",
    )
    import_all(client, {"invoices": [delta]})
    data = active_data(client)
    early = observed(data, "2026-01-19").set_index("invoice_id")
    assert (
        list(early.index) == ["ORIGINAL"]
        and early.loc["ORIGINAL", "remaining_amount"] == 600
    )
    later = observed(data, "2026-01-24").set_index("invoice_id")
    assert (
        list(later.index) == ["REPLACEMENT"]
        and later.loc["REPLACEMENT", "remaining_amount"] == 600
    )
    adjusted = observed(data, "2026-01-25").iloc[0]
    assert (
        adjusted.amount == 550
        and adjusted.remaining_amount == 50
        and adjusted.known_at == pd.Timestamp("2026-01-25")
    )
    plan = client.post(
        "/v1/predict",
        json=dict(cutoff="2026-01-25", opening_balance=0, payments_complete=True),
    )
    assert plan.status_code == 200, plan.text
    assert plan.json()["open_invoices"] == 1
    cancel = dict(
        event_id="CANCEL",
        invoice_id="REPLACEMENT",
        event_type="cancel",
        event_date="2026-01-26",
        known_at="2026-02-01",
    )
    import_all(client, {"invoice_events": [cancel]})
    data = active_data(client)
    assert len(observed(data, "2026-01-31")) == 1
    assert observed(data, "2026-02-01").empty
    plan = client.post(
        "/v1/predict",
        json=dict(cutoff="2026-02-01", opening_balance=0, payments_complete=True),
    )
    assert plan.status_code == 200 and plan.json()["open_invoices"] == 0, plan.text
    assert client.delete("/v1/records/invoices/REPLACEMENT").status_code == 409
    # Events are immutable and replaying the identical event is safe.
    assert upload(client, "invoice_events", [cancel])["can_commit"]
    assert not upload(
        client, "invoice_events", [dict(cancel, event_date="2026-01-27")]
    )["can_commit"]
    # A later extraction correction keeps the already known document chain.
    import_all(
        client,
        {"invoices": [dict(replacement, record_version=2, known_at="2026-03-01")]},
    )
    assert observed(active_data(client), "2026-01-25").iloc[0].remaining_amount == 50


def test_late_revisions_and_payment_corrections_do_not_erase_history(client):
    import_all(client, {"invoices": [accounting_invoice()]})
    correction = accounting_invoice(
        amount_net=2000, vat=200, amount=2200, record_version=2, known_at="2026-02-01"
    )
    import_all(client, {"invoices": [correction]})
    pay = dict(
        payment_id="P",
        invoice_id="ORIGINAL",
        payment_date="2026-01-15",
        known_at="2026-02-02",
        amount=1000,
    )
    import_all(client, {"payments": [pay]})
    import_all(client, {"payments": [dict(pay, amount=1500, known_at="2026-03-01")]})
    data = active_data(client)
    assert observed(data, "2026-01-31").iloc[0].amount == 1100
    assert observed(data, "2026-02-02").iloc[0].remaining_amount == 1200
    assert observed(data, "2026-03-01").iloc[0].remaining_amount == 700
    for bad in [
        dict(correction, amount=3300),
        dict(correction, record_version=1),
        dict(correction, known_at="2026-01-01"),
    ]:
        before = fingerprint(active_data(client))
        assert not upload(client, "invoices", [bad])["can_commit"]
        assert fingerprint(active_data(client)) == before


def test_legacy_invoice_can_be_completed_without_losing_its_original_clock(client):
    full = accounting_invoice()
    basic = {
        k: full[k]
        for k in (
            "invoice_id",
            "customer_id",
            "issue_date",
            "due_date",
            "known_at",
            "amount",
            "currency",
        )
    }
    import_all(client, {"invoices": [basic]})
    legacy = dict(full, available_on="2026-01-03", amount_gross=full["amount"])
    del legacy["known_at"], legacy["amount"]
    import_all(client, {"invoices": [legacy]})
    data = active_data(client)
    assert (
        len(data["invoices"]) == 1 and data["invoices"][0]["known_at"] == "2026-01-03"
    )
    assert observed(data, "2026-01-02").iloc[0].known_at == pd.Timestamp("2026-01-01")
    # Changing accounting facts also requires a new knowledge day.
    assert not upload(
        client,
        "invoices",
        [dict(full, amount_net=1100, vat=0, record_version=2, known_at="2026-01-03")],
    )["can_commit"]
    missing_clock = accounting_invoice("NO_CLOCK")
    del missing_clock["known_at"]
    preview = upload(client, "invoices", [missing_clock])
    assert preview["can_commit"] and preview["sample"][0]["known_at"] == str(
        pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").date()
    )


def test_adjustment_settlement_keeps_its_own_business_and_knowledge_dates(client):
    import_all(
        client,
        {
            "invoices": [accounting_invoice()],
            "payments": [
                dict(
                    payment_id="P",
                    invoice_id="ORIGINAL",
                    amount=550,
                    payment_date="2026-01-05",
                    known_at="2026-01-05",
                )
            ],
        },
    )
    delta = accounting_invoice(
        "DELTA",
        adjustment_type="adjustment",
        adjusts_invoice_id="ORIGINAL",
        amount_net=-500,
        vat=-50,
        amount=-550,
        issue_date="2026-01-21",
        known_at="2026-02-02",
    )
    import_all(client, {"invoices": [delta]})
    assert pd.isna(observed(active_data(client), "2026-02-01").iloc[0].settled)
    settled = observed(active_data(client), "2026-02-02").iloc[0]
    assert settled.remaining_amount == 0 and settled.received == 550
    assert settled.settled == pd.Timestamp(
        "2026-01-21"
    ) and settled.settled_known_at == pd.Timestamp("2026-02-02")


def test_xml_and_excel_share_accounting_gate_and_document_identity(client):
    original = accounting_invoice()
    inv = pd.Series(dict(original, amount_gross=1100, term_days=31, vat_rate=0.1))
    content = invoice_to_xml(
        inv,
        pd.Series(dict(name="Seller", mst=original["seller_mst"])),
        pd.Series(dict(name="Buyer", mst=original["buyer_mst"])),
    )
    preview = client.post(
        "/v1/imports/preview",
        files={"file": ("invoice.xml", content)},
        data=dict(kind="invoices", known_at="2026-01-02"),
    ).json()
    assert preview["can_commit"] and preview["mapping_locked"], preview
    assert client.post("/v1/imports/" + preview["id"] + "/commit").is_success
    erp = dict(original, invoice_id="ERP-ALIAS", known_at="2026-01-03")
    workbook = io.BytesIO()
    pd.DataFrame([erp]).to_excel(workbook, index=False, sheet_name="Invoices")
    preview = client.post(
        "/v1/imports/preview",
        files={"file": ("ledger.xlsx", workbook.getvalue())},
        data=dict(
            kind="invoices",
            sheet="Invoices",
            date_format="%Y-%m-%d",
            number_format="plain",
        ),
    ).json()
    assert preview["can_commit"], preview
    assert client.post("/v1/imports/" + preview["id"] + "/commit").is_success
    rows = active_data(client)["invoices"]
    assert len(rows) == 1 and rows[0]["sources"] == ["erp", "xml"]
    assert rows[0]["source_ids"] == {"xml": "ORIGINAL", "erp": "ERP-ALIAS"}
    assert (
        rows[0]["source_lineage"]["xml"]["sha256"]
        == hashlib.sha256(content).hexdigest()
    )
    import_all(
        client,
        {
            "payments": [
                dict(
                    payment_id="P",
                    invoice_id="ERP-ALIAS",
                    payment_date="2026-01-05",
                    known_at="2026-01-05",
                    amount=1100,
                )
            ]
        },
    )
    assert observed(active_data(client), "2026-01-05").iloc[0].remaining_amount == 0
    for xml in [b'<!DOCTYPE x [<!ENTITY e "bad">]><HDon/>', b"<HDon>"]:
        assert (
            client.post(
                "/v1/imports/preview",
                files={"file": ("bad.xml", xml)},
                data=dict(kind="invoices"),
            ).status_code
            == 422
        )


def test_invalid_lifecycle_and_accounting_rows_never_commit(client):
    import_all(client, {"invoices": [accounting_invoice()]})
    for row in [
        accounting_invoice("X", buyer_mst="bad"),
        accounting_invoice("X", vat=300),
        accounting_invoice(
            "X", adjustment_type="replacement", adjusts_invoice_id="MISSING"
        ),
        accounting_invoice("X", adjustment_type="replacement", adjusts_invoice_id="X"),
    ]:
        preview = upload(client, "invoices", [row])
        assert not preview["can_commit"]
        assert (
            client.post("/v1/imports/" + preview["id"] + "/commit").status_code == 422
        )
    assert len(active_data(client)["invoices"]) == 1
    partial = dict(accounting_invoice("X"))
    del partial["vat"]
    assert not upload(client, "invoices", [partial])["can_commit"]


def test_exact_vnd_and_strict_headers(client):
    huge = 100000000000000001
    import_all(
        client,
        {"invoices": [dict(accounting_invoice(), amount_net=huge, vat=0, amount=huge)]},
    )
    assert active_data(client)["invoices"][0]["amount"] == huge
    assert observed(active_data(client), "2026-01-02").iloc[0].amount == huge
    assert observed(active_data(client), "2026-01-02").iloc[0].remaining_amount == huge
    assert upload(
        client,
        "invoices",
        [dict(accounting_invoice(), amount_net=huge, vat=0, amount=huge)],
    )["sample"][0]["amount"] == str(huge)
    import_all(
        client,
        {
            "bank": [
                dict(
                    bank_id="B",
                    account="A",
                    date="2026-01-01",
                    known_at="2026-01-01",
                    direction="in",
                    amount=1,
                )
            ],
            "statements": [
                dict(
                    statement_id="S",
                    account="A",
                    start_date="2026-01-01",
                    end_date="2026-01-01",
                    known_at="2026-01-01",
                    opening_balance=huge,
                    closing_balance=huge + 1,
                )
            ],
        },
    )
    assert not upload(
        client,
        "statements",
        [
            dict(
                active_data(client)["statements"][0],
                closing_balance=huge + 2,
                known_at="2026-02-01",
            )
        ],
    )["can_commit"]
    for text in ["invoice_id,invoice_id\nI,I\n", "invoice_id,customer_id\nI,C,EXTRA\n"]:
        assert (
            client.post(
                "/v1/imports/preview",
                files={"file": ("bad.csv", text.encode())},
                data=dict(kind="invoices"),
            ).status_code
            == 422
        )
    assert (
        client.post(
            "/v1/allocations",
            json=dict(payment_id="P", invoice_id="ORIGINAL", bank_id="B", amount=0.5,
                      reviewed_by="Test reviewer", note="Test evidence"),
        ).status_code
        == 422
    )
    import_all(
        client,
        {
            "bank": [
                dict(
                    bank_id="LARGE",
                    account="A",
                    date="2026-01-02",
                    known_at="2026-01-02",
                    direction="in",
                    amount=huge,
                )
            ]
        },
    )
    pending = client.get("/v1/reconciliation").json()["pending"]
    assert next(r for r in pending if r["bank_id"] == "LARGE")["unallocated"] == str(
        huge
    )
    assert client.post(
        "/v1/allocations",
        json=dict(
            payment_id="EXACT", bank_id="LARGE", invoice_id="ORIGINAL", amount=str(huge),
            reviewed_by="Test reviewer", note="Large VND bank evidence"
        ),
    ).is_success
    assert active_data(client)["payments"][0]["amount"] == huge
    assert not upload(
        client,
        "bank",
        [
            dict(
                bank_id="USD",
                account="A",
                date="2026-01-02",
                known_at="2026-01-02",
                direction="in",
                amount=100,
                currency="USD",
            )
        ],
    )["can_commit"]


def test_reviewed_bank_scope_requires_preview_and_unchanged_evidence(
    client, tmp_path, monkeypatch
):
    evidence = tmp_path / "accounts.txt"
    evidence.write_bytes(b"synthetic account confirmation")
    registry = dict(
        firm_id="SME",
        source_type="bank_confirmation",
        reviewed_by="Test",
        reviewed_on="2026-01-01",
        evidence_file=evidence.name,
        evidence_sha256=hashlib.sha256(evidence.read_bytes()).hexdigest(),
        accounts=[dict(account_id=a, bank="vcb", currency="VND") for a in ("A", "B")],
    )
    path = tmp_path / "scope.json"
    path.write_text(json.dumps(registry), encoding="utf-8")
    # The app resolves its registry when constructed, just as the research API does.
    monkeypatch.setenv("AGENT1_BANK_ACCOUNTS_FILE", str(path))
    app = create_app(
        tmp_path / "scoped-data",
        key_dir=tmp_path / "scoped-keys",
        token="scope",
        firm_id="SME",
    )
    with TestClient(app) as scoped:
        scoped.headers["Authorization"] = "Bearer scope"
        bank = dict(
            bank_id="B1",
            account="A",
            date="2026-01-01",
            known_at="2026-01-01",
            direction="in",
            amount=100,
        )
        assert not upload(scoped, "bank", [dict(bank, account="UNKNOWN")])["can_commit"]
        import_all(scoped, {"bank": [bank]})
        assert account_scope(active_data(scoped), "2026-01-01") == ["A", "B"]
        registry["accounts"].append(dict(account_id="C", bank="vcb", currency="VND"))
        path.write_text(json.dumps(registry), encoding="utf-8")
        preview = upload(scoped, "bank", [bank])
        assert preview["can_commit"] and any(
            "Phạm vi" in w for w in preview["warnings"]
        )
        assert scoped.post("/v1/imports/" + preview["id"] + "/commit").is_success
        assert account_scope(active_data(scoped), "2026-01-01") == ["A", "B", "C"]
        preview = upload(scoped, "bank", [dict(bank, bank_id="B2")])
        assert preview["can_commit"]
        evidence.write_bytes(b"changed evidence")
        assert (
            scoped.post("/v1/imports/" + preview["id"] + "/commit").status_code == 422
        )


def test_vietnamese_mapping_strict_money_dates():
    raw = pd.DataFrame(
        [
            {
                "Mã hóa đơn": "HD1",
                "Mã khách hàng": "KH1",
                "Ngày lập": "01/01/2026",
                "Hạn thanh toán": "31/01/2026",
                "Số tiền": "1.500.000,00",
            }
        ]
    )
    mapping = suggested_mapping(raw.columns, "invoices")
    rows, errors, warnings = parse_rows(raw, "invoices", mapping)
    assert not errors and rows[0]["amount"] == 1500000 and warnings
    for invalid in [
        "1.500.000,50",
        "1.2.3",
        "1,000.00",
        "NaN",
        "inf",
        "-50",
        "=SUM(1,2)",
    ]:
        raw.loc[0, "Số tiền"] = invalid
        assert parse_rows(raw, "invoices", mapping)[1]
    raw.loc[0, "Số tiền"] = "1000"
    raw.loc[0, "Ngày lập"] = "31/02/2026"
    assert parse_rows(raw, "invoices", mapping)[1]


def test_excel_native_date_and_numeric_values():
    raw = pd.DataFrame(
        [
            dict(
                invoice_id="I",
                customer_id="C",
                issue_date=pd.Timestamp("2026-01-01"),
                due_date=pd.Timestamp("2026-02-01"),
                amount=1500000.0,
            )
        ]
    )
    rows, errors, _ = parse_rows(
        raw, "invoices", suggested_mapping(raw.columns, "invoices")
    )
    assert not errors and rows[0]["amount"] == 1500000
    for value in (1500000.5, float(2**53)):
        raw.loc[0, "amount"] = value
        assert parse_rows(raw, "invoices", suggested_mapping(raw.columns, "invoices"))[
            1
        ]


def test_duplicates_orphans_overpayments_and_schedule_clock():
    data = company_data(2)
    raw = pd.DataFrame(data["invoices"][:1] * 2)
    assert parse_rows(
        raw, "invoices", suggested_mapping(raw.columns, "invoices"), "%Y-%m-%d", "plain"
    )[1]
    data["payments"].append(
        dict(
            payment_id="bad",
            invoice_id="absent",
            payment_date="2025-01-01",
            known_at="2025-01-01",
            amount=5,
        )
    )
    with pytest.raises(ValueError, match="chưa có"):
        validate_dataset(data)
    data["payments"][-1]["invoice_id"] = data["invoices"][0]["invoice_id"]
    data["payments"][-1]["amount"] = 1e12
    with pytest.raises(ValueError, match="vượt"):
        validate_dataset(data)
    raw = pd.DataFrame(
        [dict(expense_id="X", date="2026-12-01", amount=100, category="rent")]
    )
    assert parse_rows(
        raw, "outflows", suggested_mapping(raw.columns, "outflows"), "%Y-%m-%d", "plain"
    )[1]


def test_future_and_late_payment_do_not_leak_or_erase_partial_payments():
    data = company_data(1)
    iid = data["invoices"][0]["invoice_id"]
    data["payments"] = [
        dict(
            payment_id="A",
            invoice_id=iid,
            payment_date="2025-01-03",
            known_at="2025-01-03",
            amount=40000,
        ),
        dict(
            payment_id="B",
            invoice_id=iid,
            payment_date="2025-01-05",
            known_at="2025-02-10",
            amount=60000,
        ),
    ]
    early = observed(data, "2025-02-01").set_index("invoice_id").loc[iid]
    assert pd.isna(early.settled) and early.remaining_amount == 60000
    late = observed(data, "2025-02-11").set_index("invoice_id").loc[iid]
    assert late.settled == pd.Timestamp(
        "2025-01-05"
    ) and late.settled_known_at == pd.Timestamp("2025-02-10")
    frame = observed(data, "2025-02-11")
    target = frame.iloc[:1].copy()
    target.issue_date = pd.Timestamp("2025-02-01")
    assert features(target, frame)[0, -1] == 0


def test_full_week_risk_includes_only_complete_observation():
    data = company_data(1)
    data["payments"] = [
        dict(
            payment_id="P",
            invoice_id=data["invoices"][0]["invoice_id"],
            payment_date="2025-01-03",
            known_at="2025-01-03",
            amount=100000,
        )
    ]
    model = Method("survival").fit(observed(data, "2025-01-06"), "2025-01-06")
    assert model.hazard[0] == pytest.approx(0.5 / 5)
    model = Method("survival").fit(observed(data, "2025-01-08"), "2025-01-08")
    assert model.hazard[0] == pytest.approx(1.5 / 7)
    p = model.distribution(model.history)
    assert np.allclose(p.sum(axis=1), 1) and (p >= 0).all()


def test_training_cohorts_refits_and_audit_is_not_selection():
    data = company_data()
    calls = []
    original = Method.fit

    def fit(self, frame, clock):
        calls.append((self.name, pd.Timestamp(clock), frame.issue_date.max()))
        return original(self, frame, clock)

    with patch.object(Method, "fit", fit):
        bundle = train(data, "2025-08-01", names=["customer", "survival", "logistic"])
    assert (
        bundle["train_n"] >= 60
        and bundle["validation_n"] >= 20
        and bundle["audit"]["n"] >= 20
    )
    assert all(latest <= clock for _, clock, latest in calls)
    assert {"2025-05-09", "2025-06-06", "2025-07-04"}.issubset(
        {str(clock.date()) for _, clock, _ in calls}
    )
    assert {str(clock.date()) for _, clock, _ in calls}.issuperset(
        {
            "2025-04-11",
            "2025-06-06",
            "2025-08-01",
        }
    )
    assert [r["method"] for r in bundle["selection"]] == [
        "customer",
        "survival",
        "logistic",
        "pool",
    ]
    assert np.isfinite(bundle["audit"]["log_loss4"])
    assert (
        bundle["audit"]["improvement_ci_low"] <= bundle["audit"]["improvement_ci_high"]
    )
    assert bundle["weight"] == 0 if not bundle["audit"]["accepted"] else True


def test_late_invoice_not_used_in_issue_origin_evaluation():
    data = company_data()
    for invoice in data["invoices"]:
        invoice["known_at"] = "2025-08-01"
    with pytest.raises(ValueError, match="Chưa đủ"):
        train(data, "2025-08-01", names=["customer"])


def test_forecast_cash_identity_asof_and_stress():
    data = company_data()
    baseline = forecast(data, "2025-08-01", 1000000)
    stressed = forecast(
        data, "2025-08-01", 1000000, delay_days=14, expense_multiplier=1.2
    )
    assert stressed["weeks"][0]["cash_in"] <= baseline["weeks"][0]["cash_in"]
    balance = 1000000
    for week in baseline["weeks"]:
        balance += week["cash_in"] - week["cash_out"]
        assert week["balance"] == pytest.approx(balance)
        assert week["low"] <= week["high"]
    future = dict(data)
    future["outflows"] = data["outflows"] + [
        dict(
            expense_id="future",
            date="2025-08-08",
            known_at="2025-08-02",
            amount=1e12,
            category="x",
        )
    ]
    assert forecast(future, "2025-08-01", 1000000) == baseline
    with pytest.raises(ValueError, match="sau ngày"):
        forecast(data, "2025-08-01", 0, bundle={"asof": "2025-09-01"})


def test_api_auth_static_no_secret_and_preview_atomicity(client):
    assert (
        client.get(
            "/v1/workspace", headers={"Authorization": "Bearer wrong"}
        ).status_code
        == 401
    )
    html = client.get("/workspace")
    assert html.status_code == 200 and "Sổ điều hành" in html.text
    assert "company-test-token" not in html.text
    for asset in [
        "app.js",
        "style.css",
        "vendor/uPlot.iife.min.js",
        "vendor/TABLER-LICENSE.txt",
    ]:
        assert client.get("/workspace-assets/" + asset).status_code == 200
    data = company_data(2)
    a = upload(client, "invoices", data["invoices"][:1])
    b = upload(client, "invoices", data["invoices"][1:])
    assert client.post("/v1/imports/" + a["id"] + "/commit").status_code == 200
    assert client.post("/v1/imports/" + b["id"] + "/commit").status_code == 409
    counts = client.get("/v1/workspace").json()["counts"]
    assert counts["invoices"] == 1
    bad = upload(client, "payments", data["payments"])
    assert (
        not bad["can_commit"]
        and client.post("/v1/imports/" + bad["id"] + "/commit").status_code == 422
    )
    assert client.get("/v1/workspace").json()["counts"] == counts


def test_api_requires_completeness_and_rejects_demo(client):
    assert client.post("/v1/training", json={"asof": "2025-08-01"}).status_code == 422
    assert (
        client.post(
            "/v1/predict", json={"cutoff": "2025-08-01", "opening_balance": 0}
        ).status_code
        == 422
    )
    raw = client.get("/v1/templates/invoices").content
    preview = client.post(
        "/v1/imports/preview",
        files={"file": ("demo.csv", raw)},
        data={"kind": "invoices"},
    ).json()
    assert preview["can_commit"]
    assert client.post("/v1/imports/" + preview["id"] + "/commit").status_code == 200
    assert (
        client.post(
            "/v1/training", json={"asof": "2026-11-01", "payments_complete": True}
        ).status_code
        == 422
    )
    assert client.delete("/v1/records/invoices/DEMO_HD001").status_code == 200
    assert client.get("/v1/workspace").json()["counts"]["invoices"] == 0


def test_api_end_to_end_real_models_version_activation_and_update(client):
    data = company_data()
    import_all(client, data)
    original = train
    # Bounded algorithms for integration speed; full-bag execution is checked separately.
    with patch(
        "agent1_service.workspace.api.train",
        lambda data, asof, progress: original(
            data, asof, progress, names=["customer", "survival", "logistic"]
        ),
    ):
        started = client.post(
            "/v1/training", json={"asof": "2025-08-01", "payments_complete": True}
        )
        assert started.status_code == 202
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            result = client.get("/v1/workspace").json()
            if result["jobs"][0]["status"] in ["completed", "failed"]:
                break
            time.sleep(0.05)
        assert result["jobs"][0]["status"] == "completed", result
    assert result["active_version"] is None
    version = result["versions"][0]
    assert (
        not {"artifact", "model", "selection", "selected_method", "selected_weight"}
        & version.keys()
    )
    assert client.post("/v1/models/absent/activate").status_code == 404
    assert client.post("/v1/models/" + version["id"] + "/activate").status_code == 200
    prediction = client.post(
        "/v1/predict",
        json={
            "cutoff": "2025-08-01",
            "opening_balance": 1e6,
            "payments_complete": True,
        },
    )
    assert prediction.status_code == 200, prediction.text
    assert (
        prediction.json()["model_version"] == version["id"]
        and len(prediction.json()["weeks"]) == 13
    )
    assert prediction.json()["pilot_ready"] is False
    # A prior internally generated artifact can be reactivated, without refitting.
    stored = client.app.state.store.get("SME", "company_models")[0]
    second = dict(stored, id="second-version")
    client.app.state.store.put("SME", "company_models", [second])
    assert client.post("/v1/models/second-version/activate").status_code == 200
    assert client.get("/v1/workspace").json()["active_version"] == "second-version"
    assert client.post("/v1/models/" + version["id"] + "/activate").status_code == 200
    assert client.get("/v1/workspace").json()["active_version"] == version["id"]
    update = dict(
        data["invoices"][0], amount=200000, known_at="2025-08-02", record_version=2
    )
    preview = upload(client, "invoices", [update])
    assert preview["updates"] == 1
    assert client.post("/v1/imports/" + preview["id"] + "/commit").status_code == 200
    assert client.get("/v1/workspace").json()["needs_retraining"] is True
    assert client.post(
        "/v1/predict",
        json={
            "cutoff": "2025-08-01",
            "opening_balance": 1e6,
            "payments_complete": True,
        },
    ).json()["stale_model"]
    assert (
        client.delete(
            "/v1/records/invoices/" + data["payments"][0]["invoice_id"]
        ).status_code
        == 409
    )


@pytest.mark.parametrize(
    "method",
    [
        "due",
        "customer",
        "survival",
        "logistic",
        "forest",
        "extra",
        "hist",
        "lightgbm",
        "xgboost",
    ],
)
def test_every_registered_method_can_fit_and_predict(method):
    data = company_data(65)
    frame = observed(data, "2025-04-01")
    model = Method(method).fit(frame, "2025-04-01")
    p = model.distribution(frame.iloc[:5], ages=np.arange(5) * 7)
    assert p.shape == (5, 14) and np.isfinite(p).all() and np.allclose(p.sum(1), 1)


def test_model_and_data_are_encrypted_at_rest(client):
    data = company_data(1)
    preview = upload(client, "invoices", data["invoices"])
    client.post("/v1/imports/" + preview["id"] + "/commit")
    connection = client.app.state.store.connection
    payload = connection.execute(
        "select payload from records where kind='company_datasets'"
    ).fetchone()[0]
    assert b"INV-0-0" not in payload
    assert client.app.state.store.get("another-company", "company_datasets") == []
    assert fingerprint(data) != fingerprint(dict(data, invoices=[]))


def test_browser_security_headers_and_unknown_fields(client):
    response = client.get("/workspace")
    assert response.headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert client.get("/v1/workspace").headers["x-content-type-options"] == "nosniff"
    assert (
        client.post(
            "/v1/training",
            json={"asof": "2025-08-01", "payments_complete": True, "firm": "another"},
        ).status_code
        == 422
    )


def test_delete_and_duplicate_training_blocked_until_worker_finishes(client):
    from threading import Event

    started, release = Event(), Event()

    def worker(*_):
        started.set()
        release.wait(5)
        raise ValueError("Expected test failure")

    with patch("agent1_service.workspace.api.train", worker):
        try:
            body = {"asof": "2025-08-01", "payments_complete": True}
            assert client.post("/v1/training", json=body).status_code == 202
            assert started.wait(2)
            assert client.delete("/data").status_code == 409
            assert client.post("/v1/training", json=body).status_code == 409
        finally:
            release.set()


def test_interrupted_job_is_recoverable_on_restart(tmp_path):
    first = create_app(
        state_dir=tmp_path / "data",
        key_dir=tmp_path / "keys",
        token="test",
        firm_id="SME",
    )
    with TestClient(first):
        first.state.store.put(
            "SME",
            "company_jobs",
            [
                dict(
                    id="interrupted",
                    status="running",
                    message="Old",
                    created_at="2026-01-01",
                )
            ],
        )
    second = create_app(
        state_dir=tmp_path / "data",
        key_dir=tmp_path / "keys",
        token="test",
        firm_id="SME",
    )
    with TestClient(second) as client:
        status = client.get(
            "/v1/workspace", headers={"Authorization": "Bearer test"}
        ).json()
        assert status["jobs"][0]["status"] == "failed"
        assert "khởi động lại" in status["jobs"][0]["message"]


def test_variable_forecast_horizon_and_excel_export(client):
    from datetime import date
    from io import BytesIO
    from openpyxl import load_workbook

    data = company_data()
    # This expense is known at the forecast origin, but falls beyond week 13.
    data["outflows"].append(
        dict(
            expense_id="LATE",
            date="2025-12-10",
            known_at="2025-07-01",
            amount=800000,
            category="rent",
        )
    )
    import_all(client, data)
    body = dict(cutoff="2025-08-01", opening_balance=10000000, payments_complete=True)
    standard = client.post("/v1/predict", json=body).json()
    assert len(standard["weeks"]) == 13
    short = client.post("/v1/predict", json={**body, "horizon_weeks": 1}).json()
    assert short["weeks"] == standard["weeks"][:1]
    assert short["collections"] == standard["collections"]
    response = client.post("/v1/predict", json={**body, "horizon_weeks": 26})
    assert response.status_code == 200, response.text
    plan = response.json()
    assert len(plan["weeks"]) == 26
    assert plan["weeks"][18]["cash_out"] == 800000
    assert plan["weeks"][-1]["date"] == "2026-01-30"
    assert plan["inference_ms"] >= 0
    assert (
        client.post(
            "/v1/predict", json={**body, "horizon_weeks": 2, "confirmed_weeks": [3]}
        ).status_code
        == 422
    )

    exported = client.get("/v1/forecasts/" + plan["id"] + "/xlsx")
    assert exported.status_code == 200, exported.text
    workbook = load_workbook(BytesIO(exported.content))
    assert workbook.sheetnames == [
        "Kết quả dự báo",
        "Kế hoạch từng tuần",
        "Khoản cần chú ý",
        "Phân rã từng tuần",
        "Thu theo hóa đơn",
        "Thu theo khách",
        "Lịch chi đã biết",
        "So sánh thời điểm",
        "Kịch bản từng tuần",
        "Nghĩa vụ T5",
        "Thanh toán T5",
    ]
    weeks = workbook["Kế hoạch từng tuần"]
    assert weeks.max_row == 27
    assert weeks["B27"].value.date() == date(2026, 1, 30)
    assert weeks["B27"].number_format == "dd-mm-yy"
    assert weeks["E20"].value == 800000
    assert workbook["Khoản cần chú ý"].max_row == len(plan["collections"]) + 1


@pytest.fixture
def t9_workspace(client, monkeypatch):
    from agent1.reconciliation import operations
    from agent1_service.workspace import reconciliation, api
    clock = ["2026-03-01"]
    monkeypatch.setattr(operations, "today", lambda: clock[0])
    monkeypatch.setattr(reconciliation, "today", lambda: clock[0])
    monkeypatch.setattr(api, "t9_today", lambda: clock[0])
    return client, clock


def seed_t9(client, *, invoices=None, bank=None, payments=None):
    data = dict(
        invoices=invoices or [dict(invoice_id="I1", customer_id="C1", customer_name="Khach mot",
                                  issue_date="2026-01-01", due_date="2026-02-01", known_at="2026-01-01", amount=100)],
        bank=bank or [dict(bank_id="B1", account="A", date="2026-02-01", known_at="2026-02-02",
                          direction="in", amount=100, memo="Thanh toan I1", counterparty="Khach mot")],
    )
    if payments:
        data["payments"] = payments
    import_all(client, data)


def run_t9(client):
    response = client.post("/v1/reconciliation/run", json={})
    assert response.is_success, response.text
    return response.json()


def review_t9(client, proposal, action="accept", **changes):
    body = dict(idempotency_key="review-" + action, proposal_id=proposal["id"], bank_id="B1",
                reviewed_by="Ke toan", note="Da doi chieu bang ke")
    return client.post("/v1/reconciliation/" + action, json=dict(body, **changes))


def test_t9_workspace_proposal_scores_and_acceptance_update_the_forecast_dataset(t9_workspace):
    client, _ = t9_workspace
    seed_t9(client)
    before = active_data(client)
    proposal = run_t9(client)
    assert proposal["method"] == "constrained_flow"
    assert proposal["cases"][0]["candidates"][0]["score"] == 1
    assert proposal["cases"][0]["available_minor"] == 100
    assert proposal["allocations"][0]["amount_minor"] == 100
    assert active_data(client) == before
    assert client.get("/v1/reconciliation").json()["unallocated"] == 100
    accepted = review_t9(client, proposal)
    assert accepted.is_success, accepted.text
    assert review_t9(client, proposal).json()["replayed"]
    data = active_data(client)
    assert observed(data, "2026-03-01").iloc[0].remaining_amount == 0
    assert observed(data, "2026-02-28").iloc[0].remaining_amount == 100
    assert data["payments"][0]["t9_decision_id"] == accepted.json()["decision_id"]
    view = client.get("/v1/reconciliation").json()
    assert view["pending_count"] == 0 and view["proposal"]["stale"]
    assert view["history"][0]["status"] == "committed"
    assert view["history"][0]["reviewed_by"] == "Ke toan"
    assert client.app.state.store.get("SME", "t9_events") == []  # Research inputs stay separate.
    assert len(client.app.state.store.get("SME", "company_t9_events")) > 0


def test_t9_workspace_rejection_is_audited_idempotent_and_does_not_allocate(t9_workspace):
    client, _ = t9_workspace
    seed_t9(client)
    proposal = run_t9(client)
    before = active_data(client)
    assert review_t9(client, proposal, "reject", note="   ").status_code == 409
    result = review_t9(client, proposal, "reject", note="Khach chua xac nhan")
    assert result.is_success, result.text
    assert review_t9(client, proposal, "reject", note="Khach chua xac nhan").json()["replayed"]
    assert review_t9(client, proposal, "reject", note="Ly do khac").status_code == 409
    assert active_data(client) == before
    assert client.app.state.store.get("SME", "company_t9_events") == []
    assert review_t9(client, proposal).status_code == 409
    fresh = run_t9(client)
    assert fresh["cases"][0]["status"] == "rejected" and not fresh["allocations"]
    view = client.get("/v1/reconciliation").json()
    assert view["unallocated"] == 100 and view["history"][0]["note"] == "Khach chua xac nhan"
    manual = client.post("/v1/allocations", json=dict(payment_id="MANUAL", invoice_id="I1", bank_id="B1", amount=100,
                                                       reviewed_by="Ke toan", note="Bang ke bo sung da ky"))
    assert manual.is_success, manual.text
    assert client.get("/v1/reconciliation").json()["pending_count"] == 0


def test_t9_workspace_scores_cannot_force_an_ambiguous_reference(t9_workspace):
    client, _ = t9_workspace
    seed_t9(client, invoices=[dict(invoice_id=i, customer_id="C1", customer_name="Khach mot", amount=100,
                                  issue_date="2026-01-01", due_date="2026-02-01", known_at="2026-01-01") for i in ("I1", "I2")])
    proposal = run_t9(client)
    assert not proposal["allocations"]
    case = proposal["cases"][0]
    assert case["status"] == "review" and len(case["candidates"]) == 2
    assert case["candidates"][0]["score"] == 1
    assert case["reason_text"]
    assert review_t9(client, proposal).status_code == 409
    assert not active_data(client)["payments"]


def test_t9_workspace_approval_is_per_bank_and_other_cases_become_stale(t9_workspace):
    client, _ = t9_workspace
    seed_t9(client, invoices=[dict(invoice_id=f"I{n}", customer_id=f"C{n}", amount=100*n,
                                  issue_date="2026-01-01", due_date="2026-02-01", known_at="2026-01-01") for n in (1, 2)],
            bank=[dict(bank_id=f"B{n}", account="A", date="2026-02-01", known_at="2026-02-02", direction="in",
                       amount=100*n, memo=f"I{n}", customer_id=f"C{n}") for n in (1, 2)])
    proposal = run_t9(client)
    assert len(proposal["allocations"]) == 2
    assert review_t9(client, proposal).is_success
    assert {r["bank_id"] for r in active_data(client)["payments"]} == {"B1"}
    assert review_t9(client, proposal, bank_id="B2", idempotency_key="second").status_code == 409
    assert review_t9(client, run_t9(client), bank_id="B2", idempotency_key="second").is_success
    assert len(active_data(client)["payments"]) == 2


def test_t9_workspace_partial_imports_reserve_cash_and_reversal_preserves_history(t9_workspace):
    client, clock = t9_workspace
    seed_t9(client, payments=[dict(payment_id="IMPORT", invoice_id="I1", bank_id="B1", amount=20,
                                   payment_date="2026-02-01", known_at="2026-02-02")])
    proposal = run_t9(client)
    assert proposal["allocations"][0]["amount_minor"] == 80
    accepted = review_t9(client, proposal).json()
    clock[0] = "2026-03-02"
    body = dict(idempotency_key="reverse", decision_id=accepted["decision_id"], reviewed_by="Ke toan", note="Sai bang ke")
    response = client.post("/v1/reconciliation/reverse", json=body)
    assert response.is_success, response.text
    assert client.post("/v1/reconciliation/reverse", json=body).json()["replayed"]
    data = active_data(client)
    assert [r["payment_id"] for r in data["payments"]] == ["IMPORT"]
    assert observed(data, "2026-03-01").iloc[0].remaining_amount == 0
    assert observed(data, "2026-03-02").iloc[0].remaining_amount == 80
    view = client.get("/v1/reconciliation").json()
    assert view["unallocated"] == 80 and view["history"][0]["status"] == "reversed"
    assert view["history"][0]["reversal"]["note"] == "Sai bang ke"
    assert data["bank"][0]["amount"] == 100


def test_t9_workspace_stale_sources_and_managed_payment_edits_are_blocked(t9_workspace):
    client, _ = t9_workspace
    seed_t9(client)
    proposal = run_t9(client)
    import_all(client, {"payments": [dict(payment_id="P0", invoice_id="I1", bank_id="B1", amount=20,
                                        payment_date="2026-02-01", known_at="2026-02-02")]})
    assert review_t9(client, proposal).status_code == 409
    accepted = review_t9(client, run_t9(client))
    assert accepted.is_success, accepted.text
    payment = next(r for r in active_data(client)["payments"] if r.get("t9_decision_id"))
    before = active_data(client)
    assert client.delete("/v1/records/payments/" + payment["payment_id"]).status_code == 422
    assert not upload(client, "payments", [dict(payment, amount=79, known_at="2026-03-02")])["can_commit"]
    assert active_data(client) == before
    # A corrected payer on the source cannot silently move a committed receipt.
    bank = active_data(client)["bank"][0]
    assert not upload(client, "bank", [dict(bank, customer_id="OTHER", known_at="2026-03-02")])["can_commit"]


def test_t9_workspace_acceptance_rolls_back_events_and_dataset_together(t9_workspace, monkeypatch):
    client, _ = t9_workspace
    from agent1_service.workspace import reconciliation
    seed_t9(client)
    proposal = run_t9(client)
    before = active_data(client)
    original = reconciliation.dataset_batches
    def invalid_batch(data):
        batches, result = original(data)
        batches["company_datasets"][0]["not_serializable"] = object()
        return batches, result
    monkeypatch.setattr(reconciliation, "dataset_batches", invalid_batch)
    assert review_t9(client, proposal).status_code == 409
    assert active_data(client) == before
    store = client.app.state.store
    assert not store.get("SME", "company_t9_events")
    assert not store.get("SME", "company_t9_requests")
    assert not store.get("SME", "company_t9_reviews")


def test_t9_workspace_huge_vnd_stays_exact_and_non_ar_is_not_matched(t9_workspace):
    client, _ = t9_workspace
    huge = 2**53 + 17
    seed_t9(client, invoices=[dict(invoice_id="I1", customer_id="C1", amount=str(huge + 1), issue_date="2026-01-01",
                                  due_date="2026-02-01", known_at="2026-01-01")],
            bank=[dict(bank_id="B1", account="A", date="2026-02-01", known_at="2026-02-02", direction="in", amount=str(huge), memo="I1"),
                  dict(bank_id="NONAR", account="A", date="2026-02-01", known_at="2026-02-02", direction="in", amount=100,
                       memo="I1", cash_flow_class="financing")])
    proposal = run_t9(client)
    assert proposal["allocations"][0]["amount_minor"] == str(huge)
    assert next(r for r in proposal["cases"] if r["bank_id"] == "NONAR")["reason"] == "non_ar_bank_movement"
    assert review_t9(client, proposal).is_success
    assert observed(active_data(client), "2026-03-01").iloc[0].remaining_amount == 1
    view = client.get("/v1/reconciliation").json()
    assert view["pending_count"] == 0 and view["unallocated"] == 0
    assert client.post("/v1/allocations", json=dict(payment_id="INVALID", invoice_id="I1", bank_id="NONAR", amount=1,
                                                      reviewed_by="Test reviewer", note="Loan transfer")).status_code == 422


def test_t9_workspace_routes_require_accountant_and_ui_contains_review_controls(t9_workspace, monkeypatch):
    client, _ = t9_workspace
    monkeypatch.setenv("AGENT1_VIEWER_TOKEN", "readonly")
    for endpoint in ("run", "accept", "reject", "reverse"):
        assert client.post("/v1/reconciliation/" + endpoint, json={}, headers={"Authorization": "Bearer readonly"}).status_code == 401
    html = client.get("/workspace").text
    for identifier in ("run-reconciliation", "reconciliation-reviewer", "reconciliation-cases", "reconciliation-history", "allocate-note"):
        assert f'id="{identifier}"' in html


def test_t9_workspace_mixed_optional_invoice_metadata_does_not_create_nan_candidates(t9_workspace):
    client, _ = t9_workspace
    seed_t9(client, invoices=[
        dict(invoice_id="I1", customer_id="C1", amount=100, issue_date="2026-01-01", due_date="2026-02-01", known_at="2026-01-01"),
        dict(invoice_id="I2", customer_id="C2", customer_name="Khach hai", amount=200,
             issue_date="2026-01-01", due_date="2026-02-01", known_at="2026-01-01"),
    ])
    proposal = run_t9(client)
    assert proposal["allocations"][0]["invoice_id"] == "I1"
    assert review_t9(client, proposal).is_success


def test_t0_deleted_id_cannot_be_reimported_with_retroactive_knowledge(client):
    seed_t9(client)
    assert client.delete('/v1/records/bank/B1').is_success
    before = active_data(client)
    changed = dict(bank_id='B1', account='A', date='2026-02-01', known_at='2026-02-03', direction='in', amount=200)
    preview = upload(client, 'bank', [changed])
    assert not preview['can_commit'], 'Reusing a deleted ID must not rewrite an older snapshot'
    assert active_data(client) == before


@pytest.mark.parametrize('change', [dict(cash_flow_class='financing'), dict(customer_id='OTHER')])
def test_t0_payment_csv_obeys_bank_class_and_customer_constraints(t9_workspace, change):
    client, _ = t9_workspace
    bank = dict(bank_id='B1', account='A', date='2026-02-01', known_at='2026-02-02', direction='in', amount=100, **change)
    seed_t9(client, bank=[bank])
    payment = dict(payment_id='P1', invoice_id='I1', bank_id='B1', amount=100,
                   payment_date='2026-02-01', known_at='2026-02-02')
    assert not upload(client, 'payments', [payment])['can_commit']
    assert not active_data(client)['payments']


def test_t0_payment_csv_cannot_split_a_bank_receipt_across_customers(t9_workspace):
    client, _ = t9_workspace
    seed_t9(client, invoices=[dict(invoice_id=i, customer_id=c, amount=100, issue_date='2026-01-01',
                                  due_date='2026-02-01', known_at='2026-01-01') for i, c in [('I1', 'C1'), ('I2', 'C2')]])
    receipts = [dict(payment_id='P' + str(n), invoice_id=i, bank_id='B1', amount=50,
                     payment_date='2026-02-01', known_at='2026-02-02') for n, i in enumerate(('I1', 'I2'))]
    assert not upload(client, 'payments', receipts)['can_commit']
    assert client.get('/v1/reconciliation').is_success


def test_t9_writeoff_follows_replacement_chain_and_cannot_be_allocated(t9_workspace):
    client, _ = t9_workspace
    original = accounting_invoice()
    replacement = accounting_invoice('REPLACEMENT', issue_date='2026-01-10', known_at='2026-01-20',
                                     adjustment_type='replacement', adjusts_invoice_id='ORIGINAL')
    import_all(client, dict(invoices=[original]))
    import_all(client, dict(invoices=[replacement]))
    import_all(client, dict(actions=[dict(event_id='WO', invoice_id='ORIGINAL', date='2026-01-05',
                                         known_at='2026-01-05', kind='write_off')],
                           bank=[dict(bank_id='B1', account='A', date='2026-02-01', known_at='2026-02-02',
                                      direction='in', amount=1100, memo='REPLACEMENT', customer_id='BUYER')]))
    assert observed(active_data(client), '2026-03-01').iloc[0].written_off_at == pd.Timestamp('2026-01-05')
    proposal = run_t9(client)
    assert not proposal['allocations'], 'A replaced invoice must retain its write-off state'
    manual = client.post('/v1/allocations', json=dict(payment_id='P1', invoice_id='REPLACEMENT', bank_id='B1', amount=100,
                                                      reviewed_by='Test reviewer', note='Replaced invoice'))
    assert manual.status_code == 422


def test_t9_manual_retry_cannot_silently_change_reviewer_or_evidence(t9_workspace):
    client, _ = t9_workspace
    seed_t9(client)
    request = dict(payment_id='P1', invoice_id='I1', bank_id='B1', amount=100,
                   reviewed_by='Original reviewer', note='Original evidence')
    assert client.post('/v1/allocations', json=request).is_success
    assert client.post('/v1/allocations', json=request).json()['replayed']
    response = client.post('/v1/allocations', json=dict(request, reviewed_by='Other reviewer', note='Other evidence'))
    assert response.status_code in (409, 422)
    assert client.get('/v1/reconciliation').json()['history'][0]['reviewed_by'] == 'Original reviewer'


def test_t9_manual_allocation_requires_explicit_reviewer_and_evidence(t9_workspace):
    client, _ = t9_workspace
    seed_t9(client)
    request = dict(payment_id='P1', invoice_id='I1', bank_id='B1', amount=100)
    for incomplete in (request, dict(request, reviewed_by='Accountant'),
                       dict(request, note='Signed receipt'),
                       dict(request, reviewed_by='  ', note='Signed receipt'),
                       dict(request, reviewed_by='Accountant', note='  ')):
        response = client.post('/v1/allocations', json=incomplete)
        assert response.status_code == 422, response.text
        assert client.get('/v1/reconciliation').json()['history'] == []
    response = client.post('/v1/allocations', json=dict(request, reviewed_by=' Accountant ', note=' Signed receipt '))
    assert response.is_success, response.text
    history = client.get('/v1/reconciliation').json()['history']
    assert history[0]['reviewed_by'] == 'Accountant'
    assert history[0]['note'] == 'Signed receipt'


def test_t0_replacement_cannot_move_observed_receipts_to_another_customer(t9_workspace):
    client, _ = t9_workspace
    original = accounting_invoice()
    import_all(client, dict(invoices=[original], payments=[dict(payment_id='P1', invoice_id='ORIGINAL', amount=500,
                                                               payment_date='2026-01-05', known_at='2026-01-05')]))
    replacement = accounting_invoice('REPLACEMENT', customer_id='OTHER',
        buyer_mst=make_mst(np.random.default_rng(21)), issue_date='2026-01-10', known_at='2026-01-20',
        adjustment_type='replacement', adjusts_invoice_id='ORIGINAL')
    assert not upload(client, 'invoices', [replacement])['can_commit']
    assert observed(active_data(client), '2026-03-01').iloc[0].customer_id == 'BUYER'


def test_t9_accepted_bank_source_cannot_be_moved_to_a_different_account(t9_workspace):
    client, _ = t9_workspace
    seed_t9(client)
    assert review_t9(client, run_t9(client)).is_success
    bank = active_data(client)['bank'][0]
    assert not upload(client, 'bank', [dict(bank, account='OTHER', known_at='2026-03-01')])['can_commit']
    assert active_data(client)['bank'][0]['account'] == 'A'


def test_t0_restore_deleted_id_with_a_later_clock_preserves_the_old_snapshot():
    from agent1.adaptive.data import merge_import, as_of
    first = dict(invoice_id='I1', customer_id='C1', amount=100, issue_date='2026-01-01',
                 due_date='2026-02-01', known_at='2026-01-01')
    data = dict(invoices=[], payments=[], outflows=[], record_history=dict(invoices=[first,
        dict(invoice_id='I1', known_at='2026-02-01', _deleted=True)]))
    restored = merge_import(data, 'invoices', [dict(first, amount=200, known_at='2026-02-02', record_version=2)])
    assert as_of(restored, '2026-01-31')['invoices'][0]['amount'] == 100
    assert not as_of(restored, '2026-02-01')['invoices']
    assert as_of(restored, '2026-02-02')['invoices'][0]['amount'] == 200


@pytest.mark.parametrize('kind,change', [
    ('bank', dict(amount=110)), ('bank', dict(date='2026-02-03')),
    ('bank', dict(customer_id='OTHER')), ('invoices', dict(customer_id='OTHER', record_version=2)),
])
def test_t0_reversed_ledger_endpoints_cannot_be_reused_with_changed_identity(t9_workspace, kind, change):
    client, clock = t9_workspace
    seed_t9(client)
    accepted = review_t9(client, run_t9(client)).json()
    clock[0] = '2026-03-02'
    response = client.post('/v1/reconciliation/reverse', json=dict(idempotency_key='undo',
        decision_id=accepted['decision_id'], reviewed_by='Ke toan', note='Doi chieu nguon'))
    assert response.is_success, response.text
    original = active_data(client)[kind][0]
    preview = upload(client, kind, [dict(original, known_at=clock[0], **change)])
    assert not preview['can_commit'], 'An immutable ledger endpoint must not become an unusable new proposal'
    assert run_t9(client)['allocations']


def preview_source_edit(client, changes, **extra):
    body = dict(base_hash=fingerprint(active_data(client)), changes=changes,
                reviewed_by='Ke toan sua nguon', note='Doi chieu chung tu goc, sua loi nhap')
    return client.post('/v1/corrections/preview', json=dict(body, **extra))


def commit_source_edit(client, preview, key='correct-1'):
    return client.post('/v1/corrections/' + preview['id'] + '/commit', json=dict(idempotency_key=key))


def test_source_correction_bank_reverses_old_allocation_and_counts_corrected_cash_once(t9_workspace, monkeypatch):
    client, _ = t9_workspace
    from agent1_service.workspace import reconciliation
    from agent1.reconciliation.ledger import DecisionLedger
    from agent1.adaptive.data import as_of
    timestamp = ['2026-03-01T10:00:00+07:00']
    monkeypatch.setattr(reconciliation, 'correction_time', lambda: timestamp[0])
    seed_t9(client, invoices=[dict(invoice_id=i, customer_id=c, amount=a, issue_date='2026-01-01',
                                  due_date='2026-02-01', known_at='2026-01-01') for i,c,a in [('I1','C1',100),('I2','C2',150)]])
    old = review_t9(client, run_t9(client)).json()
    before = active_data(client)
    ledger = DecisionLedger(client.app.state.store, 'SME', prefix='company_')
    old_sequence = len(ledger.events())
    timestamp[0] = '2026-03-01T11:00:00+07:00'
    response = preview_source_edit(client, [dict(kind='bank', identifier='B1', values=dict(
        amount='150', date='2026-02-03', account='CORRECT', customer_id='C2', memo='TT I2'))])
    assert response.is_success, response.text
    preview = response.json()
    assert len(preview['affected_decisions']) == len(preview['affected_payments']) == 1
    assert active_data(client) == before and ledger.gold('2026-03-01')['decisions'][0]['status'] == 'committed'
    timestamp[0] = '2026-03-01T11:01:00+07:00'
    result = commit_source_edit(client, preview)
    assert result.is_success, result.text
    assert commit_source_edit(client, preview).json()['replayed']
    data = active_data(client)
    assert not data['payments'] and data['bank'][0]['bank_id'] == 'B1' and data['bank'][0]['amount'] == 150
    assert as_of(data, '2026-03-01T10:30:00+07:00')['bank'][0]['amount'] == 100
    assert len(as_of(data, '2026-03-01T10:30:00+07:00')['payments']) == 1
    assert as_of(data, '2026-03-01T11:02:00+07:00')['bank'][0]['amount'] == 150
    assert ledger.gold('2026-03-01', until_sequence=old_sequence)['bank_movements'][0]['net_minor'] == 100
    gold = ledger.gold('2026-03-01')
    assert gold['bank_movements'][0]['net_minor'] == 150
    assert gold['decisions'][0]['decision_id'] == old['decision_id'] and gold['decisions'][0]['status'] == 'reversed'
    timestamp[0] = '2026-03-01T12:00:00+07:00'
    proposal = run_t9(client)
    assert proposal['allocations'][0]['invoice_id'] == 'I2'
    accepted = review_t9(client, proposal, idempotency_key='accept-corrected')
    assert accepted.is_success, accepted.text
    assert ledger.gold('2026-03-01')['bank_movements'][0]['net_minor'] == 150
    assert not as_of(active_data(client), '2026-03-01T11:30:00+07:00')['payments']
    history = client.get('/v1/reconciliation').json()['history']
    assert any(r['status'] == 'corrected' and r['changes'][0]['before']['amount'] == 100 for r in history)
    assert client.app.state.store.one('SME', 'company_datasets', fingerprint(before))['data'] == before


def test_source_correction_invoice_can_change_party_and_amount_then_be_reviewed_again(t9_workspace):
    client, _ = t9_workspace
    from agent1.reconciliation.ledger import DecisionLedger
    seed_t9(client)
    assert review_t9(client, run_t9(client)).is_success
    response = preview_source_edit(client, [dict(kind='invoices', identifier='I1', values=dict(
        customer_id='C2', amount='200', issue_date='2026-01-02'))])
    assert response.is_success, response.text
    result = commit_source_edit(client, response.json())
    assert result.is_success, result.text
    assert not active_data(client)['payments']
    proposal = run_t9(client)
    accepted = review_t9(client, proposal, idempotency_key='corrected-invoice')
    assert accepted.is_success, accepted.text
    row = observed(active_data(client), '2026-03-01').iloc[0]
    assert row.customer_id == 'C2' and row.remaining_amount == 100
    gold = DecisionLedger(client.app.state.store, 'SME', prefix='company_').gold('2026-03-01')
    assert gold['bank_movements'][0]['net_minor'] == 100
    assert gold['invoices'][0]['party_id'] == 'C2'


def test_source_correction_supports_same_day_unallocated_record_and_keeps_old_version(t9_workspace, monkeypatch):
    client, _ = t9_workspace
    from agent1_service.workspace import reconciliation
    from agent1.adaptive.data import as_of
    seed_t9(client, invoices=[dict(invoice_id='I1', customer_id='C1', amount=100, issue_date='2026-03-01',
                                  due_date='2026-04-01', known_at='2026-03-01')])
    monkeypatch.setattr(reconciliation, 'correction_time', lambda: '2026-03-01T11:00:00+07:00')
    response = preview_source_edit(client, [dict(kind='invoices', identifier='I1', values=dict(amount='200'))])
    assert response.is_success, response.text
    assert not response.json()['affected_decisions']
    assert commit_source_edit(client, response.json()).is_success
    data = active_data(client)
    assert as_of(data, '2026-03-01T10:00:00+07:00')['invoices'][0]['amount'] == 100
    assert as_of(data, '2026-03-01T12:00:00+07:00')['invoices'][0]['amount'] == 200
    assert as_of(data, '2026-03-01')['invoices'][0]['amount'] == 200


def test_source_correction_stale_preview_and_changed_idempotency_key_are_blocked(t9_workspace):
    client, _ = t9_workspace
    seed_t9(client)
    changes = [dict(kind='bank', identifier='B1', values=dict(amount='120'))]
    first = preview_source_edit(client, changes).json()
    assert review_t9(client, run_t9(client)).is_success
    assert commit_source_edit(client, first).status_code == 409
    fresh = preview_source_edit(client, changes).json()
    assert commit_source_edit(client, fresh).is_success
    second = preview_source_edit(client, [dict(kind='bank', identifier='B1', values=dict(amount='130'))]).json()
    assert commit_source_edit(client, second).status_code == 409
    assert commit_source_edit(client, second, key='correct-2').is_success


def test_source_correction_batch_checks_statement_balance_and_preserves_imported_receipt_history(t9_workspace):
    client, _ = t9_workspace
    seed_t9(client, payments=[dict(payment_id='IMPORTED', invoice_id='I1', bank_id='B1', amount=20,
                                   payment_date='2026-02-01', known_at='2026-02-02')])
    import_all(client, dict(statements=[dict(statement_id='S1', account='A', start_date='2026-02-01', end_date='2026-02-28',
                                            opening_balance=0, closing_balance=100, known_at='2026-02-28')]))
    bank_change = dict(kind='bank', identifier='B1', values=dict(amount='200'))
    assert preview_source_edit(client, [bank_change]).status_code == 422
    response = preview_source_edit(client, [bank_change, dict(kind='statements', identifier='S1', values=dict(closing_balance='200'))])
    assert response.is_success, response.text
    assert response.json()['affected_payments'][0]['payment_id'] == 'IMPORTED'
    assert commit_source_edit(client, response.json()).is_success
    assert not active_data(client)['payments']
    assert observed(active_data(client), '2026-02-28').iloc[0].received == 20
    assert active_data(client)['statements'][0]['closing_balance'] == 200


def test_source_correction_is_atomic_if_dataset_write_fails(t9_workspace, monkeypatch):
    client, _ = t9_workspace
    from agent1_service.workspace import reconciliation
    seed_t9(client)
    assert review_t9(client, run_t9(client)).is_success
    response = preview_source_edit(client, [dict(kind='bank', identifier='B1', values=dict(amount='120'))])
    assert response.is_success, response.text
    before = active_data(client)
    events = client.app.state.store.get('SME', 'company_t9_events')
    original = reconciliation.dataset_batches
    def fail(data):
        batches, result = original(data)
        batches['company_datasets'][0]['invalid'] = object()
        return batches, result
    monkeypatch.setattr(reconciliation, 'dataset_batches', fail)
    assert commit_source_edit(client, response.json()).status_code == 409
    assert active_data(client) == before
    assert client.app.state.store.get('SME', 'company_t9_events') == events


def test_source_correction_read_and_write_require_accountant_and_server_owns_knowledge_clock(t9_workspace, monkeypatch):
    client, _ = t9_workspace
    monkeypatch.setenv('AGENT1_VIEWER_TOKEN', 'readonly')
    seed_t9(client)
    readonly = dict(Authorization='Bearer readonly')
    assert client.get('/v1/corrections/record?kind=bank&identifier=B1', headers=readonly).status_code == 401
    assert client.post('/v1/corrections/preview', json={}, headers=readonly).status_code == 401
    assert client.post('/v1/corrections/unknown/commit', json=dict(idempotency_key='x'), headers=readonly).status_code == 401
    record = client.get('/v1/corrections/record?kind=bank&identifier=B1')
    assert record.is_success and record.json()['values']['amount'] == '100'
    for values in (dict(known_at='2020-01-01'), dict(bank_id='OTHER'), dict(amount=100.5), dict(amount=True)):
        assert preview_source_edit(client, [dict(kind='bank', identifier='B1', values=values)]).status_code == 422
    assert preview_source_edit(client, [dict(kind='bank', identifier='MISSING', values=dict(amount='120'))]).status_code == 422
    from html.parser import HTMLParser
    class Forms(HTMLParser):
        depth = 0
        def __init__(self):
            super().__init__()
            self.identifiers = set()
        def handle_starttag(self, tag, attrs):
            if tag == 'form':
                assert not self.depth, 'Nested HTML forms prevent source correction submission'
                self.depth += 1
            for key, value in attrs:
                if key == 'id':
                    assert value not in self.identifiers
                    self.identifiers.add(value)
        def handle_endtag(self, tag):
            if tag == 'form':
                self.depth -= 1
    forms = Forms()
    forms.feed(client.get('/workspace').text)
    assert forms.depth == 0
    assert {'source-correction-load', 'source-correction-form', 'source-correction-preview', 'commit-source-correction'} <= forms.identifiers


def test_source_correction_reverses_shared_bank_decisions_and_preserves_unrelated_cash(t9_workspace):
    client, _ = t9_workspace
    from agent1.reconciliation.ledger import DecisionLedger
    seed_t9(client, invoices=[dict(invoice_id=i, customer_id='C1', amount=a, issue_date='2026-01-01',
        due_date='2026-02-01', known_at='2026-01-01') for i,a in [('I1',100),('I2',200),('I3',70)]],
        bank=[dict(bank_id=b, account='A', date='2026-02-01', known_at='2026-02-02', direction='in',
                   amount=a, memo=m, customer_id='C1') for b,a,m in [('B1',150,'I1 I2'),('B2',70,'I3')]])
    for pid, iid, bid, amount in [('P1','I1','B1',100), ('P2','I2','B1',50), ('P3','I3','B2',70)]:
        response = client.post('/v1/allocations', json=dict(payment_id=pid, invoice_id=iid, bank_id=bid, amount=amount,
                                                            reviewed_by='Test reviewer', note='Shared bank source evidence'))
        assert response.is_success, response.text
    response = preview_source_edit(client, [dict(kind='invoices', identifier='I1', values=dict(amount='90'))])
    assert response.is_success, response.text
    assert len(response.json()['affected_decisions']) == 2
    assert {r['payment_id'] for r in response.json()['affected_payments']} == {'P1','P2'}
    assert commit_source_edit(client, response.json()).is_success
    assert [r['payment_id'] for r in active_data(client)['payments']] == ['P3']
    ledger = DecisionLedger(client.app.state.store, 'SME', prefix='company_')
    gold = ledger.gold('2026-03-01')
    assert gold['bank_movements'][0]['net_minor'] == 220
    assert sorted(r['status'] for r in gold['decisions']) == ['committed','reversed','reversed']
    second = preview_source_edit(client, [dict(kind='bank', identifier='B1', values=dict(amount='160'))])
    assert second.is_success, second.text
    assert commit_source_edit(client, second.json(), key='second-correction').is_success
    assert ledger.gold('2026-03-01')['bank_movements'][0]['net_minor'] == 230


def test_source_correction_full_invoice_keeps_original_source_retry_idempotent(t9_workspace):
    client, _ = t9_workspace
    original = accounting_invoice()
    import_all(client, dict(invoices=[original]))
    response = preview_source_edit(client, [dict(kind='invoices', identifier='ORIGINAL',
        values=dict(amount='2200', amount_net='2000', vat='200'))])
    assert response.is_success, response.text
    assert commit_source_edit(client, response.json()).is_success
    corrected = active_data(client)['invoices'][0]
    assert corrected['amount'] == 2200 and corrected['record_version'] == 2
    assert corrected['source_lineage']['workspace_correction']['correction_id'] == response.json()['id']
    # An older original file cannot silently overwrite reviewed corrected facts.
    retry = upload(client, 'invoices', [original])
    assert not retry['can_commit'] or not retry['updates']
    assert active_data(client)['invoices'][0]['amount'] == 2200


def test_source_correction_imported_payment_and_nonfinancial_edit_do_not_erase_unrelated_allocations(t9_workspace):
    client, _ = t9_workspace
    seed_t9(client, payments=[dict(payment_id='CSV1', invoice_id='I1', bank_id='B1', amount=20,
                                   payment_date='2026-02-01', known_at='2026-02-02')])
    change = dict(kind='payments', identifier='CSV1', values=dict(amount='30'))
    response = preview_source_edit(client, [change])
    assert response.is_success, response.text
    assert commit_source_edit(client, response.json()).is_success
    assert observed(active_data(client), '2026-03-01').iloc[0].received == 30
    assert observed(active_data(client), '2026-02-28').iloc[0].received == 20
    assert review_t9(client, run_t9(client)).is_success
    preview = preview_source_edit(client, [dict(kind='invoices', identifier='I1', values=dict(customer_name='Ten da sua'))])
    assert preview.is_success and not preview.json()['affected_decisions']
    assert commit_source_edit(client, preview.json(), key='rename').is_success
    assert observed(active_data(client), '2026-03-01').iloc[0].remaining_amount == 0
    protected = next(r for r in active_data(client)['payments'] if r.get('t9_decision_id'))
    assert client.get('/v1/corrections/record', params=dict(kind='payments', identifier=protected['payment_id'])).status_code == 422


def test_source_correction_clears_old_writeoff_with_explicit_preview(t9_workspace):
    client, _ = t9_workspace
    seed_t9(client)
    import_all(client, dict(actions=[dict(event_id='WO1', invoice_id='I1', date='2026-02-01',
                                          known_at='2026-02-02', kind='write_off')]))
    preview = preview_source_edit(client, [dict(kind='invoices', identifier='I1', values=dict(amount='120'))])
    assert preview.is_success, preview.text
    assert preview.json()['affected_actions'][0]['event_id'] == 'WO1'
    assert commit_source_edit(client, preview.json()).is_success
    assert not active_data(client)['actions']
    assert observed(active_data(client), '2026-02-28').iloc[0].written_off_at == pd.Timestamp('2026-02-01')
    assert pd.isna(observed(active_data(client), '2026-03-01').iloc[0].written_off_at)


def test_source_correction_preview_is_invalidated_by_another_source_revision_and_cannot_change_ids(t9_workspace):
    client, _ = t9_workspace
    seed_t9(client)
    preview = preview_source_edit(client, [dict(kind='bank', identifier='B1', values=dict(amount='120'))]).json()
    other = preview_source_edit(client, [dict(kind='bank', identifier='B1', values=dict(amount='130'))]).json()
    assert commit_source_edit(client, other, key='other-editor').is_success
    assert commit_source_edit(client, preview).status_code == 409
    assert active_data(client)['bank'][0]['amount'] == 130
    assert commit_source_edit(client, other, key='new-key-same-preview').status_code == 409


def test_source_correction_can_correct_a_credit_to_a_debit_without_retaining_old_cash(t9_workspace):
    client, _ = t9_workspace
    from agent1.reconciliation.ledger import DecisionLedger
    seed_t9(client)
    assert review_t9(client, run_t9(client)).is_success
    preview = preview_source_edit(client, [dict(kind='bank', identifier='B1', values=dict(direction='out'))])
    assert preview.is_success, preview.text
    assert commit_source_edit(client, preview.json()).is_success
    gold = DecisionLedger(client.app.state.store, 'SME', prefix='company_').gold('2026-03-01')
    assert gold['bank_movements'][0]['net_minor'] == -100
    assert not run_t9(client)['allocations']
    assert client.get('/v1/reconciliation').json()['total_received'] == 0
