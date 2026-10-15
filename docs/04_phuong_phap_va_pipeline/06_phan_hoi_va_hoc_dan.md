# Phản hồi, học dần và độ trôi

## 1. Vì sao không huấn luyện có giám sát riêng cho từng công ty
Với 3 cảnh báo mỗi tuần, một năm chỉ có khoảng 156 phản hồi, trong đó gian lận thật rất ít (Phần 8 [N]). Nhãn quá thưa để học hàng trăm tham số. Giải pháp: hiệu chỉnh ở **mức loại tín hiệu** (vài chục tham số), và dùng mô hình chung huấn luyện sẵn.

## 2. Thiết kế vòng phản hồi
Dựa trên Active Anomaly Discovery (Das và cộng sự, ICDM 2016) [T]: học lại trọng số kết hợp các tín hiệu từ phản hồi, với ngân sách xem hữu hạn. **Phần đã cài:** mô phỏng 52 tuần với học lại trọng số, nhiễu nhãn và hard trigger không hạ cấp (`agent2/feedback_sim.py`, `sme_fraud/feedback.py`). **Phần mới là thiết kế [N], chưa cài:** các bước 2 và 3 dưới đây ở dạng hoàn chỉnh trong đường ống thật.

1. Người rà soát ghi kết luận cho mỗi vụ: `hợp lệ`, `nghi vấn`, `xác nhận`.
2. Cập nhật trọng số luật và bộ phát hiện bằng hồi quy logistic có chính quy hóa quanh tiên nghiệm (như CES) trên các kết luận.
3. Ước lượng tỷ lệ báo sai theo loại tín hiệu bằng Beta–Binomial với tiên nghiệm lấy từ thế giới tổng hợp (Phần 8 [N]).
4. **Hard trigger không bao giờ bị hạ cấp bởi phản hồi** (`test_hard_triggers_not_demoted_in_feedback`).
5. Nhật ký kiểm toán chỉ ghi thêm (`sme_fraud/feedback.py`), có khóa tệp.

## 3. Kết quả mô phỏng [M] (52 tuần, 5 seed; `feedback_sim.py`)

| Chiến lược | Số dòng gian lận tìm được | Khi nhiễu nhãn tăng 0 → 15 → 30% |
|---|---:|---|
| Không học | 58 | 58 |
| Nới ngưỡng khi bị từ chối | 58 → 52 → 48 | Nhiễu làm hỏng |
| Học lại trọng số kiểu AAD | 83 → 79 → 54 | Nhạy với nhãn sai nhưng vẫn hơn nới ngưỡng khi nhiễu thấp |

**Hạn chế.** Mô phỏng giả định phản hồi đúng khi 0% nhiễu; người thật sai theo kiểu hệ thống (tin người quen). Bậc 2 của thiết kế: yêu cầu hai người xác nhận với kết luận "xác nhận" (chưa làm).

## 4. Độ trôi
- Người gian lận thay đổi cách làm; chính sách 2+1 giữ một khe không học.
- Giám sát: tỷ lệ cảnh báo "đáng kiểm tra" theo tháng; hạng điểm trung vị của cảnh báo; khoảng cách phân phối của từng đặc trưng so với huấn luyện (PSI).
- Chưa làm: thử nghiệm huấn luyện 6 tháng và kiểm thử từng tháng; huấn luyện lại định kỳ (H16).

## 5. Khi nào cập nhật mô hình huấn luyện sẵn
Mỗi khi (a) có bản dữ liệu tổng hợp mới hoặc kịch bản mới, (b) kết quả thí điểm cho thấy hệ số suy giảm khác nhiều với giả định, (c) luật hoặc chuẩn kế toán thay đổi. Mô hình có phiên bản và băm; nhật ký ghi phiên bản cho mỗi cảnh báo.

## 6. Ba nguyên tắc an toàn khi học
1. Không bao giờ để phản hồi từ một công ty thay đổi cách chấm công ty khác (cách ly).
2. Nhãn "hợp lệ" chỉ hạ điểm loại tín hiệu **đó** trong **công ty đó**, không hạ toàn bộ.
3. Ghi lại ai đã đánh dấu gì; mọi thay đổi trọng số có thể truy vết và đảo.
