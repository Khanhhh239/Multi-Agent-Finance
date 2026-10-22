# Đề xuất đổi hướng: dịch vụ rà soát định kỳ cho đơn vị kế toán

Soạn 2026-10-22 theo mục 7 của đăng ký v5. Đây là **phương án sản phẩm khi mô hình học máy chưa đạt cổng**, và cũng là con đường đưa sản phẩm vào dùng sớm nhất dù cổng đạt. Không quảng bá phát hiện gian lận tự động hay thu hồi tổn thất dựa trên dữ liệu tổng hợp.

## 1. Ý tưởng một câu
Bán cho **đơn vị dịch vụ kế toán** (không bán thẳng cho chủ doanh nghiệp siêu nhỏ) một công cụ rà soát định kỳ. Mỗi tuần công cụ đưa ra vài **câu hỏi đối chiếu có bằng chứng** cho từng khách, để kế toán viên hỏi lại khách. Phán đoán vẫn do con người.

## 2. Công việc kế toán được hỗ trợ (dựa trên phần đã có, không cần học máy)

| Công việc | Thành phần đã có | Chất lượng đã biết (dữ liệu tổng hợp) |
|---|---|---|
| Đối chiếu nhà cung cấp với nhân viên (trùng tài khoản, điện thoại, địa chỉ, người đại diện) | Luật B1, B2, B5, E3, E4, đồ thị quan hệ | Bắt chắc chắn khi có trùng; không bắt nhà cung cấp ma "sạch" |
| Thanh toán trùng, vượt hóa đơn, chia nhỏ né hạn mức | P1, A1 đến A6 | Bắt tốt `duplicate_payment`, `overbilling` (khoảng 83 đến 100%) |
| Lương sau nghỉ việc, lương không chấm công | E1, E2, đặc trưng v4 | Bắt tốt `terminated_still_paid` |
| Tạm ứng quá hạn, xóa nợ tạm ứng thiếu hồ sơ | T1, T2 | Bắt tốt `advance_unsettled` |
| Đổi tài khoản nhà cung cấp gần ngày chi | B7 | Trung bình |
| Bút toán tay sát khóa sổ | F1, F2 | Trung bình |
| Lệch so với chính thực thể (giá, lương, khách) | EntityDeviation, `EntityDeviation2` | Tín hiệu yếu, cần người đọc |

Mỗi câu hỏi kèm lý do tiếng Việt kiểm được số (`explain_v4.py`, `explain_v5.py`) và danh sách chứng từ cần xin.

## 3. Phần vẫn phải do con người
- Quyết định có hỏi khách hay không; hỏi ai; kết luận.
- Đối chiếu chứng từ gốc (hợp đồng, biên bản giao nhận, sao kê).
- Mọi việc liên quan đến cá nhân: không hệ thống nào kết luận một người gian lận.
- Báo cáo cho chủ doanh nghiệp.

## 4. Ngân sách cảnh báo và thời gian
- Tối đa 3 câu hỏi mỗi khách mỗi tuần (có thể đặt 1).
- Mục tiêu thời gian rà soát: không quá 30 phút mỗi khách mỗi tuần (giả định, phải đo).
- Một kế toán dịch vụ quản lý 20 khách sẽ có tối đa 60 câu hỏi mỗi tuần, nên cần lọc theo mức ưu tiên.

## 5. Phải đo trong thí điểm (không tự thay bằng số tổng hợp)

| Chỉ số | Cách đo | Ngưỡng tiếp tục |
|---|---|---|
| Tỷ lệ câu hỏi "đáng kiểm tra" | Kế toán viên đánh dấu | Từ 15% |
| Thời gian rà soát | Bấm giờ | Không quá 30 phút mỗi khách mỗi tuần |
| Phát hiện có giá trị (sai sót, vi phạm quy trình, nghi vấn) | Biên bản | Ít nhất 1 trên 2 khách sau 3 tháng |
| Sẵn lòng trả của đơn vị kế toán | Báo giá thử | Ít nhất 3 trên 5 đơn vị |
| Sự cố dữ liệu cá nhân | Rà soát | 0 sự cố nghiêm trọng |

Các ngưỡng này là **giả định**. Chỉ thí điểm sau khi có thẩm định pháp lý (Nghị định 13/2023/NĐ-CP, cùng Luật 91/2025/QH15 và Nghị định 356/2025/NĐ-CP mà hồ sơ pháp lý đã ghi cần cập nhật) và có thỏa thuận với doanh nghiệp.

## 6. Kinh tế
- Đơn vị kế toán thu phí dịch vụ của khách. Công cụ giúp họ bán thêm gói "rà soát kiểm soát nội bộ" (giả định 300 nghìn đến 1 triệu đồng mỗi khách mỗi tháng).
- Chi phí phía nhà cung cấp thấp vì không cần huấn luyện mô hình riêng; luật và kênh không nhãn chạy cục bộ.
- Hòa vốn bên cung cấp vẫn tính như tệp 07; phân phối qua đơn vị kế toán giảm chi phí bán hàng.

## 7. Đường nâng cấp
Nếu một vòng sau có mô hình có giám sát đạt cổng niêm phong độc lập, mô hình chỉ thêm **thứ tự ưu tiên** cho các câu hỏi. Giao diện và quy trình con người giữ nguyên, nên không phải đổi sản phẩm.

## 8. Mã và hiện vật dùng ngay
`sme_fraud/rules.py` (luật, đồ thị), `agent2/alerting.py` (ngân sách, gộp vụ), `agent2/explain_v4.py`, `agent2/explain_v5.py`, `agent2/service.py` (API cục bộ), `review_ui/` (hàng đợi, phản hồi), `agent2/schema.py` (kiểm tra đầu vào). Đã bổ sung ngày 2026-10-22: trang danh mục nhiều khách cho đơn vị kế toán (`/portfolio`, `review_ui/portfolio.html`, chỉ đọc), đo chỉ số thí điểm K1, K2, K3, K5 từ kho rà soát (`scripts/pilot_kpis.py`, chỉ đọc, phân theo mức ưu tiên và họ tín hiệu), quan sát biến động v5 trong lý do tuần (`agent2/change_ops.py`, chỉ thêm lời giải thích). Hướng dẫn cho người rà soát: `docs/05_ke_hoach_giao_viec/huong_dan_ke_toan_vien.md`.

Còn thiếu: bộ nhận dữ liệu từ phần mềm kế toán thật (chủ dự án xác nhận ngày 2026-10-16 là chưa có tệp mẫu; xem `docs/05_ke_hoach_giao_viec/adapters.md`).
