# State machine — capture/review v1

Ngày: 13/10/2026. Validator: `src/jobs/state.py`; repository/worker: `src/jobs/service.py`. Đường xử lý tốn thời gian chạy trong worker hữu hạn, ngoài HTTP request.

| Từ | Đến | Điều kiện |
|---|---|---|
| QUEUED | PREPARING | Claim bằng transaction, cấp lease token, tăng attempts |
| PREPARING | EXTRACTING | Reader đã commit Document/PNG và hash |
| EXTRACTING | ASSESSING | OCR/normalized result và extraction artifact đã commit |
| ASSESSING | REVIEW | Quality và task builder chạy xong; chưa hoàn tất nhập liệu |
| REVIEW | COMPLETED | Người dùng gọi complete; kiểm tra lại head dưới lock, không còn task đang mở/chờ dữ liệu/operator hoặc issue ngoài INFO |
| PREPARING / EXTRACTING / ASSESSING | PROCESSING_ERROR | Lỗi được ghi bằng code; không lưu exception chứa nội dung chứng từ |
| PROCESSING_ERROR | QUEUED | RETRY có lý do, lỗi retryable, chưa hết attempts |
| PROCESSING_ERROR | WAITING_DATA / OPERATOR | Yêu cầu nguồn mới hoặc chuyển người vận hành |
| REVIEW | WAITING_DATA / OPERATOR | Nguồn hoặc segmentation cần xử lý riêng; API recover chấp nhận hai hành động này |
| WAITING_DATA | OPERATOR | Cần người vận hành; nguồn thay thế đi qua upload mới |
| QUEUED | WAITING_DATA / OPERATOR | Nhánh vận hành được validator cho phép; không tự hoàn tất |

COMPLETED và OPERATOR là trạng thái kết thúc của lượt xử lý hiện tại. Không tự chuyển lỗi sang COMPLETED. Retry thất bại tới giới hạn mặc định 3 attempts sẽ chuyển OPERATOR. Reader/OCR vẫn có giới hạn subprocess riêng. Capture lease bao phủ ngân sách reader + số trang tối đa × ngân sách OCR + margin; worker mất lease không được ghi trạng thái hoàn tất. Worker sau phát hiện lease hết hạn đưa job về PROCESSING_ERROR; phải có recovery rõ ràng rồi mới claim lại.

OCR lỗi lưu bất biến. Retry capture tạo OCR config version/key mới theo job/attempt thay vì xóa hoặc sửa kết quả cũ. Lỗi nguồn không retryable chỉ còn REQUEST_DATA/OPERATOR; thay nguồn phải upload bằng key mới. Không tự sửa file gốc để tiếp tục. `REQUEST_DATA` và `OPERATOR` là bàn giao có trạng thái/audit; chưa tích hợp gửi thông báo, nhận file thay thế hoặc tự tách hóa đơn.

Review task dùng trạng thái riêng: OPEN → WAITING_DATA/OPERATOR theo hành động có lý do; REOPEN trở về OPEN nếu vẫn là head revision. Correction tạo revision mới, task cũ được RESOLVED khi issue tương ứng biến mất, còn lại SUPERSEDED; task mới có `previous_ids`. Task đã RESOLVED/SUPERSEDED hoặc thuộc revision cũ không được sửa head.

COMPLETED chỉ xác nhận lượt nhập liệu đã được kiểm tra thủ công trong phạm vi profile. Quality vẫn giữ `review_required=true` và policy auto-accept tắt; không có kết luận thuế.
