# 2. Problem Statement

## 2.1 Phát biểu một câu

> Chủ doanh nghiệp nhỏ và kế toán kiêm nhiệm ở Việt Nam **không biết trước 4–13 tuần** tuần nào công ty sẽ thiếu tiền,
> với xác suất bao nhiêu và vì sao, vì dòng thu phụ thuộc hành vi trả tiền không chắc chắn, tương quan và một phần nằm
> ngoài sổ sách; hệ quả là vay nóng, trễ lương/thuế/nhà cung cấp, giữ tiền nhàn rỗi quá mức hoặc phá sản dù có lãi.

## 2.2 Phát biểu chuẩn (5W2H)

| Mục | Nội dung |
|---|---|
| **Ai** | SME Việt Nam bán B2B có công nợ (sản xuất, bán buôn, dịch vụ B2B), 10–200 lao động, doanh thu 5–300 tỷ/năm; người dùng là chủ DN, kế toán trưởng/kế toán kiêm nhiệm; người hưởng lợi gián tiếp là ngân hàng/đơn vị cho vay |
| **Cái gì** | Dự báo phân phối số dư tiền mặt theo tuần cho 13 tuần tới, xác suất thiếu hụt, nguyên nhân, hành động khuyến nghị và kịch bản "nếu như" |
| **Khi nào** | Cập nhật mỗi đêm/tuần; cảnh báo ngay khi xác suất thiếu hụt vượt ngưỡng hoặc hành vi khách đổi |
| **Ở đâu** | Trên dữ liệu doanh nghiệp đã có: hoá đơn điện tử (XML theo NĐ 123/2020), sổ kế toán, sao kê ngân hàng; kênh cảnh báo Zalo OA / ứng dụng |
| **Vì sao** | Bảng tính giả định trả đúng hạn, bỏ qua tương quan và nợ xấu; dữ liệu sổ sai ngày do ghi theo lô; thông tin lời hứa trả nằm ngoài hệ thống |
| **Như thế nào** | Mô hình hoá từng hoá đơn (khi nào/có trả/trả bao nhiêu) + chi tất định theo luật + doanh thu mới, tổng hợp bằng mô phỏng có sốc chung, hiệu chỉnh khoảng, giải thích bằng ngôn ngữ tự nhiên (LLM chỉ diễn giải số đã tính) |
| **Bao nhiêu** | Mục tiêu: độ phủ khoảng 80% trong ±5 điểm; cảnh báo trước ≥4 tuần cho ≥70% sự kiện thiếu hụt; sai số dòng thu 4 tuần thấp hơn mốc ≥30% (chi tiết 03_Evaluation) |

## 2.3 Các câu hỏi nghiệp vụ phải trả lời được (N1–N7, Phần 7)

| Mã | Câu hỏi của người dùng | Đầu ra sản phẩm |
|---|---|---|
| N1 | "4–13 tuần tới có tuần nào tiền xuống dưới mức an toàn? Xác suất?" | Dải P10/P50/P90 số dư theo tuần + P(thiếu hụt) |
| N2 | "Khoản nào sẽ trễ, đòi khoản nào trước hiệu quả nhất?" | Danh sách hoá đơn xếp theo mức giảm P(thiếu hụt) nếu thu sớm |
| N3 | "Khách nào có thể không trả, giá trị đang rủi ro?" | P(nợ xấu) theo hoá đơn/khách, tổn thất kỳ vọng, đề xuất dự phòng theo TT48 |
| N4 | "Nếu khách lớn trả chậm 2 tuần / tôi hoãn một khoản chi?" | Kịch bản "nếu như" chạy lại mô phỏng |
| N5 | "Vì sao tuần đó bị cảnh báo?" | Lý do (đóng góp đặc trưng, khoản thu lớn bị trễ, khoản chi lớn) |
| N6 | "Số dư, công nợ hệ thống dùng có khớp sổ của tôi?" | Đối chiếu sổ – sao kê, cổng chất lượng dữ liệu |
| N7 | "Khách đang chậm hơn thường lệ — có chuyện gì?" | Cảnh báo điểm gãy hành vi theo khách / toàn danh mục |

## 2.4 Giả thuyết giá trị (phải kiểm chứng ở T13)

- **H1 (độ chính xác)**: Dự báo dòng thu theo hành vi từng khách chính xác hơn giả định đúng hạn và trung vị trễ ≥30%.
- **H2 (cảnh báo sớm)**: Cảnh báo thiếu hụt trước ≥4 tuần giúp DN hành động rẻ hơn (vay kế hoạch thay vì vay nóng).
- **H3 (vốn lưu động)**: Danh sách "đòi khoản nào trước" giảm DSO hành vi ≥3 ngày trong 6 tháng.
- **H4 (niềm tin)**: Dải xác suất kèm lý do được chủ DN dùng lại hằng tuần (tỷ lệ quay lại ≥60%).
- **H5 (chi phí dữ liệu)**: Không cần nhập tay: hoá đơn điện tử + sao kê đủ để chạy (≥90% hoá đơn khớp tự động).

## 2.5 Điều sản phẩm KHÔNG hứa

- Không dự báo được thiên nga đen; thay vào đó **phát hiện nhanh + suy biến có kiểm soát + biết trước sức chịu đựng**
  (kịch bản căng thẳng). Định vị: *radar cảnh báo sớm, không phải quả cầu pha lê*.
- Không thay thế quyết định tín dụng của ngân hàng, không là tư vấn đầu tư.
- Không tự sinh số bằng LLM; mọi con số đến từ lớp mô hình định lượng có kiểm định.
