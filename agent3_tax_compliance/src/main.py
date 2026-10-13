import os
import uvicorn
import yaml
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List

from src.extraction.ocr_pipeline import OCRPipeline
from src.extraction.llm_extractor import LLMExtractor
from src.rule_engine.rules_loader import RulesLoader
from src.rule_engine.engine import RuleEngine
from src.rag.retriever import Retriever
from src.rag.explainer import RAGExplainer
from src.database import DatabaseManager

app = FastAPI(
    title="Agent 3: Tax Compliance Engine",
    description="Hệ thống tự động kiểm soát và thẩm định tuân thủ luật thuế Việt Nam (CIT & Invoice) dùng Lõi Tất Định + RAG.",
    version="1.0.0"
)

# Initialize components
CONFIG_PATH = "d:/financial/agent3_tax_compliance/config/config.yaml"
db_mgr = DatabaseManager(CONFIG_PATH)

# Load configuration for OCR
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    app_config = yaml.safe_load(f)
ocr_enabled = app_config.get("extraction", {}).get("ocr", {}).get("enabled", False)

ocr_pipe = OCRPipeline(enabled=ocr_enabled)
llm_extractor = LLMExtractor(CONFIG_PATH)
rules_loader = RulesLoader("d:/financial/agent3_tax_compliance/config/rules")
rule_engine = RuleEngine(rules_loader)
retriever = Retriever(CONFIG_PATH)
rag_explainer = RAGExplainer(retriever, CONFIG_PATH)

class TransactionRequest(BaseModel):
    description: Optional[str] = Field(None, description="Mô tả giao dịch bằng chữ. Nếu không có, phải điền image_path.")
    image_path: Optional[str] = Field(None, description="Đường dẫn đến file hình ảnh hóa đơn để quét OCR.")
    amount: float = Field(..., description="Số tiền giao dịch (VND).")
    date: str = Field(..., description="Ngày phát sinh giao dịch (định dạng YYYY-MM-DD).")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Các metadata bổ sung (ví dụ: welfare_ytd_spent_with_current, avg_monthly_salary) để chạy các luật biên động.")

class ProcessResponse(BaseModel):
    id: int = Field(..., description="Mã định danh giao dịch trong DB.")
    date: str = Field(..., description="Ngày giao dịch.")
    original_description: str = Field(..., description="Mô tả gốc.")
    description_redacted: str = Field(..., description="Mô tả đã che PII.")
    amount: float = Field(..., description="Số tiền.")
    verdict: str = Field(..., description="Kết luận thuế: PASS, FAIL hoặc REVIEW.")
    rules_triggered: List[str] = Field(..., description="Danh sách các mã rule bị kích hoạt.")
    explanation: str = Field(..., description="Lời tư vấn giải thích thuế và hướng khắc phục từ RAG.")
    citations: List[Dict[str, Any]] = Field(..., description="Báo cáo xác thực nguồn trích dẫn từ luật thuế.")
    expense_category: str = Field(..., description="Danh mục chi phí trích xuất.")
    payment_method: str = Field(..., description="Hình thức thanh toán trích xuất.")
    beneficiary_type: str = Field(..., description="Đối tượng thụ hưởng.")
    has_docs: bool = Field(..., description="Có chứng từ đi kèm không.")
    is_personal_expense: bool = Field(..., description="Có phải chi phí cá nhân không.")

@app.post("/process_transaction", response_model=ProcessResponse)
async def process_transaction(req: TransactionRequest):
    # 1. OCR text extraction if image provided
    description = req.description
    if req.image_path:
        ocr_text = ocr_pipe.extract_text(req.image_path)
        if not ocr_text:
            raise HTTPException(status_code=400, detail="Không thể quét được chữ từ hóa đơn hoặc file hình không tồn tại.")
        description = ocr_text

    if not description:
        raise HTTPException(status_code=400, detail="Vui lòng cung cấp description hoặc image_path.")

    # 2. Extract structured features from description
    extracted = llm_extractor.extract(description)
    
    # 3. Build full transaction context for Rule Engine
    tx_context = {
        "date": req.date,
        "amount": req.amount,
        "description": description,
        "expense_category": extracted["expense_category"],
        "category": extracted["expense_category"],
        "payment_method": extracted["payment_method"],
        "beneficiary_type": extracted["beneficiary_type"],
        "has_docs": extracted["has_docs"],
        "has_supporting_docs": extracted["has_docs"],
        "is_personal_expense": extracted["is_personal_expense"],
    }
    
    # Merge additional metadata
    if req.metadata:
        tx_context.update(req.metadata)

    # 4. Execute Rule Engine
    engine_res = rule_engine.evaluate(tx_context, req.date)
    verdict = engine_res["verdict"]
    rule_hits = engine_res["hits"]

    # 5. Generate Explanation and verify citations
    explanation_res = {"explanation": "Giao dịch hợp lệ, không vi phạm các luật thuế được cấu hình.", "citations": []}
    if verdict != "PASS":
        explanation_res = rag_explainer.generate_explanation(tx_context, rule_hits)

    # 6. Save to Database
    db_record = {
        "date": req.date,
        "description": description,
        "description_redacted": llm_extractor.redact_pii(description),
        "amount": req.amount,
        "payment_method": tx_context["payment_method"],
        "expense_category": tx_context["expense_category"],
        "beneficiary_type": tx_context["beneficiary_type"],
        "has_docs": tx_context["has_docs"],
        "is_personal_expense": tx_context["is_personal_expense"],
        "verdict": verdict,
        "rules_triggered": [hit["rule_id"] for hit in rule_hits],
        "explanation": explanation_res["explanation"]
    }
    
    tx_id = db_mgr.insert_transaction(db_record)

    return ProcessResponse(
        id=tx_id,
        date=req.date,
        original_description=description,
        description_redacted=db_record["description_redacted"],
        amount=req.amount,
        verdict=verdict,
        rules_triggered=[hit["rule_id"] for hit in rule_hits],
        explanation=explanation_res["explanation"],
        citations=explanation_res["citations"],
        expense_category=tx_context["expense_category"],
        payment_method=tx_context["payment_method"],
        beneficiary_type=tx_context["beneficiary_type"],
        has_docs=tx_context["has_docs"],
        is_personal_expense=tx_context["is_personal_expense"]
    )

@app.get("/views/internal")
async def get_internal_view():
    """
    View nội bộ phục vụ kiểm toán nội bộ công ty (Hiện đầy đủ thông tin PII và lý do vi phạm).
    """
    return db_mgr.get_internal_view()

@app.get("/views/tax_inspector")
async def get_tax_inspector_view():
    """
    View dành cho cơ quan thuế thanh tra (Ẩn PII, lọc chỉ các chi phí đủ điều kiện được trừ).
    """
    return db_mgr.get_tax_inspector_view()

@app.get("/rules")
async def get_rules(date: Optional[str] = "2026-07-19"):
    """
    Trả về danh sách các luật thuế đang hiệu lực tại ngày truyền vào.
    """
    rules = rules_loader.load_rules(date)
    return {
        "date": date,
        "rules_count": len(rules),
        "rules": [
            {
                "id": r["rule_id"],
                "name": r.get("name", ""),
                "description": r.get("description", ""),
                "citation": r.get("citation", ""),
                "effective_from": r.get("effective_from", ""),
                "effective_to": r.get("effective_to", "")
            }
            for r in rules
        ]
    }

if __name__ == "__main__":
    uvicorn.run("src.main:app", host="127.0.0.1", port=8000, reload=True)
