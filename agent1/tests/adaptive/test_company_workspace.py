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
            json=dict(payment_id="P", invoice_id="ORIGINAL", bank_id="B", amount=0.5),
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
            payment_id="EXACT", bank_id="LARGE", invoice_id="ORIGINAL", amount=str(huge)
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
    ]
    weeks = workbook["Kế hoạch từng tuần"]
    assert weeks.max_row == 27
    assert weeks["B27"].value.date() == date(2026, 1, 30)
    assert weeks["B27"].number_format == "dd-mm-yy"
    assert weeks["E20"].value == 800000
    assert workbook["Khoản cần chú ý"].max_row == len(plan["collections"]) + 1
