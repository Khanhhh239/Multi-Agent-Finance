# Giao diện Agent 3

Giao diện trợ lý thuế mà portal mở tại cổng 8640. Mã nguồn ở `src/`; đây là ứng dụng JavaScript thuần với Carbon và Vite, khác ứng dụng capture/review tại `/review`.

## Build và chạy

Tại thư mục này:

```powershell
npm ci --no-audit --no-fund
npm run build
```

Vite tạo bản chạy trong `../src/assistant/static/`. Sau build, tải lại trang Agent 3 bằng Ctrl+F5. Không cần chạy lại các lệnh đồng bộ luật hoặc tạo vector.

```powershell
npm run dev -- --host 127.0.0.1
```

Development server chuyển `/api` đến Agent 3 đang chạy ở `127.0.0.1:8640`.

Plugin trong `vite.config.js` đọc theme/script/font trực tiếp từ `design/` tại gốc repo, phục vụ trong development và đóng gói lại sau mỗi build sạch. Thứ tự CSS: Carbon và layout cũ → theme nền tảng → `src/product.css`. Không sửa bản sao theme trong thư mục build, không chạy đồng bộ theme toàn hệ thống để build riêng Agent 3.

## Kiểm thử giao diện độc lập

Yêu cầu Node 22+ và Google Chrome. Có thể đặt biến `CHROME_PATH` nếu Chrome ở vị trí khác mặc định.

```powershell
npm run build
node scripts/ui-check.mjs
```

Script mở một HTTP server trên cổng local ngẫu nhiên, giả lập API và dữ liệu doanh nghiệp. Mọi lần lưu quyết định trong bài kiểm tra đều gọi API giả lập, không gọi dịch vụ doanh nghiệp thật. Script tự đóng Chrome và server sau khi chạy.

Kết quả tại `.qa/ui-results.json`; ảnh tổng quan tại `.qa/overview-{1440,1024,768,390,320}.png` và `.qa/dark.png`. Các tệp `.qa/`, profile Chrome, node_modules và npm cache được bỏ qua khi commit.

Phạm vi kiểm tra: tài nguyên build, bố cục, lọc/sắp xếp/phân trang, dialog và focus, lỗi lưu đơn/hàng loạt, validation, trang phụ, phản hồi chậm khi chuyển trang/doanh nghiệp, trạng thái trống/lỗi, sáng/tối, reduced motion, reflow 200% bằng CSS zoom và nhập liệu khi nhúng trong portal.

## Các ranh giới cần giữ

- Giữ nguyên URL, API và logic luật/tiền tệ. Hủy yêu cầu HTTP khi chuyển trang không đồng nghĩa hoàn tác một thao tác ghi đã được máy chủ nhận.
- Liên kết về portal chỉ chấp nhận HTTP trên `localhost` hoặc `127.0.0.1`, theo ngữ cảnh `portal` hiện có. Nhập liệu độc lập vẫn được giữ.
- Người dùng vẫn quyết định; nhãn luật nháp, dữ liệu mô phỏng và giới hạn AI phải được giữ.
- Taste được áp dụng cho phân cấp, căn lề, typography và tương tác; UI UX Pro Max cho bảng, trạng thái và accessibility. Các kiểm tra marketing của taste (hero toàn màn hình, ảnh, hiệu ứng, nhịp section và thông tin liên hệ giả) không áp dụng cho ứng dụng nghiệp vụ này. Không công bố đã đạt marketing gate.
- Bộ kiểm tra giả lập không thay thế đánh giá độ chính xác thuế, kiểm thử model thật hoặc kiểm thử tích hợp với toàn bộ dữ liệu doanh nghiệp.
