import os
import pytest
from unittest.mock import MagicMock, patch
from src.extraction.llm_extractor import LLMExtractor, ExtractedInvoiceInfo

def test_redact_pii():
    extractor = LLMExtractor()
    
    # Test 13-digit tax code
    text1 = "Công ty TNHH ABC, MST 0102030405-123 thanh toán tiền hàng"
    assert "0102030405-123" not in extractor.redact_pii(text1)
    assert "[TAX_CODE_13]" in extractor.redact_pii(text1)

    # Test 10-digit tax code
    text2 = "Mua văn phòng phẩm tại nhà sách, mã số thuế 0987654321"
    assert "0987654321" not in extractor.redact_pii(text2)
    assert "[TAX_CODE_10]" in extractor.redact_pii(text2)

    # Test bank account / phone number
    text3 = "Chuyển khoản thanh toán qua số tài khoản 19034567890123"
    assert "19034567890123" not in extractor.redact_pii(text3)
    assert "[PHONE_OR_ACCOUNT]" in extractor.redact_pii(text3)

@patch('src.extraction.llm_extractor.OpenAI')
def test_llm_extractor_consistent(mock_openai_class):
    # Setup mock client response
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content='{"expense_category": "welfare", "payment_method": "cash", "beneficiary_type": "employee", "has_docs": true, "is_personal_expense": false}'))
    ]
    mock_client.chat.completions.create.return_value = mock_response

    extractor = LLMExtractor()
    result = extractor.extract("Chi tiền mừng sinh nhật nhân viên Nguyễn Văn A 100k")
    
    assert result["expense_category"] == "welfare"
    assert result["payment_method"] == "cash"
    assert result["beneficiary_type"] == "employee"
    assert result["has_docs"] is True
    assert result["is_personal_expense"] is False
    assert result["confidence"] == 1.0
    assert result["is_consistent"] is True

@patch('src.extraction.llm_extractor.OpenAI')
def test_llm_extractor_inconsistent(mock_openai_class):
    # Setup mock client to return different values on consecutive calls
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    
    mock_response1 = MagicMock()
    mock_response1.choices = [
        MagicMock(message=MagicMock(content='{"expense_category": "welfare", "payment_method": "cash", "beneficiary_type": "employee", "has_docs": true, "is_personal_expense": false}'))
    ]
    mock_response2 = MagicMock()
    mock_response2.choices = [
        MagicMock(message=MagicMock(content='{"expense_category": "other", "payment_method": "bank_transfer", "beneficiary_type": "employee", "has_docs": false, "is_personal_expense": false}'))
    ]
    
    mock_client.chat.completions.create.side_effect = [mock_response1, mock_response2]

    extractor = LLMExtractor()
    result = extractor.extract("Chi tiền mừng sinh nhật")
    
    # Should fallback to the first output but with low confidence
    assert result["expense_category"] == "welfare"
    assert result["confidence"] == 0.5
    assert result["is_consistent"] is False

from src.extraction.ocr_pipeline import OCRPipeline

@patch('src.extraction.ocr_pipeline.os.path.exists')
def test_ocr_pipeline_mock_mode(mock_exists):
    mock_exists.return_value = True
    ocr = OCRPipeline(enabled=False)
    
    text_cash = ocr.extract_text("dummy_cash_20m.png")
    assert "25.000.000" in text_cash
    assert "tiền mặt" in text_cash

    text_welfare = ocr.extract_text("dummy_welfare.jpg")
    assert "phúc lợi" in text_welfare

    text_other = ocr.extract_text("some_random_invoice.png")
    assert "văn phòng phẩm" in text_other

