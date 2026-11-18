# Nhập nhiều nguồn qua giao diện cho profile 35 luật

Ngày: 18/11/2026. Trạng thái: **READY_FOR_REVIEW kỹ thuật**.

## Luồng được nối

Chọn doanh nghiệp → chọn Excel nhiều sheet / các CSV → đọc bảng và cột →
ánh xạ bảng/cột → khai báo mốc và phạm vi lịch sử → kiểm tra → xem mức sẵn
sàng của 35 luật → xác nhận lưu snapshot → tiếp tục đến phân tích/bundle.

Giữ luồng canonical CSV/Excel/JSON cũ. Nguồn nhiều bảng chuẩn hóa về
`agent2-rule-snapshot/1.0.0`; không thêm một engine luật hoặc snapshot store
khác. `rule-source-intake/1.0.0` xử lý ranh giới file/mapping.

## Kiểm tra quan trọng

- `inspect` dùng cùng quyền nhập, actor và company scope của draft; không đọc
  draft người khác/doanh nghiệp khác. Phiên Portal cũ vẫn là nguồn quyền.
- Ánh xạ tên bảng/cột; không nhận biểu thức, giá trị mặc định hoặc quyền từ
  file. Hai cột hoặc hai nguồn trỏ cùng đích bị chặn, không ghi đè âm thầm.
- CSV UTF-8, Excel `.xlsx` không macro/công thức; kiểm tra kích thước nén/
  giải nén, số hàng/cột và tên bảng. Tệp sai có vị trí tệp/sheet/dòng/trường.
- Giữ mã dạng Text, số 0 đầu và số tiền VND có dấu chính xác. Tiền lớn trong
  Excel cần Text; không nhận float/phần lẻ hoặc làm tròn ngầm timestamp.
- Lịch sử `complete/partial/unknown` và `since_inception/bounded_period/unknown`
  là khai báo rõ. Không có coverage không thành “đủ”. Rút lại khai báo trên web
  bỏ được claim cũ trong file. Checksum/số dòng tính lại từ dữ liệu đã ánh xạ.
- Mỗi kiểm tra có `ready/partial/needs_data/not_applicable`, số lượng khả dụng/
  thiếu/không áp dụng và bảng/cột/lý do thiếu. Preview dùng evaluator local
  hiện có để kiểm tra khả dụng, không fit, gọi cloud, ghi queue hoặc tiêu quota.
  DTO không chứa điểm, ngưỡng, mã luật hay kết quả trúng/không trúng.
- Giữ 200 ứng viên riêng khỏi tối đa 30.000 dòng nguồn. Chọn “toàn bộ” với
  hơn 200 giao dịch bị chặn, không tự cắt lịch sử.
- Đổi file/mapping/phạm vi làm preview cũ hết hiệu lực. Lưu retry giữ cùng
  idempotency key; snapshot bất biến, file/gói CSV gốc và mapping lưu riêng.

## Nghiệm thu giao diện trên dữ liệu mô phỏng

`browser_multi_source.json`: **10 nhóm kiểm tra qua**, không lỗi JavaScript.

1. Tải khung Excel nhiều sheet.
2. Đọc metadata, bảng và cột Excel.
3. Preview mức sẵn sàng 35 kiểm tra trước khi lưu.
4. Đổi coverage làm mất preview cũ và cập nhật kiểm tra bị ảnh hưởng.
5. Rút claim complete trong file về chưa có phạm vi.
6. Viewport 390px không tràn ngang.
7. Lưu Excel và phân tích cùng snapshot.
8. Nhiều CSV, đổi tên bảng và `MaGD` → `transaction_id`; chưa có coverage
   không được báo đủ nguồn.
9. Lưu snapshot từ nhiều CSV.
10. Chuyển C001 → C002 xóa lựa chọn nguồn và chặn workbook thuộc C001.

`browser_standard_import.json`: **19 ca UI luồng nhập cũ qua**, gồm quyền,
lỗi dòng, lưu/mất phản hồi/chống trùng, sửa file sau preview, reload và nguồn.
Đã sửa lỗi thông báo tiếng Anh khi file trên đĩa đổi sau lần đọc.

`browser_standard_tabular.json`: **4 nhóm UI CSV/Excel chuẩn qua**, gồm tải
mẫu qua Portal, lưu, lỗi Excel đúng sheet/dòng và canonical CSV.

Trong lượt hồi quy, test thu hồi phiên Portal tái hiện `WinError 10053`:
request POST bị từ chối trước khi body được đọc hết, gây TCP reset trên Windows.
Đã bổ sung drain thuần vận chuyển **chỉ khi từ chối session Agent2**, tối đa
10 MB và 0,25 giây; không parse, lưu hay forward body bị từ chối. Test phiên
thu hồi với upload nguồn xác nhận 401, không gọi backend và không tạo snapshot.
Test drain xác nhận giới hạn kích thước/transfer-encoding và khôi phục timeout.
Không đổi xác thực hoặc hành vi Agent1/3/4.

Receipt backend tổng hợp: `backend_tests.json`, chứa số test, lỗi, thời gian
và hash các nguồn được kiểm tra. Các lần tái hiện lỗi vận chuyển trước sửa
không được tính là một lượt hồi quy đạt.

Lượt cuối: **202 test qua, 0 lỗi / 0 thất bại**, unittest 187,199 giây
(190,234 giây gồm nạp suite). Trong đó **29 test nhập nguồn/Portal/drain mới**.
Phạm vi gồm nhập chuẩn, snapshot, rule profile/cutoff, bridge ML, signed/PIT,
quyền Portal, gate phát hành, shadow plan và bundle workspace. Đây là bộ hồi
quy liên quan đến thay đổi, không phải mọi bộ kiểm thử HE/production của dự án.

Ảnh UI và hướng dẫn: [MULTI_SOURCE_IMPORT.md](../../../../agent2/docs/MULTI_SOURCE_IMPORT.md).

## Giới hạn

- Đây là khả dụng trên nguồn đã cung cấp theo logic hiện tại, không xác minh
  độc lập completeness của ERP, đúng sai nghiệp vụ hoặc hiệu quả gian lận.
- Dữ liệu thật có bằng chứng đã xác minh vẫn cần quyền `evidence.verify` khi
  nhập; không biến mô phỏng hay bản xuất thành chứng từ gốc đã xác minh.
- Bộ native vẫn có các giới hạn số âm/master và chính sách đã ghi ở
  `FULL_RULE_PIPELINE.md`; tệp sparse canonical không tự thành full35.
- Chưa có adapter tổng quát chuyển invoices/payment_allocations canonical
  thành cấu trúc invoice header native; UI không tự suy dữ liệu đó.
- Khung Excel trống, không điền sẵn khoản chi/bằng chứng/coverage hoàn chỉnh.
  Các bảng chưa có dữ liệu và phần kỹ thuật được thu gọn.
- Các test dùng kho tạm và Portal/Chrome riêng. Chưa restart/deploy bản này
  vào phiên Portal live; không đổi DB, model, khóa, bundle hoặc phiên hiện hành.
- Runtime hash đổi cần qualification lại bundle trước khi dùng. Không mở rộng
  HE, production, budget hay tự phê duyệt phát hành. Không đổi R0–R6 thành DONE.
