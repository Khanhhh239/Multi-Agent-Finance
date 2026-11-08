# Quyền rà hồ sơ và chốt kết luận

Chính sách `accountant-review-final-approval-v1` được chốt theo yêu cầu ngày 24/10/2026:

| Vai trò | Quyền |
|---|---|
| `accountant` — Kế toán viên | Gửi kết quả rà lần đầu, cập nhật yêu cầu tài liệu trong công ty được cấp |
| `chief_accountant` — Kế toán trưởng | Kiểm tra, chốt hoặc trả lại kết quả của một người khác |
| `director` — Giám đốc | Kiểm tra, chốt hoặc trả lại kết quả của một người khác |

Kế toán trưởng **hoặc** giám đốc chốt là đủ; không bắt cả hai cùng duyệt. Cả ba vai trò có thể ghi chú UAT trong phạm vi được cấp. Thay ngân sách/xem trước thông báo toàn không gian cần vai trò kế toán trưởng/giám đốc và đủ phạm vi các công ty trong không gian.

## Trạng thái hiện tại

Đã có quyền và luồng hai cấp; **chưa tạo tài khoản và chưa có luồng đăng nhập** theo lựa chọn của người dùng. Bản mô phỏng vẫn xem được; các thao tác ghi cần danh tính từ máy chủ. Không cung cấp danh sách chọn vai trò để tự nâng quyền.

`TwoStageReview(store)` bật chính sách cho đúng SQLite đã liên kết với snapshot. `make_server` tự nạp lại chính sách đã bật khi khởi động lại, hoặc có thể khởi tạo mới bằng `--two-stage-review`. API feedback cũ và CLI ghi kết luận trực tiếp không bỏ qua được bước kiểm tra cuối trên kho đã bật chính sách.

## Nối với đăng nhập sau này

`identity_provider` là hàm phía máy chủ, được gọi sau khi cơ chế đăng nhập của bạn xác thực phiên làm việc. Hàm trả về `ReviewPrincipal` hoặc `None`; không tạo principal từ trường role/user_id do trình duyệt gửi lên.

```python
from sme_fraud.review_roles import ReviewPrincipal
from sme_fraud.review_workflow import TwoStageReview
from sme_fraud.review_server import make_server

def identity_provider(request):
    account = your_login.validate_session(request)
    if account is None:
        return None
    return ReviewPrincipal(
        user_id=account.user_id,
        person_id=account.person_id,  # cùng một người giữ cùng ID dù đổi tài khoản
        display_name=account.display_name,
        role=account.role,
        company_ids=tuple(account.allowed_company_ids),
    )

server = make_server(store, review_workflow=TwoStageReview(store),
                     identity_provider=identity_provider)
```

`your_login` là phần đăng nhập sẽ được triển khai sau, không phải module đã có. Phiên làm việc, mật khẩu, thu hồi tài khoản và quyền đọc dữ liệu thật thuộc bước tích hợp đó. Bản hiện tại tiếp tục là ứng dụng mô phỏng cục bộ có chế độ xem khi chưa đăng nhập.

## Luồng API

- `POST /api/review-workflow/primary`: chỉ kế toán viên; ghi đề xuất và phút rà thực tế, hồ sơ chờ kiểm tra cuối.
- `POST /api/review-workflow/finalize`: kế toán trưởng hoặc giám đốc khác người rà; có thể sửa đề xuất kèm lý do. Bước này mới ghi vào nhật ký kết luận hiện có.
- `POST /api/review-workflow/return`: trả lại kèm lý do và công kiểm tra thực tế; cần kế toán viên gửi lại trước khi chốt.

Payload gồm `scenario`, `case_id`, `decision`, `reason`, `missing_evidence`, `active_minutes`, `timing_method="measured_stopwatch"`, `expected_event_hash`, `expected_scope_hash`. Hai hash lấy từ `review_workflow` trong phản hồi `/api/case`. Không gửi tên người thực hiện hoặc vai trò: máy chủ lấy từ principal. Không dùng thời gian ước lượng; khi cần bổ sung phải ghi rõ phần thiếu.

Các sự kiện ghi nối tiếp và có chuỗi hash. Thay bằng chứng/phạm vi không kế thừa bước rà cũ. Cổng yêu cầu tài liệu đang mở vẫn được giữ. Backup/restore giữ cả chính sách và nhật ký hai cấp. Chuỗi hash là kiểm tra tính liên tục, không phải chữ ký số.

## Rà độc lập ML

Phân quyền không tự xác nhận tính độc lập hoặc tạo kết quả rà. Gói mù ML có thể dùng `role_policy` cùng phiên bản ở file phân công; `people` ghi người thật và vai trò từ tài khoản đã cấp, `units` có thể phân công riêng từng phiếu. Kế toán viên là người rà; kế toán trưởng/giám đốc khác người là người chốt. Các xác nhận độc lập/mù, lý do, chứng từ và phút thực tế vẫn phải đủ. Không lấy kết luận từ màn hình có điểm rules/IF để tự ký là đánh giá mù.
