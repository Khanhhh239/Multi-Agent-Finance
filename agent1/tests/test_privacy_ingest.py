"""Cam kết bảo mật Điều 3.2 (khoá tách khỏi dữ liệu) và 3.4 (ẩn danh HMAC khi nạp)."""
import sqlite3

import pytest
from fastapi.testclient import TestClient
from rapidfuzz import fuzz

from agent1_service.api import create_app, key_directory
from agent1_service.ingest.privacy import pseudo_id, pseudo_memo, pseudo_name, pseudonymize_row
from agent1.models.t9_recon import memo_numbers

KEY = b"k" * 32
HEADERS = {"Authorization": "Bearer secret"}


def test_key_directory_is_outside_data_and_migrates_legacy_keys(tmp_path):
    data = tmp_path / "state"; data.mkdir()
    (data / "encryption.key").write_bytes(b"legacy-key")
    keys = key_directory(data)
    assert keys == (tmp_path / "state-keys").resolve()
    assert (keys / "encryption.key").read_bytes() == b"legacy-key" and not (data / "encryption.key").exists()
    with pytest.raises(ValueError):
        key_directory(data, data / "inner-keys")


def test_conflicting_legacy_key_is_not_silently_overwritten(tmp_path):
    data = tmp_path / "state"; data.mkdir(); keys = tmp_path / "state-keys"; keys.mkdir()
    (data / "encryption.key").write_bytes(b"A"); (keys / "encryption.key").write_bytes(b"B")
    with pytest.raises(ValueError):
        key_directory(data)


def test_pseudonyms_have_no_digits_and_keep_invoice_numbers_and_name_overlap():
    memo = "MBVCB.123.456.Cong ty TNHH Thep Hoa Phat TT HD 0000345"
    p = pseudo_memo(memo, KEY)
    assert memo_numbers(p) == memo_numbers(memo.upper())          # số HĐ và tiền tố ngân hàng còn nguyên
    assert "HOA PHAT" not in p and "TT HD" in p                    # tên bị che, từ thanh toán giữ
    assert not any(c.isdigit() for c in pseudo_name("Nguyen Van An 0912", KEY))
    assert not any(c.isdigit() for c in pseudo_id("0101234567", KEY))
    # cùng tên ở hai nơi (khác tiền tố pháp lý, khác dấu) ⇒ chuỗi đã ẩn danh vẫn khớp
    assert fuzz.partial_ratio(pseudo_name("Công ty TNHH Thép Hoà Phát", KEY), pseudo_name("THEP HOA PHAT", KEY)) == 100


def test_row_pseudonymization_is_consistent_across_tables():
    inv = pseudonymize_row(dict(invoice_id="I1", customer_id="C-77", invoice_no="0001", buyer_name="Cty A"), KEY)
    cus = pseudonymize_row(dict(customer_id="C-77", short="Cty A", name="Cong ty A"), KEY)
    assert inv["customer_id"] == cus["customer_id"] != "C-77"
    assert inv["invoice_no"] == "0001" and inv["invoice_id"] == "I1"


def test_ingest_stores_only_pseudonyms_and_keys_live_outside_data_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENT1_PSEUDONYMIZE", raising=False); monkeypatch.delenv("AGENT1_KEY_DIR", raising=False)
    data = tmp_path / "state"
    app = create_app(data, token="secret", firm_id="F000")
    with TestClient(app) as client:
        rec = dict(customer_id="KH-TRAN-VAN-B", short="Tran Van B", name="Ho kinh doanh Tran Van B")
        assert client.post("/ingest", headers=HEADERS, json=dict(table="customers", records=[rec])).status_code == 200
    files = {p.name for p in data.iterdir()}
    assert "encryption.key" not in files and "pseudonym.key" not in files
    assert (tmp_path / "state-keys" / "encryption.key").exists() and (tmp_path / "state-keys" / "pseudonym.key").exists()
    # cơ sở dữ liệu không chứa tên hay mã gốc (đã mã hoá); giải mã ra cũng chỉ thấy mã ẩn danh
    raw = sqlite3.connect(data / "agent1.db").execute("SELECT id FROM records").fetchall()
    assert all("TRAN" not in r[0].upper() for r in raw)
