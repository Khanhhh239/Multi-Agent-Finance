# Sửa bằng chứng UI và đối chứng P2 — 19/10/2026

Đã triển khai RR01–RR03, bổ sung phần hiển thị thời điểm và hoàn/đảo P2 theo yêu cầu tiếp theo. RR09 được ghi thành phiếu chờ quyết định riêng. Không thay detector, trọng số, ngưỡng, hàng đợi hoặc nguồn đã khóa.

Web P2 đang phục vụ bản sửa tại [localhost:8767/p2-controls](http://127.0.0.1:8767/p2-controls). Nếu đã mở bản cũ, tải lại trang để nhận JavaScript/CSS mới. Kiểm tra HTTP xác nhận ba asset hiện hành khớp nội dung trên đĩa; chưa nghiệm thu trực quan browser.

**Kết quả theo hạng mục**

| Hạng mục | Thay đổi | Bằng chứng / giới hạn |
|---|---|---|
| RR01 | Hàm định dạng xử lý null trước số tiền/đối tượng; thẻ A4 theo tháng hiển thị kỳ tháng và số lần, bỏ cửa sổ ngày không áp dụng | `RC_d3c7009ff2ea6dbf`: trước có TypeError; sau dựng được `2024-01`, 3 lần, không biến null thành 0 ngày |
| RR02 — C4 | Hiện nhân viên, hành động/thời điểm, kỳ nghỉ, tham chiếu và thời điểm biết nguồn; hiện quyền làm việc nếu có | Đối chiếu được E0000418, hành động 09/04/2025 và kỳ nghỉ 08–10/04/2025; kiểm cả C4 của hồ sơ thiếu mẫu A5 |
| RR02 — E2 | Hiện sự kiện lao động, ngày hiệu lực, loại chi, kỳ phục vụ và hai nguồn phê duyệt/được biết | Đối chiếu được chấm dứt 06/09/2025, lương thường kỳ, kỳ phục vụ 07/09–26/10/2025 của E0000388 |
| RR02 — F1 | Hiện mã nhật ký nhập sổ, lịch khóa sổ, chính sách trọng yếu, thời điểm và nguồn tương ứng; làm tròn khoảng ngày để dễ đọc | Xem được AUD_37c5b8d37a9d83b4a3, CLOSE_4e3e579f42934ef64e, MAT_79219e8e57f93abe93; hiển thị 3,64 ngày |
| RR03 | Tab giao dịch, chứng từ và hóa đơn giữ nhãn chưa xác minh VND; số nguồn ngoại tệ không gắn ký hiệu ₫ hoặc được gọi là số nguyên tệ đã xác nhận | `LIMIT_FOREIGN` vẫn P2 0 điểm; các chứng từ VND thông thường vẫn hiển thị VND |
| P2 — thời điểm (phần UI RR04) | Đặt mốc chi cạnh ngày phát hành, mốc ghi nhận hóa đơn, xác minh và hiệu lực hạn mức; giải thích tài liệu phát sinh sau và ranh giới hết hiệu lực | FUTURE_INVOICE, LIMIT_FUTURE/EXPIRED có cảnh báo rõ; không lấy cấu hình xác minh muộn để chấm ngược quá khứ |
| P2 — trả nhiều đợt (phần UI RR04) | Nêu chênh lệch giữa mốc ghi nhận hóa đơn nguồn và snapshot giao dịch trước đó | INSTALL_CASH/MIXED yêu cầu lịch sử phiên bản; chưa sửa nguồn hoặc kết luận detector dùng dữ liệu tương lai |
| P2 — hoàn/đảo (phần UI RR06) | Hiện chi gốc, hoàn/đảo liên quan, số chênh lệch theo nguồn và hồ sơ gốc; có nút quay về giao dịch gốc | Hoàn toàn phần/hoàn một phần vẫn giữ hồ sơ gốc 8 điểm trong snapshot. Đảo journal ghi rõ chưa chứng minh nhận lại tiền thực |
| P2 — trạng thái nghiệm thu | Tách “đã có ghi chú UAT” khỏi nghiệm thu kế toán độc lập; chuẩn bị phiếu đủ 32 tình huống | Chưa có biên bản độc lập được xác minh; không coi reviewer trợ lý hoặc kết quả tự động là chữ ký kế toán |
| RR09 | Lập phiếu có dữ kiện vượt 1 VND, phương án thảo luận và trường phê duyệt còn trống | Vẫn giữ 14 điểm/ưu tiên cao theo cấu hình hiện tại; chưa chọn phương án, dung sai hoặc ngày hiệu lực mới |

Các phần hiển thị lấy từ bằng chứng đã lưu và nguồn của đúng tình huống/công ty. Không truy vấn master hiện tại để bổ sung ngược vào quá khứ. Thông tin cấu hình hạn mức biết sau chỉ được hiển thị trong ngữ cảnh đối chiếu và ghi rõ chưa dùng tại lúc chi.

Mốc ghi nhận hóa đơn trong nguồn mô phỏng trả nhiều đợt đang phản ánh bản cập nhật sau. UI làm rõ giới hạn này; thiết kế first-observed/last-updated hoặc nguồn có lịch sử phiên bản vẫn là việc riêng cần phiên bản dữ liệu mới. Không sửa snapshot cũ.

Số chi trừ hoàn chỉ là đối chiếu các dòng tiền theo nguồn cùng đơn vị VND; không phải quyết định điều kiện VAT, không tự đóng/xóa hit gốc. Với journal, UI giải thích là đảo sổ dù liên kết cũ mang tên cash_return_of; giá trị liên kết nguồn được giữ nguyên.

**Tài liệu có thể rà lại**

- [Bản đối chiếu HTML trước/sau](ui_evidence_repairs_20261019/before_after.html): 5 thẻ A4/C4/E2/F1 và 9 tình huống P2. HTML lấy trực tiếp từ renderer, không phải ảnh chụp browser; các nút trong bản xuất chỉ minh họa.
- [Payload thẻ trước/sau](ui_evidence_repairs_20261019/cards_before_after.json) và [các tab P2 trước/sau](ui_evidence_repairs_20261019/p2_before_after.json).
- [Phiếu nghiệm thu kế toán độc lập P2](ui_evidence_repairs_20261019/p2_independent_acceptance.md): 32 tình huống/73 giao dịch, để trống người rà/kết quả/chữ ký.
- [Phiếu quyết định RR09](ui_evidence_repairs_20261019/rr09_policy_decision.md): chờ chủ kiểm soát quyết định, không phải chính sách đã được phê duyệt.
- [Tổng hợp kiểm chứng và hash code](ui_evidence_repairs_20261019/verification.json), [bảo toàn dữ liệu](ui_evidence_repairs_20261019/preservation.json).

**Kiểm chứng**

- 19 kiểm tra JavaScript đạt: payload thật đã lỗi, C4 có/không có quyền, E2 thiếu nguồn, F1 và nguồn lịch sử, escape HTML, đơn vị ngoại tệ, thời điểm chứng từ, hoàn/đảo và nút quay lại khoản gốc. Dựng đủ 32 tình huống, 73 giao dịch và 78 chứng từ, không làm biến đổi payload.
- 27 kiểm thử Python liên quan đạt, không lỗi/bỏ qua: hồ sơ, luồng P2, API Sprint 1.4 và P2 web. Database thử riêng; không ghi kết luận vào journal người dùng. [Kết quả](../.runtime/ui_evidence_repairs_20261019/backend_final.json).
- 1.209 tệp nguồn/kết quả giữ nguyên hash; 005 chỉ băm tệp, không nạp/chấm. Không gửi Email/Zalo.
- JavaScript được thực thi bằng Node runtime tích hợp/VM với DOM tối thiểu. Có thể chạy bộ hồi quy bằng `node tests/review_evidence_ui.test.js` trong môi trường có Node trên PATH. Đây không thay thế kiểm tra bố cục và thao tác trên browser thật.

Các lượt test đang chạy bị ngắt ở ranh giới phiên trước không được tính là đạt; số 27 ở trên lấy từ lượt cuối đã kết thúc thành công. Không chạy lại toàn bộ benchmark/ML vì thay đổi chỉ ở UI.

Mã thay đổi chính: [app.js](../review_ui/app.js), [p2_controls.js](../review_ui/p2_controls.js), [p2_controls.html](../review_ui/p2_controls.html), [p2_controls.css](../review_ui/p2_controls.css). Kiểm thử hồi quy: [review_evidence_ui.test.js](../tests/review_evidence_ui.test.js).

**Còn chờ**

Browser không có surface kết nối; thử tạo tab IAB trả `Browser is not available`. Chưa nghiệm thu trực quan. Kế toán độc lập chưa rà/ký phiếu và chủ kiểm soát chưa chốt RR09. Các kết quả trợ lý, khớp kỳ vọng mô phỏng hoặc test kỹ thuật không thay thế những bước đó; cũng không chứng minh chất lượng trên SME thật.
