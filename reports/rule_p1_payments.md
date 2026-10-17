# Sửa P1 — hóa đơn thiếu số và thanh toán tiền mặt

Ngày kiểm tra: 16/10/2026. Đã sửa hai phát hiện R1 trong [báo cáo readiness](rule_readiness_recheck_20261016.md). Ngưỡng, trọng số P1 và cơ chế commit sau batch giữ nguyên.

## Hành vi sau sửa

- P1 kiểm tra các khoản `vendor_payment` tài chính qua tiền mặt hoặc ngân hàng, kể cả khi không có tài khoản nhận.
- Khóa cộng tiền cần đủ công ty, NCC và số hóa đơn không rỗng sau chuẩn hóa. Không lưu lịch sử thanh toán vào khóa hóa đơn rỗng.
- Nếu có gross nhưng thiếu định danh, P1 ghi `evidence_status=information_gap`, vai trò `context`, **0 điểm, không hard trigger**. Các dòng này không bị tự coi là cùng hóa đơn.
- Tiền mặt và chuyển khoản cùng hóa đơn dùng chung tổng đã trả trên toàn lịch sử quan sát, kể cả khoản ngoài cửa sổ A1/A2.
- Vẫn gom cùng số hóa đơn chuẩn hóa khi có nhiều mã hóa đơn ERP khác nhau; không dùng `invoice_id` làm khóa thay thế cho số hóa đơn thiếu.
- Trả góp chưa vượt tổng hóa đơn vẫn không kích hoạt P1. Các công ty/NCC khác nhau không dùng chung hạn mức hóa đơn.

Ví dụ: hai lần trả tiền mặt 9 triệu cho hóa đơn 9 triệu, không có tài khoản nhận, hiện tạo P1 ở lần thứ hai với tổng đã trả 18 triệu, vượt 9 triệu, **20 điểm và hard trigger**. Hai khoản riêng có số hóa đơn rỗng chỉ tạo chẩn đoán thiếu dữ kiện, không tạo cảnh báo cứng P1.

## Mã và kiểm thử

[Helper khóa thanh toán hóa đơn](../sme_fraud/rules.py#L102) được dùng chung khi truy vấn và ghi lịch sử. Kiểm tra P1 đã tách khỏi khối kiểm tra theo tài khoản nhận; dữ liệu không phải khoản chi tài chính tiền mặt/ngân hàng không tiêu thụ tổng hóa đơn này.

[7 test mới](../tests/test_p1_payments.py) bao phủ:

1. Số hóa đơn rỗng, khoảng trắng hoặc chỉ dấu phân cách, ở cả policy legacy và phase4.
2. Trả trùng tiền mặt không có TK nhận, cách nhau 45 ngày.
3. Chuyển đổi tiền mặt → ngân hàng và ngân hàng → tiền mặt.
4. Trả góp tiền mặt đúng tổng hóa đơn.
5. Hai NCC có cùng số hóa đơn nhưng nghĩa vụ độc lập.
6. Nhiều mã ERP nhưng cùng số hóa đơn chuẩn hóa.
7. Thêm khoản trả tương lai không đổi điểm/hit của khoản trước.

Chạy toàn bộ: **198/198 test đạt**, không failure/error, gồm 191 test cũ và 7 test mới. Các đối chứng trả góp, nguồn bằng chứng, tính nhân quả và chính sách giao dịch cùng timestamp tiếp tục đạt. [Kết quả máy đọc](../.runtime/p1_repair_20261016/result.json).

```powershell
python -B -m unittest discover -s tests -v
```

## Phạm vi còn lại

Hai vấn đề R1 đã được sửa ở mức mã và kiểm thử. Chưa chấm lại benchmark lớn hoặc nghiệm thu nguồn SME thật. Các mục chưa hoàn thành xem trạng thái mới nhất trong [báo cáo readiness](rule_readiness_recheck_20261016.md). R4 đã có [kiểm tra tổng lô riêng](rule_batch_close.md), giữ nguyên điểm/hit từng dòng của bản sửa R1.

Khóa hóa đơn tiếp tục dùng công ty–NCC–số hóa đơn chuẩn hóa theo hợp đồng dữ liệu hiện có. Khi số hóa đơn lặp giữa nhiều ký hiệu/năm hoặc nguồn có định danh nghĩa vụ khác, cần mở rộng và đối soát khóa chuẩn trước khi nhập; bản sửa này không suy ra chúng từ mã ERP.
