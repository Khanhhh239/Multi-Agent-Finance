import re
import yaml
import json
import logging
from typing import Dict, Any, Tuple
from pydantic import BaseModel, Field, ValidationError
from openai import OpenAI

logger = logging.getLogger(__name__)

# Pydantic model for structured output validation
class ExtractedInvoiceInfo(BaseModel):
    expense_category: str = Field(
        description="Category of the expense. Must be one of: welfare, uniform_expense, commission, outsourced_service, car_expense, loan_interest, depreciation, personal_expense, business_travel, office_expense, marketing_expense, other."
    )
    payment_method: str = Field(
        description="Method of payment. Must be one of: cash, bank_transfer, other."
    )
    beneficiary_type: str = Field(
        description="Type of beneficiary. Must be one of: employee, customer, vendor, personal, unknown."
    )
    has_docs: bool = Field(
        description="Whether description mentions supporting documents (e.g., 'kèm HD', 'đầy đủ hợp đồng'). True if yes, False otherwise."
    )
    is_personal_expense: bool = Field(
        description="True if the expense is personal/consumption (e.g. golf, family travel, personal dining), False otherwise."
    )

class LLMExtractor:
    def __init__(self, config_path: str = "d:/financial/agent3_tax_compliance/config/config.yaml"):
        self.config = self._load_config(config_path)
        llm_config = self.config.get("extraction", {}).get("llm", {})
        self.provider = llm_config.get("provider", "openai")
        self.model = llm_config.get("model", "gpt-4o-mini")
        self.temperature = float(llm_config.get("temperature", 0.0))
        self.consistency_runs = int(llm_config.get("self_consistency_runs", 2))
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import os
            openai_key = os.environ.get("OPENAI_API_KEY")
            groq_key = os.environ.get("GROQ_API_KEY")
            api_key = openai_key or groq_key
            
            base_url = None
            if api_key and api_key.startswith("gsk_"):
                base_url = "https://api.groq.com/openai/v1"
            elif groq_key:
                api_key = groq_key
                base_url = "https://api.groq.com/openai/v1"
                
            if base_url:
                self._client = OpenAI(api_key=api_key, base_url=base_url)
                if "gpt" in self.model:
                    self.model = "llama-3.3-70b-versatile"
            else:
                self._client = OpenAI()
        return self._client

    def _load_config(self, path: str) -> Dict[str, Any]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load config from {path}: {e}")
            return {}

    def redact_pii(self, text: str) -> str:
        """
        Redacts sensitive info like Vietnamese Tax Codes (10 or 13 digits) and bank accounts/phone numbers.
        """
        # Redact 13-digit tax codes (e.g. 0102030405-001)
        text = re.sub(r"\b\d{10}-\d{3}\b", "[TAX_CODE_13]", text)
        # Redact 10-digit tax codes (e.g. 0102030405)
        text = re.sub(r"\b\d{10}\b", "[TAX_CODE_10]", text)
        # Redact phone numbers/bank accounts (8-15 digits starting with optional zero or plus)
        text = re.sub(r"\b(?:\+84|0)?\d{8,15}\b", "[PHONE_OR_ACCOUNT]", text)
        return text

    def extract(self, description: str) -> Dict[str, Any]:
        """
        Extracts structured tax features from raw description using LLM with self-consistency.
        """
        # Step 1: Redact PII
        redacted_desc = self.redact_pii(description)
        logger.info(f"Extracting from description (redacted): {redacted_desc}")

        runs = []
        # Step 2: Call LLM multiple times for self-consistency
        for i in range(self.consistency_runs):
            try:
                extracted_info = self._call_llm(redacted_desc)
                if extracted_info:
                    runs.append(extracted_info)
            except Exception as e:
                logger.error(f"LLM call {i+1} failed: {e}")

        if not runs:
            # If all runs failed, return a fallback object with low confidence
            return {
                "expense_category": "other",
                "payment_method": "other",
                "beneficiary_type": "unknown",
                "has_docs": False,
                "is_personal_expense": False,
                "confidence": 0.0,
                "is_consistent": False
            }

        # Step 3: Check consistency
        first_run = runs[0]
        consistent = True
        for r in runs[1:]:
            if (r.expense_category != first_run.expense_category or 
                r.payment_method != first_run.payment_method or 
                r.beneficiary_type != first_run.beneficiary_type or
                r.has_docs != first_run.has_docs or
                r.is_personal_expense != first_run.is_personal_expense):
                consistent = False
                break

        # Step 4: Resolve output and confidence
        # If consistent, confidence is high (1.0), otherwise medium-low (0.5) and needs REVIEW
        confidence = 1.0 if consistent else 0.5
        
        # In case of inconsistency, we default to the first run but tag it for review
        return {
            "expense_category": first_run.expense_category,
            "payment_method": first_run.payment_method,
            "beneficiary_type": first_run.beneficiary_type,
            "has_docs": first_run.has_docs,
            "is_personal_expense": first_run.is_personal_expense,
            "confidence": confidence,
            "is_consistent": consistent
        }

    def _call_llm(self, text: str) -> ExtractedInvoiceInfo:
        system_prompt = (
            "Bạn là trợ lý AI chuyên nghiệp phân tích mô tả giao dịch kế toán tại Việt Nam.\n"
            "Hãy phân tích đoạn văn bản mô tả giao dịch và trích xuất các trường dữ liệu theo đúng định nghĩa dưới đây.\n"
            "Các trường dữ liệu phải tuân thủ nghiêm ngặt các giá trị cho phép:\n"
            "- expense_category: Danh mục chi phí. Phải là một trong các giá trị: welfare (phúc lợi như sinh nhật, đám hiếu hỷ, nghỉ mát, khám sức khỏe), uniform_expense (đồng phục), commission (hoa hồng môi giới), outsourced_service (dịch vụ thuê ngoài như vận chuyển, bốc xếp, tư vấn pháp lý), car_expense (chi phí liên quan xe cộ, xăng, sửa xe), loan_interest (lãi vay), depreciation (khấu hao), personal_expense (tiêu dùng cá nhân như golf, du lịch gia đình), business_travel (công tác phí, taxi đi công tác), office_expense (văn phòng phẩm, internet, điện nước văn phòng), marketing_expense (quảng cáo, tiếp thị), other (khác).\n"
            "- payment_method: Phương thức thanh toán. Phải là: cash (nếu mô tả nhắc đến tiền mặt, tm, thanh toan truc tiep), bank_transfer (chuyển khoản, ck, unc, ủy nhiệm chi), other (khác hoặc không rõ).\n"
            "- beneficiary_type: Đối tượng thụ hưởng. Phải là: employee (nhân viên), customer (khách hàng), vendor (nhà cung cấp), personal (cá nhân thành viên công ty), unknown (không rõ).\n"
            "- has_docs: Có hóa đơn/chứng từ kèm theo hay không. True nếu mô tả nhắc đến hóa đơn, hợp đồng, biên bản bàn giao (ví dụ: 'kèm HD', 'đầy đủ HĐ', 'có BBGB'). False nếu không nhắc đến hoặc nhắc đến thiếu.\n"
            "- is_personal_expense: Có phải chi tiêu cá nhân không. True nếu là chi tiêu cá nhân (golf, du lịch cá nhân/gia đình), False nếu là chi cho hoạt động sản xuất kinh doanh của công ty.\n"
            "\n"
            "Hãy trả về kết quả ở định dạng JSON hợp lệ có cấu trúc chính xác như sau:\n"
            "{\n"
            "  \"expense_category\": \"Giá trị phân loại\",\n"
            "  \"payment_method\": \"Giá trị thanh toán\",\n"
            "  \"beneficiary_type\": \"Giá trị thụ hưởng\",\n"
            "  \"has_docs\": true hoặc false,\n"
            "  \"is_personal_expense\": true hoặc false\n"
            "}\n"
            "Lưu ý: Không tự ý dịch tên các trường JSON sang tiếng Việt."
        )

        user_content = f"Mô tả giao dịch: \"{text}\""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            temperature=self.temperature,
            response_format={"type": "json_object"}
        )

        content = response.choices[0].message.content.strip()
        data = json.loads(content)
        
        # Normalize Vietnamese keys to English fields for robustness (e.g. for Groq Llama models)
        normalized = {}
        for k, v in data.items():
            k_lower = k.lower().strip()
            if k_lower in ("expense_category", "danh_muc_chi_phi", "danhmuc"):
                normalized["expense_category"] = v
            elif k_lower in ("payment_method", "phuong_thuc_thanh_toan", "hinh_thuc_thanh_toan"):
                normalized["payment_method"] = v
            elif k_lower in ("beneficiary_type", "doi_tuong_thu_huong"):
                normalized["beneficiary_type"] = v
            elif k_lower in ("has_docs", "co_chung_tu", "chung_tu"):
                normalized["has_docs"] = v
            elif k_lower in ("is_personal_expense", "chi_phi_ca_nhan", "ca_nhan"):
                normalized["is_personal_expense"] = v
            else:
                normalized[k] = v
                
        # Fill missing values with default fallbacks
        if "expense_category" not in normalized:
            normalized["expense_category"] = "other"
        if "payment_method" not in normalized:
            normalized["payment_method"] = "other"
        if "beneficiary_type" not in normalized:
            normalized["beneficiary_type"] = "unknown"
        if "has_docs" not in normalized:
            normalized["has_docs"] = False
        if "is_personal_expense" not in normalized:
            normalized["is_personal_expense"] = False
            
        return ExtractedInvoiceInfo(**normalized)
