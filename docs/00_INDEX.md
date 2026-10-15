# Agent 1 — Trợ lý Dòng tiền (Cash-Flow Copilot) · Bộ tài liệu

Người thực hiện: Khánh (agent1-Khanh). Ngày: 15/10/2026. Nền tảng: Phần 1, 4, 5, 7 trong `graphRAG/`,
code tham chiếu `invoice_prediction/` và nhánh `agent1-Thắng`.

| Thư mục | Vai trò người viết | Đọc khi cần |
|---|---|---|
| [01_Business_Analyst](01_Business_Analyst/README.md) | BA, nhà nghiên cứu kinh tế – tài chính | Vì sao sản phẩm tồn tại, ai trả tiền, nỗi đau, bằng chứng, yêu cầu |
| [02_Data](02_Data/README.md) | Data scientist / data analyst | Dữ liệu thật dùng/không dùng, máy phát tổng hợp, hard case, quy mô, bộ đánh giá |
| [03_Evaluation](03_Evaluation/README.md) | Tester, BA đánh giá | Metric kỹ thuật + kinh tế, cổng nghiệm thu, kết quả hiện có, chi phí, ROI trước/sau |
| [04_AI_Methods](04_AI_Methods/README.md) | AI engineer / researcher | Pipeline, mô hình từng T, domain adaptation, thí nghiệm, tham số |
| [05_Coding_Agent_Plan](05_Coding_Agent_Plan/README.md) | Kiến trúc sư / người giao việc | Kế hoạch từng gói việc cho coding agent tiếp theo |

## Tóm tắt một trang

**Vấn đề.** SME Việt Nam bán chịu 65% doanh số B2B, kỳ hạn 45 ngày, 39% giá trị hoá đơn quá hạn, khách trả chậm
thêm khoảng một tháng, nợ xấu 3% (Atradius VN 2025). Lãi trên sổ không trả được lương: thiếu hụt tiền mặt xảy ra vì
**thời điểm** tiền về lệch khỏi giả định "trả đúng hạn" của bảng tính, và các khách trả chậm **cùng lúc** khi thị trường
thiếu thanh khoản (47% nguyên nhân trễ là thanh khoản của khách).

**Sản phẩm.** Mỗi tuần trả lời: *13 tuần tới tuần nào có thể thiếu tiền, xác suất bao nhiêu, vì sao, nên đòi khoản nào
trước, nếu khách lớn trả chậm thì sao* — bằng dải P10/P50/P90 thay vì một con số.

**Đã làm được (đo trên dữ liệu, xem 03_Evaluation/04):**
- Dữ liệu: crawl 8 nguồn thật (~1,6 GB, có SHA-256) + 4 thế giới SME VN tổng hợp (394k hoá đơn, 376k giao dịch NH,
  89k lời hứa), hiệu chỉnh theo Atradius, OxCGRT VN, luật VN; thiết kế cho domain adaptation.
- T1 (khi nào tiền về): hazard rời rạc LightGBM giảm sai số dự báo **dòng thu 4 tuần (WAPE) 63%** so với mốc
  "trung vị trễ theo khách" (1,08 → 0,40), IBS 0,267 → 0,105, độ phủ khoảng 80% thực tế 85,7% (hơi thận trọng).
  Trên dữ liệu AR thật (Customer Invoices): ensemble giảm MAE 17% so với mốc (2,77 → 2,29 ngày).
- T4: LightGBM toàn cục thắng mọi mốc trên tổng hợp; trên dữ liệu thật Online Retail II, tiền huấn luyện tổng hợp giảm
  SPL 3,8% nhưng **Chronos-Bolt zero-shot tốt nhất** (báo cáo trung thực).
- T7: CUSUM trên phần dư PIT phát hiện 52% điểm gãy hành vi trong 180 ngày (trễ trung vị 50 ngày) ở miền giữ lại.
- T9: khớp sao kê giảm sai số ngày trả từ 12,6 ngày (ngày ghi sổ) xuống **2,0 ngày**, F1 liên kết 0,69 (> quy tắc 0,63).
- T0/T5: 15 kiểm thử đạt (hạn thuế theo ví dụ luật, kể cả dịch hạn do Tết 2025).

- T6: Monte Carlo copula-t + ACI cho cov80 số dư 0,79–0,81 (không ACI 0,70/0,68); IS80 thắng mọi đối chứng ở tuần 1–4; thay phân phối T1 bằng ngày điểm B1 làm IS80 ×4.
- Thích nghi miền: zero-shot đã thấp hơn mốc 60% pinball; fine-tune chỉ +1,5–2% (giả thuyết ≥10% bị bác bỏ). T8 −7,2% MAE (cổng 10% chưa đạt); nhãn ngân hàng vs sổ: −5,6% WAPE.
- T2: Cure-GBM PR-AUC 0,97 (tổng hợp), 15,7× nền trên SBA thật (kèm cảnh báo nhãn `EXEMPT`).

**Chưa xong / cần làm lại** (05_Coding_Agent_Plan): lead time và báo giả của T6 (G13), demo T10 (lỗi), dashboard, API, giám sát trôi, chạy lại A/B/E/T6 theo giao thức đo đã sửa (as-of, CDF công bằng), dữ liệu thật bổ sung, pilot T13.

**Kinh tế.** Với một SME doanh thu 40 tỷ/năm, giá trị kỳ vọng ≈ 194 triệu đồng/năm (khoảng 96–330; giải phóng đệm tiền mặt,
giảm DSO, tránh chi phí thiếu hụt, giảm nợ xấu, tiết kiệm giờ đối chiếu) so với giá dự kiến 9–18 triệu/năm (lợi ích/giá ≈ 5–18×, cơ sở 10,7×)
(chi tiết và độ nhạy: 03_Evaluation/06).
