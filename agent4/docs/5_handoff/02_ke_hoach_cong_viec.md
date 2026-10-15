# 02 · Kế hoạch công việc (WBS, thứ tự, phụ thuộc)

> Làm **tuần tự theo giai đoạn**; trong một giai đoạn có thể song song các thẻ không phụ thuộc. Ước lượng là *công sức một coding agent/dev*, chưa tính thời gian chạy thí nghiệm.

## Bản đồ giai đoạn
```
P0 Củng cố lõi (kiểm chứng)  ──►  P1 Agent lõi  ──►  P2 Bộ đánh giá + thí nghiệm  ──►  P3 Sản phẩm  ──►  P4 Pilot & mở rộng
 (không LLM)                      (LLM + guardrail)    (đo, chọn cấu hình B*)           (API, UI, duyệt)    (dữ liệu thật, quy mô)
        Cổng G0                          Cổng G1 (một phần)              Cổng G1                      Cổng G2
```

## Danh sách thẻ việc
| ID | Thẻ | Giai đoạn | Phụ thuộc | Ước lượng | Ưu tiên | Giả thuyết/đầu ra chính |
|---|---|---|---|---|---|---|
| **T0.1** | Môi trường, cấu trúc dự án, CI nhanh | P0 | — | 0,5 ngày | P0 | `pyproject.toml`, `pytest`, script chạy |
| **T0.2** | **Oracle SQL độc lập + golden tests cho 66 chỉ số** | P0 | T0.1 | 3 ngày | **P0** | Báo cáo lệch công thức, G0.1 |
| **T0.3** | Test bất biến & tính chất (Σ nhóm, cộng kỳ, phương trình kế toán, LNST hai đường) | P0 | T0.2 | 1,5 ngày | P0 | G0.2 |
| **T0.4** | Unit test `periods.py`, `formatting.py` | P0 | T0.1 | 1 ngày | P0 | G0.3, G0.4 |
| **T0.5** | Sửa/bổ sung lõi: so sánh kỳ cho chỉ số `custom`, viết lại `cash_journals`, `dso_actual` theo `bank_txn_date` (tham số), phân quyền hàng‑mức trong engine | P0 | T0.2 | 2 ngày | P1 | K5, K6, K9, G0.6 |
| **T0.6** | Rà soát công thức với kế toán (phiên làm việc + biên bản) | P0 | T0.2 | 0,5 ngày + phụ thuộc người | P0 | G0.7 |
| **T1.1** | Client LLM (Ollama) + client giả (mock) | P1 | T0.1 | 1 ngày | P0 | `agent/llm.py` |
| **T1.2** | Tool specs sinh tự động từ `REGISTRY` + executor + "facts pack" | P1 | T0.5 | 1,5 ngày | P0 | `agent/tools.py`, `agent/packer.py` |
| **T1.3** | Retriever thu hẹp công cụ (BM25 → lai embedding) | P1 | T1.2 | 1,5 ngày | P0 | H1 |
| **T1.4** | Tiền xử lý tất định (hints) | P1 | T0.4 | 1,5 ngày | P0 | H2 |
| **T1.5** | Prompt, few‑shot kNN, trạng thái hội thoại | P1 | T1.2–1.4 | 2 ngày | P0 | H7, H8 |
| **T1.6** | Validator lời gọi + sửa lỗi có chẩn đoán | P1 | T1.2 | 1,5 ngày | P0 | |
| **T1.7** | Renderer khối sự kiện + Verifier số | P1 | T0.4 | 2,5 ngày | **P0** | H5, H6, G1.5 |
| **T1.8** | Orchestrator (vòng lặp, chính sách hỏi lại/từ chối, suy biến) | P1 | T1.1–1.7 | 2 ngày | P0 | |
| **T1.9** | Guardrail: pre‑filter, bọc dữ liệu không tin cậy, dò mẫu lệnh | P1 | T1.8 | 1,5 ngày | P0 | G1.10 |
| **T1.10** | CLI chat + trace log (từng bước) | P1 | T1.8 | 0,5 ngày | P1 | |
| **T2.1** | Sinh E1/E2 (mẫu câu × đồng nghĩa × kỳ × nhiễu) + oracle giá trị | P2 | T0.2 | 3 ngày | P0 | `eval/gen/*` |
| **T2.2** | Sinh E3/E4/E5 (hỏi lại, từ chối, khung) + E‑gold khung | P2 | T2.1 | 1,5 ngày | P0 | |
| **T2.3** | Sinh E6 (tiêm lỗi số) và E7 (đa lượt) | P2 | T1.7 | 2 ngày | P0 | |
| **T2.4** | Sinh E8 (red‑team) + E9 (SQL) + E10 | P2 | T1.9 | 2 ngày | P1 | |
| **T2.5** | Runner + chấm điểm + báo cáo + lưu kết quả | P2 | T2.1 | 2 ngày | **P0** | `eval/run.py` |
| **T2.6** | Thí nghiệm B0 → H1…H8, H13 → chọn B* | P2 | T1.*, T2.5 | 4–6 ngày | P0 | Báo cáo từng H |
| **T2.7** | (Tùy chọn) H12 tinh chỉnh QLoRA | P2 | T2.6 | 4 ngày | P2 | |
| **T3.1** | Ops DB: approvals + audit (chuỗi băm) + hội thoại | P3 | T1.8 | 2 ngày | P1 | G1.9 |
| **T3.2** | Phân quyền theo vai trò/phạm vi (gateway) | P3 | T0.5, T3.1 | 1,5 ngày | P1 | I2 |
| **T3.3** | API FastAPI | P3 | T3.1–3.2 | 2 ngày | P1 | |
| **T3.4** | UI web tối thiểu (chat, nhãn, Xem cách tính, duyệt) | P3 | T3.3 | 3 ngày | P2 | |
| **T3.5** | Bản tin tuần | P3 | T1.8 | 2 ngày | P2 | H16 |
| **T3.6** | Adapter mock Agent 1/2/3 + `orchestrate_agents` | P3 | T1.8 | 1,5 ngày | P2 | |
| **T3.7** | Text‑to‑SQL có kiểm soát (sqlglot) | P3 | T1.9 | 3 ngày | P2 | H14 |
| **T4.1** | Hồ sơ doanh nghiệp tham số hóa + nhiều ngành + chạy hàng loạt | P4 | T0.2 | 5 ngày | P1 | `2_data/06` |
| **T4.2** | Kiểm thử quy mô 10⁶–10⁷ dòng | P4 | T4.1 | 2 ngày | P2 | NFR‑P2 |
| **T4.3** | Adapter nhập CSV ERP thật + ánh xạ tài khoản + báo cáo đối soát | P4 | T0.2 | 4 ngày | P1 | G2.1 |
| **T4.4** | Red‑team mở rộng (garak) + kịch bản demo | P4 | T3.4 | 2 ngày | P2 | |
| **T4.5** | Pilot đo kinh tế | P4 | T4.3 | 6 tuần lịch | P1 | H‑biz |

## Đường găng (critical path) tối thiểu để có "bản chạy được, đo được"
`T0.1 → T0.2 → T0.5 → T1.2 → T1.3/1.4 → T1.5/1.6/1.7 → T1.8 → T2.1 → T2.5 → T2.6` (≈ 25–30 ngày công).

## Quy tắc làm việc
1. **Mỗi thẻ = một nhánh con + PR nhỏ**, có test đi kèm; không gộp nhiều thẻ.
2. **Không sửa dữ liệu mẫu** mà không tăng `data_version` và cập nhật `2_data/05` + `ground_truth`.
3. **Mọi thay đổi prompt/model** chạy lại bộ val và đính kèm bảng so sánh (xem `3_evaluation/04`).
4. **Không dùng LLM để sinh nhãn kỳ vọng** của bộ test (chỉ dùng oracle SQL hoặc quy tắc); LLM chỉ để paraphrase câu hỏi và phải duyệt mẫu 10%.
5. **Cập nhật tài liệu** cùng PR khi đổi hành vi.
6. Ghi **quyết định** vào `docs/5_handoff/DECISIONS.md` (ngày, bối cảnh, lựa chọn, lý do).

## Mốc nghiệm thu
| Mốc | Điều kiện |
|---|---|
| M0 (hết P0) | Cổng G0 đạt |
| M1 (hết P1) | Agent chạy được CLI trên 4B & 8B; verifier chặn số lạ; không cần số đo |
| M2 (hết P2) | Báo cáo B0 vs B*; Cổng G1 đạt trên dev/val; test chạy một lần |
| M3 (hết P3) | Demo 7 cảnh (xem `1_business_analyst/04` hành trình) trên UI |
| M4 (hết P4) | Cổng G2 |
