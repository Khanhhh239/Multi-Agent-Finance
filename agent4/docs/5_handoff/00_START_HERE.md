# 00 · START HERE — dành cho coding agent tiếp nhận Agent 4

**Cập nhật 17/10/2026:** đã dừng tại **M1 P1 thử nghiệm**, 10/10 câu dev đúng bằng Qwen4B thật, 2.586 test passed (có Ollama). Đọc [M1_REPORT.md](M1_REPORT.md) và [PROGRESS.md](PROGRESS.md) trước khi tiếp nhận. **công thức chưa được kế toán duyệt (G0.7 mở)**; G0.7 **CHƯA ĐẠT**, 22 Must **cần duyệt trước pilot**. Chưa chạy P2–P4/held-out.

## Bạn sẽ làm gì
Hoàn thiện **Agent 4 "CFO ảo"**: lõi dữ liệu + chỉ số **đã có**; bạn xây **agent LLM (Qwen ≤ 10B) + guardrail + bộ đánh giá + sản phẩm**, rồi *đo* và *tối ưu*. Đừng viết lại phần đã có; hãy kiểm chứng nó (P0) trước.

## Thứ tự đọc (30 phút)
1. `docs/1_business_analyst/01_tom_tat_dieu_hanh.md` — sản phẩm và nguyên tắc.
2. `docs/5_handoff/01_hien_trang_va_khoang_trong.md` — cái gì có / chưa có / lỗi đã biết.
3. `docs/4_ai_engineering/01,02,04` — kiến trúc, chiến lược model nhỏ, guardrail.
4. `docs/2_data/03,05` — kho dữ liệu và hard case.
5. `docs/3_evaluation/01,05` — metric và cổng nghiệm thu.
6. `docs/5_handoff/02` rồi các thẻ `03,04,05`.

## Lệnh đầu tiên (Windows + Git Bash; chi tiết: `06_runbook_moi_truong.md`)
```bash
cd agent4
export PYTHONUTF8=1
python -m pip install -r requirements.txt            # hoặc dùng uv/venv
python -m agent4.datagen.build --out data/cfo_warehouse.duckdb      # ~1 phút
python -m pytest tests -q                                           # số đo hiện tại: PROGRESS.md
ollama list                                                         # cần qwen3:8b, qwen3:4b-instruct-2507-q4_K_M
```
Thử nhanh lõi:
```python
from agent4.engine.engine import ExecutionEngine
e = ExecutionEngine("data/cfo_warehouse.duckdb")
e.query("overdue_receivables", None, params={"min_days": 30})["summary"]
e.query("net_revenue", "last_quarter", compare_to="previous_period")["comparison"]
e.explain("net_profit", "2026-Q2")["accounts_summary"]
```

## 7 quy tắc không được vi phạm
1. **LLM không tính số, không viết SQL tài chính** (trừ T3.7 có kiểm soát). Mọi số ← `ExecutionEngine`.
2. **Oracle độc lập trước, đo agent sau** (T0.2). Không chấm engine bằng engine.
3. **Không đưa văn bản tự do** (`description`, tên đối tác) vào prompt khi chưa bọc/ẩn (ca A8).
4. **Không có công cụ ghi** cho LLM. Hành động = đề xuất → duyệt → handler.
5. **Tách dev/val/test** theo seed + khuôn câu; test chạy *một lần* mỗi mốc.
6. **Mọi thay đổi prompt/model** có bảng so sánh trước/sau và không làm xấu metric Must.
7. **Trung thực**: báo cáo cả giả thuyết bị bác bỏ; không ghi "đạt" khi chưa đo; không chỉnh test cho khớp mà không ghi `DECISIONS.md`.

## Định nghĩa mốc đầu tiên bạn cần đạt (M1, ≈ 2 tuần)
- P0 hoàn tất (golden + bất biến + unit test), `FORMULA_REVIEW.md` điền kết quả oracle.
- CLI chat (`python -m agent4.agent.cli`) trả lời 10 câu mẫu với Qwen3‑4B‑2507 bằng đường: hints → retriever → LLM (schema) → validator → engine → khối sự kiện → verifier.
- Trace JSONL đọc được cho từng câu.

## Khi vướng
- Quyết định kiến trúc đã chốt ở `01_hien_trang…` §3 — không bàn lại trừ khi có số đo bác bỏ.
- Mâu thuẫn công thức: ghi vào `FORMULA_REVIEW.md` + `DECISIONS.md`, hỏi kế toán (T0.6), đừng tự chọn im lặng.
- Máy dev: GPU 6 GB; ưu tiên `qwen3:4b-instruct-2507-q4_K_M` khi đo nhanh; `qwen3:8b` cần cấu hình VRAM (`4_ai_engineering/06`).
