# T0/T9: từ chứng từ tới công nợ quan sát

Điểm vào: [adaptive/data.py](../../agent1/adaptive/data.py), [ingest](../../agent1_service/ingest/), [workspace/reconciliation.py](../../agent1_service/workspace/reconciliation.py) và [ledger](../../agent1/reconciliation/ledger.py). Hợp đồng cột nằm ở [Data](../02_Data/01_chien_luoc_du_lieu.md); hướng dẫn chi tiết nằm ở [dịch vụ](../../agent1_service/README.md#luong-t0-t9-thong-nhat).

## T0: kiểm trước khi ghi

Nạp CSV/Excel/XML → chọn bảng/sheet → ghép cột và định dạng ngày/tiền → xem trước → xác nhận. Lỗi chặn cả lần lưu. Xem trước chưa đổi dữ liệu; dữ liệu đổi sau xem trước thì cần kiểm lại trước khi lưu.

Tiền VND là số nguyên chính xác. Dòng tổng, tiền lẻ VND, quan hệ hóa đơn–thanh toán sai hoặc phân bổ vượt nguồn bị chặn. XML có kiểm cấu trúc/an toàn và các trường kế toán; bảng đơn giản thiếu dữ liệu kế toán chỉ có mức kiểm tương ứng, không được dùng làm gốc điều chỉnh/thay thế đầy đủ.

Chứng từ kế toán giữ MST, ký hiệu/số, nguồn/dòng/hash và phiên bản. Thay thế/điều chỉnh/hủy kiểm chuỗi tham chiếu, không nhân đôi công nợ. Hủy/giảm nghĩa vụ không tạo khoản tiền nhận. Dữ liệu sửa giữ lịch sử theo `known_at`/availability; snapshot quá khứ chỉ lấy phiên bản được biết khi đó.

`payment_id` xác định khoản thanh toán: retry cùng mã/nội dung không cộng tiền. Nhiều khoản trả cho một hóa đơn có mã riêng; không suy mọi dòng cùng ngày/số tiền là trùng. Lịch sử nạp ghi thông tin đã có, không đoán tên tệp hoặc trạng thái của lần nạp cũ thiếu metadata.

## T9: đề xuất, quyết định và sổ phân bổ

```text
Bank chưa phân bổ + hóa đơn còn mở
             ↓
Tìm ứng viên và constrained allocation
             ↓
Đề xuất / cần xem xét / nhiều nghiệm
             ↓
Người dùng duyệt hoặc phân bổ thủ công có bằng chứng
             ↓
Commit quyết định + thanh toán nguyên tử → công nợ mới
```

Adapter Workspace dùng lõi constrained flow/ledger có provenance trong `agent1/reconciliation/_thang/`, với scorer/quan hệ dữ liệu của adapter. Quy tắc kiểm tiền, khách, chứng từ và phạm vi vẫn áp dụng khi có nghiệm duy nhất. Không ép FIFO để che mơ hồ. Không có bằng chứng phí/tỷ giá hợp lệ thì giữ chênh lệch chưa phân bổ.

| Thao tác | Hệ quả |
|---|---|
| Tìm đề xuất | Chưa đổi công nợ; `auto` chỉ mức đủ điều kiện đề xuất |
| Duyệt | Lưu người xử lý, bằng chứng và phân bổ; không vượt tiền bank hoặc dư nợ |
| Thủ công | Kiểm tiền/khách/phạm vi như đề xuất, cần nguồn/lý do |
| Từ chối | Giữ lịch sử/lý do, chưa tạo tiền thu |
| Đảo | Hoàn nguyên ảnh hưởng phân bổ; không xóa giao dịch bank hay lịch sử |

Mỗi giao dịch phân bổ cho một khách theo hợp đồng; một giao dịch có thể chia nhiều hóa đơn, một hóa đơn nhận nhiều khoản. Sửa T0 ảnh hưởng quyết định cũ phải kiểm lại, đảo/xử lý xung đột trước khi tiếp tục. Không tự mang write-off sang hóa đơn đổi phạm vi; chưa hỗ trợ mọi nghiệp vụ thu hồi sau write-off hoặc write-off từng phần.

## Hai đồng hồ và nhãn tiền

Ngày giá trị bank khác ngày quyết định đối soát được biết. Quyết định duyệt/đảo dùng ngày hiện tại theo Việt Nam, không cho backdate ngày biết; duyệt hôm nay không xuất hiện trong snapshot tháng trước. Khi demo sau duyệt, chọn cutoff từ ngày duyệt trở đi để thấy dư nợ mới.

`last_cash_date` là lần thu cuối; `closed_date` là ngày hết công nợ. Đóng bằng credit note/write-off không tự tạo `paid_date_est`. T1 chỉ nhận nhãn tất toán bằng tiền theo hợp đồng đã khóa và phạm vi quan sát; chưa đủ chứng từ không thành nhãn “không trả”.

Workspace có adapter T9 riêng; các API `/reconciliation/*` của research có cùng mục tiêu truy vết nhưng hợp đồng request khác. Tra endpoint Workspace trong [api.py](../../agent1_service/workspace/api.py), không copy lệnh từ benchmark cũ.

Bộ thực hành: [UAT core/lifecycle/large](../../pilot/t0_t9_uat_20261110/README.md). Fixture synthetic chứng minh hành vi của ca kiểm, chưa đo precision/recall trên mọi doanh nghiệp.
