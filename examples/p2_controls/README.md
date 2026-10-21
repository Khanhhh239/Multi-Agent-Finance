# Bộ đối chứng P2 riêng

**Đã có giao diện web nghiệm thu:** đủ 32 tình huống/73 giao dịch, xem cả dòng không phát sinh P2, chứng từ và kỳ vọng; lưu kết quả nghiệm thu riêng. [Lệnh mở và cách dùng](../p2_controls_web/README.md).

Nguồn hoàn chỉnh: [data/p2_controls_20261018_v2](../../data/p2_controls_20261018_v2/manifest.json). [Báo cáo kết quả](../../reports/p2_controls_20261018.md).

32 tình huống, 73 giao dịch, chia thành sáu nhóm:

| Nhóm | Số tình huống | Nội dung |
| --- | ---: | --- |
| Hóa đơn đầy đủ | 6 | Dưới/đúng/trên mốc đối chiếu, mốc lịch sử và thanh toán ngân hàng |
| Thiếu chứng từ | 5 | Thiếu toàn bộ, ngày, tổng tiền, định danh, hóa đơn có sau lúc chi |
| Trả nhiều đợt | 5 | Hóa đơn lớn/khoản chi nhỏ, hóa đơn nhỏ, ngân hàng + tiền mặt, cùng thời điểm, thiếu ngày hóa đơn |
| Hoàn/đảo | 6 | Hoàn đủ/một phần/nhiều lần, hoàn ngân hàng, đảo sổ, dòng thu chưa nối chứng từ gốc |
| Định kỳ | 5 | Khoản nhỏ, trả ngân hàng, tiền mặt cần đối chiếu, hợp đồng thiếu hóa đơn, ngoại lệ A5 có lịch sử |
| Hạn mức nội bộ | 5 | Xác minh hợp lệ, chưa xác minh, xác minh tương lai, hết hiệu lực, ngoại tệ chưa quy đổi |

`control_index.json` mô tả tình huống; `expected_outcomes.json` là kỳ vọng đã khai báo trước khi chấm. Mỗi thư mục tình huống có `tables.json`, `rule_config.json` và CSV giao dịch/hóa đơn/sổ kế toán/liên kết tương ứng. `tables.json` chỉ có nguồn nghiệp vụ, không chứa nhãn kỳ vọng. Các ID giao dịch lặp lại giữa tình huống vì mỗi tình huống được chạy độc lập; dùng khóa `(control_id, transaction_id)` khi tổng hợp.

Hoàn tiền dùng số tiền dương và chiều Nợ tiền/Có chi phí, có liên kết với chứng từ gốc khi nguồn đã biết. Mẫu `cash_refund` là mẫu sổ tổng hợp riêng của bộ đối chứng; không mở rộng danh sách cặp tài khoản của bộ dữ liệu 001/003. Khoản thu chưa nối nguồn gốc không được coi là chi tiền mới, đồng thời không được chứng nhận là nghiệp vụ hợp lệ. Bộ này không triển khai tự bù trừ VAT hoặc tự đóng hồ sơ của khoản chi gốc sau khi hoàn tiền.

Khoản định kỳ đã duyệt không tự miễn P2. Nhánh `RECUR_A5` có 22 giao dịch lịch sử và một khoản định kỳ có bằng chứng để kiểm ngoại lệ A5; các mẫu tiền mặt cần đối chiếu P2 vẫn giữ 8 điểm hoặc yêu cầu bổ sung đúng dữ kiện.

Để tạo nguồn mới và chấm vào output riêng, chạy tại thư mục dự án:

```powershell
python -B -m sme_fraud.run_p2_controls --data-output data/p2_controls_repeat --output reports/p2_controls_repeat
```

Để chấm lại đúng nguồn đã khóa mà không tạo/sửa dữ liệu:

```powershell
python -B -m sme_fraud.run_p2_controls --prepared data/p2_controls_20261018_v2 --output reports/p2_controls_replay
```

Output phải trống; runner từ chối nạp hoặc ghi vào các root nguồn/báo cáo 001/003/005 đã khóa. Manifest chứa SHA256 của nguồn và kỳ vọng. Detector chỉ nhận bảng nguồn và cấu hình; kết quả/hàng đợi được khóa hash trước khi nối kỳ vọng. Không fit model hoặc gửi thông báo trong quy trình này.

Đây là bộ đối chứng xác định để kiểm tra logic và chống hồi quy; kết quả khớp kỳ vọng không phải precision/recall gian lận trên SME thật.
