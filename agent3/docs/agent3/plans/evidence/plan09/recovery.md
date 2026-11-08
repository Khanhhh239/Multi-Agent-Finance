# Phục hồi PLAN_09

- **Mạng lỗi sau POST:** gửi lại cùng Idempotency-Key và body. Yêu cầu đã hoàn tất trả cùng report, không chạy lại stage đã commit.
- **Quality/planning lỗi trước khi pin request:** chưa có public evaluation ID; sửa nguyên nhân rồi gửi lại cùng key/body. Các stage artifacts đã commit được dedupe bởi repository của từng stage.
- **FAILED sau khi pin request (execution/template/audit):** xem GET evaluation hoặc lịch sử revision; dùng POST `/evaluations/{id}/resume`. Snapshot/package/template/record revision cũ được giữ; không tự chuyển sang versions mới.
- **Worker hoặc tiến trình dừng đột ngột:** chờ lease 120 giây hết hạn rồi resume. Execution attempts đã commit được giữ; unit terminal không chạy lại. Callback heartbeat gia hạn lease ở mỗi attempt; worker bị thay lease không được commit report.
- **EXECUTION_RUNNING / EVALUATION_RUNNING (409):** một worker còn giữ lease. Làm mới và chờ, không sửa token/lease/raw rows bằng tay. Resume có thể phải chờ lease của execution bên trong, dù workflow ngoài đã FAILED.
- **Revision conflict:** tải bản mới, đối chiếu và tạo yêu cầu mới với key mới. Report cũ vẫn đúng với revision được pin; `is_current_revision=false` chỉ là trạng thái hiện tại bên ngoài report immutable.
- **Rule timeout:** engine giữ ERROR và attempt history, không thành tax REVIEW/PASS. Retry tự động hữu hạn theo PLAN_08; report đã terminal không được sửa. Điều tra nguyên nhân và phát hành policy/package/version mới có kiểm soát khi cần execution mới.
- **Model/legal/taxonomy chưa duyệt hoặc ngoài lịch support:** bổ sung/rà căn cứ và publish package/snapshot mới qua quy trình nghiệp vụ. Không đổi confidence, bỏ blocker hoặc mặc định latest để vượt gate.
- **Contract error:** verdict null; template chỉ mô tả lỗi xử lý. Capture export vẫn dùng được. Replay yêu cầu pinned implementation; nâng code không ghi đè bằng chứng cũ để ép replay qua.
- **Rollback ứng dụng/DB:** dừng server/worker, giữ bản DB v9 và khôi phục backup tương thích với code trước đó. Không tự hạ `user_version` hoặc xóa tables để giả downgrade.

Hiện API chạy đồng bộ cho phạm vi MVP, không có scheduler compliance tự phục hồi nền hoặc tự chạy khi upload. UI có nút kiểm tra/resume; PLAN_14 cần kiểm tải, tổng ngân sách job và vận hành production.
