import yaml
import json
import logging
import re
from typing import Dict, Any, List
from openai import OpenAI
from rapidfuzz import fuzz
from src.rag.retriever import Retriever
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class ExplainerOutput(BaseModel):
    explanation: str = Field(description="Lời giải thích bằng tiếng Việt chuyên nghiệp, tự nhiên, giải thích rõ lý do vi phạm luật thuế hoặc rủi ro và các bước khắc phục.")
    quoted_text: str = Field(description="Đoạn trích dẫn nguyên văn từ văn bản luật thuế (phải trích chính xác từng từ từ context được cung cấp).")

class RAGExplainer:
    def __init__(self, retriever: Retriever, config_path: str = "d:/financial/agent3_tax_compliance/config/config.yaml"):
        self.retriever = retriever
        self.config = self._load_config(config_path)
        
        llm_config = self.config.get("extraction", {}).get("llm", {})
        self.model = llm_config.get("model", "gpt-4o-mini")
        self.temperature = float(llm_config.get("temperature", 0.0))
        self.citation_threshold = float(self.config.get("rag", {}).get("citation_threshold", 0.95))
        
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

    def generate_explanation(self, transaction: Dict[str, Any], rule_hits: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generates explanation and verifies citation authenticity.
        """
        if not rule_hits:
            return {
                "explanation": "Giao dịch hợp lệ, không vi phạm các luật thuế được cấu hình.",
                "citations": []
            }

        explanations = []
        citations_status = []

        for hit in rule_hits:
            rule_id = hit.get("rule_id")
            citation_query = hit.get("citation", "")
            verdict = hit.get("verdict", "REVIEW")
            fix_hint = hit.get("fix_hint", "")

            # 1. Retrieve the legal text chunk
            chunks = self.retriever.retrieve_by_citation(citation_query)
            if not chunks:
                # If not found directly, search FTS5
                chunks = self.retriever.retrieve_by_query(citation_query)

            legal_context = ""
            original_text = ""
            if chunks:
                legal_context = chunks[0]["content"]
                original_text = chunks[0]["content"]
            else:
                legal_context = "Không tìm thấy văn bản luật trực tiếp. Hãy giải thích dựa trên luật định chung."

            # 2. Call LLM to draft the explanation
            llm_result = self._call_llm_explainer(transaction, rule_id, verdict, fix_hint, legal_context)
            
            explanation_text = llm_result.explanation
            quoted = llm_result.quoted_text

            # 3. Citation Verifier
            verified = False
            match_score = 0.0
            
            if original_text and quoted:
                # We compute partial ratio since quoted text is a snippet of the original chunk
                match_score = float(fuzz.partial_ratio(quoted.strip().lower(), original_text.strip().lower())) / 100.0
                if match_score >= self.citation_threshold:
                    verified = True
                else:
                    logger.warning(f"Citation verification failed for {rule_id}. Score: {match_score:.2f}, Quoted: '{quoted}'")

            # 4. Auto-correction: append original text if LLM quotes inaccurately
            if not verified and original_text:
                explanation_text += f"\n\n[Trích dẫn kiểm định chính thức]:\n\"{original_text}\""

            explanations.append(f"**[{rule_id} - Kết luận: {verdict}]**\n{explanation_text}")
            citations_status.append({
                "rule_id": rule_id,
                "citation": citation_query,
                "quoted_text": quoted if quoted else "N/A",
                "verified": verified,
                "score": match_score
            })

        return {
            "explanation": "\n\n---\n\n".join(explanations),
            "citations": citations_status
        }

    def _call_llm_explainer(self, transaction: Dict[str, Any], rule_id: str, verdict: str, fix_hint: str, legal_context: str) -> ExplainerOutput:
        system_prompt = (
            "Bạn là một chuyên gia tư vấn thuế và kế toán trưởng tại Việt Nam.\n"
            "Hãy viết lời giải thích chi tiết lý do tại sao giao dịch vi phạm hoặc cần xem xét lại dựa trên kết quả kiểm tra luật thuế dưới đây.\n"
            "\n"
            "Thông tin đầu vào:\n"
            f"- Mã luật/Quy tắc: {rule_id}\n"
            f"- Kết luận: {verdict}\n"
            f"- Hướng khắc phục đề xuất: {fix_hint}\n"
            f"- Văn bản luật tham chiếu (Context): \"\"\"\n{legal_context}\n\"\"\"\n"
            "\n"
            "Yêu cầu:\n"
            "1. Phân tích giao dịch dựa trên văn bản luật tham chiếu. Giải thích rõ ràng, lịch sự, chuyên nghiệp bằng tiếng Việt.\n"
            "2. Trích xuất CHÍNH XÁC nguyên văn một đoạn văn bản từ văn bản luật tham chiếu (Context) để làm căn cứ pháp lý và điền vào trường 'quoted_text'. KHÔNG được sửa đổi bất cứ từ ngữ nào trong đoạn trích này.\n"
            "3. Trả về kết quả dưới định dạng JSON có cấu trúc chính xác như sau:\n"
            "{\n"
            "  \"explanation\": \"Lời giải thích của bạn\",\n"
            "  \"quoted_text\": \"Đoạn trích dẫn nguyên văn\"\n"
            "}\n"
            "Lưu ý: Không tự ý dịch tên các trường JSON sang tiếng Việt (như giai_thich, trich_dan)."
        )

        user_content = f"Thông tin giao dịch: {json.dumps(transaction, ensure_ascii=False)}"

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
            if k_lower in ("giai_thich", "giaithich", "explanation", "explanation_text"):
                normalized["explanation"] = v
            elif k_lower in ("trich_dan", "trichdan", "quoted_text", "quoted"):
                normalized["quoted_text"] = v
            else:
                normalized[k] = v
                
        # Fill missing values with fallbacks if needed
        if "explanation" not in normalized:
            normalized["explanation"] = normalized.get("explanation") or ""
        if "quoted_text" not in normalized:
            normalized["quoted_text"] = normalized.get("quoted_text") or ""
            
        return ExplainerOutput(**normalized)
