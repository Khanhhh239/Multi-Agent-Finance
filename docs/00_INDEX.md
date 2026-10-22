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

> **Trạng thái 22/10/2026 (bản cuối của đợt này).** Toàn bộ chuỗi đã chạy lại với `expand` đã sửa (hậu tố `-fullweek`),
> 340/340 kiểm thử đạt. Cổng: 9 đạt, 9 trượt ([GATES_CURRENT](03_Evaluation/GATES_CURRENT.md)).
> **Quyết định:** GO cho bậc 0 "bóng" (chạy song song, không ai hành động theo) với luật an toàn; NO-GO cho mọi bậc hành động
> cho tới khi có dữ liệu doanh nghiệp thật — xem [GO_NO_GO_SYNTHETIC_ONLY](03_Evaluation/GO_NO_GO_SYNTHETIC_ONLY.md).
> Nhật ký đầy đủ: [NHAT_KY_SPRINT1](05_Coding_Agent_Plan/NHAT_KY_SPRINT1_2026-10-20.md) mục 1–12.

**Vấn đề.** SME Việt Nam bán chịu 65% doanh số B2B, kỳ hạn 45 ngày, 39% giá trị hoá đơn quá hạn, khách trả chậm
thêm khoảng một tháng, nợ xấu 3% (Atradius VN 2025). Lãi trên sổ không trả được lương: thiếu hụt tiền mặt xảy ra vì
**thời điểm** tiền về lệch khỏi giả định "trả đúng hạn" của bảng tính, và các khách trả chậm **cùng lúc** khi thị trường
thiếu thanh khoản (47% nguyên nhân trễ là thanh khoản của khách).

**Sản phẩm.** Mỗi tuần trả lời: *13 tuần tới tuần nào có thể thiếu tiền, xác suất bao nhiêu, vì sao, nên đòi khoản nào
trước, nếu khách lớn trả chậm thì sao* — bằng dải P10/P50/P90 thay vì một con số.

**Đã làm được (đo trên dữ liệu, xem 03_Evaluation/04):**
- Dữ liệu: crawl 8 nguồn thật (~1,5 GB, có SHA-256) + **66 thế giới SME VN tổng hợp (~6,9 triệu hoá đơn)**: nguồn/đích,
  12 hard-case, 20 thế giới ngẫu nhiên hoá, 4 thế giới lớn (3,5 triệu HĐ), và **`tgt2` niêm phong** (40 công ty, 71 sự kiện thiếu tiền)
  chỉ dùng một lần cho luồng đã đóng băng. Hiệu chỉnh theo Atradius, OxCGRT VN, luật VN. Kiểm định giống/khác (C2ST) tách
  phần thiết kế (kỳ hạn) khỏi phần hành vi: hành vi AUC 0,70–0,79; bộ thật tham chiếu chỉ 6 công ty nên không đủ để chỉnh máy phát thêm
  ([10_realism_v2](02_Data/10_realism_v2.md)).
- T1 dữ liệu thật — **giao thức v2, cập nhật 21/10/2026**: BLEND(DH-GBM,B1d), w chọn trên cửa sổ hiệu chỉnh rồi refit; Customer Invoices: giảm pinball 14.4% [11.7; 17.4] so với B1d; BPI: giảm pinball 6.5% [2.1; 11.0] so với B1d.
  Đây là bằng chứng phương pháp trên hai bộ thật, chưa đại diện SME Việt Nam. Trên `tgt2` niêm phong, luồng triển khai T1 (tinh chỉnh 12 tháng)
  thắng B1d +47,5% [30,9; 60,7]; có **cổng thoái lui** tự chuyển về B1d theo từng doanh nghiệp nếu mô hình thua 4 tuần liên tiếp.
- T6 dải tiền mặt: copula-t gốc hẹp (cov80 0,62–0,72); **copula-t + ACI** đúng khoảng 75–85% trên cả `tgt` (0,754/0,767) và `tgt2` (0,767/0,771).
- G13 cảnh báo thiếu tiền (chính sách chọn trên nguồn rồi đóng băng): `tgt2` phát hiện ≥4 tuần 0,75, báo giả 0,75/công ty-năm (đạt điểm ước lượng);
  `tgt` báo giả 2,08 (trượt) ⇒ chỉ dùng làm gợi ý có người duyệt ([G13_ALERT_POLICY](03_Evaluation/G13_ALERT_POLICY.md)).
- T4: LightGBM toàn cục thắng mọi mốc trên tổng hợp; trên dữ liệu thật Online Retail II, tiền huấn luyện tổng hợp giảm
  SPL 3,8% nhưng **Chronos-Bolt zero-shot tốt nhất** (báo cáo trung thực).
- T7: có phát hiện thay đổi theo khách/danh mục và phép đo chuyển chế độ; kết quả và giới hạn ở bảng hiện hành.
- T9: khớp sao kê lai quy tắc/ML, phần mơ hồ vào hàng chờ. Trên nguồn đạt (F1 0,826); trên `tgt` trượt sát nút
  (F1 0,796, precision 0,925 < 0,95) — chẩn đoán ở [T9_RECALL_DIAGNOSIS](03_Evaluation/T9_RECALL_DIAGNOSIS.md).
  **T9 v2** (đăng ký trước, đo một lần trên bộ đích sạch `tgt3`): precision 0,962 (đạt), ngày trả chính xác hơn 3 lần, nhưng F1 0,706 do recall
  ⇒ liên kết tự động đáng tin, phần còn lại vào hàng chờ ([G15_T9_V2_PREREG](03_Evaluation/G15_T9_V2_PREREG.md)).
- T0/T5: 15 kiểm thử đạt (hạn thuế theo ví dụ luật, kể cả dịch hạn do Tết 2025).

- T6: E2E XML/CSV, nhãn T9 ước lượng, khoảng số dư và cảnh báo; số đo hiện hành ở G12/G13 và CSV fullweek, đối chứng bổ sung được báo riêng.
- Thích nghi miền/T8: xem kết quả và CI của chuỗi fullweek; các giả thuyết chưa đạt giữ nguyên tiêu chí đăng ký.
- T2: có các biến thể SBA EXEMPT và hiệu chỉnh xác suất; bằng chứng cho vay Mỹ giữ phạm vi phương pháp.

**Trạng thái nghiệm thu (22/10/2026):** đạt G1, G2, G5, G6, G9, G10, G12, G16, G18; trượt G3, G4, G7, G8, G11, G13 (tgt), G14, G15, G17.
API/dashboard/T10/giám sát local đã có; chuyên gia, UAT và pilot thật vẫn cần bằng chứng ngoài mô phỏng.
Không có dữ liệu doanh nghiệp VN thật ⇒ cam kết hợp lệ duy nhất: "không tệ hơn mốc đơn giản B1d, tự thoái lui nếu tệ hơn".

**Kinh tế.** Với một SME doanh thu 40 tỷ/năm, giá trị kỳ vọng ≈ 194 triệu đồng/năm (khoảng 96–330; giải phóng đệm tiền mặt,
giảm DSO, tránh chi phí thiếu hụt, giảm nợ xấu, tiết kiệm giờ đối chiếu) so với giá dự kiến 9–18 triệu/năm (lợi ích/giá ≈ 5–18×, cơ sở 10,7×)
(chi tiết và độ nhạy: 03_Evaluation/06).
