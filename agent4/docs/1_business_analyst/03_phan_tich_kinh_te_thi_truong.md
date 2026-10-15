# 03 · Phân tích kinh tế & thị trường

## 1. Bối cảnh vĩ mô tác động tới nhu cầu
| Yếu tố | Nội dung (đã/ chưa kiểm chứng) | Tác động lên sản phẩm |
|---|---|---|
| **Chế độ kế toán** | Thông tư 99/2025/TT‑BTC thay Thông tư 200 từ 01/01/2026; DNNVV *có thể tiếp tục* dùng TT133 hoặc tự nguyện chuyển sang TT99 từ đầu năm tài chính (theo các bài phân tích; cần đối chiếu Điều 31 văn bản gốc). | Lớp chỉ số phải **đa chế độ** (TT133 hiện làm; TT99/TT200 là mở rộng: mã TK 521, 641/642). |
| **Thuế GTGT giảm 2%** (10%→8%) đến 31/12/2026 theo NĐ 174/2025 | Phạm vi loại trừ có chỗ nguồn không thống nhất (CNTT vs viễn thông). | Dữ liệu mẫu mô phỏng thuế suất 8% có hiệu lực theo ngày; agent phải trả lời **theo ngày chứng từ**. |
| **Lương tối thiểu vùng I** | 5.310.000 đ/tháng từ 01/01/2026 (NĐ 293/2025); tỷ lệ BH bắt buộc 32% (NLĐ 10,5% + DN 21,5%) + KPCĐ 2%. | Sinh dữ liệu lương/bảo hiểm đúng quy tắc; chỉ số `labor_cost`. |
| **Luật Trí tuệ nhân tạo** (134/2025/QH15) | Thông qua 10/12/2025, hiệu lực 01/03/2026; có cơ chế hệ thống rủi ro cao, nguyên tắc con người giám sát; danh mục chi tiết còn ở văn bản dưới luật (dự thảo). | Thiết kế *human‑in‑the‑loop*, nhãn "AI‑generated", nhật ký kiểm toán ngay từ đầu. |
| **Hóa đơn điện tử, thanh toán không tiền mặt** | Dữ liệu hóa đơn/chứng từ ngày càng số hóa. | Nguồn dữ liệu vào đã có cấu trúc (hóa đơn, sao kê) → khả thi tự động hóa. |

## 2. Phân tích cầu
**Ai trả tiền & vì sao?**
- *Chủ DN/CEO*: mua "sự yên tâm" và tốc độ quyết định; ngưỡng chi trả thấp (so với phần mềm kế toán đang trả).
- *Kế toán trưởng*: mua **giảm khối lượng yêu cầu ad‑hoc**, giảm rủi ro "làm vội".
- *Ngân hàng / quỹ* (kênh thứ cấp): muốn theo dõi sức khỏe tài chính khách hàng DN (xem Agent 1/2).

**Động lực mua (jobs‑to‑be‑done):** "Cho tôi biết con số đúng, ngay bây giờ, và vì sao" · "Báo cho tôi trước khi có chuyện" · "Giúp tôi ra quyết định nhưng đừng tự làm thay tôi".

## 3. Cạnh tranh & cách thị trường đánh giá
| Nhóm giải pháp | Ví dụ (tham khảo, chưa đo thị phần) | Điểm mạnh | Hạn chế mà Agent 4 nhắm vào |
|---|---|---|---|
| Phần mềm kế toán VN tích hợp trợ lý | MISA AMIS (trợ lý AVA), các phần mềm Fast, Bravo… | Dữ liệu sẵn; được tin dùng; ra lệnh bằng chữ/giọng nói | Chủ yếu *tra cứu báo cáo có sẵn / nhắc việc*; ít diễn giải phân tích đa bước, so sánh kỳ, truy vết tới chứng từ, khung thuế/quản trị tách bạch. |
| Nền tảng FP&A/Copilot quốc tế | Microsoft Copilot cho Finance, Datarails… | Chiều sâu phân tích | Chi phí/ngôn ngữ/chuẩn kế toán không bám TT133; dữ liệu rời khỏi VN. |
| BI/Dashboard (Power BI, Metabase) | — | Trực quan | Không hiểu ngôn ngữ tự nhiên; cần biết trước chỉ số. |
| Chatbot NL2SQL tự do | — | Linh hoạt | Độ chính xác thấp trên schema thật (E3), khó kiểm toán. |
| Excel + kế toán | Mặc định ở phần lớn DNVVN | Quen thuộc | Chậm, dễ lệch số, phụ thuộc người. |

**Cách thị trường/khách hàng đánh giá một sản phẩm kiểu này** (rút từ thực tiễn tài chính doanh nghiệp):
1. **Độ chính xác & khả năng kiểm toán** (truy vết số) — điều kiện cần.
2. **Tuân thủ chuẩn kế toán/thuế VN** (TT133/TT99, tách khung).
3. **Bảo mật & nơi đặt dữ liệu** (không gửi sổ cái ra API ngoài).
4. **Thời gian tới giá trị** (tích hợp phần mềm kế toán hiện có trong vài ngày).
5. **Chi phí so với giờ kế toán tiết kiệm** (xem `3_evaluation/03`).

## 4. Định cỡ thị trường (minh họa — *giả định, cần xác thực*)
Không có số thị phần đáng tin trong phiên nghiên cứu này; mô hình dưới là **khung tính** để nhóm điền số thật:

```
TAM  = số DN đang hoạt động ở VN                 (≈ 800 nghìn theo ước tính cũ 2022 – CẦN số mới)
SAM  = DN có phần mềm kế toán + ≥ 5 nhân sự TCKT + doanh thu ≥ 50 tỷ   (giả định 2% TAM ≈ 16 nghìn DN)
SOM  = % SAM mua trong 3 năm                      (đặt 3% / 8% / 15%)
Doanh thu tiềm năng/năm = SAM × giá thuê bao × tỷ lệ thâm nhập
   – giá giả định 60–120 triệu/DN/năm (phải ≥ chi phí biên ~60 triệu, xem 3_evaluation/03)
       ⇒ SAM ≈ 960–1.920 tỷ đồng/năm
   – kịch bản giá thấp 24–36 triệu/DN/năm chỉ khả thi nếu chi phí biên < ~15 triệu/DN/năm
```
Việc phải làm: lấy số DN theo quy mô từ Tổng cục Thống kê, số khách hàng công bố của nhà cung cấp phần mềm kế toán, khảo sát 20–30 kế toán trưởng về mức sẵn sàng chi trả.

## 5. Mô hình kinh doanh khả thi
| Mô hình | Mô tả | Ưu | Nhược |
|---|---|---|---|
| **A. Tích hợp vào phần mềm kế toán (OEM/đối tác)** | Chạy cạnh ERP/phần mềm kế toán, đọc qua API/CSV | Phân phối nhanh, chi phí phân bổ thấp | Phụ thuộc đối tác |
| **B. SaaS đa khách hàng** | Mỗi DN một kho dữ liệu riêng, model dùng chung | Biên tốt khi ≥ 10 khách | Trách nhiệm bảo mật |
| **C. Triển khai riêng (on‑prem)** | Một GPU + gói dịch vụ | Dữ liệu ở lại DN | **Không kinh tế** nếu < 5–10 khách (xem mô hình chi phí) |

## 6. Vì sao *bây giờ* (why now)
1. Model ≤ 10B chạy tại chỗ đủ dùng cho *chọn công cụ có cấu trúc* (không cần model lớn) → rào chi phí giảm.
2. Khung pháp lý AI mới yêu cầu giám sát con người/minh bạch → lợi thế cho thiết kế "đề xuất – phê duyệt – nhật ký".
3. Chuyển chế độ kế toán (TT99) tạo nhu cầu rà soát số liệu và báo cáo → thời điểm để bán công cụ "xem số".
