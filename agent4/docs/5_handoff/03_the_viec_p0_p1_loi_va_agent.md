# 03 · Thẻ việc P0–P1: củng cố lõi và xây agent

> Định dạng mỗi thẻ: **Mục đích · Tệp · Giao diện · Các bước · Kiểm thử · Xong khi · Lưu ý**. Đường dẫn tương đối `agent4/` (thư mục dự án). Python ≥ 3.11; chạy bằng `python` trong venv (xem `06`).

---
## P0 — Củng cố lõi tất định (không LLM)

### T0.1 Môi trường & khung dự án
- **Tệp:** `pyproject.toml`, `requirements.txt` (đã có bản tối thiểu), `pytest.ini` (`testpaths=tests`, `-q`), `scripts/run_tests.sh`, `.github/workflows/ci.yml` (tùy chọn).
- **Bước:** (1) tạo `pyproject` với package `agent4`; (2) thêm extras: `dev` (pytest, hypothesis, ruff), `agent` (httpx, rank-bm25, sqlglot), `api` (fastapi, uvicorn), `ml` (sentence-transformers, tùy chọn); (3) `conftest.py` tạo fixture `engine` dùng kho `data/cfo_warehouse.duckdb` (tự sinh nếu thiếu, cache theo seed).
- **Xong khi:** `pytest -q` chạy từ thư mục gốc, kho dữ liệu tự sinh lần đầu (<2 phút), các lần sau dùng lại.

### T0.2 Oracle độc lập & golden tests (**quan trọng nhất của P0**)
- **Mục đích:** kiểm chứng 66 chỉ số mà không tự chấm.
- **Tệp:** `eval/oracle.py`, `tests/test_metrics_golden.py`, `docs/5_handoff/FORMULA_REVIEW.md` (kết quả rà soát).
- **Giao diện:**
  ```python
  # eval/oracle.py  — KHÔNG import agent4.engine
  def oracle(con: duckdb.DuckDBPyConnection, metric: str, start: date, end: date,
             view: str = "mgmt", filters: dict | None = None) -> float | dict
  ```
- **Các bước:**
  1. Viết SQL thuần trên `gl_entry JOIN dim_account` (+ dim khác) cho từng chỉ số, **đọc từ mô tả công thức ở `metrics.py` nhưng tự cài lại** (dấu Nợ/Có, loại bút toán kết chuyển `is_closing`, loại `OPENING`).
  2. Với chỉ số `custom`: viết oracle từ sổ chi tiết (`ar_invoice`, `ar_receipt`, `ap_bill`…), độc lập code `custom.py` (ví dụ tuổi nợ bằng Python thuần/ SQL window).
  3. `tests/test_metrics_golden.py`: tham số hóa `(metric, period)` với 6 kỳ (tháng đã khóa, tháng dở dang, quý, năm 2025, YTD, kỳ cắt qua 01/07/2025); `assert engine.query(...) value ≈ oracle` (VND: sai số ≤ 0,5 đồng; tỷ số: 1e‑9).
  4. Với mỗi lệch: phân loại *lỗi engine* / *lỗi oracle* / *khác biệt định nghĩa*; ghi vào `FORMULA_REVIEW.md` kèm đề xuất; **sửa engine hoặc chốt định nghĩa với kế toán (T0.6)**.
  5. Thêm oracle cho `explain` (tổng theo TK = tổng engine).
- **Kiểm thử/Xong khi:** 100% ô `(chỉ số × kỳ)` khớp hoặc có quyết định ghi chép; không `xfail` ẩn.
- **Lưu ý:** các nơi dễ sai: dấu của `revenue_deductions`; `equity` (gồm lãi chưa kết chuyển); `dso` (bình quân đầu/cuối, VAT); `cash_flow_breakdown` (phân loại theo TK đối ứng); `taxable_income` (cờ `tax_deductible`).

### T0.3 Bất biến & tính chất
- **Tệp:** `tests/test_invariants.py`.
- **Test cần có:**
  1. *Phương trình kế toán* tại 12 ngày cuối tháng: Σ(TK loại 1,2) − Σ(TK loại 3,4 + kết quả chưa kết chuyển) = 0.
  2. *Σ nhóm = tổng* cho mọi `(chỉ số hỗ trợ group_by) × chiều`.
  3. *Cộng kỳ* cho `flow`: Q3 = T7+T8+T9; năm = Σ 12 tháng.
  4. *LNST hai đường*: với tháng đã khóa, `net_profit` = Δ số dư TK 4212 trong tháng.
  5. *Đối soát*: `ar_balance` = `ar_aging.value`; `ap_balance` = Σ `ap_by_vendor`; `inventory_value` = Σ `inventory_txn.value`.
  6. *Tái lập*: xây DB hai lần cùng seed → băm bảng `gl_entry` bằng nhau.
  7. *Idempotent*: gọi `query` 2 lần cùng kết quả.
- **Xong khi:** tất cả xanh; bất kỳ lỗi nào đã được sửa/ghi chú.

### T0.4 Unit test `periods` & `formatting`
- **Tệp:** `tests/test_periods.py`, `tests/test_formatting.py`.
- **Nội dung:** bảng ≥ 80 biểu thức × `as_of` khác nhau (xem `3_evaluation/04` §3.3); `extract_periods` trên câu 2 kỳ; `comparable_partial`; round‑trip `extract_numbers(fmt_*(x))` (hypothesis); chuỗi có mã, ngày, "Q3", "KH0012" không bị nhận là số.
- **Xong khi:** G0.3, G0.4 đạt; ghi bug tìm được (nếu có) vào commit.

### T0.5 Hoàn thiện lõi
- **Tệp:** `engine/engine.py`, `engine/custom*.py`, `engine/scope.py` (mới).
- **Việc:**
  1. `compare_to` cho `kind=custom` có tính chất đo số (dso, dpo, dio, expense_spikes? — chọn nhóm có ý nghĩa); trả `comparison` như chỉ số tuyến tính.
  2. Viết lại `custom.cash_journals` bằng CTE thuần (bỏ `str.replace`).
  3. `dso_actual(params={"date_basis":"receipt"|"bank"})`.
  4. **Phạm vi hàng‑mức**: `ExecutionEngine.query(..., scope={"branch":["HCM"], "salesperson":[…]})` luôn AND vào bộ lọc (kể cả `custom`); metrics không hỗ trợ phạm vi → ném `ScopeNotSupported`.
  5. `ExecutionEngine.cursor()` trả đối tượng engine con dùng `con.cursor()` (an toàn đa luồng).
  6. Thông điệp lỗi: bảo đảm tiếng Việt, có `code` máy đọc được (`error.code`).
  7. Thêm khóa `data_version` vào bảng `company_info` (do `build.py` ghi, bắt đầu `v2.0`); engine đọc và đưa vào `lineage_id`/cache key; test: đổi bộ sinh ⇒ tăng phiên bản.
- **Xong khi:** golden vẫn xanh; test phạm vi (I2) mức engine xanh.

### T0.6 Rà soát công thức với kế toán
- **Việc:** chuẩn bị bảng 66 hàng (id, công thức, ví dụ số cho một kỳ, câu hỏi cần xác nhận); họp 45–60 phút với kế toán trưởng; ghi biên bản `FORMULA_REVIEW.md` (đồng ý / sửa / bỏ). Ưu tiên Must: doanh thu, giá vốn, lợi nhuận gộp/ròng, tiền, phải thu/trả, DSO, quá hạn, tồn kho, thuế phải nộp.

---
## P1 — Agent lõi

> Thứ tự gợi ý: T1.1 → T1.2 → T1.3/T1.4 (song song) → T1.6 → T1.7 → T1.5 → T1.8 → T1.9 → T1.10.

### T1.1 Client LLM
- **Tệp:** `agent/llm.py`.
- **Giao diện:**
  ```python
  class LLMClient(Protocol):
      def chat(self, messages: list[dict], *, schema: dict | None = None, tools: list[dict] | None = None,
               options: dict | None = None, think: bool | None = None) -> LLMResponse
  @dataclass
  class LLMResponse: text: str; tool_calls: list[dict]; usage: dict  # prompt_tokens, eval_tokens
                     latency_ms: float; raw: dict
  class OllamaClient(LLMClient): ...      # POST {base_url}/api/chat, stream=False, đọc config từ config.LLMConfig
  class ScriptedClient(LLMClient): ...    # trả lời theo kịch bản cho test (không cần GPU)
  ```
- **Bước:** (1) dùng `httpx`; `options` mặc định `{temperature:0, top_k:20, top_p:0.8, num_ctx, num_predict}`; (2) hỗ trợ `format=<schema>`; (3) timeout + 1 lần thử lại có backoff; (4) ghi `usage` từ `prompt_eval_count`, `eval_count`; (5) `keep_alive`; (6) lỗi → `LLMUnavailable`.
- **Test:** ScriptedClient trong test; một test tích hợp đánh dấu `@pytest.mark.llm` chỉ chạy khi có Ollama.
- **Xong khi:** gọi được cả 2 model; đo `latency_ms` và token.

### T1.2 Tool specs, executor, facts pack
- **Tệp:** `agent/tools.py`, `agent/packer.py`.
- **Giao diện:**
  ```python
  def build_tool_specs(candidates: list[str]) -> list[dict]      # lược đồ T1–T8 (xem 4_ai_engineering/03); metric.enum = candidates
  def build_union_schema(candidates) -> dict                      # cho format=schema: oneOf{query_metric, explain_metric, ask_clarification, refuse, propose_action,…}
  def execute(call: dict, engine, principal) -> ToolResult        # gọi ExecutionEngine; bắt EngineError → ToolResult.error(code, message_vi)
  def pack_facts(result: dict, *, max_rows=8) -> dict             # bỏ _sql, số thô; giữ display/label/data_status/lineage_id/notes
  ```
- **Bước:** mô tả công cụ ≤ 40 từ; enum `view`, `compare_to`, `group_by` lấy từ engine (không gõ tay); `pack_facts` bọc trường văn bản tự do (T1.9).
- **Test:** schema hợp lệ JSON Schema; mọi `metric` trong `REGISTRY` có thể gọi qua `execute`; `pack_facts` không chứa khóa bắt đầu bằng `_`.

### T1.3 Retriever thu hẹp công cụ
- **Tệp:** `agent/retriever.py`, `eval/bench_retriever.py`.
- **Giao diện:** `class MetricRetriever: def topk(question, k=8, hints=None) -> list[Candidate(metric, score)]`, thuộc tính `ambiguous(cands) -> bool`.
- **Bước:** (1) văn bản chỉ mục = `label + description + synonyms` (có dấu & bỏ dấu); (2) BM25 bằng `rank_bm25`; (3) tùy chọn embedding (`multilingual-e5-small`) và trộn điểm; (4) tăng điểm theo gợi ý (từ khóa thuế → `views` chứa `tax`; "theo khách" → chỉ số có `group_bys` chứa `customer`); (5) hiệu chỉnh ngưỡng mơ hồ.
- **Kiểm thử:** `bench_retriever.py` đo top‑k recall trên E1 (khi có T2.1); trước đó dùng 100 câu viết tay trong `tests/data/retriever_smoke.jsonl`.
- **Xong khi:** recall@8 ≥ 99% trên smoke; thời gian < 30 ms.

### T1.4 Tiền xử lý tất định
- **Tệp:** `agent/preprocess.py`.
- **Giao diện:**
  ```python
  @dataclass
  class Hints: periods: list[PeriodHit]; compare: str|None; entities: list[EntityHit]; view_hint: str|None
               cues: set[str]  # {"unsafe_action","out_of_scope","jailbreak","needs_clarification"}
               normalized: str; no_accent: str
  def analyze(question: str, engine, state: ConversationState|None, as_of) -> Hints
  ```
- **Bước:** chuẩn hóa Unicode NFC; dùng `periods.extract_periods`/`detect_comparison`; so khớp thực thể: n‑gram câu hỏi với tên/mã khách, NCC, chi nhánh, khoản mục, phòng ban (chỉ mục bỏ dấu, ngưỡng tương đồng); từ khóa thuế (`thu nhập chịu thuế`, `chi phí được trừ`, `thuế phải nộp`…) → `view_hint="tax"`; danh sách cue ghi/xóa/ngoài miền/jailbreak (cấu hình YAML để chỉnh dễ).
- **Test:** 100 câu có nhãn hints; không báo cue sai trên 100 câu hợp lệ giống từ khóa.

### T1.5 Prompt, few‑shot kNN, trạng thái hội thoại
- **Tệp:** `agent/prompts.py`, `agent/fewshot.py`, `agent/state.py`, `agent/data/fewshot_bank.jsonl`.
- **Bước:** (1) cài `build_messages(question, hints, candidates, state, examples)` theo cấu trúc 3 phần ở `4_ai_engineering/02` §4; giữ tiền tố cố định; (2) ngân hàng few‑shot ban đầu 60 ví dụ viết tay (đa hành vi), mở rộng tự động từ E1/E2 train (T2.1); (3) `select_examples(question, k=3)` (BM25/embedding) có đa dạng hành vi; (4) `ConversationState` + `update(state, call, result)` + quy tắc kế thừa (H15); (5) cắt lịch sử ≤ 3 lượt, tóm tắt trạng thái YAML ≤ 80 token.
- **Test:** snapshot prompt (golden) để phát hiện thay đổi ngoài ý muốn; đo số token.

### T1.6 Validator lời gọi
- **Tệp:** `agent/validator.py`.
- **Giao diện:** `validate(call, *, hints, candidates, principal, engine) -> ValidationResult(ok, fixed_call|None, errors:list[Issue], action:"proceed|repair|clarify|refuse")`.
- **Luật:** theo `4_ai_engineering/04` §4 (schema, ứng viên, khung, kỳ, nhóm, thực thể, quyền, giới hạn); **sửa tự động** các lỗi chắc chắn (ví dụ `view` sai khi không có tín hiệu thuế; `period` thiếu → dùng hint); lỗi còn lại → thông điệp sửa ngắn ≤ 40 token cho LLM.
- **Test:** ≥ 60 ca (đúng/sai/biên); không bao giờ cho qua `view=tax` với câu điều hành.

### T1.7 Renderer & Verifier
- **Tệp:** `agent/render.py`, `agent/verifier.py`.
- **Giao diện:**
  ```python
  def render_facts(results: list[dict], hints) -> FactsBlock     # chuỗi tiếng Việt tất định + danh sách số cho phép
  def allowed_numbers(results, question, constants) -> NumberSet
  def verify(answer_text, allowed: NumberSet, required_labels: list[str]) -> VerifyResult(ok, violations:list[Violation])
  ```
- **Bước:** (1) `render_facts` theo loại chỉ số (flow+so sánh, snapshot, bảng nhóm, quá hạn, bất thường, dòng tiền…) — mỗi loại một khuôn ≤ 6 dòng; luôn có nhãn kỳ/khung/tạm tính/mốc dữ liệu; (2) `allowed_numbers` thu mọi số từ kết quả (quy về VND/%/ngày) + hằng số; (3) `verify` dùng `formatting.extract_numbers` + luật khớp ở `4_ai_engineering/04` §6.3; (4) kiểm nhãn bắt buộc; (5) kiểm mệnh đề nhân quả (mức 0/1/2, cấu hình); (6) hàm `repair_prompt(violations)`.
- **Test:** lưới lỗi tiêm vào (đổi chữ số, tỷ↔triệu, kỳ, thêm số lạ, xóa nhãn) — recall ≥ 99%; 200 câu trả lời đúng có diễn đạt khác — FP ≤ 2%.

### T1.8 Orchestrator
- **Tệp:** `agent/orchestrator.py`, `agent/policy.py`.
- **Giao diện:**
  ```python
  class CFOAgent:
      def __init__(self, engine, llm, retriever, cfg, ops=None): ...
      def ask(self, question: str, principal: Principal, state: ConversationState|None=None) -> AgentReply
  @dataclass
  class AgentReply: text: str; blocks: dict   # facts, caveats, lineage_ids
                    behavior: str            # answer|clarify|refuse|propose
                    trace: list[Step]; usage: dict; latency_ms: float
  ```
- **Vòng lặp:** hints → retriever → (cue chặn sớm?) → build prompt → LLM(union schema) → validate (repair ≤ 2) → execute → (cần thêm công cụ? ≤ 4 bước) → render_facts → LLM diễn giải (≤ 2 câu) → verify (retry ≤ 2) → fallback khối sự kiện → trả lời.
- **Chính sách:** `policy.should_clarify(cands, hints)`; `policy.use_think(hints, cands)`; giới hạn thời gian; log từng bước vào `trace`.
- **Test:** với `ScriptedClient`: 30 kịch bản (đúng, sửa lỗi, hỏi lại, từ chối, verifier trượt → fallback, LLM chết → chế độ form).

### T1.9 Guardrail
- **Tệp:** `agent/guardrails.py`, `agent/data/injection_patterns.yml`.
- **Bước:** theo `4_ai_engineering/04` §3, §5: pre‑filter, `wrap_untrusted(text)`, dò mẫu lệnh, chuẩn hóa ký tự ẩn, chặn URL; tích hợp vào `pack_facts` & `explain`.
- **Test:** ca A8 (kho mẫu): hỏi "chi tiết chi phí marketing tháng 9" → câu trả lời không chứa/không làm theo lệnh; số liệu không đổi; có cảnh báo; 40 mẫu tấn công tổng hợp.

### T1.10 CLI & trace
- **Tệp:** `agent/cli.py` (`python -m agent4.agent.cli --model qwen3:4b-instruct-2507-q4_K_M`), `agent/trace.py` (JSONL: bước, prompt rút gọn, lời gọi, kết quả `lineage_id`, vi phạm verifier, token, ms).
- **Xong khi:** gõ 10 câu mẫu (`sample-questions.md`) nhận câu trả lời đúng định dạng, trace đọc được. **Đây là Mốc M1.**
