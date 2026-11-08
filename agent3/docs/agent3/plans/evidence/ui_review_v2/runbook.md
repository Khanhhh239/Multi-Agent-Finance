# UI review v2 và cách mở local — 14/10/2026

## Mở và dừng

Tại `D:\financial`, nhấp đúp `OPEN_AGENT3.cmd`, hoặc chạy `./OPEN_AGENT3.cmd` trong PowerShell. Cần venv ứng dụng và model OCR đã có trong workspace; launcher không tự cài package/model.

Launcher khởi động HTTP server trên `127.0.0.1`, mặc định tìm cổng trống từ 8000; tự mở `/review` trên trình duyệt mặc định. Không tắt ứng dụng khác đang dùng cổng. Một worker riêng tự nhận các job QUEUED của `demo-tenant/demo-payer`, có lease/retry như capture hiện hành. Không chạy OCR trong HTTP upload.

Mã truy cập random được giữ tại `agent3_tax_compliance/data/local_web/credentials.json` bị gitignore, chỉ hash được đưa vào grant. Trên Windows launcher sao chép token vào clipboard bằng stdin, không đặt token vào URL/command line hay log. Bấm **Dán mã và kết nối**, hoặc Ctrl+V vào ô mã nếu trình duyệt từ chối đọc clipboard. Mã chỉ ở bộ nhớ trang; reload phải kết nối lại. Clipboard có thể chứa token cho tới khi người dùng sao chép nội dung khác.

Mặc định dùng DB `data invoice/plan06_local/demo.sqlite3` và staging demo đã có. Nếu master revision 1 đã tồn tại thì giữ nguyên; chỉ provision master tổng hợp khi chưa có. Đây không phải scope doanh nghiệp thật. Không dùng launcher này để phục vụ mạng LAN/Internet hoặc như hệ thống đăng nhập production.

Giữ cửa sổ mở. Ctrl+C dừng server/worker; hoặc chạy `STOP_AGENT3.cmd` ở thư mục gốc. Mở lại `OPEN_AGENT3.cmd` khi phiên demo còn hoạt động sẽ mở lại web và sao chép mã. Nếu worker bị ngắt trong một job và kịp nhận tín hiệu, job chuyển PROCESSING_ERROR và cho retry tường minh. Hard kill/mất điện vẫn theo cơ chế lease/recovery hiện hành.

Quy ước trích xuất của worker local mặc định VI, hiển thị ở mục “Về bản đang dùng”. Có thể chạy thủ công từ `agent3_tax_compliance`:

```powershell
.\.venv\Scripts\python.exe -m src.local_web --number-locale AUTO
```

Dừng phiên cũ trước khi đổi quy ước. Không có dropdown frontend giả vờ thay profile job. API chạy thủ công bằng uvicorn vẫn cần worker thủ công.

## Giao diện đã triển khai

- Thanh kết nối thu gọn sau khi xác thực; sidebar upload/danh sách, trạng thái xử lý dựa vào state server.
- Workspace hai cột trên desktop, tab dữ liệu/nguồn trên màn hình hẹp. PDF/ảnh zoom 50–250%, cuộn xem vùng nguồn; nguồn có bbox và candidate.
- Thông tin hóa đơn, người bán, người mua, tổng tiền chia nhóm. Dòng hàng thành bảng cuộn ngang, giữ item ID bất biến khi lưu.
- “Đã đọc được · Chưa xác nhận”, “Chưa đọc được”, “Cần đối chiếu”, “Đã xác nhận”, “Không áp dụng” thay enum kỹ thuật ở trường dữ liệu. Không hiển thị accuracy % giả.
- “Xem vị trí” không sửa input; “Dùng giá trị” đưa candidate vào bản nháp và cần lưu để xác nhận.
- Tiền/số lượng/đơn giá nhập theo VI `1.234,56`, ngày DD/MM/YYYY, thuế suất 8 cho 8%. Chuyển thành chuỗi Decimal/ISO/rate trước khi gửi; không dùng float để chuyển tiền. MST là chuỗi giữ số 0 đầu.
- Chọn lý do có chủ ý hoặc nhập ghi chú; checkbox nghĩa là đưa trường vào lệnh lưu. Giới hạn 32 trường/lần, không giả transaction nhiều lô.
- Lỗi định dạng ở cạnh ô, lỗi lưu giữ bản nháp. 409 tải revision mới và giữ thay đổi trong panel so sánh; người dùng phải áp dụng lại hoặc bỏ từng trường. Không tự ghi đè.
- Theo dõi trang đã mở; chỉ cho xác nhận đủ hàng khi đã mở tất cả trang và có dòng để đối chiếu. Mở trang không tự xác nhận trường.
- Danh sách có summary thật từ CFR; view có job mapping theo tenant/taxpayer/ingestion để nút hoàn tất vẫn hoạt động khi mở lại từ danh sách.
- Lịch sử dễ đọc từ audit metadata, chi tiết JSON ở mục mở rộng. Export là dữ liệu đã lưu, không có bản nháp và không đồng nghĩa kết luận thuế.

## Kiểm chứng

Python review suite, gồm tenant isolation, summary/job mapping và interrupt/retry. DOM harness kiểm tra ID, Decimal lớn, ngày sai, KCT, candidate xem không sửa, auth/evidence và giữ conflict draft.

Chrome headless thực đã chạy trên DB riêng: upload fixture PDF → worker thực tự nhận → review → xem bbox/zoom → lưu Decimal → hai phiên sửa gây 409 → áp lại có chủ ý → mobile 390 px → audit và JSON export. Bổ sung hóa đơn CyberBill công khai để kiểm tra luồng OCR thực. Kết quả cuối ghi tại [validation.json](validation.json). Đây là browser acceptance tự động, không phải nghiệm thu nghiệp vụ của người dùng hay kiểm tra toàn diện screen reader.

Để chạy lại browser test, trước hết mở một server **DB kiểm thử riêng**, không dùng DB demo người dùng:

```powershell
# Cwd: agent3_tax_compliance
.\.venv\Scripts\python.exe -m src.local_web --no-browser --no-clipboard --port 8765 --database data/local_web/browser_smoke.sqlite3

# Terminal khác, cwd: D:\financial
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts/check_review_browser.py --url http://127.0.0.1:8765
```

Script dùng Playwright ở `agent3_tax_compliance/data/local_web/browser_tools` và Chrome cài trên Windows. Công cụ này được cài riêng trong thư mục local; không thêm vào dependency runtime ứng dụng. Screenshots/result/log/credentials/DB không được commit. Browser script chỉ dùng fixture tổng hợp; tùy chọn `--real` nhận PDF CyberBill pilot đã tải, không có nhãn đáp án hardcode vào runtime.

## Giới hạn còn lại

Chưa có tìm kiếm toàn bộ dữ liệu, danh sách toàn bộ job, dropdown đơn vị có quyền, SSO, thêm/tách/gộp hàng hay kéo đường chia pane. Chưa có pan bằng chuột kéo riêng; viewer dùng cuộn native khi zoom. Danh sách task/audit báo rõ số đã tải và còn trang; không tính length của một trang thành tổng vấn đề toàn chứng từ. Lỗi backend chi tiết vẫn có thể cần developer kiểm tra code/log; UI không tự sửa dữ liệu để vượt quality gate.

Đọc kế hoạch tại [UI_REVIEW_REDESIGN_PLAN.md](../../UI_REVIEW_REDESIGN_PLAN.md). Sau vòng này cần người dùng thử tốc độ đối chiếu, màn hình nhỏ, bàn phím và xác nhận hành vi trên chứng từ thật trước khi chốt trải nghiệm.
