# 7. Kế hoạch kiểm thử

Kiểm thử theo 7 tầng, từ rẻ đến đắt. Mỗi tầng có đầu vào, tiêu chí qua/rớt, công cụ, và ai chạy.

| Tầng | Mục tiêu | Công cụ / mã | Khi nào | Qua/rớt |
|---|---|---|---|---|
| 1. Đơn vị | Hàm lõi đúng (lịch, MST, XML, cổng chất lượng, metric) | `pytest tests/` | mỗi commit | 100% |
| 2. Hợp đồng dữ liệu | Lược đồ bảng chuẩn, kiểu, khoá, không trùng, không rò nhãn | kiểm thử lược đồ (WP-0.2) | mỗi lần sinh/nhập | 0 vi phạm |
| 3. Mô hình trên nhãn tổng hợp | Chỉ số kỹ thuật vs mốc, theo cổng G1–G18 | `scripts/run_*.py` + `make_report.py` | mỗi thay đổi mô hình | cổng G |
| 4. Chịu nhiễu | Thay đổi đuôi, ghi sổ, memo, sốc | `sens_*`, `hc_*`, ma trận tham số | trước phát hành | suy giảm có kiểm soát (≤30% pinball) |
| 5. Tích hợp đầu-cuối | Pipeline T9→T1→T4→T5→T6→T10 chạy từ dữ liệu thô | `run_e2e.py` (WP-6) | hằng đêm trên môi trường staging | không lỗi; thời gian ≤ NFR-03 |
| 6. UAT | Người dùng hiểu & hành động | 5–10 kế toán/chủ DN; kịch bản A1–A6 | trước pilot | A1–A6 đạt |
| 7. Pilot/A-B | Hiệu quả thật | song song 8–12 tuần + bật 12–24 tuần; DiD | pilot | K1–K9, G tầng thật |

## 7.1 Bộ kiểm thử đơn vị đã có (15)

`tests/test_t0_t5.py`: hạn VAT tháng/quý (kể cả dịch do Chủ nhật, nghỉ lễ 30/4–1/5, Tết), TNDN tạm nộp/quyết toán, môn bài (bỏ 2026), lương tối thiểu vùng 2019–2026, VAT 8%/10% theo thời kỳ + loại trừ kim loại,
Tết không là ngày làm việc, lịch nghĩa vụ đủ hạng mục & rơi vào ngày làm việc, MST chữ số kiểm tra (200 MST sinh ra), XML ↔ bảng (50 file), cổng chất lượng (recall & precision ≥95% với 30% lỗi chèn).

## 7.2 Kiểm thử cần bổ sung (giao ở 05_Coding_Agent_Plan)

| Mã | Nội dung | Loại |
|---|---|---|
| TC-01 | Bất biến máy phát: thanh toán ≥ ngày lập; tổng thanh toán ≤ giá trị HĐ (trừ thu hồi); ≤1,5% trả cuối tuần; mọi MST hợp lệ; số dư = đệm + luỹ kế | property-based (hypothesis) |
| TC-02 | Không rò rỉ: đặc trưng tại T không đổi khi thêm dữ liệu sau T (`snapshot(T)` bất biến với nhãn tương lai) | metamorphic |
| TC-03 | Nhãn kiểm duyệt: `event`, `time_obs` đúng với `label_end` | đơn vị |
| TC-04 | Hazard hợp lệ: Σ P_ik + S_K = 1; phân vị đơn điệu | thuộc tính |
| TC-05 | CQR: độ phủ lý thuyết trên dữ liệu hoán đổi được (mô phỏng) | thống kê |
| TC-06 | ACI: độ phủ dài hạn ≈ 1−α trên chuỗi có trôi dạng bước | thống kê |
| TC-07 | MC: ρ=0 và n→∞ ⇒ dòng thu → kỳ vọng; ρ=1 ⇒ ba khách trễ cùng nhau | thuộc tính |
| TC-08 | T9: không gán một đồng cho hai hoá đơn; tổng phân bổ ≤ số tiền giao dịch + dung sai | thuộc tính |
| TC-09 | Cổng LLM: mọi số trong văn bản xuất hiện trong bảng tính | đối chiếu |
| TC-10 | Tính tái lập: cùng seed ⇒ sai khác chỉ số <0,5% | hồi quy |
| TC-11 | Hồi quy hiệu năng: batch DN 2.000 HĐ mở ≤5 phút trên 4 vCPU | hiệu năng |
| TC-12 | Bảo mật: không ghi MST/tên thật vào log; mã hoá lưu trữ; kiểm quyền truy cập | bảo mật |

## 7.3 UAT — kịch bản người dùng

| Kịch bản | Nhiệm vụ | Qua nếu |
|---|---|---|
| U1 | Mở app, nói tuần nào nguy hiểm | 5/5 đúng ≤30 giây |
| U2 | Đọc một cảnh báo, nói lý do và hành động | ≥4/5 đúng |
| U3 | Dùng "đòi ai trước" và xác nhận danh sách có hợp lý | ≥70% đồng ý ≥3/5 mục đầu |
| U4 | Ghi một lời hứa trả và thấy dải thay đổi | hiểu được vì sao dải đổi |
| U5 | Thử kịch bản "khách lớn trễ 2 tuần" | đọc đúng kết quả |
| U6 | Đối chiếu số dư đầu kỳ với sao kê | sai lệch 0đ |

## 7.4 Pilot — thiết kế đo

1. **Chọn DN:** 3–5 DN (hoặc 1 văn phòng kế toán phục vụ 5–10 DN), có HĐĐT + sao kê ≥12 tháng, đồng ý theo NĐ 13/2023, ẩn danh khi đưa vào môi trường phát triển.
2. **Giai đoạn 0 (8–12 tuần):** chạy song song, chỉ dự báo, không hiển thị cảnh báo; thu K1–K9 như hiện trạng.
3. **Giai đoạn 1 (12–24 tuần):** hiển thị; ghi hành động của người dùng (nhấn, đòi, thay đổi chi).
4. **Phân tích:** DiD trên K1, K3–K6; hiệu chỉnh/độ phủ trên dự báo hiển thị; báo cáo trường hợp sai (tuần thiếu hụt hệ thống không báo; khách bị đánh giá sai nhiều nhất).
5. **Tiêu chí kết thúc pilot:** G1/G2/G12/G13 đạt trên dữ liệu thật; K1 giảm ≥1 ngày; ≥60% DN dùng hằng tuần; không sự cố dữ liệu.

## 7.5 Giám sát sau triển khai

| Chỉ số | Tần suất | Ngưỡng hành động |
|---|---|---|
| cov80 trượt 12 tuần | tuần | ngoài [70, 90]% 4 tuần ⇒ retrain/nới khoảng |
| PSI `c_delay_ewm` | tuần | >0,1 ⇒ cảnh báo; >0,25 ⇒ retrain bắt buộc |
| Tỷ lệ HĐ không qua cổng chất lượng | ngày | >2% ⇒ báo DN |
| Tỷ lệ khớp tự động T9 | tuần | <50% ⇒ xem lại nội dung CK |
| Tỷ lệ báo giả bị đánh dấu | tháng | >30% ⇒ chỉnh ngưỡng |
| Thời gian batch | ngày | >5 phút ⇒ điều tra |
| Báo động T7 danh mục | liên tục | kích hoạt chế độ khủng hoảng |
