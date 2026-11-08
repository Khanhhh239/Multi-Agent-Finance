import pytest
import os
import sqlite3
from src.database import DatabaseManager

@pytest.fixture
def temp_db(tmp_path):
    # Create a database manager pointing to a temp file
    db_file = tmp_path / "test_tax.db"
    # Create a config yaml pointing to this temp db path
    config_content = f"""
database:
  path: "{db_file.as_posix()}"
"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(config_content, encoding="utf-8")
    
    db_mgr = DatabaseManager(config_path=str(config_file))
    return db_mgr

def test_db_2_views(temp_db):
    # Insert 1 PASS transaction (deductible)
    tx1 = {
        "date": "2026-07-19",
        "description": "Thanh toán hóa đơn văn phòng phẩm MST 0102030405",
        "description_redacted": "Thanh toán hóa đơn văn phòng phẩm MST [TAX_CODE_10]",
        "amount": 5000000.0,
        "payment_method": "bank_transfer",
        "expense_category": "office_expense",
        "beneficiary_type": "vendor",
        "has_docs": True,
        "is_personal_expense": False,
        "verdict": "PASS",
        "rules_triggered": [],
        "explanation": "Chi phí văn phòng phẩm hợp lệ."
    }
    
    # Insert 1 FAIL transaction (non-deductible)
    tx2 = {
        "date": "2026-07-19",
        "description": "Chi tiền mặt mua máy tính trị giá 25.000.000 MST 0102030405",
        "description_redacted": "Chi tiền mặt mua máy tính trị giá 25.000.000 MST [TAX_CODE_10]",
        "amount": 25000000.0,
        "payment_method": "cash",
        "expense_category": "office_expense",
        "beneficiary_type": "vendor",
        "has_docs": True,
        "is_personal_expense": False,
        "verdict": "FAIL",
        "rules_triggered": ["R-CASH-20M"],
        "explanation": "Giao dịch bằng tiền mặt trên 20 triệu vi phạm."
    }
    
    temp_db.insert_transaction(tx1)
    temp_db.insert_transaction(tx2)
    
    # Internal view should show BOTH transactions
    internal_view = temp_db.get_internal_view()
    assert len(internal_view) == 2
    descriptions = [r["raw_description"] for r in internal_view]
    assert any("MST 0102030405" in d for d in descriptions)
    assert "explanation" in internal_view[0]
    
    # Tax Inspector view should ONLY show the PASS transaction and hide PII
    tax_view = temp_db.get_tax_inspector_view()
    assert len(tax_view) == 1
    assert tax_view[0]["amount"] == 5000000.0
    assert "MST 0102030405" not in tax_view[0]["description"]
    assert "[TAX_CODE_10]" in tax_view[0]["description"]
    assert "explanation" not in tax_view[0]
