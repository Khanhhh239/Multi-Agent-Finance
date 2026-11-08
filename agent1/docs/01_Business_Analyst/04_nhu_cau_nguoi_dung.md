# 4. Nhu cầu người dùng

## 4.1 Chân dung (persona)

| Persona | Mô tả | Mục tiêu | Rào cản |
|---|---|---|---|
| **Chị Lan — chủ xưởng nhựa** (40 lao động, 35 tỷ/năm) | Tự quyết mọi khoản chi lớn; xem số dư trên app ngân hàng mỗi sáng | Không bao giờ trễ lương; biết khi nào cần vay | Không có thời gian đọc báo cáo; nghi ngờ "AI đoán mò" |
| **Anh Tuấn — kế toán kiêm nhiệm** | Dùng MISA/Excel; đối chiếu sao kê cuối tháng | Bớt làm tay; số khớp sổ; không bị sếp trách | Sợ hệ thống sai làm mình chịu trách nhiệm |
| **Chị Hà — phụ trách công nợ/sales** | Gọi điện, nhắn Zalo đòi nợ | Biết gọi ai trước; ghi lại lời hứa nhanh | Không muốn nhập liệu thêm |
| **Ngân hàng đối tác** (người hưởng lợi gián tiếp) | Thẩm định hạn mức vốn lưu động | Thấy dòng tiền dự kiến có kiểm định | Cần dữ liệu đồng ý chia sẻ theo NĐ 13/2023 |

## 4.2 Jobs-to-be-done

| Khi… | Tôi muốn… | Để… |
|---|---|---|
| đầu tuần mở app | thấy ngay 13 tuần tới có tuần nào nguy hiểm | quyết định có cần hành động không trong 30 giây |
| có cảnh báo | biết vì sao (khoản nào trễ, khoản chi nào lớn) | tin cảnh báo và biết làm gì |
| chuẩn bị đi đòi nợ | có danh sách ưu tiên kèm lý do | dùng ít cuộc gọi nhất mà an toàn nhất |
| khách hứa trả | ghi lời hứa bằng một tin nhắn | dự báo cập nhật mà không phải nhập form |
| định ký hợp đồng lớn / hoãn khoản chi | thử kịch bản | thấy tác động trước khi cam kết |
| cuối tháng | số dư và công nợ khớp sổ, khớp sao kê | không phải đối chiếu tay |

## 4.3 Nhu cầu ưu tiên (MoSCoW)

| Ưu tiên | Nhu cầu | T liên quan |
|---|---|---|
| Must | Dải P10/P50/P90 số dư 13 tuần + P(thiếu hụt) tuần nào | T1, T4, T5, T6 |
| Must | Không nhập tay: đọc hoá đơn điện tử XML + sao kê | T0, T9 |
| Must | Lịch chi lương/BHXH/thuế đúng luật, dịch ngày nghỉ/Tết | T5 |
| Should | Danh sách đòi nợ ưu tiên + lý do | T10, T1, T2 |
| Should | Cảnh báo khách thay đổi hành vi | T7 |
| Should | Kịch bản "nếu như" | T6, T10 |
| Should | Xác suất nợ xấu + đề xuất dự phòng theo TT48/2019 | T2 |
| Could | Ghi lời hứa qua chat (Agent 4 CFO ảo) | T8 |
| Could | Chia sẻ dự báo có kiểm định cho ngân hàng (có đồng ý) | T6, T13 |
| Won't (giai đoạn này) | Tự động vay/thanh toán thay DN | — |

## 4.4 Hành trình người dùng (tóm tắt)

1. **Onboard (≤1 ngày):** kết nối cổng hoá đơn điện tử (tải XML từ 07/2022), tải sao kê 12–24 tháng, chọn ngày lương.
2. **Tuần đầu:** hệ thống khớp sao kê – hoá đơn (T9), báo tỷ lệ khớp sổ (N6), chạy dự báo với mô hình nguồn đã thích
   nghi cho DN (domain adaptation, 04_AI_Methods/05).
3. **Hằng tuần:** màn hình dải màu 13 tuần; thẻ cảnh báo; danh sách đòi nợ; nút thử kịch bản.
4. **Khi có sự kiện:** tin Zalo OA "Tuần 9/12: xác suất số dư âm 23%. Nguyên nhân: 3 hoá đơn khách A (trễ trung bình
   20 ngày gần đây). Gợi ý: gọi khách A trước ngày 25."
5. **Vòng phản hồi:** tiền về thực tế được so với dự báo; mô hình tự hiệu chỉnh theo khách.

## 4.5 Tiêu chí chấp nhận nghiệp vụ (UAT)

| # | Tiêu chí | Cách kiểm |
|---|---|---|
| A1 | Người dùng hiểu màn hình chính trong ≤30 giây (5/5 người thử nói đúng "tuần nguy hiểm") | Thử nghiệm người dùng |
| A2 | Mỗi cảnh báo có ≥1 lý do định lượng và ≥1 hành động gợi ý | Kiểm thử nội dung |
| A3 | Số dư đầu kỳ hệ thống = sao kê (sai lệch 0đ); công nợ khớp sổ trong dung sai 0,5% | Đối chiếu |
| A4 | Lịch thuế/BHXH/lương đúng 100% bộ ví dụ luật | `tests/test_t0_t5.py` |
| A5 | Không con số nào trong câu trả lời LLM khác số trong bảng tính toán | Kiểm thử đối chiếu tự động |
| A6 | Độ phủ khoảng 80% thực tế trong [75%, 85%] khi backtest | 03_Evaluation |
