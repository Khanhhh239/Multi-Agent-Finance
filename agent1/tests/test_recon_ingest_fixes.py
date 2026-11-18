"""Regression tests for Agent 1 QĐ 1450 XML ingestion, TT 86/2024 12-digit CCCD MST & blended VAT schema, and T9 reconciliation fixes."""
from __future__ import annotations

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
import numpy as np
import pandas as pd
import pytest

from agent1.data.schema import inject_errors, quality_gate
from agent1.reconciliation import operations
from agent1.reconciliation._thang.allocation import Config, allocate as greedy_allocate
from agent1.reconciliation._thang.constrained import allocate as constrained_allocate
from agent1.reconciliation._thang.matching import (
    Config as MatchConfig,
    extract_invoice_refs,
    reconcile as scored_reconcile,
    references,
)
from agent1.reconciliation.pipeline import ObservedSource
from agent1.synth.einvoice import invoice_to_xml, parse_xml
from agent1.synth.names import make_cccd_mst, make_mst, valid_mst
from agent1_service.api import create_app
from agent1_service.ingest.einvoice_xml import read_invoice_xml
from agent1_service.store import Store


def _qd1450_xml(
    *,
    invoice_id: str = "HD-QD1450-01",
    symbol: str = "1C26TAA",
    invoice_no: str = "00000123",
    issue_date: str = "2026-08-01",
    payment_method: str = "TM/CK",
    seller_mst: str = "0100109106",
    buyer_mst: str | None = "079090001234",
    buyer_cccd: str | None = None,
    buyer_name: str = "Hộ kinh doanh Nguyễn Văn An",
    lines: list[tuple[str, int, str]] | None = None,
    vat_summary: list[tuple[str, int, int | None]] | None = None,
    amount_net: int | None = 10_000_000,
    vat: int | None = 800_000,
    amount_gross: int = 10_800_000,
    extra_ttchung_xml: str = "",
    ttkhac_xml: str = "",
) -> bytes:
    lines = lines or [("Dịch vụ tư vấn phần mềm", 10_000_000, "8%")]
    line_nodes = "".join(
        f"<HHDVu><STT>{idx}</STT><THHDVu>{desc}</THHDVu><ThTien>{net}</ThTien><TSuat>{rate}</TSuat></HHDVu>"
        for idx, (desc, net, rate) in enumerate(lines, 1)
    )
    summary_xml = ""
    if vat_summary is not None:
        lt_nodes = "".join(
            f"<LTSuat><TSuat>{rate}</TSuat><ThTien>{net}</ThTien>"
            + (f"<TThue>{tax}</TThue>" if tax is not None else "")
            + "</LTSuat>"
            for rate, net, tax in vat_summary
        )
        summary_xml = f"<THTTLTSuat>{lt_nodes}</THTTLTSuat>"
    buyer_id_xml = ""
    if buyer_mst is not None:
        buyer_id_xml += f"<MST>{buyer_mst}</MST>"
    if buyer_cccd is not None:
        buyer_id_xml += f"<CCCDan>{buyer_cccd}</CCCDan>"
    net_xml = f"<TgTCThue>{amount_net}</TgTCThue>" if amount_net is not None else ""
    vat_xml = f"<TgTThue>{vat}</TgTThue>" if vat is not None else ""
    xml_text = (
        f"<?xml version='1.0' encoding='utf-8'?>"
        f"<HDon><DLHDon Id='{invoice_id}'>"
        f"<TTChung><PBan>2.0.1</PBan><THDon>HÓA ĐƠN GIÁ TRỊ GIA TĂNG</THDon>"
        f"<KHMSHDon>1</KHMSHDon><KHHDon>{symbol}</KHHDon><SHDon>{invoice_no}</SHDon>"
        f"<NLap>{issue_date}</NLap><DVTTe>VND</DVTTe><TGia>1</TGia>"
        f"<HTTToan>{payment_method}</HTTToan>{extra_ttchung_xml}{ttkhac_xml}</TTChung>"
        f"<NDHDon>"
        f"<NBan><Ten>CÔNG TY TNHH SỔ SON</Ten><MST>{seller_mst}</MST></NBan>"
        f"<NMua><Ten>{buyer_name}</Ten>{buyer_id_xml}</NMua>"
        f"<DSHHDVu>{line_nodes}</DSHHDVu>"
        f"<TToan>{summary_xml}{net_xml}{vat_xml}<TgTTTBSo>{amount_gross}</TgTTTBSo></TToan>"
        f"</NDHDon></DLHDon></HDon>"
    )
    return xml_text.encode("utf-8")


# ---------------------------------------------------------------------------
# 1. QĐ 1450 E-Invoice XML Ingestion (due-date fallback & multi-rate VAT)
# ---------------------------------------------------------------------------


def test_qd1450_xml_omitting_due_date_falls_back_gracefully():
    raw = _qd1450_xml(issue_date="2026-08-01", payment_method="TM/CK")
    parsed = read_invoice_xml(raw, "F000", validate=True)
    assert parsed["issue_date"] == pd.Timestamp("2026-08-01")
    assert parsed["due_date"] == pd.Timestamp("2026-08-31")
    assert parsed["term_days"] == 30
    assert parsed["due_date_inferred"] is True

    parsed_45 = read_invoice_xml(raw, "F000", validate=True, default_payment_terms_days=45)
    assert parsed_45["due_date"] == pd.Timestamp("2026-09-15")
    assert parsed_45["term_days"] == 45


def test_qd1450_xml_parses_ttkhac_payment_terms_and_immediate_cash():
    terms_xml = _qd1450_xml(
        invoice_id="HD-TERMS-15",
        issue_date="2026-08-01",
        ttkhac_xml="<TTKhac><TTin><TTruong>ThoiHanThanhToan</TTruong><DLieu>Thanh toán trong vòng 15 ngày</DLieu></TTin></TTKhac>",
    )
    row_terms = read_invoice_xml(terms_xml, "F000", validate=True)
    assert row_terms["due_date"] == pd.Timestamp("2026-08-16")
    assert row_terms["term_days"] == 15
    assert "due_date_inferred" not in row_terms

    cash_xml = _qd1450_xml(
        invoice_id="HD-CASH-TM",
        issue_date="2026-08-05",
        payment_method="TM",
    )
    row_cash = read_invoice_xml(cash_xml, "F000", validate=True)
    assert row_cash["due_date"] == pd.Timestamp("2026-08-05")
    assert row_cash["term_days"] == 0


def test_qd1450_xml_supports_multirate_blended_vat_and_kct_kkknt():
    blended_xml = _qd1450_xml(
        invoice_id="HD-BLENDED-VAT",
        invoice_no="00000456",
        issue_date="2026-08-10",
        lines=[
            ("Nông sản sơ chế", 2_000_000, "KCT"),
            ("Khoản thu hộ không kê khai", 1_000_000, "KKKNT"),
            ("Hàng xuất khẩu tại chỗ", 3_000_000, "0%"),
            ("Thiết bị y tế", 4_000_000, "5%"),
            ("Dịch vụ phần mềm giảm thuế NĐ 180/2024", 10_000_000, "8%"),
            ("Dịch vụ viễn thông", 10_000_000, "10%"),
        ],
        vat_summary=[
            ("KCT", 2_000_000, None),
            ("KKKNT", 1_000_000, 0),
            ("0%", 3_000_000, 0),
            ("5%", 4_000_000, 200_000),
            ("8%", 10_000_000, 800_000),
            ("10%", 10_000_000, 1_000_000),
        ],
        amount_net=30_000_000,
        vat=2_000_000,
        amount_gross=32_000_000,
    )
    row = read_invoice_xml(blended_xml, "F000", validate=True)
    assert row["amount_net"] == "30000000"
    assert row["vat"] == "2000000"
    assert row["amount_gross"] == "32000000"
    assert set(row["vat_rates"].split(",")) == {"KCT", "KKKNT", "0%", "5%", "8%", "10%"}

    # Invalid rate (e.g. 15%) must still fail closed.
    bad_rate_xml = _qd1450_xml(
        invoice_id="HD-BAD-RATE",
        lines=[("Hàng lỗi thuế suất", 10_000_000, "15%")],
        amount_net=10_000_000,
        vat=1_500_000,
        amount_gross=11_500_000,
    )
    with pytest.raises(ValueError, match="Thuế suất"):
        read_invoice_xml(bad_rate_xml, "F000", validate=True)


def test_qd1450_xml_commits_through_both_ingest_and_workspace_v1_apis(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT1_PSEUDONYMIZE", "0")
    app = create_app(tmp_path / "state", key_dir=tmp_path / "keys", token="secret", firm_id="SME")
    xml_bytes = _qd1450_xml(
        invoice_id="XML-WS-01",
        symbol="1C26TBB",
        invoice_no="00000789",
        issue_date="2026-09-01",
        buyer_mst=None,
        buyer_cccd="001195012345",
        lines=[
            ("Hàng giảm thuế 8%", 10_000_000, "8%"),
            ("Hàng chịu thuế 10%", 5_000_000, "10%"),
        ],
        vat_summary=[
            ("8%", 10_000_000, 800_000),
            ("10%", 5_000_000, 500_000),
        ],
        amount_net=15_000_000,
        vat=1_300_000,
        amount_gross=16_300_000,
    )
    headers = {"Authorization": "Bearer secret"}
    with TestClient(app) as client:
        # 1) Legacy /ingest/file XML admission
        res_ingest = client.post(
            "/ingest/file",
            headers=headers,
            data={"kind": "xml", "available_on": "2026-09-02"},
            files={"file": ("qd1450.xml", xml_bytes, "application/xml")},
        )
        assert res_ingest.status_code == 200, res_ingest.text

        # 2) Live Portal/Workspace /v1/imports/preview + commit XML admission
        res_preview = client.post(
            "/v1/imports/preview",
            headers=headers,
            data={"kind": "invoices", "known_at": "2026-09-02", "imported_by": "Ke toan"},
            files={"file": ("qd1450.xml", xml_bytes, "application/xml")},
        )
        assert res_preview.status_code == 200, res_preview.text
        preview = res_preview.json()
        assert preview["can_commit"] is True, preview["errors"]
        assert preview["sample"][0]["due_date"] == "2026-10-01"
        assert preview["sample"][0]["buyer_mst"] == "001195012345"
        assert preview["sample"][0]["amount"] == 16_300_000
        res_commit = client.post(f"/v1/imports/{preview['id']}/commit", headers=headers)
        assert res_commit.status_code == 200, res_commit.text


# ---------------------------------------------------------------------------
# 2. Schema & 12-Digit CCCD Personal Tax Code (Thông tư 86/2024/TT-BTC)
# ---------------------------------------------------------------------------


def test_valid_mst_accepts_10_12_cccd_and_13_branch_and_rejects_invalid():
    rng = np.random.default_rng(2026)
    # 10-digit enterprise MST
    assert valid_mst("0100109106") is True
    assert valid_mst("0100109107") is False
    # Regression: 11- or 14-digit strings starting with a valid 10-digit MST must NOT be truncated & accepted
    assert valid_mst("01001091069") is False
    assert valid_mst("01001091069999") is False

    # 12-digit CCCD personal/HKD MST (TT 86/2024/TT-BTC)
    assert valid_mst("079090001234") is True
    assert valid_mst("001195012345") is True
    assert all(valid_mst(make_cccd_mst(rng)) for _ in range(100))
    assert valid_mst("000090001234") is False
    assert valid_mst("079090000000") is False
    assert valid_mst("000000000000") is False
    assert valid_mst("111111111111") is False

    # 13-digit branch MST (both 10-3 hyphenated and 13-digit compact)
    assert valid_mst("0100109106-001") is True
    assert valid_mst("0100109106001") is True
    assert valid_mst("0100109106-000") is False
    assert valid_mst("0100109107-001") is False


def test_quality_gate_accepts_cccd_branch_mst_and_blended_vat_and_catches_errors():
    rng = np.random.default_rng(42)
    df = pd.DataFrame(
        [
            dict(
                seller_mst=make_mst(rng),
                buyer_mst="079090001234",
                symbol="1C26TAA",
                invoice_no="0001",
                issue_date="2026-08-01",
                due_date="2026-08-31",
                amount_net=20_000_000,
                vat=1_800_000,  # 8% + 10% blended
                amount_gross=21_800_000,
                currency="VND",
                vat_rates="8%,10%",
            ),
            dict(
                seller_mst="0100109106-002",
                buyer_mst=make_cccd_mst(rng),
                symbol="1C26TAA",
                invoice_no="0002",
                issue_date="2026-08-02",
                due_date="2026-09-01",
                amount_net=15_000_000,
                vat=800_000,  # KCT + 8% blended
                amount_gross=15_800_000,
                currency="VND",
                vat_rates="KCT,8%",
            ),
        ]
    )
    flags = quality_gate(df, today="2026-10-01")
    assert not flags["any_error"].any(), flags.to_dict("records")

    dirty, truth = inject_errors(pd.concat([df] * 10, ignore_index=True).assign(
        invoice_no=[f"{i:04d}" for i in range(20)]
    ), rate=0.5, seed=7)
    detected = quality_gate(dirty, today="2026-10-01")["any_error"]
    assert (detected & truth).sum() == truth.sum()


def test_synth_einvoice_roundtrip_with_cccd_and_omitted_due_date():
    seller = pd.Series({"name": "CÔNG TY CP MINH ANH", "mst": "0100109106-001"})
    buyer = pd.Series({"name": "HKD Trần Thị B", "mst": "079192004567"})
    inv = pd.Series(
        dict(
            invoice_id="SYNTH-CCCD-1",
            symbol="1C26TAA",
            invoice_no="00001024",
            issue_date="2026-08-10",
            due_date=None,
            term_days=30,
            amount_net=20_000_000,
            vat=1_800_000,
            amount_gross=21_800_000,
            currency="VND",
            line_items=[
                {"description": "Nhóm hàng 8%", "amount_net": 10_000_000, "vat_rate": 0.08},
                {"description": "Nhóm hàng 10%", "amount_net": 10_000_000, "vat_rate": 0.10},
            ],
            vat_breakdown=[
                {"vat_rate": "8%", "amount_net": 10_000_000, "vat": 800_000},
                {"vat_rate": "10%", "amount_net": 10_000_000, "vat": 1_000_000},
            ],
        )
    )
    xml_bytes = invoice_to_xml(inv, seller, buyer)
    parsed = parse_xml(xml_bytes)
    assert parsed["due_date"] == "2026-09-09"
    assert parsed["buyer_mst"] == "079192004567"
    assert parsed["vat_rates"] == "8%,10%"
    admitted = read_invoice_xml(xml_bytes, "F000", validate=True)
    assert admitted["due_date"] == pd.Timestamp("2026-09-09")


# ---------------------------------------------------------------------------
# 3. T9 Bank-to-Invoice Reconciliation Fixes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "narrative,expected_ref,invoice_no",
    [
        ("TT HD123", "123", "123"),
        ("TT HD123", "123", "00000123"),
        ("THANH TOAN HD00123", "00123", "00123"),
        ("THANH TOAN HD00123", "123", "123"),
        ("CT DEN CONG TY A HD-2026-045", "2026-045", "2026-045"),
        ("CT DEN CONG TY A HD2026-045", "2026-045", "2026-045"),
        ("INV1024", "1024", "1024"),
        ("INV1024", "1024", "INV-1024"),
        ("MBHDB.8374621.192837.IBFT CONG TY B TT HD567", "567", "00567"),
    ],
)
def test_compact_vietnamese_invoice_ref_extraction_and_matching(narrative, expected_ref, invoice_no):
    refs = extract_invoice_refs(narrative)
    assert expected_ref in refs
    assert references({"reference": narrative}, {"invoice_id": invoice_no}) is True
    # Boundary safety: must not match unrelated numbers or HDBank prefix
    assert references({"reference": narrative}, {"invoice_id": "999999"}) is False
    assert references({"reference": "MBHDB.8374621.192837.TT TIEN HANG THANG 5"}, {"invoice_id": "00005"}) is False


def test_interbank_transfer_fee_tolerance_records_fee_transparently():
    invoices = [
        dict(
            tenant_id="T1",
            id="I_CITAD",
            invoice_number="00123",
            party_id="C1",
            side="AR",
            currency="VND",
            amount_minor=11_000_000,
            issued_on="2026-08-01",
            due_on="2026-08-31",
        ),
        dict(
            tenant_id="T1",
            id="I_PARTY_ONLY",
            invoice_number="00456",
            party_id="C2",
            side="AR",
            currency="VND",
            amount_minor=25_000_000,
            issued_on="2026-08-01",
            due_on="2026-08-31",
        ),
        dict(
            tenant_id="T1",
            id="I_GRP_1",
            invoice_number="1001",
            party_id="C3",
            side="AR",
            currency="VND",
            amount_minor=4_000_000,
            issued_on="2026-08-01",
            due_on="2026-08-31",
        ),
        dict(
            tenant_id="T1",
            id="I_GRP_2",
            invoice_number="1002",
            party_id="C3",
            side="AR",
            currency="VND",
            amount_minor=6_000_000,
            issued_on="2026-08-05",
            due_on="2026-09-04",
        ),
    ]
    payments = [
        # 1) Compact ref + 11,000 VND interbank fee
        dict(
            tenant_id="T1",
            id="P_REF_FEE",
            side="AR",
            party_id="",
            currency="VND",
            amount_minor=10_989_000,
            payment_on="2026-08-20",
            reference="THANH TOAN HD123",
        ),
        # 2) No invoice ref, strong party match + 22,000 VND CITAD fee
        dict(
            tenant_id="T1",
            id="P_PARTY_FEE",
            side="AR",
            party_id="C2",
            currency="VND",
            amount_minor=24_978_000,
            payment_on="2026-08-21",
            reference="CTY B THANH TOAN CONG NO",
        ),
        # 3) Multi-invoice compact ref + 5,500 VND fee
        dict(
            tenant_id="T1",
            id="P_GRP_FEE",
            side="AR",
            party_id="C3",
            currency="VND",
            amount_minor=9_994_500,
            payment_on="2026-08-22",
            reference="TT HD1001+1002",
        ),
    ]

    res = constrained_allocate(invoices, payments, Config(fee_tolerance_vnd=55_000))
    by_pay = {d["payment_id"]: d for d in res["decisions"]}
    assert by_pay["P_REF_FEE"]["status"] == "auto" and by_pay["P_REF_FEE"]["fee_minor"] == 11_000
    assert by_pay["P_PARTY_FEE"]["status"] == "auto" and by_pay["P_PARTY_FEE"]["fee_minor"] == 22_000
    assert by_pay["P_GRP_FEE"]["status"] == "auto" and by_pay["P_GRP_FEE"]["fee_minor"] == 5_500

    alloc_map = {(a["payment_id"], a["invoice_id"]): a for a in res["allocations"]}
    assert alloc_map[("P_REF_FEE", "I_CITAD")]["amount_minor"] == 10_989_000
    assert alloc_map[("P_REF_FEE", "I_CITAD")]["fee_minor"] == 11_000
    assert alloc_map[("P_PARTY_FEE", "I_PARTY_ONLY")]["amount_minor"] == 24_978_000
    assert alloc_map[("P_PARTY_FEE", "I_PARTY_ONLY")]["fee_minor"] == 22_000
    assert alloc_map[("P_GRP_FEE", "I_GRP_1")]["amount_minor"] == 4_000_000
    assert alloc_map[("P_GRP_FEE", "I_GRP_2")]["amount_minor"] == 5_994_500
    assert alloc_map[("P_GRP_FEE", "I_GRP_2")]["fee_minor"] == 5_500

    # Also verify greedy allocation & scored_reconcile honor fee_tolerance_vnd
    res_greedy = greedy_allocate(invoices, payments, Config(fee_tolerance_vnd=55_000))
    assert all(d["status"] == "auto" for d in res_greedy["decisions"])

    scored_inv = [
        dict(
            tenant_id="T1",
            invoice_id="00123",
            customer_id="C1",
            customer_name="CÔNG TY TNHH THƯƠNG MẠI MINH ANH",
            currency="VND",
            amount_minor=11_000_000,
            issued_on="2026-08-01",
            due_on="2026-08-20",
        )
    ]
    scored_bank = [
        dict(
            tenant_id="T1",
            transaction_id="B_SCORED_FEE",
            customer_id="",
            counterparty="CTY TNHH TM MINH ANH",
            reference="THANH TOAN TIEN HANG",
            currency="VND",
            amount_minor=10_989_000,
            booked_on="2026-08-20",
        )
    ]
    res_scored = scored_reconcile(scored_inv, scored_bank, method="scored_global", config=MatchConfig(fee_tolerance_vnd=55_000))
    assert len(res_scored["allocations"]) == 1
    assert res_scored["allocations"][0]["fee_minor"] == 11_000


def test_equal_amount_monthly_retainers_disambiguated_by_invoice_ref(tmp_path, monkeypatch):
    monkeypatch.setattr(operations, "today", lambda: "2026-09-01")
    store = Store(tmp_path / "state" / "agent1.db", Fernet.generate_key())
    try:
        # Two open monthly retainers of exact same amount 11,000,000 VND
        store.put(
            "F",
            "invoices",
            [
                dict(
                    id="RET_JAN",
                    invoice_id="RET_JAN",
                    firm_id="F",
                    customer_id="C_RET",
                    invoice_no="2026-044",
                    issue_date="2026-07-05",
                    due_date="2026-08-05",
                    amount_gross=11_000_000,
                    amount_gross_minor=11_000_000,
                    available_on="2026-07-05",
                    currency="VND",
                ),
                dict(
                    id="RET_FEB",
                    invoice_id="RET_FEB",
                    firm_id="F",
                    customer_id="C_RET",
                    invoice_no="2026-045",
                    issue_date="2026-08-05",
                    due_date="2026-09-05",
                    amount_gross=11_000_000,
                    amount_gross_minor=11_000_000,
                    available_on="2026-08-05",
                    currency="VND",
                ),
            ],
        )
        store.put("F", "customers", [dict(id="C_RET", customer_id="C_RET", short="CONG TY A", available_on="2026-07-01")])
        store.put(
            "F",
            "bank_txns",
            [
                dict(
                    id="B_RET",
                    txn_id="B_RET",
                    firm_id="F",
                    value_date="2026-08-25",
                    amount=11_000_000,
                    amount_minor=11_000_000,
                    available_on="2026-08-25",
                    currency="VND",
                    memo="CT DEN CONG TY A HD-2026-045",
                    counterparty="CONG TY A",
                    direction="in",
                )
            ],
        )
        source = ObservedSource(store, "F")
        proposal = operations.propose(source, "2026-09-01")
        assert len(proposal["allocations"]) == 1
        assert proposal["allocations"][0]["invoice_id"] == "RET_FEB"
        assert proposal["allocations"][0]["amount_minor"] == 11_000_000
    finally:
        store.connection.close()


def test_workspace_fuzzy_candidate_pool_is_nonempty_on_partial_or_fee_miss_and_strong_counterparty_fee_match(
    tmp_path, monkeypatch
):
    from agent1_service.workspace import api as ws_api, reconciliation as ws_recon

    monkeypatch.setattr(operations, "today", lambda: "2026-09-01")
    monkeypatch.setattr(ws_recon, "today", lambda: "2026-09-01")
    monkeypatch.setattr(ws_api, "t9_today", lambda: "2026-09-01")

    app = create_app(tmp_path / "ws_state", key_dir=tmp_path / "ws_keys", token="ws-secret", firm_id="SME")
    headers = {"Authorization": "Bearer ws-secret"}
    with TestClient(app) as client:
        inv_csv = pd.DataFrame(
            [
                dict(
                    invoice_id="INV_PARTIAL",
                    customer_id="C_FUZZY",
                    customer_name="CÔNG TY TNHH DỆT MAY HOÀNG PHÁT",
                    seller_mst="0100109106",
                    buyer_mst="079090001234",
                    symbol="1C26TAA",
                    invoice_no="000101",
                    issue_date="2026-08-01",
                    due_date="2026-08-20",
                    known_at="2026-08-01",
                    amount_net=20_000_000,
                    vat=0,
                    amount=20_000_000,
                    currency="VND",
                ),
                dict(
                    invoice_id="INV_OTHER",
                    customer_id="C_OTHER",
                    customer_name="CÔNG TY CỔ PHẦN THÉP ĐẠI DƯƠNG",
                    seller_mst="0100109106",
                    buyer_mst="0100109106-001",
                    symbol="1C26TAA",
                    invoice_no="000102",
                    issue_date="2026-08-01",
                    due_date="2026-08-20",
                    known_at="2026-08-01",
                    amount_net=35_000_000,
                    vat=0,
                    amount=35_000_000,
                    currency="VND",
                ),
                dict(
                    invoice_id="INV_STRONG_CP",
                    customer_id="C_STRONG",
                    customer_name="CÔNG TY TNHH THƯƠNG MẠI MINH ANH",
                    seller_mst="0100109106",
                    buyer_mst="001195012345",
                    symbol="1C26TAA",
                    invoice_no="000103",
                    issue_date="2026-08-05",
                    due_date="2026-08-25",
                    known_at="2026-08-05",
                    amount_net=15_000_000,
                    vat=0,
                    amount=15_000_000,
                    currency="VND",
                ),
            ]
        ).to_csv(index=False).encode("utf-8-sig")
        p1 = client.post(
            "/v1/imports/preview",
            headers=headers,
            files={"file": ("inv.csv", inv_csv, "text/csv")},
            data={"kind": "invoices", "date_format": "%Y-%m-%d", "number_format": "plain"},
        ).json()
        assert p1["can_commit"], p1
        assert client.post(f"/v1/imports/{p1['id']}/commit", headers=headers).is_success

        bank_csv = pd.DataFrame(
            [
                # Partial payment without customer_id and without invoice ref (previously got empty pool {}!)
                dict(
                    bank_id="B_FUZZY_PARTIAL",
                    account="TK01",
                    date="2026-08-22",
                    known_at="2026-08-22",
                    direction="in",
                    amount=7_500_000,
                    currency="VND",
                    counterparty="HOANG PHAT TEXTILE",
                    memo="THANH TOAN DOT 1 TIEN HANG",
                ),
                # Strong counterparty match ("CTY TNHH TM MINH ANH") + 11,000 VND CITAD fee deduction
                dict(
                    bank_id="B_STRONG_FEE",
                    account="TK01",
                    date="2026-08-25",
                    known_at="2026-08-25",
                    direction="in",
                    amount=14_989_000,
                    currency="VND",
                    counterparty="CTY TNHH TM MINH ANH",
                    memo="THANH TOAN CONG NO",
                ),
            ]
        ).to_csv(index=False).encode("utf-8-sig")
        p2 = client.post(
            "/v1/imports/preview",
            headers=headers,
            files={"file": ("bank.csv", bank_csv, "text/csv")},
            data={"kind": "bank", "date_format": "%Y-%m-%d", "number_format": "plain"},
        ).json()
        assert p2["can_commit"], p2
        assert client.post(f"/v1/imports/{p2['id']}/commit", headers=headers).is_success

        proposal = client.post("/v1/reconciliation/run", headers=headers, json={}).json()
        cases = {c["bank_id"]: c for c in proposal["cases"]}

        # 1) Fuzzy partial payment has a NON-EMPTY candidate pool with INV_PARTIAL ranked #1
        partial_case = cases["B_FUZZY_PARTIAL"]
        assert len(partial_case["candidates"]) >= 2
        assert partial_case["candidates"][0]["invoice_id"] == "INV_PARTIAL"
        assert partial_case["candidates"][0]["score"] > partial_case["candidates"][1]["score"]

        # 2) Strong counterparty + 11,000 VND CITAD fee auto-matches and records fee_minor = 11,000
        fee_case = cases["B_STRONG_FEE"]
        assert fee_case["status"] == "auto"
        assert fee_case["fee_minor"] == 11_000
        assert fee_case["allocations"][0]["invoice_id"] == "INV_STRONG_CP"
        assert fee_case["allocations"][0]["amount_minor"] == 14_989_000
        assert fee_case["allocations"][0]["fee_minor"] == 11_000
