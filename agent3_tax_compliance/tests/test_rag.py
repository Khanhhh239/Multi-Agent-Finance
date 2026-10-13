import pytest
from unittest.mock import MagicMock, patch
from src.rag.retriever import Retriever
from src.rag.explainer import RAGExplainer, ExplainerOutput

@pytest.fixture
def retriever():
    return Retriever()

def test_retriever_by_citation(retriever):
    results = retriever.retrieve_by_citation("Thông tư 96/2015/TT-BTC")
    assert len(results) > 0
    citations = [r["citation"] for r in results]
    assert any("thông tư 96/2015/tt-btc" in c.lower() for c in citations)

def test_retriever_by_query(retriever):
    results = retriever.retrieve_by_query("chi phúc lợi")
    assert len(results) > 0
    assert any("phúc lợi" in r["content"].lower() for r in results)

@patch('src.rag.explainer.OpenAI')
def test_explainer_verified_citation(mock_openai_class, retriever):
    # Setup mock client
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    
    # Mock LLM response with a correct quote from TT96
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content='{"explanation": "Hóa đơn thanh toán bằng tiền mặt trên 20 triệu sẽ bị loại chi phí hợp lý.", "quoted_text": "có giá trị từ 20 triệu đồng trở lên"}'))
    ]
    mock_client.chat.completions.create.return_value = mock_response

    explainer = RAGExplainer(retriever)
    
    transaction = {"amount": 25000000, "payment_method": "cash"}
    rule_hits = [{
        "rule_id": "R-CASH-20M",
        "verdict": "FAIL",
        "fix_hint": "Thanh toán qua chuyển khoản.",
        "citation": "Khoản 1 Điều 4 Thông tư 96/2015/TT-BTC"
    }]
    
    result = explainer.generate_explanation(transaction, rule_hits)
    
    assert len(result["citations"]) == 1
    assert result["citations"][0]["verified"] is True
    assert result["citations"][0]["score"] >= 0.95
    assert "[Trích dẫn kiểm định chính thức]" not in result["explanation"]

@patch('src.rag.explainer.OpenAI')
def test_explainer_unverified_citation(mock_openai_class, retriever):
    # Setup mock client
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    
    # Mock LLM response with a hallucinated quote
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content='{"explanation": "Quy định tiền mặt.", "quoted_text": "Quy định này hoàn toàn tự chế bởi LLM"}'))
    ]
    mock_client.chat.completions.create.return_value = mock_response

    explainer = RAGExplainer(retriever)
    
    transaction = {"amount": 25000000, "payment_method": "cash"}
    rule_hits = [{
        "rule_id": "R-CASH-20M",
        "verdict": "FAIL",
        "fix_hint": "Thanh toán qua chuyển khoản.",
        "citation": "Khoản 1 Điều 4 Thông tư 96/2015/TT-BTC"
    }]
    
    result = explainer.generate_explanation(transaction, rule_hits)
    
    assert len(result["citations"]) == 1
    assert result["citations"][0]["verified"] is False
    assert result["citations"][0]["score"] < 0.6
    # The output should auto-correct and append the official text block
    assert "[Trích dẫn kiểm định chính thức]" in result["explanation"]
