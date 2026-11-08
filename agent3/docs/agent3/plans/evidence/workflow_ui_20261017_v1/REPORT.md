# UI theo quy trình — 17/10/2026

Đợt này tổ chức lại giao diện đối chiếu thành bốn bước: **Dữ liệu hóa đơn → Hồ sơ bổ sung → Kiểm tra thuế → Diễn giải**. Thuộc nhánh hoàn thiện UI hiện có của PLAN_06/09/12; chưa nghiệm thu PLAN_14 hoặc phê duyệt rule pháp lý.

## Cách sử dụng

1. Khởi động lại web bằng `STOP_AGENT3.cmd` rồi `OPEN_AGENT3.cmd` trong terminal đã đặt `AGENT3_EXPLANATION_POLICY` nếu muốn dùng Qwen. Nhấn Ctrl+F5 trên trình duyệt để tải asset mới.
2. Bấm **Tải hóa đơn** ở sidebar hoặc chọn chứng từ đã xử lý. Ô tìm kiếm chỉ lọc danh sách đã tải; dùng **Xem thêm** để tải tiếp.
3. **Dữ liệu hóa đơn:** đối chiếu trường với nguồn, sửa/xác nhận rồi lưu. Bảng hàng dùng **Chi tiết** để mở trạng thái và nút xem nguồn của từng dòng. Nút nguồn trên màn hình nhỏ chuyển sang tab hóa đơn gốc.
4. **Hồ sơ bổ sung:** ghi phần có căn cứ, đính kèm tài liệu và lưu xác nhận. Phần chưa đủ căn cứ để chưa xác định. Chuyển bước giữ bản nháp; đổi chứng từ/phiên bản vẫn tuân theo các guard cũ.
5. **Kiểm tra thuế:** bấm **Kiểm tra bản đã lưu**, xem phạm vi, lý do cần review, nguồn/trace và xuất kết quả. Bản nháp chưa lưu chặn chạy kiểm tra như trước.
6. **Diễn giải:** tạo diễn giải cho đúng kết quả đã lưu. Chưa có kết quả sẽ có nút quay về bước kiểm tra. Lỗi timeout/model/định dạng được hiển thị cụ thể, giữ diễn giải mẫu. Nút lịch sử luôn mở phần dữ liệu chứa lịch sử.

## Thay đổi và giới hạn

- Hóa đơn gốc luôn ở cạnh bước đang xử lý trên desktop. Tablet/mobile dùng tab nguồn và dữ liệu; không ép hai cột quá hẹp.
- Điều hướng, bộ lọc và các panel dùng lại form/handler hiện có; không tạo bản sao state hoặc endpoint nghiệp vụ mới. API chỉ thêm whitelist cho hai asset workflow.
- Thông tin bản nháp và trường chưa xác nhận hiển thị ở đầu workspace. Chuyển bước không xác nhận trường, không tự chạy thuế và không ghi dữ liệu.
- Tìm kiếm xử lý Unicode NFC và render văn bản an toàn. ID dòng hàng, Decimal, chứng cứ, revision, idempotency và tenant scope được giữ bởi backend hiện có.
- Bảng hàng vẫn có cuộn ngang trong khung; chưa thêm/tách/gộp dòng. Tìm kiếm chưa phải tìm toàn bộ cơ sở dữ liệu. Chưa có dashboard quản trị mới.
- Rule thật vẫn DRAFT, danh mục sản phẩm chưa được duyệt. Kiểm thử diễn giải dùng model giả lập; không chứng minh tốc độ hoặc accuracy của Qwen thật.

## Kiểm chứng

**428/428 Python tests, 30 nhóm Chrome checks, 5 JavaScript syntax checks và 2 client harness checks PASS.** Sau chỉnh riêng CSS về chiều cao workspace desktop, cả bốn bộ browser được chạy lại; mã Python/backend không đổi. Hash asset cuối nằm trong báo cáo JSON.

Chạy từ root bằng `.\agent3_tax_compliance\.venv\Scripts\python.exe scripts/validate_workflow_ui.py`.

Kết quả đầy đủ, số lượng test, hash asset và từng nhóm browser nằm trong [validation_summary.json](validation_summary.json). Bốn bài browser chạy Chrome thật với server HTTP và DB fixture tạm, không dùng/chỉnh DB demo của người dùng:

- [Workflow](browser_workflow.json): bước, bản nháp, tìm kiếm, bảng hàng, lịch sử và các kích thước 1024/768/390 px.
- [Hồ sơ nghiệp vụ](browser_business.json): đính kèm, lưu/mở lại, xung đột và đổi revision.
- [Kiểm tra thuế](browser_compliance.json): engine ZEN fixture, nguồn, xuất, guard và chạy lại.
- [Diễn giải](browser_explanation.json): template, model giả lập, nguồn, bản nháp và reset revision.

Ảnh chụp chứa fixture nằm local tại `agent3_tax_compliance/data/workflow_ui/browser/`; không đưa DB, access token, model weights hoặc cấu hình local lên Git.
