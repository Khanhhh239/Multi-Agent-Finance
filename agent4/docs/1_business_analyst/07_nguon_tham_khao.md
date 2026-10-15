# 07 · Nguồn tham khảo và mức độ tin cậy

**Quy ước:** A = đã đọc nguồn gốc / tự kiểm chứng; B = đọc qua trang tổng hợp, báo chí, hoặc trích trong tài liệu của nhóm (chưa đọc nguồn gốc); C = chưa kiểm chứng/cần tìm.

## Tài liệu nội bộ của nhóm
| Mã | Tài liệu | Dùng cho |
|---|---|---|
| N1 | `Agent4.md` (đề cương Agent "CFO ảo") | Ý tưởng, bằng chứng E1–E3, kiến trúc lai |
| N2 | `DIGITAL_ACCOUNTING_PART4_PRODUCT_SPEC.md` §AGENT 4 | Yêu cầu sản phẩm, UX, roadmap 3 giai đoạn |
| N3 | `DIGITAL_ACCOUNTING_PART2_ARCH_PART3_PLAN.md` §3.5 | 4 bước kế hoạch, bộ 100 câu, ngưỡng nghiệm thu A4 |
| N4 | `schema.md`, `metrics-v0.md`, `sample-questions.md` (nhánh `agent4`) | Schema TT133 gốc, 16 chỉ số v0, 30 câu mẫu |
| N5 | Phiên "Agent 1" — kiểm tra bộ Customer Invoices (Kaggle) | Bài học về mức "thật" của dữ liệu công khai (`2_data/02`) |

## Nguồn bên ngoài đã tham chiếu
| Chủ đề | Nguồn | Tin cậy | Ghi chú |
|---|---|---|---|
| TT99/2025 thay TT200, DNNVV được giữ TT133 | luatvietnam.vn, einvoice.vn, thuvienphapluat.vn (bài phân tích) | B | Đối chiếu Điều 31 TT99/2025/TT‑BTC |
| TT133: không dùng TK 521; 6421/6422 | helpact.misa.vn, accgroup.vn, luatminhkhue.vn | B | Có bài nêu trái chiều (theo dõi 521 nội bộ) → coi là tùy chọn |
| Luật Trí tuệ nhân tạo 134/2025/QH15 | lsvn.vn, luatvietnam.vn, apolatlegal.com | B | Danh mục rủi ro cao còn dự thảo |
| Lương tối thiểu vùng 2026 | thuvienphapluat.vn, luatvietan.vn, helpact.misa.vn | B | NĐ 293/2025/NĐ‑CP |
| Tỷ lệ BHXH/BHYT/BHTN 2026 | luatvietnam.vn, easyhrm.vn | B | DN 21,5% + KPCĐ 2%; NLĐ 10,5% |
| GTGT 8% đến 31/12/2026 | thuvienphapluat.vn, sme.misa.vn | B | NĐ 174/2025/NĐ‑CP; phạm vi có bất nhất |
| SME: tỷ trọng, chuyển đổi số | vcci.com.vn, vneconomy.vn, báo Bộ KH&ĐT | B | Số khác nhau theo nguồn; không có thị phần phần mềm kế toán |
| Qwen3 function calling / Ollama | Model card Qwen3‑4B‑Instruct‑2507; hướng dẫn Ollama/Unsloth | B | Điểm BFCL các nguồn mâu thuẫn → **tự đo** (`4_ai_engineering/05`) |
| Spider 2.0, ConvFinQA/FinQA, BFCL, τ‑bench, BIRD | Bài báo/benchmark công khai | C (chưa đọc lại trong phiên) | Dùng làm tham chiếu thiết kế bộ đánh giá |
| APQC khóa sổ, G‑Accon 94% Excel, công bố MISA AVA | Trích trong N1/N2 | B→C | Cần tra nguồn gốc trước khi nộp hồ sơ |

## Việc xác minh còn tồn
1. Tra nguồn gốc APQC (6,4 ngày), G‑Accon (94%), Spider 2.0 (10,1% / 17,1%), công bố MISA AVA.
2. Đọc văn bản gốc: TT99/2025 Điều 31; Luật AI 134/2025/QH15 (Chương về hệ thống rủi ro cao, nghĩa vụ minh bạch); NĐ 174/2025 Phụ lục I–II.
3. Lấy số DN theo quy mô (Tổng cục Thống kê) và số khách hàng công bố của các hãng phần mềm kế toán.
4. Khảo sát 20–30 kế toán trưởng: tần suất & thời gian xử lý yêu cầu ad‑hoc (thay các giả định trong `3_evaluation/03`).
