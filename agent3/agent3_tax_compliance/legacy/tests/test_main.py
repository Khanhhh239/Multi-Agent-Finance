import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from src.main import app

client = TestClient(app)

@pytest.fixture
def mock_pipeline_calls():
    with patch('src.main.llm_extractor') as mock_llm, \
         patch('src.main.rag_explainer') as mock_rag:
        
        # Setup mock extractor
        mock_llm.extract.return_value = {
            "expense_category": "office_expense",
            "payment_method": "bank_transfer",
            "beneficiary_type": "vendor",
            "has_docs": True,
            "is_personal_expense": False
        }
        mock_llm.redact_pii.side_effect = lambda x: x.replace("0102030405", "[TAX_CODE_10]")
        
        # Setup mock RAG
        mock_rag.generate_explanation.return_value = {
            "explanation": "Chi phí hợp lý.",
            "citations": [{"rule_id": "R-MISSING-DOC", "verified": True, "score": 1.0}]
        }
        
        yield mock_llm, mock_rag

def test_process_transaction_pass(mock_pipeline_calls):
    payload = {
        "description": "Thanh toán văn phòng phẩm cho cty ABC MST 0102030405",
        "amount": 5000000.0,
        "date": "2026-07-19"
    }
    
    response = client.post("/process_transaction", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["verdict"] == "PASS"
    assert data["description_redacted"] == "Thanh toán văn phòng phẩm cho cty ABC MST [TAX_CODE_10]"
    assert len(data["rules_triggered"]) == 0

def test_process_transaction_fail_cash(mock_pipeline_calls):
    mock_llm, mock_rag = mock_pipeline_calls
    mock_llm.extract.return_value = {
        "expense_category": "office_expense",
        "payment_method": "cash",
        "beneficiary_type": "vendor",
        "has_docs": True,
        "is_personal_expense": False
    }
    
    payload = {
        "description": "Chi tiền mặt mua linh kiện máy tính cty ABC MST 0102030405",
        "amount": 25000000.0,
        "date": "2026-07-19"
    }
    
    response = client.post("/process_transaction", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["verdict"] == "FAIL"
    assert "R-CASH-20M" in data["rules_triggered"]

def test_process_transaction_ocr(mock_pipeline_calls):
    payload = {
        "image_path": "d:/financial/agent3_tax_compliance/tests/dummy_cash_20m.png",
        "amount": 25000000.0,
        "date": "2026-07-19"
    }
    
    mock_llm, mock_rag = mock_pipeline_calls
    mock_llm.extract.return_value = {
        "expense_category": "office_expense",
        "payment_method": "cash",
        "beneficiary_type": "vendor",
        "has_docs": True,
        "is_personal_expense": False
    }
    mock_llm.redact_pii.side_effect = lambda x: x
    
    with patch('src.main.ocr_pipe.extract_text') as mock_ocr:
        mock_ocr.return_value = "Giao dịch 25 triệu thanh toán bằng tiền mặt"
        
        response = client.post("/process_transaction", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["original_description"] == "Giao dịch 25 triệu thanh toán bằng tiền mặt"

def test_get_views():
    res_internal = client.get("/views/internal")
    assert res_internal.status_code == 200
    assert isinstance(res_internal.json(), list)
    
    res_tax = client.get("/views/tax_inspector")
    assert res_tax.status_code == 200
    assert isinstance(res_tax.json(), list)

def test_get_rules():
    response = client.get("/rules?date=2026-07-19")
    assert response.status_code == 200
    data = response.json()
    assert data["rules_count"] == 12
    assert len(data["rules"]) == 12
