# Bộ đối chứng P2 trên web — 18/10/2026

> Tài liệu tham chiếu theo mốc ghi trong tiêu đề. Xem [trạng thái hiện tại](../../STATUS.md) trước khi dùng số liệu hoặc kế hoạch cũ.

Đã thêm màn hình nghiệm thu riêng cho đủ **32 tình huống / 73 giao dịch** từ bộ nguồn và dự đoán đã khóa. Truy cập **http://127.0.0.1:8767/p2-controls** khi dịch vụ đang chạy; [lệnh mở lại và cách dùng](../../../examples/p2_controls_web/README.md).

## Phạm vi giao diện

- Sáu nhóm: hóa đơn đầy đủ, thiếu chứng từ, trả nhiều đợt, hoàn/đảo, định kỳ và hạn mức nội bộ. Bộ lọc nhóm, kết quả P2, trạng thái nghiệm thu và tìm kiếm.
- Hiển thị mọi giao dịch, gồm **43 dòng không phát sinh P2**, **14 yêu cầu bổ sung 0 điểm**, **15 dòng đối chiếu 8 điểm**, **1 dòng vượt hạn mức đã xác minh 14 điểm**. Không biến dòng không có P2 thành hồ sơ cảnh báo.
- Chi tiết số tiền theo đồng tiền nguồn, Nợ/Có, hóa đơn, hạn mức, bằng chứng, trường còn thiếu và hướng xử lý. Ngoại tệ chưa xác minh không được trình bày như tiền VND đã xác minh.
- Sổ kế toán và tổng Nợ/Có, hóa đơn, liên kết hoàn/đảo, thỏa thuận định kỳ; giữ nguyên P2 của khoản chi gốc khi dòng hoàn không phát sinh P2.
- Hàng đợi thực tế và phần kỳ vọng có thể mở ra để đối chiếu theo từng giao dịch, gồm điểm, tuyến xử lý, mức ưu tiên và ngoại lệ A5.
- Kết quả **Đạt / Cần sửa / Cần bổ sung** theo tình huống, bắt buộc người nghiệm thu và lý do; lịch sử giữ qua khởi động lại, chống ghi đè khi có kết quả mới; xuất CSV theo bộ lọc.

Các mã giao dịch lặp lại được phân biệt bằng tình huống. Kết quả nghiệm thu được lưu riêng với phiên bản nguồn/dự đoán; không dùng làm kết luận gian lận, nhãn huấn luyện hoặc phản hồi trên hồ sơ vận hành 001/003.

## Cách chạy

```powershell
& 'C:\Users\Technical Support\AppData\Local\Programs\Python\Python312\python.exe' -B -m sme_fraud.p2_controls_server --port 8767
```

Database người dùng: `.runtime/p2_controls_web/reviews.sqlite3`. Phần thử nghiệm tự động dùng database khác; màn hình người dùng bắt đầu với **0/32** tình huống đã nghiệm thu.

Có thể gắn module vào ứng dụng cũ bằng cờ `--p2-controls` của `sme_fraud.review_server`; menu **Đối chứng P2** chỉ hiện khi module được bật. [Hướng dẫn đầy đủ](../../../examples/p2_controls_web/README.md).

## Kiểm chứng

- **585/585 kiểm thử Python đạt**; **34/34 kiểm thử trọng tâm đạt**. Bao gồm khóa theo tình huống, bản ghi không có P2, khoản hoàn, ghi đồng thời, dữ liệu bị sửa, nguồn/database bất biến, API, CSRF/origin và tích hợp cùng Case Management.
- Kiểm tra HTTP toàn bộ **32/32 tình huống, 73/73 giao dịch**: đối chiếu kỳ vọng, **78 chứng từ / 165 dòng sổ cân đối**, lọc/xuất cả sáu nhóm, lưu 32 nghiệm thu tự động, đọc lại sau khởi động và từ chối 32 lần ghi bằng trạng thái cũ.
- **10 kiểm tra JavaScript đạt**, dựng đủ bốn tab cho 32 tình huống và chi tiết 73 giao dịch. Kiểm tra giá trị hóa đơn đầy đủ/thiếu, ngoại tệ, hoàn tiền, định kỳ, escape nội dung, trường bắt buộc, bộ lọc và menu module.
- **1.209 tệp nguồn/kết quả được đối chiếu hash và giữ nguyên**, gồm nguồn 001/003/005, bộ đối chứng P2 và các kết quả đã khóa. 005 chỉ được băm tệp, không nạp/chấm/đọc oracle. Luồng web không fit model, không gửi thông báo.
- Trình duyệt được thử qua công cụ computer-use: IAB và Chrome đều báo `Browser is not available`, danh sách browser rỗng. **Chưa nghiệm thu trực quan bằng trình duyệt**; các kiểm tra JavaScript không thay thế bước đó. Bạn có thể mở địa chỉ trên để thực hiện nghiệm thu giao diện.
- Các nghiệm thu mang tên `SIM_P2_WEB_AUTOMATED` chỉ nằm trong database kiểm thử; **người kế toán độc lập nghiệm thu = 0**. Tỷ lệ khớp kỳ vọng không phải precision/recall gian lận.

[Kết quả hồi quy](../../../.runtime/p2_controls_web_20261018/full.json) · [Kiểm tra trọng tâm](../../../.runtime/p2_controls_web_20261018/focused.json) · [Luồng HTTP](../../../.runtime/p2_controls_web_20261018/flow_checks.json) · [Hiển thị JavaScript](../../../.runtime/p2_controls_web_20261018/ui_checks.json).

## Mã cần đọc

1. [p2_controls_web.py](../../../sme_fraud/p2_controls_web.py): xác minh nguồn/kết quả, khóa tình huống và journal nghiệm thu.
2. [p2_controls_server.py](../../../sme_fraud/p2_controls_server.py): dịch vụ localhost, API, CSV và route dùng chung với Case Management.
3. [p2_controls.js](../../../review_ui/p2_controls.js), [HTML](../../../review_ui/p2_controls.html), [CSS](../../../review_ui/p2_controls.css): danh sách và bốn tab chi tiết.
4. [test_p2_controls_web.py](../../../tests/test_p2_controls_web.py): kiểm chứng trạng thái, biên API và tích hợp.
