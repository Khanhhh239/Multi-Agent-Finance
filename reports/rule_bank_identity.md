# Thống nhất định danh tài khoản — R2, 16/10/2026

**R2 đã sửa kỹ thuật:** A1/A2, lịch sử người nhận, B7/callback và các feature tài khoản dùng chung định danh **ngân hàng + số TK**. Hai ca audit khác ngân hàng cùng số TK đã đạt; **268/268 test hồi quy đạt**, gồm 21 test mới. Không thay ngưỡng, trọng số hoặc chính sách thiếu hồ sơ nghĩa vụ chi.

## Định danh và phạm vi đối chiếu

Helper [`bank_identity`](../sme_fraud/temporal_evidence.py) được đặt trong module bằng chứng dùng chung để feature và B7 sử dụng mà không tạo import vòng. `spec_policy.bank_identity` tiếp tục xuất cùng helper cho B1, đồ thị, nghĩa vụ chi và kiểm tra lô; không có bản chuẩn hóa ngân hàng riêng cho A1/A2.

Chuẩn hóa thống nhất hoa/thường, bỏ dấu phân cách/khoảng trắng và giữ số 0 đầu. Định danh chứa mã ngân hàng có phân định chiều dài, nên không nối nhầm giữa phần mã và phần số. Đây là chuẩn hóa khóa, chưa phải xác minh ngân hàng/tài khoản với nguồn bên ngoài.

| Trường hợp | Hành vi hiện tại |
| --- | --- |
| Cùng số TK, khác ngân hàng | A1/A2 không cộng lịch sử; B7 không ghép sự kiện/callback của ngân hàng khác |
| Cùng ngân hàng + TK, khác cách trình bày | Ghép đúng sau chuẩn hóa; cảnh báo chia nhỏ vẫn giữ khi thiếu hồ sơ chi hợp lệ |
| Thiếu mã ngân hàng ở tài khoản thực | A1/A2 ghi `information_gap`, 0 điểm, không gộp lịch sử; B7 ghi gap nếu số TK khớp nhưng thiếu mã ở nguồn/giao dịch, không hard trigger và không công nhận callback |
| Khác số TK | Không coi là cùng tài khoản, kể cả bỏ riêng số 0 đầu có vẻ giống số học |
| Namespace `BANK_SYN_*` duy nhất của generator | Giữ hỗ trợ khi thiếu mã ngân hàng để tương thích mô phỏng; không dùng ngoại lệ này cho tài khoản thực |

Không suy ngân hàng từ master NCC hiện tại. Khi định danh người nhận đã đủ, thiếu hợp đồng/PO/yêu cầu chi vẫn giữ cảnh báo theo chính sách hiện hành. Ngoại lệ chi có chứng từ vẫn qua các kiểm tra phạm vi và tổng tiền đã có. A3 dựa trên liên kết mạnh độc lập vẫn hoạt động khi mã ngân hàng người nhận chưa rõ; P1 tiền mặt/định danh hóa đơn tiếp tục qua hồi quy.

## Nguồn đổi tài khoản và callback

Nguồn bổ sung `new_bank_code`, tùy khả năng cung cấp `old_bank_code`; giao dịch dùng `recipient_bank_code`. [Header và hướng dẫn nhập](../examples/bank_identity_sources/README.md).

`(company_id, change_id)` gắn bất biến với NCC, TK/ngân hàng cũ–mới và `effective_at`. Revision callback/thu hồi giữ binding và có `observed_at` riêng. Đổi binding phải dùng ID mới; kể cả việc bổ sung mã ngân hàng cho ID trước đó chưa có mã cũng cần ID/bằng chứng phù hợp, tránh mang xác minh cũ sang định danh mới. Revision cùng định danh sau chuẩn hóa không bị từ chối chỉ do khác cách trình bày. Xung đột binding bị từ chối kể cả ở revision tương lai.

`bank_change_evidence` kiểm tra công ty/NCC và ngân hàng + TK trước khi xác minh callback. Hit B7 chứa hai định danh đã đối chiếu, mã ngân hàng nguồn/giao dịch, trạng thái bằng chứng, trường thiếu và binding của callback nếu đã xác minh. Feature `bank_changed_recently`/`bank_change_verified` dùng cùng phép đối chiếu; tài khoản chưa xác nhận không trở thành feature đã đổi/đã xác minh.

Quy tắc chọn nguồn vẫn là thay đổi có hiệu lực mới nhất đã quan sát của mỗi NCC. Hợp đồng hiện tại chưa mở rộng sang nhiều tài khoản đang có hiệu lực đồng thời cho một NCC.

## Feature và dữ liệu dẫn xuất

Đã sửa khóa lịch sử cho `recipient_count_3d`, `recipient_sum_limit_3d`, `creator_recipients_7d`; các trường trùng TK nhân viên `employee_bank_overlap`, `recipient_employee_bank_count`, `payable_to_employee_bank` cũng dùng cùng ngân hàng + TK. Snapshot nhân viên đổi TK/ngân hàng loại số đếm của định danh cũ trước khi thêm định danh mới, tránh một nhân viên tiếp tục bị đếm ở TK cũ.

Cạnh `bank_account` trong feature đồ thị dùng `bank_identity(target_id, bank_code)`; thiếu ngân hàng thực không ghép cạnh chỉ vì cùng chuỗi số. Bản R2 không viết lại thuật toán lịch sử/thu hồi các cạnh feature ngoài phạm vi đối chiếu tài khoản.

Tên/thứ tự cột feature giữ nguyên nhưng ngữ nghĩa tài khoản đã đổi. Cần tạo dataset dẫn xuất mới và dựng lại cache bằng `python -B -m sme_fraud.rebuild_features --data <dataset_moi>`, rồi kiểm tra/chấm lại model trước khi dùng cùng feature mới. Không tự sửa snapshot, cache hoặc model lịch sử trong lần sửa R2 này.

## Kiểm chứng và giới hạn

**268/268 test đạt**, 47,721 giây, không failure/error: [log](../.runtime/bank_identity_20261016/tests.log), [kết quả/hash](../.runtime/bank_identity_20261016/result.json). [21 test mới](../tests/test_bank_identity_controls.py) bao phủ A1/A2, cùng/khác ngân hàng, chuẩn hóa/số 0 đầu, thiếu mã/no master inference, cách ly lịch sử chưa xác nhận, A3 độc lập, B7 và callback, binding revision, phạm vi công ty/NCC, feature nhân sự/lịch sử/đồ thị và nguồn tương lai.

```powershell
python -B -m unittest discover -s tests
```

Chạy lại **bản sao** 7 probe readiness để giữ nguyên artifact trước sửa: **2 ca R2 đạt**, **5 ca R6/R7/R8 chưa đạt**, 0 lỗi chạy test. [Quan sát từng ca](../.runtime/bank_identity_20261016/observations.json), [log probe](../.runtime/bank_identity_20261016/readiness_probes.log). Các probe chưa đạt nằm ngoài bộ hồi quy 268 test và tiếp tục là việc mở; không diễn giải 268 test đạt thành toàn lớp luật đã sẵn sàng.

R8 sau đó đã sửa [lịch sử người ký E1/B7 và các helper liên quan](rule_signer_history.md); R7 đã có [kiểm định scalar/cờ cấp ngoại lệ](rule_exception_validation.md); R6 đã có [định danh và migration hồ sơ](rule_case_identity.md). Đúng định danh tài khoản không tự chứng minh callback đã hợp lệ về mọi mặt. Chưa chấm lại benchmark lớn, huấn luyện ML hoặc nghiệm thu nguồn SME thật. Tích hợp và nghiệm thu vận hành tiếp tục được theo dõi tại [readiness](rule_readiness_recheck_20261016.md).
