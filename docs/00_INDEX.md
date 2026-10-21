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

> Cập nhật 21/10/2026: số T1 thật dùng giao thức v2 ở dưới. Các số hazard tổng
> hợp/E2E trước sửa `expand` đang được chạy lại; chỉ CSV có `fullweek` được
> dùng nghiệm thu mới. Xem cổng hiện hành và nhật ký Sprint 1.

**Vấn đề.** SME Việt Nam bán chịu 65% doanh số B2B, kỳ hạn 45 ngày, 39% giá trị hoá đơn quá hạn, khách trả chậm
thêm khoảng một tháng, nợ xấu 3% (Atradius VN 2025). Lãi trên sổ không trả được lương: thiếu hụt tiền mặt xảy ra vì
**thời điểm** tiền về lệch khỏi giả định "trả đúng hạn" của bảng tính, và các khách trả chậm **cùng lúc** khi thị trường
thiếu thanh khoản (47% nguyên nhân trễ là thanh khoản của khách).

**Sản phẩm.** Mỗi tuần trả lời: *13 tuần tới tuần nào có thể thiếu tiền, xác suất bao nhiêu, vì sao, nên đòi khoản nào
trước, nếu khách lớn trả chậm thì sao* — bằng dải P10/P50/P90 thay vì một con số.

**Đã làm được (đo trên dữ liệu, xem 03_Evaluation/04):**
- Dữ liệu: crawl 8 nguồn thật (~1,6 GB, có SHA-256) + 4 thế giới SME VN tổng hợp (394k hoá đơn, 376k giao dịch NH,
  89k lời hứa), hiệu chỉnh theo Atradius, OxCGRT VN, luật VN; thiết kế cho domain adaptation.
- T1 dữ liệu thật — **giao thức v2, cập nhật 21/10/2026**: BLEND(DH-GBM,B1d), w chọn trên cửa sổ hiệu chỉnh rồi refit; Customer Invoices: giảm pinball 14.4% [11.7; 17.4] so với B1d; BPI: giảm pinball 6.5% [2.1; 11.0] so với B1d.
  Đây là bằng chứng phương pháp trên hai bộ thật, chưa đại diện SME Việt Nam. Các kết quả hazard tổng hợp/E2E trước 20/10 đang chờ chạy lại với hậu tố `-fullweek`.
- T4: LightGBM toàn cục thắng mọi mốc trên tổng hợp; trên dữ liệu thật Online Retail II, tiền huấn luyện tổng hợp giảm
  SPL 3,8% nhưng **Chronos-Bolt zero-shot tốt nhất** (báo cáo trung thực).
- T7: có phát hiện thay đổi theo khách/danh mục và phép đo chuyển chế độ; kết quả và giới hạn ở bảng hiện hành.
- T9: khớp sao kê lai quy tắc/ML, phần mơ hồ vào hàng chờ; xem G15 và đường precision–coverage chọn trên nguồn.
- T0/T5: 15 kiểm thử đạt (hạn thuế theo ví dụ luật, kể cả dịch hạn do Tết 2025).

- T6: E2E XML/CSV, nhãn T9 ước lượng, khoảng số dư và cảnh báo; số đo hiện hành ở G12/G13 và CSV fullweek, đối chứng bổ sung được báo riêng.
- Thích nghi miền/T8: xem kết quả và CI của chuỗi fullweek; các giả thuyết chưa đạt giữ nguyên tiêu chí đăng ký.
- T2: có các biến thể SBA EXEMPT và hiệu chỉnh xác suất; bằng chứng cho vay Mỹ giữ phạm vi phương pháp.

**Trạng thái nghiệm thu:** xem cổng hiện hành và nhật ký Sprint 1. API/dashboard/T10/giám sát local đã có; chuyên gia, UAT và pilot thật vẫn cần bằng chứng ngoài mô phỏng.

**Kinh tế.** Với một SME doanh thu 40 tỷ/năm, giá trị kỳ vọng ≈ 194 triệu đồng/năm (khoảng 96–330; giải phóng đệm tiền mặt,
giảm DSO, tránh chi phí thiếu hụt, giảm nợ xấu, tiết kiệm giờ đối chiếu) so với giá dự kiến 9–18 triệu/năm (lợi ích/giá ≈ 5–18×, cơ sở 10,7×)
(chi tiết và độ nhạy: 03_Evaluation/06).
