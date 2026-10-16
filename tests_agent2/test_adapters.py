import pandas as pd
import pytest
import yaml
from decimal import Decimal
from defusedxml.common import DefusedXmlException

from agent2.adapters.csv_generic import CSVAdapter
from agent2.adapters.einvoice_xml import EInvoiceXMLAdapter


def mapping():
    return {"timezone": "Asia/Ho_Chi_Minh", "tables": {"transactions": {"file": "book.csv",
            "columns": {"CongTy": "company_id", "Ma": "transaction_id", "Lap": "created_at", "Duyet": "approved_at",
                        "Dang": "posted_at", "Loai": "txn_type", "Tien": "amount_vnd"},
            "types": {"created_at": "datetime", "approved_at": "datetime", "posted_at": "datetime", "amount_vnd": "integer"}}}}


def source(tmp_path):
    pd.DataFrame([{"CongTy": "001", "Ma": "00001", "Lap": "2025-01-01 10:00", "Duyet": "2025-01-01 11:00",
                   "Dang": "2025-01-01 12:00", "Loai": "cash_expense", "Tien": "1200000"}]).to_csv(tmp_path / "book.csv", index=False, encoding="utf-8-sig")


def test_yaml_mapping_preserves_leading_zero_and_explicit_timezone(tmp_path):
    source(tmp_path)
    path = tmp_path / "mapping.yaml"
    path.write_text(yaml.safe_dump(mapping(), allow_unicode=True), encoding="utf-8")
    adapter = CSVAdapter(path)
    table = adapter.load(tmp_path)["transactions"]
    assert table.transaction_id.tolist() == ["00001"]
    assert table.company_id.tolist() == ["001"]
    assert table.posted_at.iloc[0] == "2025-01-01T12:00:00+07:00"
    assert table.amount_vnd.iloc[0] == 1200000
    assert adapter.last_report["status"] == "reduced"


def test_missing_source_column_and_unsafe_path_are_rejected(tmp_path):
    source(tmp_path)
    config = mapping()
    config["tables"]["transactions"]["columns"]["Absent"] = "extra"
    with pytest.raises(ValueError, match="missing source"):
        CSVAdapter(config).load(tmp_path)
    config["tables"]["transactions"]["file"] = "../private.csv"
    with pytest.raises(ValueError, match="inside"):
        CSVAdapter(config).load(tmp_path)


def test_duplicate_target_columns_rejected(tmp_path):
    source(tmp_path)
    config = mapping()
    config["tables"]["transactions"]["columns"]["Tien"] = "company_id"
    with pytest.raises(ValueError, match="duplicate"):
        CSVAdapter(config).load(tmp_path)


def test_fractional_vnd_and_invalid_chronology_rejected(tmp_path):
    source(tmp_path)
    frame = pd.read_csv(tmp_path / "book.csv", dtype=str)
    frame["Tien"] = "1.5"
    frame.to_csv(tmp_path / "book.csv", index=False)
    with pytest.raises((TypeError, ValueError)):
        CSVAdapter(mapping()).load(tmp_path)
    frame["Tien"] = "100"
    frame["Lap"] = "2025-01-02"
    frame.to_csv(tmp_path / "book.csv", index=False)
    with pytest.raises(ValueError, match="validation"):
        CSVAdapter(mapping()).load(tmp_path)


XML = """<HDon xmlns="urn:synthetic"><DLHDon><TTChung><PBan>2.1.0</PBan>
<KHHDon>C26TEST</KHHDon><SHDon>000001</SHDon><NLap>2026-01-01</NLap><DVTTe>VND</DVTTe></TTChung>
<NDHDon><NBan><MST>TEST001</MST></NBan><NMua><MST>BUYER</MST></NMua>
<DSHHDVu><HHDVu><STT>1</STT><THHDVu>Hàng mẫu</THHDVu><SLuong>2</SLuong>
<DGia>123.456</DGia><ThTien>246.912</ThTien><TSuat>10%</TSuat></HHDVu></DSHHDVu>
<TToan><TgTCThue>246.912</TgTCThue><TgTThue>24.6912</TgTThue><TgTTTBSo>271.6032</TgTTTBSo></TToan>
</NDHDon></DLHDon></HDon>"""


def test_xml_namespace_and_decimal_extraction_are_explicitly_unverified(tmp_path):
    path = tmp_path / "invoice.xml"
    path.write_text(XML, encoding="utf-8")
    adapter = EInvoiceXMLAdapter("company")
    tables = adapter.load(path)
    assert tables["invoices"].invoice_number.tolist() == ["000001"]
    assert tables["invoice_lines"].unit_price_vnd.iloc[0] == Decimal("123.456")
    assert tables["invoice_lines"].quantity.iloc[0] == 2
    assert adapter.last_report["status"] == "unverified"
    assert not adapter.last_report["signature_verified"]
    assert "transactions" not in tables


def test_xml_duplicate_currency_and_entity_expansion_rejected(tmp_path):
    a = tmp_path / "a.xml"
    b = tmp_path / "b.xml"
    a.write_text(XML, encoding="utf-8")
    b.write_text(XML, encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        EInvoiceXMLAdapter("c").load(tmp_path)
    a.write_text(XML.replace("<DVTTe>VND", "<DVTTe>USD"), encoding="utf-8")
    with pytest.raises(ValueError, match="VND"):
        EInvoiceXMLAdapter("c").load(a)
    a.write_text('<!DOCTYPE x [<!ENTITY e "expanded">]><HDon>&e;</HDon>', encoding="utf-8")
    with pytest.raises(DefusedXmlException):
        EInvoiceXMLAdapter("c").load(a)
