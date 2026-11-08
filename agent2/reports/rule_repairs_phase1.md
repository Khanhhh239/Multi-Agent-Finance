# Hoàn thành sửa đợt 1: B7, E1, A2

Đã sửa ba lỗi thời gian/ngoại lệ được tái hiện trong Rule Audit. [Kết quả chấm lại và so sánh baseline](rule_repairs/phase1/summary_vi.md) dùng cùng dữ liệu và ngưỡng cũ. [Audit trước sửa](rule_audit/summary_vi.md) được giữ làm mốc lịch sử.

## B7 — giữ thay đổi đang chờ hiệu lực

`BankChangeHistory` được dùng chung trong engine và `build_features`. Sự kiện được giữ sau `observed_at`, kể cả chưa tới `effective_at`. Khi chấm, hệ thống lấy phiên bản đã biết của từng `change_id`, sau đó chọn thay đổi có hiệu lực gần nhất của đúng công ty/NCC. Một thay đổi mới còn chờ hiệu lực hoặc một sự kiện cũ được quan sát muộn không che thay đổi đang có hiệu lực.

Rule chỉ xét giao dịch nhận vào đúng TK mới trong 14 ngày tính theo giây. Callback chỉ được dùng làm ngoại lệ khi thời điểm xác minh đã qua, người xác minh đã biết, cùng công ty và khác người lập lệnh chi. Bản sửa bổ sung `observed_at` vào bằng chứng; không tăng hạn thời gian hoặc thay trọng số/ngưỡng.

Các dòng sửa/callback/hủy của một thay đổi phải giữ cùng `change_id` và có `observed_at` mới. Trạng thái `cancelled`/`revoked` không được coi là thay đổi có hiệu lực. Hai phiên bản mâu thuẫn cùng ID và thời điểm quan sát bị từ chối. Timestamp phải cùng chuẩn ISO UTC+7 của dataset.

## E1 — quyền chi nghỉ hưởng lương có bằng chứng

E1 vẫn yêu cầu **đã có chấm công cho đúng kỳ** và quan sát 0 ngày; thiếu hoặc chưa quan sát chấm công không được coi là 0 ngày để hard trigger. Bằng chứng làm việc từ xa vẫn là ngoại lệ riêng.

Ngoại lệ nghỉ hưởng lương đọc nguồn tùy chọn `payroll_entitlements`. Một bản ghi phải cùng công ty/nhân viên/kỳ, loại `paid_leave`, được duyệt và có tài liệu dẫn chiếu; người duyệt phải đã biết trước phê duyệt. Số ngày nghỉ hưởng lương phải phủ đủ ngày làm việc yêu cầu của kỳ, và số tiền đang chi không vượt quyền chi đã duyệt. Nhân viên có hợp đồng trong hồ sơ đã biết; không cho nhân viên tự cấp quyền hưởng lương của mình.

Khi đủ điều kiện, E1 lưu hit đã loại với 0 điểm, `hard_trigger=0` và bản ghi quyền chi trong evidence. Nếu chỉ có `approved_leave_days=22` hoặc chuỗi loại nghỉ, hệ thống **không tự cấp ngoại lệ**. Quyền chi phải đến từ nguồn HR/payroll tin cậy đã đối chiếu hồ sơ, không phải dữ liệu do người lập lệnh tự khai.

Schema nguồn `payroll_entitlements.csv`:

| Cột | Ý nghĩa |
| --- | --- |
| `entitlement_id` | ID quyết định quyền chi ổn định qua các phiên bản |
| `company_id`, `employee_id`, `payroll_period` | Đúng đơn vị, nhân viên và kỳ `YYYY-MM` |
| `leave_type`, `status` | `paid_leave`, `approved`; bản hủy dùng cùng ID và `revoked` |
| `required_work_days` | Số ngày làm việc phải giải trình trong kỳ, lớn hơn 0 |
| `approved_paid_leave_days` | Ngày nghỉ hưởng lương được duyệt, đủ phủ kỳ; không suy từ chấm công |
| `entitled_amount_vnd` | Trần số tiền được phép chi cho quyết định/kỳ này, VND nguyên |
| `evidence_on_file`, `evidence_id` | Cờ có hồ sơ và mã tài liệu để truy vết |
| `approver_id`, `approved_at`, `observed_at` | Người duyệt và thời điểm; phê duyệt ≤ quan sát ≤ chấm điểm |

Đây là ngoại lệ cho kỳ không có ngày công và được nghỉ hưởng lương phủ đủ kỳ. Chưa suy luận toàn bộ lịch nghỉ từng ngày, lương truy lĩnh, quyết toán nghỉ việc hoặc mọi cách tính lương. Không dùng bảng này để tuyên bố C4/E2 đã được triển khai.

## A2 — ngoại lệ đúng cửa sổ 30 ngày

Ngoại lệ hóa đơn được kiểm tra trên **nhóm các đợt của hóa đơn hiện tại trong cửa sổ A2**, không lấy kết quả từ cửa sổ A1. Nhóm này phải có ít nhất một khoản trước đó của cùng người lập/người nhận, cùng NCC/số hóa đơn không trống, có hồ sơ đã biết và gross nhất quán. Tổng tiền đã chi cho hóa đơn trên toàn lịch sử, gồm khoản ngoài 30 ngày hoặc người lập khác, không được vượt gross.

Khoản của hóa đơn khác xen vào không làm mất ngoại lệ trả góp của hóa đơn hiện tại, đồng thời không được gọi là một đợt trả góp của hóa đơn này. Evidence lưu riêng `installment_window_ids` và `other_window_ids`. Nếu giao dịch hiện tại thuộc một hóa đơn độc lập chưa có các đợt trả trước/hợp đồng được duyệt, nó không được hưởng ngoại lệ từ các hóa đơn khác trong cụm.

Hóa đơn độc lập hoặc việc chỉ cùng `project_id`/`contract_id` không tự cấp ngoại lệ. Nếu dùng trả góp theo hợp đồng, cần nguồn tùy chọn `supplier_payment_agreements` đã duyệt/as-of và các giao dịch cùng `contract_id`. Tổng toàn lịch sử phải nằm trong trần hợp đồng; kiểm tra gross hóa đơn vẫn được giữ và P1 không bị loại bởi ngoại lệ A2.

Schema `supplier_payment_agreements.csv`:

| Cột | Ý nghĩa |
| --- | --- |
| `agreement_id` | ID thỏa thuận trả góp, ổn định qua phiên bản cập nhật/hủy |
| `company_id`, `vendor_id`, `contract_id` | Đúng công ty/NCC/hợp đồng; transaction có `contract_id` tương ứng |
| `total_vnd` | Tổng được phép chi theo thỏa thuận/hợp đồng |
| `status` | `approved` để áp dụng; bản hủy dùng cùng ID và trạng thái mới |
| `evidence_on_file`, `evidence_id` | Hồ sơ hợp đồng/lịch thanh toán và mã chứng từ |
| `approver_id`, `approved_at`, `observed_at` | Người duyệt đã biết, phê duyệt và quan sát trước chấm điểm |

`support_doc_count` của các giao dịch phải lớn hơn 0; nếu cung cấp `support_docs_observed_at`, ngày này không được sau thời điểm chấm. Ngoại lệ dựa vào nguồn chứng từ, chưa xác minh nội dung hóa đơn/hợp đồng với bên thứ ba. A1/A3 và các mẫu mua độc lập ngoài phạm vi này vẫn cần tối ưu ở bước sau.

## Tích hợp nguồn và cache

Hai bảng mới là tùy chọn. Dataset v2 hiện tại không có chúng và được đọc bình thường với bảng rỗng. Khi nhập CSV vào một dataset có manifest, phải thêm entry `files[filename].sha256` của chính file; loader từ chối nguồn tùy chọn không có checksum hoặc bị thay đổi. Mã nhận tables trực tiếp cũng dùng đúng tên bảng và schema trên.

Tài liệu/hồ sơ thực được truy vết bằng `evidence_id`; `evidence_on_file=1` không tự chứng minh nội dung đúng. Các loại dữ liệu và quyền hạn từ nguồn phải được kiểm tra trước khi nhập.

Dataset, nhãn, cache `features.csv` và model cũ được giữ nguyên. Hai feature B7 có cùng tên nhưng đã được sửa ngữ nghĩa as-of/độc lập với người lập trong mã tạo feature mới. Lượt chấm lại dùng cache còn hợp lệ cho các tín hiệu khác; B7 đọc nguồn đổi TK bằng selector mới, E1 đọc quyền chi trực tiếp. Trước benchmark ML tiếp theo cần tạo lại feature/cache theo mã hiện tại và kiểm tra phiên bản model.

## Kiểm chứng

Đã chạy **66 kiểm thử** toàn dự án: 42 có sẵn và 24 kiểm thử hồi quy mới, tất cả qua. Các kiểm thử mới có nhiều nhánh: chờ hiệu lực, phiên bản callback, dữ liệu tương lai, biên 14 ngày, nghỉ hưởng lương, quyền chi sai kỳ/thiếu chứng từ/vượt tiền, hủy quyền chi, thiếu chấm công, trả góp 7 ngày, hóa đơn khác xen kẽ, hợp đồng đã duyệt, gross thay đổi và tổng ngoài cửa sổ.

51 fixture audit sau sửa khớp 46 trường hợp; ba tình huống A2/B7/E1 đã được xử lý. Fixture E1 được bổ sung quyền chi HR rõ ràng, đáp ứng yêu cầu nguồn bằng chứng mới. Năm trường hợp còn lệch thuộc A3/A4/A5/B1/B3, nằm ở các bước tiếp theo.

Chấm lại ba bộ gốc kiểm tra checksum đầu-cuối, tập hit các rule ngoài phạm vi, bằng chứng thời gian, replay tổng điểm và đối soát thành viên hàng đợi. Không điều chỉnh ngưỡng theo nhãn test; không chạy ML. D1–D6 giữ chẩn đoán baseline vì dữ liệu đầu vào và logic D không đổi.

```powershell
python -m unittest discover -s tests -v
python -m sme_fraud.run_rule_repairs --output reports/rule_repairs/phase1_new
```

Để xem hàng đợi mới trong UI:

```powershell
python -m sme_fraud.review_server --reports-root reports/rule_repairs/phase1 --database .runtime/review/phase1.sqlite3 --port 8766
```

Sau đó mở `http://127.0.0.1:8766`. UI dùng snapshot mới ở lệnh này; cổng 8765 và phản hồi của snapshot cũ không được tự chuyển trong đợt sửa luật.
