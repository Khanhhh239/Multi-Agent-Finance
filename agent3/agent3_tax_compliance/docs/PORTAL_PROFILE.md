# Hồ sơ doanh nghiệp do portal quản lý

Agent 3 sử dụng doanh nghiệp hiện tại trong hồ sơ chung của portal. Không còn chế độ tạo/chọn doanh nghiệp riêng, kể cả khi mở trực tiếp cổng 8640.

## Khởi động sau khi cập nhật

1. Dừng phiên portal và Agent 3 cũ. Nếu Agent 3 được chạy bằng terminal riêng, dừng cả tiến trình đó.
2. Khởi động lại portal theo hướng dẫn của dự án, rồi bật Agent 3 từ portal.
3. Hoàn tất hồ sơ chung ở `#config`. Hồ sơ đồng bộ khi Agent 3 khởi động và khi lưu hồ sơ tại portal.

Portal cấp đường dẫn hồ sơ chung, URL portal local và khóa kết nối ngẫu nhiên qua môi trường tiến trình Agent 3. Khóa chỉ dùng giữa hai backend, không cần điền mật khẩu quản trị để đồng bộ hồ sơ. Khi khởi động lại portal, cần khởi động lại Agent 3 để nhận khóa mới. Các thiết lập thuế, danh mục và kho luật vẫn giữ khóa quản trị hiện có.

Nếu Agent 3 đã chạy từ phiên cũ, cầu nối mới sẽ báo lỗi cho đến khi khởi động lại đúng cách. Không đưa khóa vào cấu hình frontend, URL hay localStorage.

## Dữ liệu và tương thích

- Hồ sơ chung gồm tên, MST, địa chỉ, ngành nghề, phương pháp GTGT, kỳ khai và tháng kết thúc năm tài chính. UI Agent 3 hiển thị chỉ đọc, dẫn về portal để chỉnh sửa.
- “Thiết lập nghiệp vụ thuế” gồm 5 bước, sửa cấu hình của doanh nghiệp hiện tại: quy định chi tiêu, ngưỡng, nhóm hàng, ngày nghỉ và xác nhận.
- Đồng bộ chỉ thay `profile` của `pack.json`, giữ cấu hình nội bộ, hóa đơn, quyết định và lịch sử. Đồng bộ giống nhau không thêm lịch sử trùng. Báo cáo cũ được đánh dấu cần phân tích lại qua digest đầu vào hiện có.
- Workspace cũ có cùng MST được tái sử dụng tại chỗ; dấu gạch trong MST chi nhánh được chuẩn hóa để đối chiếu. Không đổi tên hoặc gom các thư mục cũ. Nhiều workspace cùng MST hoặc trùng workspace mô phỏng sẽ bị chặn để kiểm tra thủ công, không tự nhận làm dữ liệu thật.
- Đổi MST tạo/liên kết workspace riêng. Thư mục cũ được giữ nguyên nhưng API của doanh nghiệp hiện tại không mở được nó.
- Hồ sơ thiếu/sai, chưa đồng bộ hoặc kết nối chưa cấu hình: hiển thị hướng dẫn tại portal; không mở lại doanh nghiệp cũ.
- Bản nháp thiết lập được giữ trong sessionStorage theo phiên bản hồ sơ. Không tự áp dụng bản nháp sang hồ sơ khác. Các trường đang mở khi đổi ngữ cảnh được giữ riêng tại `agent3.previous-context-draft` để có thể kiểm tra thủ công.

## API Agent 3

- `GET /api/platform/context`: trạng thái, workspace hiện tại, hồ sơ, revision và URL portal; không chứa khóa backend.
- `POST /api/platform/sync`: yêu cầu `X-Agent3-Platform-Token`, đọc trực tiếp hồ sơ chung đã cấu hình, bỏ qua hồ sơ gửi trong body.
- API `/api/workspaces/{id}/...` yêu cầu `X-Agent3-Profile-Revision`. Revision sai hoặc hồ sơ vừa đổi trả `409`; workspace khác trả `403`. Liên kết tải HTML/Excel/ZIP dùng query `profile_revision` (không phải khóa bí mật).
- `GET .../pack` trả `ETag`; `PUT .../pack` yêu cầu `If-Match` (`428` khi thiếu, `412` khi cũ). Không được sửa hồ sơ qua endpoint này (`422`).
- `POST /api/workspaces` và `POST /api/demo` trả `410`. Bộ sinh mô phỏng offline vẫn dùng cho kiểm thử.

Yêu cầu trên workspace và đồng bộ được tuần tự hóa; ghi cấu hình/lịch sử/quyết định qua file tạm. Tác vụ AI kiểm tra revision trước khi ghi và công bố kết quả. Khi revision thay đổi, UI hủy yêu cầu đang chờ, đóng panel và nạp lại ngữ cảnh; không tự gửi lại quyết định.

## Kiểm thử

Tại `agent3/agent3_tax_compliance`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/assistant -q
cd webui
npm run build
node scripts/ui-check.mjs
```

Kiểm thử backend sử dụng thư mục tạm. Script UI dùng server API mô phỏng riêng và Chrome headless; ảnh và kết quả ở `webui/.qa/` (không đưa vào Git). Không ghi hồ sơ, quyết định hay cấu hình đang sử dụng. Kiểm tra ở 1440/1024/768/390/320 px, sáng/tối, reduced motion, 200% reflow, lỗi lưu và phản hồi chậm. Tiêu chí taste cho landing page không áp dụng cho giao diện nghiệp vụ này.
