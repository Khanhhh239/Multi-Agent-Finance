# Định danh ngân hàng và nguồn đổi TK — R2

Khóa tài khoản là **mã ngân hàng + số tài khoản** sau chuẩn hóa. Chuẩn hóa giữ số 0 đầu, bỏ khoảng trắng/dấu phân cách và thống nhất hoa/thường; không xác minh mã ngân hàng với danh mục tổ chức bên ngoài.

| Nguồn | Cột định danh cần cung cấp |
| --- | --- |
| Giao dịch | `recipient_account`, `recipient_bank_code` |
| NCC/nhân sự | `bank_account`, `bank_code` |
| Cạnh ngân hàng `entity_links` | `target_id` là số TK, `bank_code` là ngân hàng, `link_type=bank_account` |
| Sự kiện đổi TK | `old_account`, `old_bank_code`, `new_account`, `new_bank_code` |

[Header đổi TK](bank_account_changes.csv) bổ sung hai mã ngân hàng. `old_bank_code` có thể trống nếu nguồn lịch sử chưa cung cấp; `new_bank_code` cần có để đối chiếu tài khoản thực. Khi thiếu mã ngân hàng đích hoặc mã trên giao dịch, số TK giống nhau chưa chứng minh cùng người nhận: B7 ghi `information_gap`, 0 điểm/không hard trigger và không công nhận callback. A1/A2 cũng không gộp lịch sử TK chưa xác nhận; không suy mã từ master NCC hiện tại.

Namespace tài khoản `BANK_SYN_*` do generator bảo đảm duy nhất vẫn hoạt động khi thiếu mã ngân hàng để tương thích dữ liệu mô phỏng. Ngoại lệ namespace này không dành cho tài khoản thực.

Mỗi `(company_id, change_id)` gắn bất biến với NCC, cặp tài khoản/ngân hàng cũ–mới và `effective_at`. Callback/thu hồi giữ binding, dùng `observed_at` mới. Thay binding hoặc bổ sung mã ngân hàng vào ID từng chưa có mã cần ID nguồn mới và bằng chứng xác minh đúng binding mới; không mang callback cũ sang tài khoản/ngân hàng khác. Engine từ chối revision đổi binding, kể cả khi nằm trong tương lai; khác cách trình bày cùng định danh sau chuẩn hóa vẫn được chấp nhận.

`callback_verified`, thời gian và người xác minh vẫn phải tuân thủ hợp đồng nguồn hiện hành. [R8 đã bổ sung lịch sử người ký](../../reports/rule_signer_history.md): cần giữ các snapshot nhân sự với ID ổn định và `recorded_at` để tra người xác minh tại `verified_at`. Kiểm định scalar R7 còn mở; không coi đúng định danh tài khoản là đã đủ bằng chứng callback.

Sau khi đổi mã, tạo bản sao dataset mới và sinh lại `features.csv` bằng `python -B -m sme_fraud.rebuild_features --data <dataset_moi>`; công cụ cập nhật manifest và data dictionary của bản đó. Tên/cột feature giữ nguyên nhưng ý nghĩa đối chiếu tài khoản đã chặt hơn; không dùng lại cache/model đã học feature cũ mà chưa kiểm tra tương thích và chấm lại. Giữ nguyên snapshot/manifest lịch sử để đối chiếu.

[Chi tiết kiểm chứng và giới hạn](../../reports/rule_bank_identity.md).
